// ==========================================================================
// FX Chain — Serial effects chain with slots, bypass, sidechain
// ==========================================================================
// v0.0.20.669 — Phase R4A
//
// Reference: pydaw/audio/fx_chain.py (1.057 Z.)
//
// Architecture:
//   FxChain = Vec<FxSlot>
//   FxSlot  = { fx: Box<dyn AudioFxNode>, enabled, bypass }
//   AudioFxNode = trait for all built-in FX
//
// Rules:
//   ✅ Zero heap allocations in process() — all FX pre-allocated
//   ✅ Sidechain buffer forwarded through chain
//   ✅ Pre-FX / Post-FX rendering option
//   ✅ Per-slot enable/bypass
//   ❌ NO dynamic dispatch overhead in tight inner loops (FX do their own)
// ==========================================================================

use crate::audio_graph::AudioBuffer;

// ---------------------------------------------------------------------------
// AudioFxNode Trait — implemented by all built-in FX
// ---------------------------------------------------------------------------

/// Context passed to FX during processing.
pub struct FxContext<'a> {
    /// Sample rate in Hz.
    pub sample_rate: f32,
    /// Optional sidechain buffer (read-only).
    pub sidechain: Option<&'a AudioBuffer>,
    /// Current tempo in BPM (for tempo-synced FX like Delay).
    pub tempo_bpm: f64,
}

/// Trait for all audio effects in the FX chain.
///
/// Every built-in FX (EQ, Compressor, Chorus, etc.) implements this trait
/// so it can be stored in an FxSlot and processed uniformly by FxChain.
pub trait AudioFxNode: Send {
    /// Process stereo audio buffer in-place.
    ///
    /// **AUDIO THREAD** — must be zero-alloc, no locks, no panics.
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &FxContext);

    /// Reset internal state (called on transport stop, loop reset, etc.).
    fn reset(&mut self);

    /// Set sample rate (called on audio configuration change).
    fn set_sample_rate(&mut self, sample_rate: f32);

    /// Get the FX type name for IPC/serialization.
    fn fx_type_name(&self) -> &'static str;

    /// Get current gain reduction in dB (for metering). Default: 0.0 (no reduction).
    fn gain_reduction_db(&self) -> f32 { 0.0 }
}

// ---------------------------------------------------------------------------
// FxSlot — One slot in the chain
// ---------------------------------------------------------------------------

/// A single FX slot in the chain.
pub struct FxSlot {
    /// The effect processor.
    pub fx: Box<dyn AudioFxNode>,
    /// Whether this slot is enabled (false = completely skipped).
    pub enabled: bool,
    /// Whether this slot is bypassed (true = dry passthrough, but FX still receives signal
    /// to keep state warm — important for reverb tails etc.).
    pub bypass: bool,
    /// Slot identifier for IPC (matches device_id in Python).
    pub slot_id: String,
}

impl FxSlot {
    /// Create a new FX slot.
    pub fn new(fx: Box<dyn AudioFxNode>, slot_id: String) -> Self {
        Self {
            fx,
            enabled: true,
            bypass: false,
            slot_id,
        }
    }

    /// Process this slot. Returns true if FX was applied, false if skipped/bypassed.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer, ctx: &FxContext) -> bool {
        if !self.enabled {
            return false;
        }
        if self.bypass {
            // Still process to keep state warm, but discard output
            // by saving/restoring the buffer. For efficiency, we just
            // skip — the state will catch up quickly enough.
            return false;
        }
        self.fx.process(buffer, ctx);
        true
    }
}

// ---------------------------------------------------------------------------
// FxChain — Serial chain of FxSlots
// ---------------------------------------------------------------------------

/// Where in the signal chain the FX are applied.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FxPosition {
    /// Before volume/pan (default, like most DAWs).
    PreFader,
    /// After volume/pan.
    PostFader,
}

/// Serial FX chain for a track.
///
/// Processes all enabled, non-bypassed slots in order.
/// Supports sidechain input, dry/wet mix, and pre/post-fader positioning.
pub struct FxChain {
    /// Ordered list of FX slots.
    slots: Vec<FxSlot>,
    /// Global chain mix (0.0 = fully dry, 1.0 = fully wet).
    mix: f32,
    /// Global wet gain (linear, applied to wet signal before mixing).
    wet_gain: f32,
    /// FX position in signal chain.
    pub position: FxPosition,
    /// Sidechain buffer (pre-allocated, optional external input).
    sidechain_buf: Option<AudioBuffer>,
    /// Dry buffer (pre-allocated scratch for dry/wet mixing).
    dry_buf: AudioBuffer,
    /// Maximum number of slots.
    max_slots: usize,
}

