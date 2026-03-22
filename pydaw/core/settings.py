"""Settings keys and persistence hooks (placeholders).

In later versions, this module will manage:
- audio backend selection (PipeWire/JACK, device routing)
- last opened project
- UI layout persistence
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsKeys:
    organization: str = "PyDAW"
    application: str = "Py DAW"

    # Future keys (v0.0.2+)
    last_project: str = "ui/last_project"
    audio_backend: str = "audio/backend"
    audio_input: str = "audio/input"
    audio_output: str = "audio/output"
    sample_rate: str = "audio/sample_rate"
    buffer_size: str = "audio/buffer_size"
    jack_enable: str = "audio/jack_enable"
    jack_in_ports: str = "audio/jack_in_ports"
    jack_out_ports: str = "audio/jack_out_ports"
    jack_input_monitor: str = "audio/jack_input_monitor"  # global passthrough monitoring

    # v0.0.20.638: Punch crossfade length in ms (0-100, default 10)
    punch_crossfade_ms: str = "audio/punch_crossfade_ms"

    # Performance (MIDI pre-render)
    prerender_auto_on_load: str = "audio/prerender_auto_on_load"
    prerender_show_progress_on_load: str = "audio/prerender_show_progress_on_load"
    prerender_wait_before_play: str = "audio/prerender_wait_before_play"
    prerender_show_progress_on_play: str = "audio/prerender_show_progress_on_play"

    # UI
    ui_enable_notation_tab: str = "ui/enable_notation_tab"  # show Notation tab entry (WIP)
    ui_python_logo_animation_enabled: str = "ui/python_logo_animation_enabled"

    # UI: optional GPU waveform overlay in Arranger (QOpenGLWidget). OFF by default.
    # This is opt-in because some compositors/drivers may hide the arranger grid if
    # an OpenGL overlay clears an opaque background.
    ui_gpu_waveforms_enabled: str = "ui/gpu_waveforms_enabled"

    # UI: optional CPU indicator in status bar (very low overhead). OFF by default.
    ui_cpu_meter_enabled: str = "ui/cpu_meter_enabled"

    # Audio: Rust Audio-Engine ein/aus. ON by default wenn Binary vorhanden.
    audio_rust_engine_enabled: str = "audio/rust_engine_enabled"

    # Audio: Engine Mode — "python" | "hybrid" | "rust" (RA4/RA5)
    audio_engine_mode: str = "audio/engine_mode"

    # Audio: Plugin Sandbox (crash-safe subprocess hosting). OFF by default.
    audio_plugin_sandbox_enabled: str = "audio/plugin_sandbox_enabled"

    # UI: Piano Roll Note Expressions overlay (Bitwig/Cubase-style). OFF by default.
    ui_pianoroll_note_expressions_enabled: str = "ui/pianoroll_note_expressions_enabled"
    ui_pianoroll_note_expressions_param: str = "ui/pianoroll_note_expressions_param"
    ui_pianoroll_expr_value_snap: str = "ui/pianoroll_expr_value_snap"

    # Audio: safe opt-in note-expression playback extensions
    audio_note_expr_mpe_mode: str = "audio/note_expr_mpe_mode"

    ui_cliplauncher_visible: str = "ui/cliplauncher_visible"
    ui_cliplauncher_overlay_enabled: str = "ui/cliplauncher_overlay_enabled"

    # UI: Clip Launcher Inspector (left "ZELLE" panel)
    ui_cliplauncher_inspector_visible: str = "ui/cliplauncher_inspector_visible"
    ui_cliplauncher_inspector_width: str = "ui/cliplauncher_inspector_width"
    # Scale constraint (Piano Roll + Notation)
    # When enabled, note input is restricted to the selected scale.
    # Mode:
    #   - "snap": out-of-scale pitches are snapped to the nearest in-scale pitch
    #   - "reject": out-of-scale pitches are rejected (nothing is created)
    scale_enabled: str = "music/scale_enabled"
    scale_root_pc: str = "music/scale_root_pc"  # 0..11 (C..B)
    scale_category: str = "music/scale_category"  # e.g. "Kirchentonarten"
    scale_name: str = "music/scale_name"  # e.g. "Dorian"
    scale_mode: str = "music/scale_mode"  # "snap" | "reject"
    scale_visualize: str = "music/scale_visualize"  # show cyan dots/hints in editors
