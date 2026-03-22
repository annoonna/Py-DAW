// ==========================================================================
// Engine Integration — A/B Testing + Capability Reporting
// ==========================================================================
// v0.0.20.694 — Phase R13A+B+C
//
// R13A: A/B Comparison Test Framework
//   - Render test signals through Python and Rust paths
//   - Compare peak/RMS deviation
//   - Report performance metrics (render time, CPU load)
//
// R13B: Per-track Rust capability check
//   - Which instrument types are implemented in Rust?
//   - Which FX types are implemented in Rust?
//   - Can a specific track be fully rendered in Rust?
//
// R13C: Migration status helpers
//   - Per-track "Rust" / "Python (Fallback: reason)" report
//   - Automatic recommendation: "X of Y tracks can run on Rust"
//
// Rules:
//   ✅ Capability checks are O(1) — just lookup tables
//   ✅ No audio-thread code in this module
// ==========================================================================

use serde::{Serialize, Deserialize};

// ═══════════════════════════════════════════════════════════════════════════
// R13B — Rust Capability Registry
// ═══════════════════════════════════════════════════════════════════════════

/// Instrument types that have Rust implementations.
///
/// When a track uses one of these instrument types, the Rust engine
/// can render it. Otherwise, fall back to Python.
const RUST_INSTRUMENTS: &[&str] = &[
    "pro_sampler",
    "chrono.pro_audio_sampler",
    "sampler",
    "multi_sample",
    "multisample",
    "chrono.multi_sample",
    "drum_machine",
    "chrono.pro_drum_machine",
    "aeterna",
    "chrono.aeterna",
    "fusion",
    "chrono.fusion",
    "bach_orgel",
    "chrono.bach_orgel",
    "sf2",     // stub — will produce silence until FluidSynth FFI
];

/// Built-in FX types that have Rust implementations.
const RUST_FX: &[&str] = &[
    // Phase R2: Essential
    "parametric_eq",
    "compressor",
    "limiter",
    "reverb",
    "delay",
    // Phase R3: Creative
    "chorus",
    "phaser",
    "flanger",
    "distortion",
    "tremolo",
    // Phase R3: Utility
    "gate",
    "deesser",
    "stereo_widener",
    "utility",
    "spectrum_analyzer",
];

/// Check if an instrument type has a Rust implementation.
pub fn has_rust_instrument(instrument_type: &str) -> bool {
    RUST_INSTRUMENTS.iter().any(|&t| t == instrument_type)
}

/// Check if a built-in FX type has a Rust implementation.
pub fn has_rust_fx(fx_type: &str) -> bool {
    RUST_FX.iter().any(|&t| t == fx_type)
}

/// Check if a track can be fully rendered in Rust.
///
/// A track can use Rust if:
/// 1. Its instrument (if any) has a Rust implementation
/// 2. All its FX have Rust implementations (or are external plugins)
/// 3. External VST/CLAP plugins are handled by Rust's plugin host
///
/// Returns `(can_use_rust, reason)`.
pub fn can_track_use_rust(
    instrument_type: Option<&str>,
    fx_types: &[String],
    has_external_plugins: bool,
) -> (bool, String) {
    // Check instrument
    if let Some(inst_type) = instrument_type {
        if !inst_type.is_empty() && !has_rust_instrument(inst_type) {
            return (false, format!("Instrument '{}' nicht in Rust implementiert", inst_type));
        }
        // SF2 is a stub — warn but allow
        if inst_type == "sf2" || inst_type == "chrono.sf2" {
            return (true, "SF2: Stub (kein Audio bis FluidSynth FFI)".to_string());
        }
    }

    // Check built-in FX
    for fx in fx_types {
        if !fx.is_empty() && !has_rust_fx(fx) && !fx.starts_with("ext.") {
            return (false, format!("FX '{}' nicht in Rust implementiert", fx));
        }
    }

    // External plugins: Rust has VST3/CLAP host stubs
    if has_external_plugins {
        return (true, "Extern-Plugins via Rust Plugin Host (Stubs)".to_string());
    }

    (true, "Vollständig in Rust".to_string())
}

// ═══════════════════════════════════════════════════════════════════════════
// R13C — Migration Status Report
// ═══════════════════════════════════════════════════════════════════════════

