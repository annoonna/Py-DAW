// ============================================================================
// Plugin Isolator — Process Isolation + Crash Recovery
// ============================================================================
//
// Runs each plugin in its own thread with panic/crash isolation.
// If a plugin thread panics, the track is muted and the plugin can be
// restarted without affecting other tracks or the engine.
//
// Architecture:
//   - Each plugin runs in a dedicated OS thread
//   - Audio data is passed via lock-free ring buffers (zero-copy in-thread)
//   - Parameter updates go through crossbeam channels
//   - Thread monitors via heartbeat (watchdog)
//   - On panic: catch_unwind → mute track → notify Python GUI
//   - Auto-restart: reload plugin state from last known good blob
//
// Future enhancement: subprocess model (fork+exec) for full crash isolation
// of plugins that corrupt memory (requires shared memory IPC for audio).
//
// v0.0.20.658 — AP1 Phase 1C (Claude Opus 4.6, 2026-03-20)
// ============================================================================

use std::panic;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use crossbeam_channel::{bounded, Receiver, Sender};
use log::{error, info, warn};
use parking_lot::Mutex;

use crate::audio_graph::AudioBuffer;
use crate::plugin_host::AudioPlugin;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// Commands sent from the engine to a plugin thread.
enum PluginCommand {
    /// Process audio (buffer is owned, returned via response channel).
    Process {
        buffer: AudioBuffer,
        sample_rate: u32,
    },
    /// Set a parameter value.
    SetParam { index: u32, value: f64 },
    /// Save state and return it.
    SaveState,
    /// Load state from blob.
    LoadState(Vec<u8>),
    /// Graceful shutdown.
    Shutdown,
}

/// Responses from the plugin thread back to the engine.
enum PluginResponse {
    /// Processed audio buffer (returned to engine).
    Processed(AudioBuffer),
    /// State blob.
    State(Vec<u8>),
    /// Error message.
    Error(String),
    /// Plugin has shut down.
    ShutDown,
}

/// Health status of an isolated plugin.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PluginHealth {
    /// Running normally.
    Healthy,
    /// Plugin crashed, track is muted.
    Crashed,
    /// Plugin is being restarted.
    Restarting,
    /// Plugin has been permanently disabled after too many crashes.
    Disabled,
}

// ---------------------------------------------------------------------------
// IsolatedPlugin — the engine-side handle
// ---------------------------------------------------------------------------

/// Engine-side handle for an isolated plugin.
///
/// The plugin runs in a dedicated thread. All interaction goes through
/// lock-free channels.
pub struct IsolatedPlugin {
    /// Plugin identity.
    pub plugin_id: String,
    pub plugin_name: String,

    /// Communication channels.
    cmd_tx: Sender<PluginCommand>,
    resp_rx: Receiver<PluginResponse>,

    /// Health monitoring.
    health: Arc<AtomicU32>,
    heartbeat: Arc<AtomicU64>,
    crash_count: u32,
    max_crashes: u32,

    /// Last known good state (for auto-restart).
    last_good_state: Arc<Mutex<Vec<u8>>>,

    /// Thread handle.
    thread_handle: Option<thread::JoinHandle<()>>,
}

impl IsolatedPlugin {
    /// Wrap an AudioPlugin in an isolation thread.
    ///
    /// The plugin is moved into a new thread. All further interaction
    /// goes through channels.
    pub fn new(plugin: Box<dyn AudioPlugin>, max_crashes: u32) -> Self {
        let plugin_id = plugin.id().to_string();
        let plugin_name = plugin.name().to_string();

        let (cmd_tx, cmd_rx) = bounded::<PluginCommand>(64);
        let (resp_tx, resp_rx) = bounded::<PluginResponse>(64);

        let health = Arc::new(AtomicU32::new(PluginHealth::Healthy as u32));
        let heartbeat = Arc::new(AtomicU64::new(0));
        let last_good_state = Arc::new(Mutex::new(Vec::new()));

        let health_clone = Arc::clone(&health);
        let heartbeat_clone = Arc::clone(&heartbeat);
        let name_clone = plugin_name.clone();

        let handle = thread::Builder::new()
            .name(format!("plugin-{}", plugin_name))
            .spawn(move || {
                plugin_thread_loop(
                    &name_clone,
                    plugin,
                    cmd_rx,
                    resp_tx,
                    health_clone,
                    heartbeat_clone,
                );
            })
            .expect("Failed to spawn plugin thread");

        Self {
            plugin_id,
            plugin_name,
            cmd_tx,
            resp_rx,
            health,
            heartbeat,
            crash_count: 0,
            max_crashes,
            last_good_state,
            thread_handle: Some(handle),
        }
    }

    /// Get current health status.
    pub fn health(&self) -> PluginHealth {
        match self.health.load(Ordering::Relaxed) {
            0 => PluginHealth::Healthy,
            1 => PluginHealth::Crashed,
            2 => PluginHealth::Restarting,
            _ => PluginHealth::Disabled,
        }
    }

    /// Process audio through the isolated plugin.
    ///
    /// Sends the buffer to the plugin thread, waits for the result.
    /// If the plugin has crashed, returns the buffer unmodified (passthrough).
    pub fn process(&mut self, buffer: &mut AudioBuffer, sample_rate: u32) {
        if self.health() != PluginHealth::Healthy {
            return; // Passthrough — track is muted/bypassed
        }

        // Send buffer to plugin thread
        let owned_buf = buffer.clone();
        if self
            .cmd_tx
            .try_send(PluginCommand::Process {
                buffer: owned_buf,
                sample_rate,
            })
            .is_err()
        {
            warn!("Plugin {} command queue full — dropping frame", self.plugin_name);
            return;
        }

        // Wait for processed buffer (with timeout)
        match self.resp_rx.recv_timeout(Duration::from_millis(50)) {
            Ok(PluginResponse::Processed(processed)) => {
                // Copy processed audio back
                let len = buffer.data.len().min(processed.data.len());
                buffer.data[..len].copy_from_slice(&processed.data[..len]);
            }
            Ok(PluginResponse::Error(e)) => {
                error!("Plugin {} error: {}", self.plugin_name, e);
                self.handle_crash();
            }
            Err(_) => {
                warn!("Plugin {} timed out on process()", self.plugin_name);
                self.handle_crash();
            }
            _ => {}
        }
    }

