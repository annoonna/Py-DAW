// Crate-wide: allow dead_code for stub modules (Phase 1C FFI not yet active)
#![allow(dead_code)]

mod audio_bridge;
mod audio_graph;
mod audio_node;
mod clap_host;
mod clip_renderer;
mod dsp;
mod engine;
mod fx;
mod instruments;
mod integration;
mod ipc;
mod lock_free;
mod lv2_host;  // v0.0.20.713: P7C — LV2 Plugin Host (FFI scaffolding)
mod midi_scheduler;  // v0.0.20.725: Beat-accurate MIDI clip scheduling
mod plugin_host;
mod plugin_isolator;
mod sample;
mod transport;
mod vst3_host;

use std::io::{Read, Write};
use std::sync::Arc;

use crossbeam_channel::{bounded, Receiver, Sender};
use log::{error, info, warn};

use crate::engine::EngineState;
use crate::ipc::{Command, Event};

// ============================================================================
// Py_DAW Audio Engine — Entry Point
// ============================================================================
//
// Usage:
//   pydaw_engine [--socket /tmp/pydaw_engine.sock] [--sr 44100] [--buf 512]
//
// The engine listens on a Unix Domain Socket for MessagePack-encoded Commands
// from the Python GUI and sends back Events (meter levels, playhead position).
//
// Phase 1A PoC:
//   - Starts a sine wave generator on a test track
//   - Sends playhead position and meter levels to Python
//   - Responds to Play/Stop/Seek/SetTempo commands
// ============================================================================

const DEFAULT_SOCKET: &str = "/tmp/pydaw_engine.sock";
const DEFAULT_SAMPLE_RATE: u32 = 44100;
const DEFAULT_BUFFER_SIZE: u32 = 512;
const DEFAULT_BPM: f64 = 120.0;

/// Read a length-prefixed MessagePack frame from a stream.
///
/// Frame format: [u32 LE length][msgpack payload]
fn read_frame(stream: &mut impl Read) -> std::io::Result<Vec<u8>> {
    let mut len_buf = [0u8; 4];
    stream.read_exact(&mut len_buf)?;
    let len = u32::from_le_bytes(len_buf) as usize;

    if len > 16 * 1024 * 1024 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("Frame too large: {} bytes", len),
        ));
    }

    let mut buf = vec![0u8; len];
    stream.read_exact(&mut buf)?;
    Ok(buf)
}

/// Write a length-prefixed MessagePack frame to a stream.
fn write_frame(stream: &mut impl Write, data: &[u8]) -> std::io::Result<()> {
    let len = (data.len() as u32).to_le_bytes();
    stream.write_all(&len)?;
    stream.write_all(data)?;
    stream.flush()?;
    Ok(())
}

/// Decode a Command from MessagePack bytes.
fn decode_command(data: &[u8]) -> Result<Command, String> {
    rmp_serde::from_slice(data).map_err(|e| format!("Decode error: {}", e))
}

/// Encode an Event to MessagePack bytes.
fn encode_event(event: &Event) -> Result<Vec<u8>, String> {
    rmp_serde::to_vec_named(event).map_err(|e| format!("Encode error: {}", e))
}

/// IPC handler thread: reads commands from Unix socket, sends to engine.
fn ipc_reader_thread(
    mut stream: std::os::unix::net::UnixStream,
    command_tx: Sender<Command>,
) {
    info!("IPC reader started");
    loop {
        match read_frame(&mut stream) {
            Ok(frame) => match decode_command(&frame) {
                Ok(cmd) => {
                    let is_shutdown = matches!(cmd, Command::Shutdown);
                    if let Err(e) = command_tx.send(cmd) {
                        error!("Failed to send command: {}", e);
                        break;
                    }
                    if is_shutdown {
                        info!("Shutdown received, closing IPC reader");
                        break;
                    }
                }
                Err(e) => {
                    warn!("Failed to decode command: {}", e);
                }
            },
            Err(e) => {
                if e.kind() == std::io::ErrorKind::UnexpectedEof {
                    info!("Client disconnected");
                } else {
                    error!("IPC read error: {}", e);
                }
                break;
            }
        }
    }
}

/// IPC writer thread: reads events from engine, sends to Unix socket.
fn ipc_writer_thread(
    mut stream: std::os::unix::net::UnixStream,
    event_rx: Receiver<Event>,
) {
    info!("IPC writer started");
    loop {
        match event_rx.recv() {
            Ok(event) => {
                let is_shutdown = matches!(event, Event::ShuttingDown);
                match encode_event(&event) {
                    Ok(data) => {
                        if let Err(e) = write_frame(&mut stream, &data) {
                            error!("IPC write error: {}", e);
                            break;
                        }
                    }
                    Err(e) => {
                        warn!("Failed to encode event: {}", e);
                    }
                }
                if is_shutdown {
                    info!("Shutdown event sent, closing IPC writer");
                    break;
                }
            }
            Err(_) => {
                info!("Event channel closed, stopping IPC writer");
                break;
            }
        }
    }
}