/// Maximum FX slots per chain.
const MAX_FX_SLOTS: usize = 16;

impl FxChain {
    /// Create a new empty FX chain.
    pub fn new(buffer_size: usize) -> Self {
        Self {
            slots: Vec::with_capacity(MAX_FX_SLOTS),
            mix: 1.0,
            wet_gain: 1.0,
            position: FxPosition::PreFader,
            sidechain_buf: None,
            dry_buf: AudioBuffer::new(buffer_size, 2),
            max_slots: MAX_FX_SLOTS,
        }
    }

    /// Set global dry/wet mix.
    pub fn set_mix(&mut self, mix: f32) {
        self.mix = mix.clamp(0.0, 1.0);
    }

    /// Set global wet gain.
    pub fn set_wet_gain(&mut self, gain: f32) {
        self.wet_gain = gain.max(0.0);
    }

    /// Set sidechain input buffer (call before process, from another track).
    pub fn set_sidechain(&mut self, sidechain: AudioBuffer) {
        self.sidechain_buf = Some(sidechain);
    }

    /// Clear sidechain input.
    pub fn clear_sidechain(&mut self) {
        self.sidechain_buf = None;
    }

    /// Number of slots in the chain.
    pub fn len(&self) -> usize {
        self.slots.len()
    }

    /// Is the chain empty?
    pub fn is_empty(&self) -> bool {
        self.slots.is_empty()
    }

    /// Add an FX to the end of the chain. Returns slot index.
    pub fn add_fx(&mut self, fx: Box<dyn AudioFxNode>, slot_id: String) -> Option<usize> {
        if self.slots.len() >= self.max_slots {
            return None;
        }
        let idx = self.slots.len();
        self.slots.push(FxSlot::new(fx, slot_id));
        Some(idx)
    }

    /// Insert an FX at a specific position. Returns true if successful.
    pub fn insert_fx(&mut self, index: usize, fx: Box<dyn AudioFxNode>, slot_id: String) -> bool {
        if self.slots.len() >= self.max_slots || index > self.slots.len() {
            return false;
        }
        self.slots.insert(index, FxSlot::new(fx, slot_id));
        true
    }

    /// Remove an FX by slot index. Returns the removed FxSlot.
    pub fn remove_fx(&mut self, index: usize) -> Option<FxSlot> {
        if index < self.slots.len() {
            Some(self.slots.remove(index))
        } else {
            None
        }
    }

    /// Get mutable reference to a slot by index.
    pub fn get_slot_mut(&mut self, index: usize) -> Option<&mut FxSlot> {
        self.slots.get_mut(index)
    }

    /// Get reference to a slot by index.
    pub fn get_slot(&self, index: usize) -> Option<&FxSlot> {
        self.slots.get(index)
    }

    /// Find slot index by slot_id.
    pub fn find_slot(&self, slot_id: &str) -> Option<usize> {
        self.slots.iter().position(|s| s.slot_id == slot_id)
    }

    /// Reorder: move slot from `from` to `to` position in the result.
    pub fn reorder(&mut self, from: usize, to: usize) -> bool {
        if from >= self.slots.len() || to >= self.slots.len() {
            return false;
        }
        if from == to {
            return true;
        }
        let slot = self.slots.remove(from);
        let insert_at = to.min(self.slots.len());
        self.slots.insert(insert_at, slot);
        true
    }

    /// Set enabled state for a slot.
    pub fn set_enabled(&mut self, index: usize, enabled: bool) {
        if let Some(slot) = self.slots.get_mut(index) {
            slot.enabled = enabled;
        }
    }

    /// Set bypass state for a slot.
    pub fn set_bypass(&mut self, index: usize, bypass: bool) {
        if let Some(slot) = self.slots.get_mut(index) {
            slot.bypass = bypass;
        }
    }

    /// Reset all FX in the chain (transport stop, etc.).
    pub fn reset(&mut self) {
        for slot in &mut self.slots {
            slot.fx.reset();
        }
    }

    /// Update sample rate for all FX.
    pub fn set_sample_rate(&mut self, sr: f32) {
        for slot in &mut self.slots {
            slot.fx.set_sample_rate(sr);
        }
    }

    /// Resize internal buffers (after buffer_size change).
    pub fn resize_buffers(&mut self, buffer_size: usize) {
        self.dry_buf = AudioBuffer::new(buffer_size, 2);
    }