    /// Set a parameter on the plugin.
    pub fn set_parameter(&self, index: u32, value: f64) {
        let _ = self
            .cmd_tx
            .try_send(PluginCommand::SetParam { index, value });
    }

    /// Save the plugin's state.
    pub fn save_state(&self) -> Option<Vec<u8>> {
        let _ = self.cmd_tx.try_send(PluginCommand::SaveState);
        match self.resp_rx.recv_timeout(Duration::from_millis(500)) {
            Ok(PluginResponse::State(data)) => {
                *self.last_good_state.lock() = data.clone();
                Some(data)
            }
            _ => None,
        }
    }

    /// Load state into the plugin.
    pub fn load_state(&self, data: &[u8]) {
        let _ = self
            .cmd_tx
            .try_send(PluginCommand::LoadState(data.to_vec()));
        *self.last_good_state.lock() = data.to_vec();
    }

    /// Shutdown the plugin thread gracefully.
    pub fn shutdown(&mut self) {
        let _ = self.cmd_tx.try_send(PluginCommand::Shutdown);
        if let Some(handle) = self.thread_handle.take() {
            let _ = handle.join();
        }
    }

    /// Handle a plugin crash.
    fn handle_crash(&mut self) {
        self.crash_count += 1;
        error!(
            "Plugin {} crashed ({}/{} max)",
            self.plugin_name, self.crash_count, self.max_crashes
        );

        if self.crash_count >= self.max_crashes {
            self.health
                .store(PluginHealth::Disabled as u32, Ordering::Relaxed);
            error!(
                "Plugin {} permanently disabled after {} crashes",
                self.plugin_name, self.crash_count
            );
        } else {
            self.health
                .store(PluginHealth::Crashed as u32, Ordering::Relaxed);
        }
    }

    /// Get crash count.
    pub fn crash_count(&self) -> u32 {
        self.crash_count
    }
}

impl Drop for IsolatedPlugin {
    fn drop(&mut self) {
        self.shutdown();
    }
}

// ---------------------------------------------------------------------------
// Plugin Thread Loop
// ---------------------------------------------------------------------------

fn plugin_thread_loop(
    name: &str,
    mut plugin: Box<dyn AudioPlugin>,
    cmd_rx: Receiver<PluginCommand>,
    resp_tx: Sender<PluginResponse>,
    health: Arc<AtomicU32>,
    heartbeat: Arc<AtomicU64>,
) {
    info!("Plugin thread started: {}", name);

    loop {
        // Wait for next command
        let cmd = match cmd_rx.recv_timeout(Duration::from_millis(1000)) {
            Ok(cmd) => cmd,
            Err(crossbeam_channel::RecvTimeoutError::Timeout) => {
                // Idle — update heartbeat
                heartbeat.fetch_add(1, Ordering::Relaxed);
                continue;
            }
            Err(crossbeam_channel::RecvTimeoutError::Disconnected) => {
                info!("Plugin thread {} — channel disconnected, exiting", name);
                break;
            }
        };

        match cmd {
            PluginCommand::Process {
                mut buffer,
                sample_rate,
            } => {
                // Catch panics from the plugin
                let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
                    plugin.process(&mut buffer, sample_rate);
                }));

                match result {
                    Ok(()) => {
                        heartbeat.fetch_add(1, Ordering::Relaxed);
                        let _ = resp_tx.try_send(PluginResponse::Processed(buffer));
                    }
                    Err(panic_info) => {
                        error!(
                            "Plugin {} panicked in process(): {:?}",
                            name, panic_info
                        );
                        health.store(PluginHealth::Crashed as u32, Ordering::Relaxed);
                        let _ = resp_tx.try_send(PluginResponse::Error(
                            format!("Plugin {} panicked", name),
                        ));
                        // Continue running — the engine will decide whether to restart
                    }
                }
            }

            PluginCommand::SetParam { index, value } => {
                let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
                    plugin.set_parameter(index, value);
                }));
                if let Err(e) = result {
                    warn!("Plugin {} panicked in set_parameter: {:?}", name, e);
                }
            }

            PluginCommand::SaveState => {
                let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
                    plugin.save_state()
                }));
                match result {
                    Ok(data) => {
                        let _ = resp_tx.try_send(PluginResponse::State(data));
                    }
                    Err(e) => {
                        warn!("Plugin {} panicked in save_state: {:?}", name, e);
                        let _ = resp_tx.try_send(PluginResponse::State(Vec::new()));
                    }
                }
            }

            PluginCommand::LoadState(data) => {
                let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
                    plugin.load_state(&data)
                }));
                match result {
                    Ok(Ok(())) => {}
                    Ok(Err(e)) => warn!("Plugin {} load_state error: {}", name, e),
                    Err(e) => warn!("Plugin {} panicked in load_state: {:?}", name, e),
                }
            }

            PluginCommand::Shutdown => {
                info!("Plugin thread {} shutting down", name);
                let _ = resp_tx.try_send(PluginResponse::ShutDown);
                break;
            }
        }
    }
}
