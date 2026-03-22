# -*- coding: utf-8 -*-
"""FX Specs (built-in) for ChronoScaleStudio.

This is the "Browser catalog" of built-in Note-FX + Audio-FX modules.
Important UX rule (Bitwig/Ableton style):
- Browser entries are templates.
- Dragging/double-clicking creates a NEW instance on the track device chain.
- The browser catalog never disappears.

Keep this list small and stable; add more devices over time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass(frozen=True)
class FxSpec:
    kind: str          # "note_fx" | "audio_fx"
    plugin_id: str
    name: str
    defaults: Dict[str, Any]


def get_note_fx() -> List[FxSpec]:
    return [
        FxSpec("note_fx", "chrono.note_fx.transpose", "Transpose", {"semitones": 0}),
        FxSpec("note_fx", "chrono.note_fx.velocity_scale", "VelScale", {"scale": 1.0}),
        FxSpec("note_fx", "chrono.note_fx.scale_snap", "ScaleSnap", {"root": 0, "scale": "major", "mode": "nearest"}),
        FxSpec("note_fx", "chrono.note_fx.chord", "Chord", {"chord": "maj", "voicing": "close", "spread": 0}),
        FxSpec("note_fx", "chrono.note_fx.arp", "Arp", {"step_beats": 0.5, "mode": "up", "octaves": 1, "gate": 0.9}),
        FxSpec("note_fx", "chrono.note_fx.random", "Random", {"pitch_range": 0, "vel_range": 0, "prob": 1.0, "timing_range": 0.0, "length_range": 0.0}),
        # v0.0.20.644: New Note FX (AP6 Phase 6A)
        FxSpec("note_fx", "chrono.note_fx.note_echo", "Note Echo", {"delay_beats": 0.5, "repeats": 3, "feedback": 0.6, "transpose_per_repeat": 0}),
        FxSpec("note_fx", "chrono.note_fx.velocity_curve", "Vel Curve", {"type": "compress", "amount": 0.5, "min": 1, "max": 127, "fixed": 0}),
        # v0.0.20.191: algorithmic "AI" composer (MIDI generation tool as Note-FX)
        FxSpec(
            "note_fx",
            "chrono.note_fx.ai_composer",
            "AI Composer",
            {
                "genre_a": "Barock (Bach/Fuge)",
                "genre_b": "Electro",
                "custom_genre_a": "",
                "custom_genre_b": "",
                "context": "Neutral",
                "form": "Mini-Fuge (Subject/Answer)",
                "instrument_setup": "Kammermusik-Setup",
                "bars": 8,
                "grid": 0.25,
                "swing": 0.0,
                "density": 0.65,
                "hybrid": 0.55,
                "seed": 1,
            },
        ),
    ]


def get_audio_fx() -> List[FxSpec]:
    # NOTE: "CHAIN" (container) is not a draggable device — it is always present per track.
    return [
        FxSpec("audio_fx", "chrono.fx.gain", "Gain", {"gain_db": 0.0, "gain": 1.0}),
        FxSpec("audio_fx", "chrono.fx.distortion", "Distortion", {"drive": 0.25, "mix": 1.0}),
        # ── v105: 15 Bitwig-Style Audio-FX ──────────────────────
        # v0.0.20.642: Essential FX now have real DSP + defaults (AP8 Phase 8A)
        FxSpec("audio_fx", "chrono.fx.eq5", "EQ-5", {
            "band0_freq": 60, "band0_gain_db": 0, "band0_q": 0.7, "band0_type": 4, "band0_enabled": 1,
            "band1_freq": 400, "band1_gain_db": 0, "band1_q": 1.0, "band1_type": 0, "band1_enabled": 1,
            "band2_freq": 1000, "band2_gain_db": 0, "band2_q": 1.0, "band2_type": 0, "band2_enabled": 1,
            "band3_freq": 3000, "band3_gain_db": 0, "band3_q": 1.0, "band3_type": 0, "band3_enabled": 1,
            "band4_freq": 10000, "band4_gain_db": 0, "band4_q": 0.7, "band4_type": 3, "band4_enabled": 1,
        }),
        FxSpec("audio_fx", "chrono.fx.delay2", "Delay-2", {
            "time_ms": 375, "feedback": 0.4, "mix": 0.3, "ping_pong": 0, "filter_freq": 8000,
        }),
        FxSpec("audio_fx", "chrono.fx.reverb", "Reverb", {
            "decay": 0.5, "damping": 0.5, "pre_delay_ms": 10, "mix": 0.3,
        }),
        FxSpec("audio_fx", "chrono.fx.comb", "Comb", {}),
        FxSpec("audio_fx", "chrono.fx.compressor", "Compressor", {
            "threshold_db": -20, "ratio": 4, "attack_ms": 10, "release_ms": 100,
            "knee_db": 6, "makeup_db": 0, "mix": 1.0,
        }),
        FxSpec("audio_fx", "chrono.fx.filter_plus", "Phaser ✏️", {
            "rate_hz": 0.5, "depth": 0.7, "feedback": 0.5, "mix": 0.5,
        }),
        FxSpec("audio_fx", "chrono.fx.distortion_plus", "Distortion+ ✏️", {
            "drive": 0.5, "tone": 0.5, "mix": 1.0,
        }),
        FxSpec("audio_fx", "chrono.fx.dynamics", "Dynamics", {}),
        FxSpec("audio_fx", "chrono.fx.flanger", "Flanger ✏️", {
            "rate_hz": 0.3, "depth_ms": 3.0, "feedback": 0.6, "mix": 0.5,
        }),
        FxSpec("audio_fx", "chrono.fx.pitch_shifter", "Pitch Shifter", {}),
        FxSpec("audio_fx", "chrono.fx.tremolo", "Tremolo ✏️", {
            "rate_hz": 4.0, "depth": 0.7, "stereo_offset": 0.0, "mix": 1.0,
        }),
        FxSpec("audio_fx", "chrono.fx.peak_limiter", "Peak Limiter", {
            "ceiling_db": -0.3, "release_ms": 50, "gain_db": 0,
        }),
        FxSpec("audio_fx", "chrono.fx.chorus", "Chorus ✏️", {
            "rate_hz": 1.5, "depth_ms": 5.0, "voices": 2, "mix": 0.5,
        }),
        FxSpec("audio_fx", "chrono.fx.xy_fx", "XY FX", {}),
        # v0.0.20.644: Utility FX (AP8 Phase 8C)
        FxSpec("audio_fx", "chrono.fx.gate", "Gate", {
            "threshold_db": -40, "attack_ms": 0.5, "hold_ms": 50,
            "release_ms": 100, "range_db": -80, "mix": 1.0,
        }),
        FxSpec("audio_fx", "chrono.fx.de_esser", "De-Esser", {
            "frequency": 6500, "threshold_db": -20, "range_db": 6,
            "attack_ms": 0.1, "release_ms": 50, "listen": 0,
        }),
        FxSpec("audio_fx", "chrono.fx.stereo_widener", "Stereo Widener", {
            "width": 1.0, "mid_gain_db": 0, "side_gain_db": 0, "mix": 1.0,
        }),
        FxSpec("audio_fx", "chrono.fx.utility", "Utility", {
            "gain_db": 0, "pan": 0, "phase_invert_l": 0, "phase_invert_r": 0,
            "mono": 0, "dc_block": 1, "channel_swap": 0,
        }),
        FxSpec("audio_fx", "chrono.fx.spectrum_analyzer", "Spectrum Analyzer", {
            "fft_size": 2048, "peak_hold_s": 2.0, "smoothing": 0.7,
        }),
    ]


def get_containers() -> List[FxSpec]:
    """v0.0.20.530: Device containers (Bitwig-Style Sound Design)."""
    return [
        FxSpec("container", "chrono.container.fx_layer", "FX Layer",
               {"mix": 1.0}),
        FxSpec("container", "chrono.container.chain", "Chain",
               {"mix": 1.0}),
        FxSpec("container", "chrono.container.instrument_layer", "Instrument Layer",
               {"mix": 1.0}),
    ]


def get_instruments() -> List[FxSpec]:
    """v0.0.20.536: Built-in instrument types for Instrument Layer picker."""
    return [
        FxSpec("instrument", "chrono.sampler", "Pro Sampler", {}),
        FxSpec("instrument", "chrono.drum_machine", "Pro Drum Machine", {}),
        FxSpec("instrument", "chrono.aeterna", "AETERNA Synthesizer", {}),
        FxSpec("instrument", "chrono.bach_orgel", "Bach Orgel", {}),
        FxSpec("instrument", "chrono.fusion", "Fusion Synth", {}),  # v0.0.20.574
        FxSpec("instrument", "chrono.sf2", "SF2 Soundfont", {}),  # v0.0.20.543
    ]