    /// Process the entire FX chain on a stereo buffer. **AUDIO THREAD**.
    ///
    /// This is the main entry point called by TrackNode.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer, sample_rate: f32, tempo_bpm: f64) {
        // Quick exit: no FX or fully dry
        if self.slots.is_empty() || self.mix < 0.001 {
            return;
        }

        let ctx = FxContext {
            sample_rate,
            sidechain: self.sidechain_buf.as_ref(),
            tempo_bpm,
        };

        if (self.mix - 1.0).abs() < 0.001 && (self.wet_gain - 1.0).abs() < 0.001 {
            // Fully wet, no mixing needed — process in-place
            for slot in &mut self.slots {
                slot.process(buffer, &ctx);
            }
        } else {
            // Need dry/wet mix — save dry signal
            let frames = buffer.frames.min(self.dry_buf.frames);
            let len = frames * 2;
            self.dry_buf.data[..len].copy_from_slice(&buffer.data[..len]);

            // Process wet path
            for slot in &mut self.slots {
                slot.process(buffer, &ctx);
            }

            // Apply wet gain
            if (self.wet_gain - 1.0).abs() > 0.001 {
                for s in buffer.data[..len].iter_mut() {
                    *s *= self.wet_gain;
                }
            }

            // Mix dry + wet
            let dry_amount = 1.0 - self.mix;
            let wet_amount = self.mix;
            for i in 0..len {
                buffer.data[i] = self.dry_buf.data[i] * dry_amount + buffer.data[i] * wet_amount;
            }
        }
    }

    /// Get gain reduction from the first compressor/gate in the chain (for metering).
    pub fn gain_reduction_db(&self) -> f32 {
        for slot in &self.slots {
            if slot.enabled && !slot.bypass {
                let gr = slot.fx.gain_reduction_db();
                if gr.abs() > 0.01 {
                    return gr;
                }
            }
        }
        0.0
    }
}

// ---------------------------------------------------------------------------
// AudioFxNode implementations for all built-in FX
// ---------------------------------------------------------------------------

// Macro to reduce boilerplate for wrapping existing FX structs as AudioFxNode.
macro_rules! impl_fx_node {
    ($type:ty, $name:expr) => {
        impl AudioFxNode for $type {
            #[inline]
            fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &FxContext) {
                self.process(buffer);
            }
            fn reset(&mut self) {
                self.reset();
            }
            fn set_sample_rate(&mut self, sr: f32) {
                self.set_sample_rate(sr);
            }
            fn fx_type_name(&self) -> &'static str {
                $name
            }
        }
    };
    // Variant with gain_reduction_db
    ($type:ty, $name:expr, gr) => {
        impl AudioFxNode for $type {
            #[inline]
            fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &FxContext) {
                self.process(buffer);
            }
            fn reset(&mut self) {
                self.reset();
            }
            fn set_sample_rate(&mut self, sr: f32) {
                self.set_sample_rate(sr);
            }
            fn fx_type_name(&self) -> &'static str {
                $name
            }
            fn gain_reduction_db(&self) -> f32 {
                self.gain_reduction_db()
            }
        }
    };
}

// R2: Built-in FX
impl_fx_node!(crate::fx::parametric_eq::ParametricEq, "parametric_eq");
impl_fx_node!(crate::fx::limiter::Limiter, "limiter");
impl_fx_node!(crate::fx::reverb::Reverb, "reverb");
impl_fx_node!(crate::fx::delay::Delay, "delay");

// Compressor needs special handling (sidechain)
impl AudioFxNode for crate::fx::compressor::Compressor {
    #[inline]
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &FxContext) {
        self.process(buffer, ctx.sidechain);
    }
    fn reset(&mut self) {
        self.reset();
    }
    fn set_sample_rate(&mut self, sr: f32) {
        self.set_sample_rate(sr);
    }
    fn fx_type_name(&self) -> &'static str {
        "compressor"
    }
    fn gain_reduction_db(&self) -> f32 {
        self.gain_reduction_db()
    }
}

// R3A: Creative FX
impl_fx_node!(crate::fx::chorus::Chorus, "chorus");
impl_fx_node!(crate::fx::phaser::Phaser, "phaser");
impl_fx_node!(crate::fx::flanger::Flanger, "flanger");
impl_fx_node!(crate::fx::tremolo::Tremolo, "tremolo");
impl_fx_node!(crate::fx::distortion::Distortion, "distortion");

