use crate::audio_graph::AudioBuffer;

// ============================================================================
// AudioNode Trait — The core processing abstraction
// ============================================================================
//
// Every entity in the audio graph that processes audio implements AudioNode.
// This is the Rust equivalent of JUCE's AudioProcessor or Bitwig's AudioUnit.
//
// Implementors include:
//   - TrackNode (volume/pan/mute/solo processing)
//   - PluginNode (wraps a VST3/CLAP/LV2 plugin)
//   - SineGeneratorNode (Phase 1A PoC)
//   - FxChainNode (serial chain of effects)
//   - SendNode (split signal to FX return)
//   - GroupBusNode (sum child tracks)
//
// The process() method is called from the audio thread.
// Rules:
//   ✅ Read from pre-allocated buffers
//   ✅ Write to pre-allocated buffers
//   ✅ Read atomic parameters
//   ❌ NO heap allocations
//   ❌ NO locks (Mutex, RwLock)
//   ❌ NO syscalls (file I/O, network, print)
//   ❌ NO exceptions / panics
// ============================================================================

/// Context passed to AudioNode::process() each cycle.
pub struct ProcessContext {
    /// Number of frames in this buffer.
    pub frames: usize,
    /// Engine sample rate.
    pub sample_rate: u32,
    /// Current playhead position in samples.
    pub position_samples: i64,
    /// Current playhead position in beats.
    pub position_beats: f64,
    /// Whether playback is active.
    pub is_playing: bool,
    /// Current tempo in BPM.
    pub bpm: f64,
    /// Time signature numerator.
    pub time_sig_num: u8,
    /// Time signature denominator.
    pub time_sig_den: u8,
}

/// The core audio processing trait.
///
/// Every node in the audio graph implements this trait. The audio graph
/// calls `process()` in topological order during each audio callback.
pub trait AudioNode: Send {
    /// Process audio for one buffer cycle.
    ///
    /// `buffer` contains input audio (if any) and must contain output audio
    /// after the call. For generators (no input), the buffer is pre-zeroed.
    ///
    /// `ctx` provides timing and transport information.
    ///
    /// **AUDIO THREAD** — no allocations, no locks, no panics.
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext);

    /// Get the node's unique identifier.
    fn node_id(&self) -> &str;

    /// Get the node's display name.
    fn node_name(&self) -> &str;

    /// Get the number of input channels (0 for generators).
    fn input_channels(&self) -> usize {
        2
    }

    /// Get the number of output channels.
    fn output_channels(&self) -> usize {
        2
    }

    /// Get the node's latency in samples (for PDC — Plugin Delay Compensation).
    fn latency_samples(&self) -> u32 {
        0
    }

    /// Get the node's tail length in samples (for reverb/delay tails).
    fn tail_samples(&self) -> u64 {
        0
    }

    /// Called when sample rate or buffer size changes.
    fn prepare(&mut self, _sample_rate: u32, _max_buffer_size: usize) {}

    /// Called when the node is removed from the graph.
    fn release(&mut self) {}
}

// ---------------------------------------------------------------------------
// Built-in Nodes
// ---------------------------------------------------------------------------

/// Gain node — simple volume control.
pub struct GainNode {
    id: String,
    gain: f32,
}

impl GainNode {
    pub fn new(id: String, gain: f32) -> Self {
        Self { id, gain }
    }

    pub fn set_gain(&mut self, gain: f32) {
        self.gain = gain;
    }
}

impl AudioNode for GainNode {
    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        buffer.apply_gain(self.gain);
    }

    fn node_id(&self) -> &str {
        &self.id
    }

    fn node_name(&self) -> &str {
        "Gain"
    }
}

/// Silence node — outputs silence (useful as placeholder).
pub struct SilenceNode {
    id: String,
}

impl SilenceNode {
    pub fn new(id: String) -> Self {
        Self { id }
    }
}

impl AudioNode for SilenceNode {
    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        buffer.silence();
    }

    fn node_id(&self) -> &str {
        &self.id
    }

    fn node_name(&self) -> &str {
        "Silence"
    }

    fn input_channels(&self) -> usize {
        0
    }
}

/// Sine generator node — produces a sine wave (Phase 1A PoC).
pub struct SineNode {
    id: String,
    phase: f64,
    frequency: f64,
    amplitude: f64,
}

impl SineNode {
    pub fn new(id: String, frequency: f64, amplitude: f64) -> Self {
        Self {
            id,
            phase: 0.0,
            frequency,
            amplitude,
        }
    }

    pub fn set_frequency(&mut self, freq: f64) {
        self.frequency = freq.clamp(20.0, 20000.0);
    }

    pub fn set_amplitude(&mut self, amp: f64) {
        self.amplitude = amp.clamp(0.0, 1.0);
    }
}

impl AudioNode for SineNode {
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext) {
        if !ctx.is_playing {
            buffer.silence();
            return;
        }

        let sr = ctx.sample_rate as f64;
        let phase_inc = self.frequency / sr;

        for frame in 0..buffer.frames {
            let sample = (self.phase * 2.0 * std::f64::consts::PI).sin() * self.amplitude;
            let s = sample as f32;

            let idx = frame * buffer.channels;
            buffer.data[idx] = s;
            if buffer.channels > 1 {
                buffer.data[idx + 1] = s;
            }

            self.phase += phase_inc;
            if self.phase >= 1.0 {
                self.phase -= 1.0;
            }
        }
    }

    fn node_id(&self) -> &str {
        &self.id
    }

    fn node_name(&self) -> &str {
        "Sine Generator"
    }

    fn input_channels(&self) -> usize {
        0 // Generator, no input
    }
}

/// Mix node — sums multiple input buffers into one output.
///
/// Used internally for group buses and the master bus.
pub struct MixNode {
    id: String,
    /// Input buffers to sum (indices into the graph's node list).
    input_indices: Vec<usize>,
}

impl MixNode {
    pub fn new(id: String) -> Self {
        Self {
            id,
            input_indices: Vec::new(),
        }
    }

    pub fn add_input(&mut self, index: usize) {
        if !self.input_indices.contains(&index) {
            self.input_indices.push(index);
        }
    }

    pub fn remove_input(&mut self, index: usize) {
        self.input_indices.retain(|&i| i != index);
    }
}

impl AudioNode for MixNode {
    fn process(&mut self, _buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        // The actual mixing is done by the AudioGraph — this node is a topology marker.
    }

    fn node_id(&self) -> &str {
        &self.id
    }

    fn node_name(&self) -> &str {
        "Mix Bus"
    }
}