/// Per-track migration status.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackMigrationStatus {
    pub track_id: String,
    pub track_name: String,
    /// Whether this track can be rendered in Rust.
    pub can_use_rust: bool,
    /// Human-readable reason (for UI display).
    pub reason: String,
    /// Instrument type on this track (if any).
    pub instrument_type: Option<String>,
    /// Backend that will be used: "rust" or "python".
    pub effective_backend: String,
}

/// Project-wide migration report.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MigrationReport {
    /// Per-track status.
    pub tracks: Vec<TrackMigrationStatus>,
    /// Number of tracks that can use Rust.
    pub rust_track_count: usize,
    /// Total number of tracks.
    pub total_track_count: usize,
    /// Overall recommendation.
    pub recommendation: String,
    /// Recommended engine mode: "off", "hybrid", "full".
    pub recommended_mode: String,
}

impl MigrationReport {
    /// Generate a report from track configurations.
    pub fn generate(
        tracks: &[(String, String, Option<String>, Vec<String>, bool)],
        // (track_id, track_name, instrument_type, fx_types, has_external_plugins)
    ) -> Self {
        let mut statuses = Vec::new();
        let mut rust_count = 0;

        for (id, name, inst, fxs, ext) in tracks {
            let (can, reason) = can_track_use_rust(
                inst.as_deref(),
                fxs,
                *ext,
            );
            if can {
                rust_count += 1;
            }
            statuses.push(TrackMigrationStatus {
                track_id: id.clone(),
                track_name: name.clone(),
                can_use_rust: can,
                reason,
                instrument_type: inst.clone(),
                effective_backend: if can { "rust".to_string() } else { "python".to_string() },
            });
        }

        let total = statuses.len();
        let (recommendation, mode) = if total == 0 {
            ("Kein Track vorhanden".to_string(), "off".to_string())
        } else if rust_count == total {
            (format!("Alle {} Tracks können in Rust laufen — Full Mode empfohlen", total), "full".to_string())
        } else if rust_count > 0 {
            (format!("{} von {} Tracks können in Rust laufen — Hybrid Mode empfohlen", rust_count, total), "hybrid".to_string())
        } else {
            ("Kein Track kann in Rust laufen — Python Mode".to_string(), "off".to_string())
        };

        Self {
            tracks: statuses,
            rust_track_count: rust_count,
            total_track_count: total,
            recommendation,
            recommended_mode: mode,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// R13A — A/B Test Helpers
// ═══════════════════════════════════════════════════════════════════════════

/// Result of an A/B comparison between Python and Rust rendering.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ABTestResult {
    /// Maximum sample deviation (absolute).
    pub max_deviation: f64,
    /// RMS deviation.
    pub rms_deviation: f64,
    /// Whether the deviation is within acceptable bounds.
    pub passes: bool,
    /// Threshold used for pass/fail (in dB below full scale).
    pub threshold_dbfs: f64,
    /// Rust render time in microseconds.
    pub rust_render_us: u64,
    /// Python render time in microseconds (0 if not measured on Rust side).
    pub python_render_us: u64,
    /// Speedup factor (python_time / rust_time).
    pub speedup: f64,
    /// Number of frames compared.
    pub frames_compared: u64,
    /// Human-readable summary.
    pub summary: String,
}

impl ABTestResult {
    /// Compare two audio buffers (interleaved stereo f32).
    ///
    /// `reference`: Python-rendered audio
    /// `test`: Rust-rendered audio
    /// `threshold_dbfs`: Maximum allowed deviation in dBFS (e.g., -96.0)
    pub fn compare(reference: &[f32], test: &[f32], threshold_dbfs: f64) -> Self {
        let n = reference.len().min(test.len());
        if n == 0 {
            return Self {
                max_deviation: 0.0,
                rms_deviation: 0.0,
                passes: true,
                threshold_dbfs,
                rust_render_us: 0,
                python_render_us: 0,
                speedup: 0.0,
                frames_compared: 0,
                summary: "Keine Daten zum Vergleichen".to_string(),
            };
        }

        let mut max_dev: f64 = 0.0;
        let mut sum_sq: f64 = 0.0;

        for i in 0..n {
            let diff = (reference[i] as f64 - test[i] as f64).abs();
            max_dev = max_dev.max(diff);
            sum_sq += diff * diff;
        }

        let rms_dev = (sum_sq / n as f64).sqrt();

        // Convert threshold from dBFS to linear
        let threshold_linear = 10.0f64.powf(threshold_dbfs / 20.0);
        let passes = max_dev < threshold_linear;

        let max_db = if max_dev > 1e-10 {
            20.0 * max_dev.log10()
        } else {
            -200.0
        };

        let summary = if passes {
            format!("✅ PASS — Max Abweichung: {:.1} dBFS ({} Frames)", max_db, n / 2)
        } else {
            format!("❌ FAIL — Max Abweichung: {:.1} dBFS > {:.1} dBFS Threshold", max_db, threshold_dbfs)
        };

        Self {
            max_deviation: max_dev,
            rms_deviation: rms_dev,
            passes,
            threshold_dbfs,
            rust_render_us: 0,
            python_render_us: 0,
            speedup: 0.0,
            frames_compared: (n / 2) as u64,
            summary,
        }
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rust_instrument_check() {
        assert!(has_rust_instrument("pro_sampler"));
        assert!(has_rust_instrument("aeterna"));
        assert!(has_rust_instrument("fusion"));
        assert!(has_rust_instrument("drum_machine"));
        assert!(has_rust_instrument("bach_orgel"));
        assert!(has_rust_instrument("sf2"));
        assert!(!has_rust_instrument("unknown_synth"));
    }

    #[test]
    fn test_rust_fx_check() {
        assert!(has_rust_fx("compressor"));
        assert!(has_rust_fx("reverb"));
        assert!(has_rust_fx("chorus"));
        assert!(has_rust_fx("gate"));
        assert!(!has_rust_fx("unknown_fx"));
    }

    #[test]
    fn test_can_track_use_rust_instrument() {
        let (ok, _) = can_track_use_rust(Some("aeterna"), &[], false);
        assert!(ok);

        let (ok, reason) = can_track_use_rust(Some("unknown_synth"), &[], false);
        assert!(!ok);
        assert!(reason.contains("nicht in Rust"));
    }

    #[test]
    fn test_can_track_use_rust_audio() {
        // Audio track (no instrument) with built-in FX
        let fxs = vec!["compressor".to_string(), "reverb".to_string()];
        let (ok, _) = can_track_use_rust(None, &fxs, false);
        assert!(ok);
    }

    #[test]
    fn test_can_track_use_rust_unknown_fx() {
        let fxs = vec!["compressor".to_string(), "magic_fx".to_string()];
        let (ok, _) = can_track_use_rust(None, &fxs, false);
        assert!(!ok);
    }

    #[test]
    fn test_migration_report_all_rust() {
        let tracks = vec![
            ("t1".into(), "AETERNA".into(), Some("aeterna".into()), vec![], false),
            ("t2".into(), "Drums".into(), Some("drum_machine".into()), vec![], false),
            ("t3".into(), "Audio".into(), None, vec!["compressor".into()], false),
        ];
        let report = MigrationReport::generate(&tracks);
        assert_eq!(report.rust_track_count, 3);
        assert_eq!(report.total_track_count, 3);
        assert_eq!(report.recommended_mode, "full");
    }

    #[test]
    fn test_migration_report_hybrid() {
        let tracks = vec![
            ("t1".into(), "AETERNA".into(), Some("aeterna".into()), vec![], false),
            ("t2".into(), "Unknown".into(), Some("weird_synth".into()), vec![], false),
        ];
        let report = MigrationReport::generate(&tracks);
        assert_eq!(report.rust_track_count, 1);
        assert_eq!(report.recommended_mode, "hybrid");
    }

    #[test]
    fn test_ab_compare_identical() {
        let a = vec![0.5f32, -0.5, 0.3, -0.3, 0.1, -0.1];
        let b = a.clone();
        let result = ABTestResult::compare(&a, &b, -96.0);
        assert!(result.passes);
        assert!(result.max_deviation < 1e-10);
    }

    #[test]
    fn test_ab_compare_different() {
        let a = vec![1.0f32, -1.0, 0.5, -0.5];
        let b = vec![0.0f32, 0.0, 0.0, 0.0]; // completely different
        let result = ABTestResult::compare(&a, &b, -96.0);
        assert!(!result.passes);
        assert!(result.max_deviation > 0.5);
    }

    #[test]
    fn test_ab_compare_small_diff() {
        let a: Vec<f32> = (0..1000).map(|i| (i as f32 * 0.01).sin()).collect();
        let b: Vec<f32> = a.iter().map(|s| s + 0.00001).collect(); // tiny offset
        let result = ABTestResult::compare(&a, &b, -96.0);
        assert!(result.passes, "Tiny diff should pass: {}", result.summary);
    }
}