/// Set up the Phase 1A proof-of-concept: sine wave generator on track 0.
fn setup_poc_sine(engine: &EngineState) {
    info!("Setting up Phase 1A/1B PoC: Sine Wave Generator + Master Track");

    // Add a master track and a test instrument track
    let mut graph = engine.graph.lock();
    graph.add_track("master".to_string(), 0, audio_graph::TrackKind::Master);
    graph.add_track(
        "sine_test".to_string(),
        1,
        audio_graph::TrackKind::Instrument,
    );

    // Write a 440Hz sine wave into the test track's buffer
    // (In production, clips are rendered by ArrangementRenderer)
    let sr = graph.sample_rate;
    let buf_size = graph.buffer_size();
    let mut sine = plugin_host::SineGenerator::new(440.0, 0.3);
    let mut buf = audio_graph::AudioBuffer::new(buf_size, 2);
    sine.generate(&mut buf, sr);
    graph.write_track_audio(1, &buf.data);

    info!("PoC ready: 440Hz sine on track 1 → master (buf={})", buf_size);
}

fn main() {
    // Initialize logging
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .init();

    info!("Py_DAW Audio Engine v0.1.0 starting...");

    // Parse command line args
    let args: Vec<String> = std::env::args().collect();
    let socket_path = args
        .iter()
        .position(|a| a == "--socket")
        .and_then(|i| args.get(i + 1))
        .map(|s| s.as_str())
        .unwrap_or(DEFAULT_SOCKET);

    let sample_rate = args
        .iter()
        .position(|a| a == "--sr")
        .and_then(|i| args.get(i + 1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_SAMPLE_RATE);

    let buffer_size = args
        .iter()
        .position(|a| a == "--buf")
        .and_then(|i| args.get(i + 1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_BUFFER_SIZE);

    info!(
        "Config: socket={}, sr={}, buf={}",
        socket_path, sample_rate, buffer_size
    );

    // Create command/event channels
    let (command_tx, command_rx) = bounded::<Command>(4096);
    let (event_tx, event_rx) = bounded::<Event>(4096);

    // Create engine state
    let engine_state = Arc::new(EngineState::new(
        sample_rate,
        buffer_size,
        DEFAULT_BPM,
        command_rx,
        event_tx,
    ));

    // Set up PoC sine generator
    setup_poc_sine(&engine_state);

    // Remove old socket file if it exists
    let _ = std::fs::remove_file(socket_path);

    // Start Unix Domain Socket listener
    let listener = match std::os::unix::net::UnixListener::bind(socket_path) {
        Ok(l) => {
            info!("Listening on {}", socket_path);
            l
        }
        Err(e) => {
            error!("Failed to bind socket {}: {}", socket_path, e);
            std::process::exit(1);
        }
    };

    // Set up cpal audio stream
    let engine_for_audio = Arc::clone(&engine_state);
    let audio_thread = std::thread::Builder::new()
        .name("pydaw-audio".to_string())
        .spawn(move || {
            use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

            let host = cpal::default_host();
            let device = match host.default_output_device() {
                Some(d) => d,
                None => {
                    error!("No audio output device found");
                    return;
                }
            };

            let config = cpal::StreamConfig {
                channels: 2,
                sample_rate: cpal::SampleRate(sample_rate),
                buffer_size: cpal::BufferSize::Fixed(buffer_size),
            };

            info!(
                "Audio device: {} ({}Hz, {} frames)",
                device.name().unwrap_or_default(),
                sample_rate,
                buffer_size
            );

            let engine_ref = Arc::clone(&engine_for_audio);
            let engine_err = Arc::clone(&engine_for_audio);
            let stream = device
                .build_output_stream(
                    &config,
                    move |data: &mut [f32], _info: &cpal::OutputCallbackInfo| {
                        let frames = data.len() / 2; // stereo
                        engine_ref.process_audio(data, frames, 2);
                    },
                    move |err| {
                        error!("Audio stream error: {:?}", err);
                        engine_err.record_xrun();
                    },
                    None,
                )
                .expect("Failed to build audio stream");

            stream.play().expect("Failed to start audio stream");

            // Keep the stream alive until engine shuts down
            while engine_for_audio
                .running
                .load(std::sync::atomic::Ordering::Relaxed)
            {
                std::thread::sleep(std::time::Duration::from_millis(100));
            }

            info!("Audio thread shutting down");
            drop(stream);
        })
        .expect("Failed to spawn audio thread");

    // Accept one client connection (single-client for Phase 1A)
    info!("Waiting for Python client connection...");
    match listener.accept() {
        Ok((stream, _addr)) => {
            info!("Client connected");

            let read_stream = stream.try_clone().expect("Failed to clone socket");
            let write_stream = stream;

            // Start IPC reader thread
            let reader_handle = std::thread::Builder::new()
                .name("pydaw-ipc-read".to_string())
                .spawn(move || {
                    ipc_reader_thread(read_stream, command_tx);
                })
                .expect("Failed to spawn IPC reader");

            // Start IPC writer thread
            let writer_handle = std::thread::Builder::new()
                .name("pydaw-ipc-write".to_string())
                .spawn(move || {
                    ipc_writer_thread(write_stream, event_rx);
                })
                .expect("Failed to spawn IPC writer");

            // Wait for threads
            let _ = reader_handle.join();
            let _ = writer_handle.join();
        }
        Err(e) => {
            error!("Failed to accept connection: {}", e);
        }
    }

    // Cleanup
    engine_state
        .running
        .store(false, std::sync::atomic::Ordering::Release);
    let _ = audio_thread.join();
    let _ = std::fs::remove_file(socket_path);

    info!("Py_DAW Audio Engine stopped");
}