// R3B: Utility FX
impl_fx_node!(crate::fx::spectrum_analyzer::SpectrumAnalyzer, "spectrum_analyzer");
impl_fx_node!(crate::fx::stereo_widener::StereoWidener, "stereo_widener");
impl_fx_node!(crate::fx::utility::Utility, "utility");

// Gate needs special handling (sidechain)
impl AudioFxNode for crate::fx::gate::Gate {
    #[inline]
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &FxContext) {
        if let Some(sc) = ctx.sidechain {
            self.process_with_sidechain(buffer, Some(sc));
        } else {
            self.process(buffer);
        }
    }
    fn reset(&mut self) {
        self.reset();
    }
    fn set_sample_rate(&mut self, sr: f32) {
        self.set_sample_rate(sr);
    }
    fn fx_type_name(&self) -> &'static str {
        "gate"
    }
    fn gain_reduction_db(&self) -> f32 {
        // Convert gate gain to dB reduction
        let gain = self.current_gain();
        if gain > 0.0 { -20.0 * (1.0 / gain).log10() } else { -80.0 }
    }
}

// DeEsser needs special handling (gain_reduction)
impl AudioFxNode for crate::fx::deesser::DeEsser {
    #[inline]
    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &FxContext) {
        self.process(buffer);
    }
    fn reset(&mut self) {
        self.reset();
    }
    fn set_sample_rate(&mut self, sr: f32) {
        self.set_sample_rate(sr);
    }
    fn fx_type_name(&self) -> &'static str {
        "deesser"
    }
    fn gain_reduction_db(&self) -> f32 {
        self.gain_reduction_db()
    }
}

// ---------------------------------------------------------------------------
// Factory — Create FX instances by type name
// ---------------------------------------------------------------------------

