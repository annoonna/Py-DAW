"""Centralized QAction creation (v0.0.7)."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import QObject, Qt


@dataclass
class AppActions:
    # File
    file_new: QAction
    file_open: QAction
    file_save: QAction
    file_save_as: QAction
    file_import_audio: QAction
    file_import_midi: QAction
    file_import_dawproject: QAction  # v0.0.20.88: DAWproject Import
    file_export_dawproject: QAction  # v0.0.20.359: DAWproject Export UI Hook
    file_export: QAction
    file_export_midi_clip: QAction  # FIXED v0.0.19.7.15
    file_export_midi_track: QAction  # FIXED v0.0.19.7.15
    file_exit: QAction

    # Edit
    edit_undo: QAction
    edit_redo: QAction
    edit_cut: QAction
    edit_copy: QAction
    edit_paste: QAction
    edit_select_all: QAction

    # View
    view_dummy: QAction
    view_toggle_pianoroll: QAction
    view_toggle_notation: QAction
    view_toggle_cliplauncher: QAction
    view_toggle_drop_overlay: QAction
    view_toggle_gpu_waveforms: QAction
    view_toggle_cpu_meter: QAction
    view_toggle_automation: QAction

    # Audio
    audio_toggle_rust_engine: QAction
    audio_toggle_plugin_sandbox: QAction

    # Project / Tracks
    project_add_audio_track: QAction
    project_add_instrument_track: QAction
    project_add_bus_track: QAction
    project_add_placeholder_clip: QAction
    project_remove_selected_track: QAction
    project_time_signature: QAction
    project_settings: QAction

    project_save_snapshot: QAction
    project_load_snapshot: QAction

    project_load_sf2: QAction
    # Audio
    audio_settings: QAction
    audio_prerender_midi: QAction
    audio_prerender_selected_clip: QAction
    audio_prerender_selected_track: QAction
    midi_settings: QAction
    midi_mapping: QAction
    midi_panic: QAction

    # Help
    help_workbook: QAction
    help_toggle_python_animation: QAction


def build_actions(parent: QObject) -> AppActions:
    # File
    a_new = QAction("Neu", parent)
    a_new.setShortcut(QKeySequence.StandardKey.New)

    a_open = QAction("Öffnen…", parent)
    a_open.setShortcut(QKeySequence.StandardKey.Open)

    a_save = QAction("Speichern", parent)
    a_save.setShortcut(QKeySequence.StandardKey.Save)

    a_save_as = QAction("Speichern unter…", parent)
    a_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)

    a_imp_a = QAction("Audio importieren…", parent)
    a_imp_m = QAction("MIDI importieren…", parent)
    a_imp_daw = QAction("DAWproject importieren… (.dawproject)", parent)
    a_imp_daw.setShortcut(QKeySequence("Ctrl+Shift+I"))

    a_exp_daw = QAction("DAWproject exportieren… (.dawproject)", parent)

    a_export = QAction("Exportieren…", parent)
    
    # FIXED v0.0.19.7.15: MIDI Export Actions
    a_export_midi_clip = QAction("Export MIDI Clip...", parent)
    a_export_midi_clip.setShortcut(QKeySequence("Ctrl+Shift+E"))
    
    a_export_midi_track = QAction("Export MIDI Track...", parent)
    a_export_midi_track.setShortcut(QKeySequence("Ctrl+Shift+T"))
    
    a_exit = QAction("Beenden", parent)
    a_exit.setShortcut(QKeySequence.StandardKey.Quit)

    # Edit
    a_undo = QAction("Rückgängig", parent)
    a_undo.setShortcut(QKeySequence.StandardKey.Undo)
    a_undo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

    a_redo = QAction("Wiederholen", parent)
    # Pro-DAW-Style: both Ctrl+Shift+Z and Ctrl+Y.
    a_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
    a_redo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

    a_cut = QAction("Ausschneiden", parent)
    a_cut.setShortcut(QKeySequence.StandardKey.Cut)

    a_copy = QAction("Kopieren", parent)
    a_copy.setShortcut(QKeySequence.StandardKey.Copy)

    a_paste = QAction("Einfügen", parent)
    a_paste.setShortcut(QKeySequence.StandardKey.Paste)

    a_sel_all = QAction("Alles auswählen", parent)
    a_sel_all.setShortcut(QKeySequence.StandardKey.SelectAll)

    # View
    a_view = QAction("Ansicht (Platzhalter)", parent)

    a_toggle_pr = QAction("Piano Roll", parent)
    a_toggle_pr.setCheckable(True)

    a_toggle_notation = QAction("Notation (WIP)", parent)
    a_toggle_notation.setCheckable(True)

    a_toggle_cl = QAction("Clip Launcher", parent)
    a_toggle_cl.setCheckable(True)
    a_toggle_cl.setShortcut(QKeySequence("Ctrl+Shift+L"))  # v0.0.20.624: L for Launcher


    a_toggle_overlay = QAction("Overlay ein/aus", parent)
    a_toggle_overlay.setCheckable(True)

    a_toggle_gpu = QAction("GPU Waveforms", parent)
    a_toggle_gpu.setCheckable(True)
    # Optional quick toggle (Pro-DAW-like): keep it out of the way.
    a_toggle_gpu.setShortcut(QKeySequence("Ctrl+Shift+G"))

    a_toggle_cpu = QAction("CPU Anzeige", parent)
    a_toggle_cpu.setCheckable(True)
    # Keep it discoverable but not too easy to hit accidentally.
    a_toggle_cpu.setShortcut(QKeySequence("Ctrl+Shift+U"))

    # v0.0.20.696: Rust Audio-Engine Toggle
    a_toggle_rust = QAction("🦀 Rust Audio-Engine", parent)
    a_toggle_rust.setCheckable(True)
    a_toggle_rust.setShortcut(QKeySequence("Ctrl+Shift+R"))
    a_toggle_rust.setToolTip(
        "Rust Audio-Engine ein/aus.\n\n"
        "⚠️ EXPERIMENTELL — Rust DSP-Module sind fertig,\n"
        "aber die IPC-Bridge zum Python Audio-Thread\n"
        "ist noch nicht aktiv. Einschalten nur zum Testen.\n\n"
        "OFF = Python Audio-Engine (stabil, alle Features)\n"
        "ON = Rust versucht zu rendern (kann stumm sein)\n\n"
        "Notfall: USE_RUST_ENGINE=0 in Terminal"
    )

    # v0.0.20.701: Plugin Sandbox Toggle
    a_toggle_sandbox = QAction("🛡️ Plugin Sandbox (Crash-Schutz)", parent)
    a_toggle_sandbox.setCheckable(True)
    a_toggle_sandbox.setToolTip(
        "Plugin Sandbox ein/aus.\n\n"
        "ON = Jedes externe Plugin (VST/CLAP/LV2) läuft\n"
        "in eigenem Prozess. Crasht ein Plugin, läuft\n"
        "die DAW weiter — nur der Track wird stumm.\n\n"
        "OFF = Plugins laufen im Hauptprozess.\n"
        "Schneller, aber ein Crash killt die ganze DAW.\n\n"
        "Bitwig-Style Crash-Isolation."
    )

    a_toggle_auto = QAction("Automation Lanes", parent)
    a_toggle_auto.setCheckable(True)
    a_toggle_auto.setShortcut(QKeySequence("Ctrl+Shift+A"))

    # Project / Tracks
    a_add_audio = QAction("Audio-Track hinzufügen", parent)
    a_add_inst = QAction("Instrument-Track hinzufügen", parent)
    a_add_bus = QAction("Bus/Master-Track hinzufügen", parent)

    a_add_clip = QAction("Clip hinzufügen (Platzhalter)", parent)
    a_rm_track = QAction("Ausgewählten Track entfernen", parent)

    a_time_sig = QAction("Taktart…", parent)
    a_time_sig.setShortcut(QKeySequence("Ctrl+T"))

    a_proj_settings = QAction("Project Settings…", parent)
    a_load_sf2 = QAction("SoundFont (SF2) laden…", parent, triggered=parent.load_sf2_for_selected_track)
    a_proj_settings.setShortcut(QKeySequence("Ctrl+P"))

    a_snap_save = QAction("Projektstand speichern…", parent)
    a_snap_save.setShortcut(QKeySequence("Ctrl+Alt+S"))

    a_snap_load = QAction("Projektstand laden…", parent)
    a_snap_load.setShortcut(QKeySequence("Ctrl+Alt+L"))

    # Audio
    a_audio = QAction("Audio-Einstellungen…", parent)
    a_prerender = QAction("MIDI-Clips vorbereiten (Pre-Render)", parent)
    a_prerender.setShortcut(QKeySequence("Ctrl+Alt+R"))

    a_prerender_clip = QAction("Pre-Render: ausgewählte Clips", parent)
    a_prerender_clip.setShortcut(QKeySequence("Ctrl+Alt+C"))

    a_prerender_track = QAction("Pre-Render: ausgewählter Track", parent)
    a_prerender_track.setShortcut(QKeySequence("Ctrl+Alt+T"))
    a_midi_settings = QAction("MIDI Settings…", parent)
    a_midi_settings.setShortcut(QKeySequence("Ctrl+M"))

    a_midi_mapping = QAction("MIDI Mapping…", parent)
    # Help
    a_workbook = QAction("Arbeitsmappe…", parent)
    a_workbook.setShortcut(QKeySequence("F1"))

    a_py_anim = QAction("Animation ein/aus", parent)
    a_py_anim.setCheckable(True)

    a_midi_mapping.setShortcut(QKeySequence("Ctrl+K"))

    a_midi_panic = QAction("MIDI Panic (All Notes Off)", parent)
    a_midi_panic.setShortcut(QKeySequence("Ctrl+Shift+P"))

    return AppActions(
        file_new=a_new,
        file_open=a_open,
        file_save=a_save,
        file_save_as=a_save_as,
        file_import_audio=a_imp_a,
        file_import_midi=a_imp_m,
        file_import_dawproject=a_imp_daw,
        file_export_dawproject=a_exp_daw,
        file_export=a_export,
        file_export_midi_clip=a_export_midi_clip,  # FIXED v0.0.19.7.15
        file_export_midi_track=a_export_midi_track,  # FIXED v0.0.19.7.15
        file_exit=a_exit,
        edit_undo=a_undo,
        edit_redo=a_redo,
        edit_cut=a_cut,
        edit_copy=a_copy,
        edit_paste=a_paste,
        edit_select_all=a_sel_all,
        view_dummy=a_view,
        view_toggle_pianoroll=a_toggle_pr,
        view_toggle_notation=a_toggle_notation,
        view_toggle_cliplauncher=a_toggle_cl,
        view_toggle_drop_overlay=a_toggle_overlay,
        view_toggle_gpu_waveforms=a_toggle_gpu,
        view_toggle_cpu_meter=a_toggle_cpu,
        view_toggle_automation=a_toggle_auto,
        audio_toggle_rust_engine=a_toggle_rust,
        audio_toggle_plugin_sandbox=a_toggle_sandbox,
        project_add_audio_track=a_add_audio,
        project_add_instrument_track=a_add_inst,
        project_add_bus_track=a_add_bus,
        project_add_placeholder_clip=a_add_clip,
        project_remove_selected_track=a_rm_track,
        project_time_signature=a_time_sig,
        project_settings=a_proj_settings,
        project_save_snapshot=a_snap_save,
        project_load_snapshot=a_snap_load,
        project_load_sf2=a_load_sf2,
        audio_settings=a_audio,
        audio_prerender_midi=a_prerender,
        audio_prerender_selected_clip=a_prerender_clip,
        audio_prerender_selected_track=a_prerender_track,
        midi_settings=a_midi_settings,
        midi_mapping=a_midi_mapping,
        midi_panic=a_midi_panic,
        help_workbook=a_workbook,
        help_toggle_python_animation=a_py_anim,
    )