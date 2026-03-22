// ==========================================================================
// DSP Module — Re-exports all DSP primitives
// ==========================================================================
// v0.0.20.667 — Phase R1
//
// All audio-thread-safe DSP building blocks in one place.
// Every FX and instrument in the Rust engine uses these primitives.
//
// Usage:
//   use crate::dsp::{Biquad, FilterType, DelayLine, AdsrEnvelope, Lfo};
// ==========================================================================

pub mod biquad;
pub mod delay_line;
pub mod envelope;
pub mod interpolation;
pub mod lfo;
pub mod math;
pub mod smooth;

// Re-export the most commonly used types at module level
// Allow unused: these are the public API consumed by fx/ and instruments/ (Phase R2+)
#[allow(unused_imports)]
pub use biquad::{Biquad, BiquadCoeffs, FilterType, StereoBiquad};
#[allow(unused_imports)]
pub use delay_line::DelayLine;
#[allow(unused_imports)]
pub use envelope::{AdsrEnvelope, EnvState};
#[allow(unused_imports)]
pub use interpolation::{
    apply_pan_to_buffer, equal_power_pan, interpolate_cubic, interpolate_linear, linear_pan,
    DcBlocker,
};
#[allow(unused_imports)]
pub use lfo::{Lfo, LfoShape};
#[allow(unused_imports)]
pub use math::{db_to_linear, fast_tanh, freq_to_midi, hard_clip, lerp, linear_to_db,
               midi_to_freq, soft_clip};
#[allow(unused_imports)]
pub use smooth::ParamSmoother;
