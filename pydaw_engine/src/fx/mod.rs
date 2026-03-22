// ==========================================================================
// FX Module — Built-in audio effects for the Rust engine
// ==========================================================================
// v0.0.20.669 — Phase R2 + R3 + R4A
//
// All effects process AudioBuffer in-place. Zero allocations in process().
//
// R2: Core FX (EQ, Compressor, Limiter, Reverb, Delay)
// R3A: Creative FX (Chorus, Phaser, Flanger, Tremolo, Distortion)
// R3B: Utility FX (Gate, DeEsser, Stereo Widener, Utility, Spectrum Analyzer)
// R4A: FX Chain System (AudioFxNode trait, FxSlot, FxChain, Factory)
// ==========================================================================

// --- Phase R2: Built-in FX ---
pub mod parametric_eq;
pub mod compressor;
pub mod limiter;
pub mod reverb;
pub mod delay;

// --- Phase R3A: Creative / Modulation FX ---
pub mod chorus;
pub mod phaser;
pub mod flanger;
pub mod tremolo;
pub mod distortion;

// --- Phase R3B: Utility FX ---
pub mod gate;
pub mod deesser;
pub mod stereo_widener;
pub mod utility;
pub mod spectrum_analyzer;

// --- Phase R4A: FX Chain System ---
pub mod chain;

// Re-exports: R2
#[allow(unused_imports)]
pub use parametric_eq::{ParametricEq, EqBandParams};
#[allow(unused_imports)]
pub use compressor::{Compressor, CompressorParams};
#[allow(unused_imports)]
pub use limiter::Limiter;
#[allow(unused_imports)]
pub use reverb::Reverb;
#[allow(unused_imports)]
pub use delay::Delay;

// Re-exports: R3A
#[allow(unused_imports)]
pub use chorus::{Chorus, ChorusParams};
#[allow(unused_imports)]
pub use phaser::{Phaser, PhaserParams};
#[allow(unused_imports)]
pub use flanger::{Flanger, FlangerParams};
#[allow(unused_imports)]
pub use tremolo::{Tremolo, TremoloParams};
#[allow(unused_imports)]
pub use distortion::{Distortion, DistortionParams, DistortionMode};

// Re-exports: R3B
#[allow(unused_imports)]
pub use gate::{Gate, GateParams};
#[allow(unused_imports)]
pub use deesser::{DeEsser, DeEsserParams};
#[allow(unused_imports)]
pub use stereo_widener::{StereoWidener, StereoWidenerParams};
#[allow(unused_imports)]
pub use utility::{Utility, UtilityParams};
#[allow(unused_imports)]
pub use spectrum_analyzer::{SpectrumAnalyzer, SpectrumAnalyzerParams, SpectrumData};

// Re-exports: R4A
#[allow(unused_imports)]
pub use chain::{AudioFxNode, FxChain, FxContext, FxPosition, FxSlot, create_fx};