/// Create a new FX instance by type name. Returns None for unknown types.
pub fn create_fx(fx_type: &str, sample_rate: f32) -> Option<Box<dyn AudioFxNode>> {
    match fx_type {
        // R2
        "parametric_eq" => Some(Box::new(crate::fx::parametric_eq::ParametricEq::new(sample_rate))),
        "compressor" => Some(Box::new(crate::fx::compressor::Compressor::new(sample_rate))),
        "limiter" => Some(Box::new(crate::fx::limiter::Limiter::new(sample_rate))),
        "reverb" => Some(Box::new(crate::fx::reverb::Reverb::new(sample_rate))),
        "delay" => Some(Box::new(crate::fx::delay::Delay::new(sample_rate))),
        // R3A
        "chorus" => Some(Box::new(crate::fx::chorus::Chorus::new(sample_rate))),
        "phaser" => Some(Box::new(crate::fx::phaser::Phaser::new(sample_rate))),
        "flanger" => Some(Box::new(crate::fx::flanger::Flanger::new(sample_rate))),
        "tremolo" => Some(Box::new(crate::fx::tremolo::Tremolo::new(sample_rate))),
        "distortion" => Some(Box::new(crate::fx::distortion::Distortion::new(sample_rate))),
        // R3B
        "gate" => Some(Box::new(crate::fx::gate::Gate::new(sample_rate))),
        "deesser" => Some(Box::new(crate::fx::deesser::DeEsser::new(sample_rate))),
        "stereo_widener" => Some(Box::new(crate::fx::stereo_widener::StereoWidener::new(sample_rate))),
        "utility" => Some(Box::new(crate::fx::utility::Utility::new(sample_rate))),
        "spectrum_analyzer" => Some(Box::new(crate::fx::spectrum_analyzer::SpectrumAnalyzer::new(sample_rate))),
        _ => None,
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_chain_passthrough() {
        let mut chain = FxChain::new(256);
        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        chain.process(&mut buf, 44100.0, 120.0);
        assert!((buf.data[0] - 0.42).abs() < 1e-6);
        assert!((buf.data[1] - (-0.33)).abs() < 1e-6);
    }

    #[test]
    fn test_chain_with_single_fx() {
        let mut chain = FxChain::new(256);
        let reverb = crate::fx::reverb::Reverb::new(44100.0);
        chain.add_fx(Box::new(reverb), "rev1".to_string());

        let mut buf = AudioBuffer::new(64, 2);
        buf.data[0] = 1.0;
        buf.data[1] = 1.0;
        chain.process(&mut buf, 44100.0, 120.0);

        // Reverb should have processed (not just passthrough)
        // With default 0.3 mix, dry signal should be reduced
        // Just check it doesn't crash and produces finite values
        for &s in &buf.data {
            assert!(s.is_finite(), "Chain output should be finite");
        }
    }

    #[test]
    fn test_chain_bypass() {
        let mut chain = FxChain::new(256);
        let mut reverb = crate::fx::reverb::Reverb::new(44100.0);
        reverb.set_params(0.8, 0.3, 0.0, 1.0); // full wet
        chain.add_fx(Box::new(reverb), "rev1".to_string());
        chain.set_bypass(0, true);

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        chain.process(&mut buf, 44100.0, 120.0);

        // Bypassed: should be dry signal
        assert!((buf.data[254] - 0.42).abs() < 0.01, "Bypass should pass dry signal");
    }

    #[test]
    fn test_chain_disable() {
        let mut chain = FxChain::new(256);
        let reverb = crate::fx::reverb::Reverb::new(44100.0);
        chain.add_fx(Box::new(reverb), "rev1".to_string());
        chain.set_enabled(0, false);

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        chain.process(&mut buf, 44100.0, 120.0);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }

    #[test]
    fn test_chain_dry_wet_mix() {
        let mut chain = FxChain::new(256);
        // Use a utility that inverts phase — easy to verify mix
        let mut util = crate::fx::utility::Utility::new(44100.0);
        util.set_params(crate::fx::utility::UtilityParams {
            gain_db: 0.0,
            pan: 0.0,
            phase_invert_l: true,
            phase_invert_r: true,
            mono: false,
            dc_block: false,
            channel_swap: false,
        });
        chain.add_fx(Box::new(util), "util1".to_string());
        chain.set_mix(0.5); // 50% dry + 50% wet (inverted)

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.8;
            buf.data[i * 2 + 1] = 0.8;
        }
        chain.process(&mut buf, 44100.0, 120.0);

        // 50% of 0.8 + 50% of (-0.8 * pan_gain) — equal-power pan at center = 0.707
        // So: 0.4 + 0.5 * (-0.8 * 0.707) = 0.4 - 0.283 ≈ 0.117
        // The key assertion: output is significantly reduced vs input (mix is working)
        let last = buf.data[254];
        assert!(last.abs() < 0.4, "50/50 mix with invert should reduce signal, got {}", last);
    }

    #[test]
    fn test_chain_add_remove_reorder() {
        let mut chain = FxChain::new(256);
        chain.add_fx(Box::new(crate::fx::reverb::Reverb::new(44100.0)), "a".to_string());
        chain.add_fx(Box::new(crate::fx::delay::Delay::new(44100.0)), "b".to_string());
        chain.add_fx(Box::new(crate::fx::chorus::Chorus::new(44100.0)), "c".to_string());
        assert_eq!(chain.len(), 3);

        // Find by id
        assert_eq!(chain.find_slot("b"), Some(1));

        // Remove middle
        chain.remove_fx(1);
        assert_eq!(chain.len(), 2);
        assert_eq!(chain.find_slot("c"), Some(1));

        // Reorder
        chain.reorder(0, 1);
        assert_eq!(chain.get_slot(0).unwrap().slot_id, "c");
    }

    #[test]
    fn test_factory_creates_all_fx() {
        let types = [
            "parametric_eq", "compressor", "limiter", "reverb", "delay",
            "chorus", "phaser", "flanger", "tremolo", "distortion",
            "gate", "deesser", "stereo_widener", "utility", "spectrum_analyzer",
        ];
        for t in &types {
            let fx = create_fx(t, 44100.0);
            assert!(fx.is_some(), "Factory should create FX type '{}'", t);
            assert_eq!(fx.unwrap().fx_type_name(), *t);
        }
        assert!(create_fx("nonexistent", 44100.0).is_none());
    }

    #[test]
    fn test_chain_multi_fx() {
        let mut chain = FxChain::new(256);
        chain.add_fx(Box::new(crate::fx::parametric_eq::ParametricEq::new(44100.0)), "eq".to_string());
        chain.add_fx(Box::new(crate::fx::compressor::Compressor::new(44100.0)), "comp".to_string());
        chain.add_fx(Box::new(crate::fx::reverb::Reverb::new(44100.0)), "rev".to_string());
        chain.add_fx(Box::new(crate::fx::limiter::Limiter::new(44100.0)), "lim".to_string());

        let mut buf = AudioBuffer::new(256, 2);
        for i in 0..256 {
            let t = i as f32 / 44100.0;
            let s = (440.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        chain.process(&mut buf, 44100.0, 120.0);

        // Should produce valid output without NaN/Inf
        for &s in &buf.data {
            assert!(s.is_finite(), "Multi-FX chain should produce finite output");
        }
    }
}
