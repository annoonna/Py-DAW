"""Main window (v0.0.19.0).

v0.0.14:
- Fix: ServiceContainer includes metronome (no crash)
- Project Settings (central BPM/TS/Grid)
- Metronome audio click (best effort via sounddevice, non-blocking)
- Grid/Snap division control (toolbar + project persistence)
- Automation lanes panel (placeholder, toggleable)
- MIDI Settings (best effort via mido) + message monitor in status bar
- JACK/PipeWire-JACK presence (best effort): registers ports to appear in qpwgraph
"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import traceback

from PyQt6.QtGui import QGuiApplication, QAction, QKeySequence, QShortcut

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QToolButton,
    QComboBox,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QDockWidget,
    QInputDialog,
    QTabWidget,
    QMenu,
)
from PyQt6.QtCore import Qt, QTimer

from pydaw.services.container import ServiceContainer
from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value, set_value
from .actions import build_actions
from .transport import TransportPanel
from .toolbar import ToolBarPanel
from .arranger import ArrangerView
from .mixer import MixerPanel, LibraryPanel
from .track_parameters import TrackParametersPanel
from .audio_settings_dialog import AudioSettingsDialog
from .midi_settings_dialog import MidiSettingsDialog
from .midi_mapping_dialog import MidiMappingDialog
from .editor_tabs import EditorTabs
from .clip_launcher import ClipLauncherPanel
from .time_signature_dialog import TimeSignatureDialog
from .project_settings_dialog import ProjectSettingsDialog
from .qt_logo_button import QtLogoButton
from .rust_logo_button import RustLogoButton
from .device_panel import DevicePanel
from .project_tab_bar import ProjectTabBar
from .project_browser_widget import ProjectBrowserWidget
from .perf_monitor import CpuUsageMonitor
from .screen_layout import ScreenLayoutManager, PanelId, LAYOUT_PRESETS


class MainWindow(QMainWindow):
    def _set_status(self, text: str, timeout_ms: int = 3000) -> None:
        """Central helper to show a status message.

        Some features (snapshots, SF2 handling, imports) want a single place to
        report feedback without raising exceptions inside Qt slots.
        """
        try:
            self.statusBar().showMessage(str(text), int(timeout_ms))
        except Exception:
            pass

    def _safe_project_call(self, method: str, *args, **kwargs):
        """Call ProjectService methods defensively.

        PyQt kann bei Exceptions in Slots hart abbrechen. Deshalb: abfangen,
        in Statusbar melden und weiterlaufen.
        """
        try:
            fn = getattr(self.services.project, method, None)
            if callable(fn):
                return fn(*args, **kwargs)
            self.statusBar().showMessage(f"ProjectService: '{method}' nicht verfügbar.", 4000)
        except Exception as exc:
            try:
                self.services.project.error.emit(str(exc))
            except Exception:
                pass
            self.statusBar().showMessage(f"Fehler in ProjectService.{method}: {exc}", 6000)
        return None

    def _safe_call(self, fn, *args, **kwargs):
        """Call any callable defensively.

        IMPORTANT: On some PyQt6 setups, uncaught Python exceptions inside Qt
        event handlers / slots can lead to a Qt fatal error (SIGABRT). This
        helper ensures we never let exceptions escape into Qt.
        """
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            try:
                self._set_status(f"Fehler: {exc}", 8000)
            except Exception:
                pass
            try:
                traceback.print_exc()
            except Exception:
                pass
            return None


    def _dispatch_edit(self, op: str) -> None:
        """Dispatch global Edit actions (Copy/Cut/Paste/SelectAll) to the focused panel.

        Rationale: avoids Qt "Ambiguous shortcut" warnings and provides consistent DAW-style editing.
        Paste in PianoRoll uses the last mouse position (grid anchor) and snaps to the current grid.
        """
        try:
            w = QApplication.focusWidget()
        except Exception:
            w = None

        # 1) PianoRoll (inside EditorTabs)
        try:
            pr = None
            et = getattr(self, "editor_tabs", None)
            if et is not None:
                pr = getattr(et, "pianoroll", None)

            if pr is not None and w is not None and pr.isVisible() and pr.isAncestorOf(w):
                c = getattr(pr, "canvas", None)
                if c is None:
                    return
                if op == "copy":
                    c.copy_selected()
                    self.statusBar().showMessage("PianoRoll: Copy", 900)
                    return
                if op == "cut":
                    c.cut_selected()
                    self.statusBar().showMessage("PianoRoll: Cut", 900)
                    return
                if op == "paste":
                    c.paste_at_last_mouse()
                    self.statusBar().showMessage("PianoRoll: Paste", 900)
                    return
                if op == "select_all":
                    c.select_all()
                    self.statusBar().showMessage("PianoRoll: Select All", 900)
                    return
        except Exception as e:
            try:
                self.statusBar().showMessage(f"Edit dispatch error: {e}", 3000)
            except Exception:
                pass

        # 2) Other panels (Arranger/ClipLauncher/Mixer) – TODO: implement.
        try:
            self.statusBar().showMessage("Edit: noch nicht für dieses Panel implementiert.", 2000)
        except Exception:
            pass
    def __init__(self, services: ServiceContainer | None = None):
        super().__init__()
        self.services = services or ServiceContainer.create_default()

        self.actions = build_actions(self)
        try:
            self.addAction(self.actions.edit_undo)
            self.addAction(self.actions.edit_redo)
        except Exception:
            pass
        self._build_menus()
        self._build_layout()
        self._wire_actions()

        # --- Status bar indicators (permanent)
        # Keep tiny, always-visible state like performance toggles here.
        try:
            self._cpu_status_label = QLabel("")
            self._cpu_status_label.setObjectName("cpuStatusLabel")
            self._cpu_status_label.setVisible(False)  # opt-in
            self.statusBar().addPermanentWidget(self._cpu_status_label)
        except Exception:
            self._cpu_status_label = None

        try:
            self._gpu_status_label = QLabel("GPU: OFF")
            self._gpu_status_label.setObjectName("gpuStatusLabel")
            self.statusBar().addPermanentWidget(self._gpu_status_label)
        except Exception:
            self._gpu_status_label = None

        # v0.0.20.696: Rust Engine status indicator (next to CPU/GPU)
        try:
            self._rust_status_label = QLabel("")
            self._rust_status_label.setObjectName("rustStatusLabel")
            self._rust_status_label.setToolTip(
                "🦀 Rust Audio-Engine Status\n\n"
                "R: ON  = Audio wird in Rust gerendert (schneller)\n"
                "R: OFF = Python Audio-Engine (Fallback)\n\n"
                "Umschalten: Audio → 🦀 Rust Audio-Engine\n"
                "Shortcut: Ctrl+Shift+R"
            )
            self.statusBar().addPermanentWidget(self._rust_status_label)
        except Exception:
            self._rust_status_label = None

        # v0.0.20.702: Plugin Sandbox status indicator
        try:
            from pydaw.ui.crash_indicator_widget import SandboxStatusWidget
            self._sandbox_status = SandboxStatusWidget(self)
            self._sandbox_status.setObjectName("sandboxStatusWidget")
            self.statusBar().addPermanentWidget(self._sandbox_status)
        except Exception:
            self._sandbox_status = None

        # CPU monitor object (created lazily). Must never run in audio callback.
        self._cpu_monitor = None

        # Sync view menu checks with current widget state (without emitting signals)
        try:
            self.actions.view_toggle_notation.blockSignals(True)
            self.actions.view_toggle_notation.setChecked(self.editor_tabs.is_notation_tab_visible())
        finally:
            self.actions.view_toggle_notation.blockSignals(False)

        # Sync Clip Launcher + Overlay toggles from persisted settings
        try:
            cl_visible = bool(get_value(SettingsKeys.ui_cliplauncher_visible, False))
        except Exception:
            cl_visible = False
        try:
            ov_enabled = bool(get_value(SettingsKeys.ui_cliplauncher_overlay_enabled, True))
        except Exception:
            ov_enabled = True

        # Sync GPU Waveform overlay toggle (OFF by default)
        try:
            raw = get_value(SettingsKeys.ui_gpu_waveforms_enabled, False)
            # QSettings may return strings: "true"/"false" instead of bool
            if isinstance(raw, str):
                gpu_enabled = raw.lower() in ("true", "1", "yes", "on")
            else:
                gpu_enabled = bool(raw)
        except Exception:
            gpu_enabled = False

        # Sync CPU meter toggle (OFF by default)
        try:
            cpu_enabled = bool(get_value(SettingsKeys.ui_cpu_meter_enabled, False))
        except Exception:
            cpu_enabled = False

        # Sync Rust Engine toggle (OFF by default — experimentell)
        try:
            _rust_raw = get_value(SettingsKeys.audio_rust_engine_enabled, None)
            if _rust_raw is None:
                # First run: default OFF (Rust can't render Python instruments yet)
                rust_enabled = False
            elif isinstance(_rust_raw, str):
                rust_enabled = _rust_raw.lower() in ("true", "1", "yes", "on")
            else:
                rust_enabled = bool(_rust_raw)
        except Exception:
            rust_enabled = False

        # Sync Plugin Sandbox toggle (OFF by default)
        try:
            _sbx_raw = get_value(SettingsKeys.audio_plugin_sandbox_enabled, None)
            if _sbx_raw is None:
                sandbox_enabled = False
            elif isinstance(_sbx_raw, str):
                sandbox_enabled = _sbx_raw.lower() in ("true", "1", "yes", "on")
            else:
                sandbox_enabled = bool(_sbx_raw)
        except Exception:
            sandbox_enabled = False

        # Apply without emitting signals
        try:
            self.actions.view_toggle_cliplauncher.blockSignals(True)
            self.actions.view_toggle_cliplauncher.setChecked(cl_visible)
        finally:
            self.actions.view_toggle_cliplauncher.blockSignals(False)
        try:
            self.actions.view_toggle_drop_overlay.blockSignals(True)
            self.actions.view_toggle_drop_overlay.setChecked(ov_enabled)
        finally:
            self.actions.view_toggle_drop_overlay.blockSignals(False)

        try:
            self.actions.view_toggle_gpu_waveforms.blockSignals(True)
            self.actions.view_toggle_gpu_waveforms.setChecked(bool(gpu_enabled))
        finally:
            self.actions.view_toggle_gpu_waveforms.blockSignals(False)

        try:
            self.actions.view_toggle_cpu_meter.blockSignals(True)
            self.actions.view_toggle_cpu_meter.setChecked(bool(cpu_enabled))
        finally:
            self.actions.view_toggle_cpu_meter.blockSignals(False)

        # Rust Engine toggle sync
        try:
            self.actions.audio_toggle_rust_engine.blockSignals(True)
            self.actions.audio_toggle_rust_engine.setChecked(bool(rust_enabled))
        finally:
            self.actions.audio_toggle_rust_engine.blockSignals(False)

        # Plugin Sandbox toggle sync
        try:
            self.actions.audio_toggle_plugin_sandbox.blockSignals(True)
            self.actions.audio_toggle_plugin_sandbox.setChecked(bool(sandbox_enabled))
        finally:
            self.actions.audio_toggle_plugin_sandbox.blockSignals(False)

        # Apply to UI
        try:
            self.launcher_dock.setVisible(bool(cl_visible))
        except Exception:
            pass
        try:
            # overlay toggle is only meaningful when clip-launcher is visible
            self.actions.view_toggle_drop_overlay.setEnabled(bool(cl_visible))
        except Exception:
            pass

        # Apply GPU overlay to ArrangerCanvas
        try:
            if hasattr(self, "arranger") and hasattr(self.arranger, "canvas"):
                self.arranger.canvas.set_gpu_waveforms_enabled(bool(gpu_enabled))
        except Exception:
            pass
        try:
            if getattr(self, "_gpu_status_label", None) is not None:
                self._gpu_status_label.setText("GPU: ON" if bool(gpu_enabled) else "GPU: OFF")
        except Exception:
            pass

        # Apply CPU meter (opt-in)
        try:
            self._apply_cpu_meter_state(bool(cpu_enabled), persist=False)
        except Exception:
            pass

        # Apply Rust Engine state
        try:
            self._apply_rust_engine_state(bool(rust_enabled), persist=False)
        except Exception:
            pass
        # Undo/Redo state updates
        try:
            self.services.project.undo_changed.connect(self._update_undo_redo_actions)
        except Exception:
            pass
        self._update_undo_redo_actions()

        # Python logo animation (UI-only, QTimer based)
        self._init_python_logo_animation()

        # Make sure the window is usable on different desktop sizes/DPI settings.
        self._fit_to_screen()

        # Prime parameter inspector with the current track selection.
        try:
            self._on_track_selected(self._selected_track_id())
        except Exception:
            pass

        self.statusBar().showMessage(
            "Bereit (v0.0.20.18: Vulkan Default + JACK-Client Hotfix + GPU Waveforms Opt-In)"
        )

        self.services.project.project_changed.connect(self._update_window_title)
        self.services.project.status.connect(lambda m: self.statusBar().showMessage(m, 3000))
        self.services.project.error.connect(self._show_error)
        try:
            self.services.audio_engine.error.connect(self._show_error)
            self.services.audio_engine.running_changed.connect(
                lambda r: self.statusBar().showMessage(
                    "Audio: läuft" if r else "Audio: gestoppt", 1200
                )
            )
        except Exception:
            pass
        self.services.midi.message_received.connect(lambda t: self.statusBar().showMessage(t, 1200))
        self._update_window_title(self.services.project.display_name())

        # JACK per-track monitoring routes (Input Monitoring per Track)
        try:
            self.services.project.project_updated.connect(self._update_jack_monitor_routes)
        except Exception:
            pass
        try:
            self._update_jack_monitor_routes()
        except Exception:
            pass

        # note_preview → SamplerRegistry for track-specific routing
        try:
            from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
            self._sampler_registry = get_sampler_registry()
            self.services.project.note_preview.connect(self._on_note_preview_routed)
            # v0.0.20.42: Wire sampler registry to audio engine for live MIDI→Sampler
            try:
                self.services.audio_engine._sampler_registry = self._sampler_registry
            except Exception:
                pass
        except Exception:
            self._sampler_registry = None

        # Live MIDI -> Notation: Ghost Noteheads (Input Monitoring)
        try:
            self.services.midi.live_note_on.connect(self.editor_tabs.notation.handle_live_note_on)
            self.services.midi.live_note_off.connect(self.editor_tabs.notation.handle_live_note_off)
            self.services.midi.panic.connect(self.editor_tabs.notation.handle_midi_panic)
        except Exception:
            pass

        # Live MIDI -> Sampler (sustain while key held)
        try:
            self.services.midi.live_note_on.connect(self._on_live_note_on_route_to_sampler)
            self.services.midi.live_note_off.connect(self._on_live_note_off_route_to_sampler)
        except Exception:
            pass

        # PianoRoll "Record" toggle -> MIDI record enable (write into clip)
        try:
            self.editor_tabs.pianoroll.record_toggled.connect(self.services.midi.set_record_enabled)
        except Exception:
            pass

        # Notation "Record" toggle -> same MIDI record path (v0.0.20.449)
        try:
            self.editor_tabs.notation.record_toggled.connect(self.services.midi.set_record_enabled)
        except Exception:
            pass


        # Panic also stops all sampler voices (No-Hang)
        try:
            self.services.midi.panic.connect(self._on_midi_panic)
        except Exception:
            pass

        # v0.0.20.609: Computer Keyboard MIDI (Bitwig-Style QWERTY→MIDI)
        self._computer_kb_midi = None
        try:
            from pydaw.services.computer_keyboard_midi import ComputerKeyboardMidi
            ckm = ComputerKeyboardMidi(midi_manager=self.services.midi, parent=self)
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(ckm)
            self._computer_kb_midi = ckm
            # Wire menu toggle
            if hasattr(self, '_a_computer_kb') and self._a_computer_kb is not None:
                self._a_computer_kb.toggled.connect(ckm.set_enabled)
                ckm.enabled_changed.connect(self._a_computer_kb.setChecked)
                ckm.octave_changed.connect(
                    lambda o: self.statusBar().showMessage(f"Computer Keyboard: Oktave {o}", 2000)
                )
            # v0.0.20.610: Dezentes Overlay mit Tastenbelegung
            try:
                from pydaw.ui.computer_keyboard_overlay import ComputerKeyboardOverlay
                overlay = ComputerKeyboardOverlay(parent=self)
                self._ckb_overlay = overlay
                ckm.enabled_changed.connect(overlay.set_visible_animated)
                ckm.octave_changed.connect(overlay.set_octave)
                ckm.key_pressed.connect(overlay.key_pressed)
                ckm.key_released.connect(overlay.key_released)
            except Exception:
                pass
        except Exception:
            pass

        # v0.0.20.609: Touch Keyboard (on-screen piano — toggleable dock)
        self._touch_kb_dock = None
        self._touch_kb_widget = None
        try:
            from pydaw.ui.touch_keyboard import TouchKeyboardWidget
            tkw = TouchKeyboardWidget(midi_manager=self.services.midi, parent=self)
            self._touch_kb_widget = tkw

            tkd = QDockWidget("Touch Keyboard", self)
            tkd.setWidget(tkw)
            tkd.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, tkd)
            tkd.hide()  # start hidden
            self._touch_kb_dock = tkd

            # Wire menu toggle
            if hasattr(self, '_a_touch_kb') and self._a_touch_kb is not None:
                self._a_touch_kb.toggled.connect(lambda on: tkd.setVisible(on))
                tkd.visibilityChanged.connect(lambda vis: self._a_touch_kb.setChecked(vis) if self._a_touch_kb else None)
        except Exception:
            pass

        # ClipContextService → Editor Integration (Pro-DAW-Style Slot → Editor Workflow)
        try:
            self.services.clip_context.active_slot_changed.connect(self._on_active_slot_changed)
        except Exception:
            pass

        # v0.0.20.173: Crash recovery + autosave (Bitwig-style prompt on restart)
        try:
            self._init_recovery()
        except Exception:
            pass


    # --- menus

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("Datei")
        m_file.addAction(self.actions.file_new)
        m_file.addAction(self.actions.file_open)
        m_file.addAction(self.actions.file_save)
        m_file.addAction(self.actions.file_save_as)
        m_file.addSeparator()

        # Multi-Project Tab actions (v0.0.20.77)
        self._act_new_tab = QAction("Neuer Tab", self)
        self._act_new_tab.setShortcut("Ctrl+T")
        self._act_new_tab.triggered.connect(lambda _=False: self._safe_call(self._on_project_tab_new))
        m_file.addAction(self._act_new_tab)

        self._act_open_in_tab = QAction("Öffnen in neuem Tab…", self)
        self._act_open_in_tab.setShortcut("Ctrl+Shift+O")
        self._act_open_in_tab.triggered.connect(lambda _=False: self._safe_call(self._on_project_tab_open))
        m_file.addAction(self._act_open_in_tab)

        self._act_close_tab = QAction("Tab schließen", self)
        self._act_close_tab.setShortcut("Ctrl+W")
        self._act_close_tab.triggered.connect(
            lambda: self._safe_call(
                self._on_project_tab_close,
                getattr(self, '_project_tab_service', None) and self._project_tab_service.active_index or 0
            )
        )
        m_file.addAction(self._act_close_tab)
        m_file.addSeparator()

        # Tab navigation shortcuts (v0.0.20.78)
        self._shortcut_next_tab = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._shortcut_next_tab.activated.connect(lambda: self._safe_call(self._on_tab_next))
        # Metadata for Hilfe → Arbeitsmappe (Shortcuts-Liste)
        try:
            self._shortcut_next_tab.setObjectName("shortcut_next_tab")
            self._shortcut_next_tab.setProperty("pydaw_desc", "Nächster Projekt-Tab")
        except Exception:
            pass
        self._shortcut_prev_tab = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._shortcut_prev_tab.activated.connect(lambda: self._safe_call(self._on_tab_prev))
        try:
            self._shortcut_prev_tab.setObjectName("shortcut_prev_tab")
            self._shortcut_prev_tab.setProperty("pydaw_desc", "Vorheriger Projekt-Tab")
        except Exception:
            pass

        m_file.addAction(self.actions.file_import_audio)
        m_file.addAction(self.actions.file_import_midi)
        m_file.addAction(self.actions.file_import_dawproject)  # v0.0.20.88
        m_file.addAction(self.actions.file_export_dawproject)  # v0.0.20.359
        m_file.addSeparator()
        m_file.addAction(self.actions.file_export)
        m_file.addAction(self.actions.file_export_midi_clip)  # FIXED v0.0.19.7.15
        m_file.addAction(self.actions.file_export_midi_track)  # FIXED v0.0.19.7.15
        m_file.addSeparator()
        m_file.addAction(self.actions.file_exit)

        m_edit = mb.addMenu("Bearbeiten")
        m_edit.addAction(self.actions.edit_undo)
        m_edit.addAction(self.actions.edit_redo)
        m_edit.addSeparator()
        m_edit.addAction(self.actions.edit_cut)
        m_edit.addAction(self.actions.edit_copy)
        m_edit.addAction(self.actions.edit_paste)
        m_edit.addSeparator()
        m_edit.addAction(self.actions.edit_select_all)

        m_view = mb.addMenu("Ansicht")
        m_view.addAction(self.actions.view_dummy)
        m_view.addSeparator()
        m_view.addAction(self.actions.view_toggle_pianoroll)
        m_view.addAction(self.actions.view_toggle_notation)
        m_view.addAction(self.actions.view_toggle_cliplauncher)
        m_view.addAction(self.actions.view_toggle_drop_overlay)
        m_view.addAction(self.actions.view_toggle_gpu_waveforms)
        m_view.addAction(self.actions.view_toggle_cpu_meter)
        m_view.addAction(self.actions.view_toggle_automation)

        # Screen Layout submenu (Bitwig-Style multi-monitor)
        m_layout = m_view.addMenu("Bildschirm-Layout")
        m_layout.setObjectName("screenLayoutMenu")
        # Will be populated after panels are created in _build_layout
        self._screen_layout_menu = m_layout

        m_proj = mb.addMenu("Projekt")
        m_proj.addAction(self.actions.project_add_audio_track)
        m_proj.addAction(self.actions.project_add_instrument_track)
        m_proj.addAction(self.actions.project_add_bus_track)
        m_proj.addSeparator()
        m_proj.addAction(self.actions.project_add_placeholder_clip)
        m_proj.addAction(self.actions.project_remove_selected_track)
        m_proj.addSeparator()
        m_proj.addAction(self.actions.project_time_signature)
        m_proj.addAction(self.actions.project_settings)
        m_proj.addSeparator()
        m_proj.addAction(self.actions.project_save_snapshot)
        m_proj.addAction(self.actions.project_load_snapshot)
        m_proj.addSeparator()
        m_proj.addAction(self.actions.project_load_sf2)

        # Project Compare (Diff between open project tabs) — v0.0.20.85
        self._act_compare_tabs = QAction("Projekt vergleichen…", self)
        self._act_compare_tabs.setShortcut("Ctrl+Alt+D")
        self._act_compare_tabs.triggered.connect(lambda _=False: self._safe_call(self._show_project_compare_dialog))
        m_proj.addSeparator()
        m_proj.addAction(self._act_compare_tabs)

        # AI Orchestrator (multi-track ensemble generator) — v0.0.20.195
        self._act_ai_orchestrator = QAction("AI Orchestrator…", self)
        try:
            self._act_ai_orchestrator.setShortcut("Ctrl+Alt+O")
        except Exception:
            pass
        self._act_ai_orchestrator.triggered.connect(lambda _=False: self._safe_call(self._show_ai_orchestrator_dialog))
        m_proj.addAction(self._act_ai_orchestrator)

        m_audio = mb.addMenu("Audio")
        m_audio.addAction(self.actions.audio_settings)
        m_audio.addSeparator()
        m_audio.addAction(self.actions.audio_prerender_midi)
        m_audio.addAction(self.actions.audio_prerender_selected_clip)
        m_audio.addAction(self.actions.audio_prerender_selected_track)
        m_audio.addSeparator()
        m_audio.addAction(self.actions.midi_settings)
        m_audio.addAction(self.actions.midi_mapping)
        m_audio.addAction(self.actions.midi_panic)
        m_audio.addSeparator()
        # v0.0.20.609: Computer Keyboard MIDI (Bitwig-Style)
        self._a_computer_kb = None
        try:
            a_ckb = QAction("Computer Keyboard MIDI (,/. = Oktave)", self)
            a_ckb.setCheckable(True)
            a_ckb.setShortcut(QKeySequence("Ctrl+Shift+K"))
            a_ckb.setToolTip("QWERTY-Tastatur als MIDI-Controller (Bitwig-Style)")
            m_audio.addAction(a_ckb)
            self._a_computer_kb = a_ckb
        except Exception:
            pass
        # v0.0.20.609: Touch Keyboard (on-screen piano)
        self._a_touch_kb = None
        try:
            a_tkb = QAction("Touch Keyboard (On-Screen Piano)", self)
            a_tkb.setCheckable(True)
            a_tkb.setShortcut(QKeySequence("Ctrl+Shift+T"))
            a_tkb.setToolTip("On-Screen Klaviatur — Mausklick erzeugt MIDI-Noten")
            m_audio.addAction(a_tkb)
            self._a_touch_kb = a_tkb
        except Exception:
            pass

        # v0.0.20.665: Engine Migration Dialog (Rust ↔ Python)
        try:
            m_audio.addSeparator()
            # v0.0.20.696: Rust Engine Toggle (checkable)
            m_audio.addAction(self.actions.audio_toggle_rust_engine)

            # v0.0.20.704: Plugin Sandbox Submenu (P6C)
            m_sandbox = m_audio.addMenu("🛡️ Plugin Sandbox")
            m_sandbox.addAction(self.actions.audio_toggle_plugin_sandbox)
            m_sandbox.addSeparator()

            a_sandbox_restart_all = QAction("🔄 Alle Plugins neu starten", self)
            a_sandbox_restart_all.setToolTip("Alle Sandbox-Worker killen und neu starten")
            a_sandbox_restart_all.triggered.connect(self._on_sandbox_restart_all)
            m_sandbox.addAction(a_sandbox_restart_all)
            self._a_sandbox_restart_all = a_sandbox_restart_all

            a_sandbox_status = QAction("Sandbox-Status…", self)
            a_sandbox_status.setToolTip("Übersicht aller Plugin-Worker und deren Zustand")
            a_sandbox_status.triggered.connect(self._on_sandbox_status_dialog)
            m_sandbox.addAction(a_sandbox_status)

            m_sandbox.addSeparator()

            a_crash_log = QAction("🔥 Plugin Crash Log…", self)
            a_crash_log.setToolTip("Zeigt alle Plugin-Abstürze und Fehlermeldungen")
            a_crash_log.triggered.connect(self._on_crash_log_dialog)
            m_sandbox.addAction(a_crash_log)

            # v0.0.20.725: Plugin Blacklist Dialog
            a_blacklist = QAction("💀 Plugin-Blacklist…", self)
            a_blacklist.setToolTip(
                "Zeigt alle geblacklisteten Plugins (Crash-Isolierung) "
                "und erlaubt manuelles Entsperren"
            )
            a_blacklist.triggered.connect(self._on_plugin_blacklist_dialog)
            m_sandbox.addAction(a_blacklist)

            a_migration = QAction("Engine Migration (Rust ↔ Python)…", self)
            a_migration.setToolTip("Subsysteme zwischen Python- und Rust-Engine umschalten, Benchmark starten")
            a_migration.triggered.connect(self._on_engine_migration_dialog)
            m_audio.addAction(a_migration)
        except Exception:
            pass

        m_help = mb.addMenu("Hilfe")
        m_help.addAction(self.actions.help_workbook)
        m_help.addAction(self.actions.help_toggle_python_animation)

        # v0.0.20.651: the three tech badges now live together in the
        # bottom-right status strip. Keep the legacy menu overlay disabled so
        # the top area stays calm and music-focused.
        self._menu_rust_anchor_action = m_help.menuAction()
        self._teardown_menu_rust_badge()


    def _init_menu_rust_badge(self, menu_bar=None) -> None:
        """Legacy no-op.

        The Rust badge was moved into the bottom status signature in
        v0.0.20.651. We keep this method so older call-sites remain harmless.
        """
        self._teardown_menu_rust_badge()

    def _teardown_menu_rust_badge(self) -> None:
        """Hide/remove the old menu-row Rust badge if it exists."""
        try:
            badge = getattr(self, "_menu_rust_badge", None)
            if badge is not None:
                try:
                    badge.hide()
                except Exception:
                    pass
                try:
                    badge.setParent(None)
                except Exception:
                    pass
            self._menu_rust_badge = None
        except Exception:
            traceback.print_exc()

    def _reposition_menu_rust_badge(self) -> None:
        """Legacy no-op after moving the badge to the status strip."""
        self._teardown_menu_rust_badge()

    def _build_status_tech_signature(self) -> None:
        """Assemble a compact Qt | Python | Rust signature in the status bar.

        Design intent:
        - logos live near CPU/GPU/engine state instead of occupying toolbar space
        - existing Python animation remains intact by reusing the same button
        - purely visual; no transport/audio behaviour changes
        """
        try:
            existing = getattr(self, "_tech_signature_widget", None)
            if existing is not None:
                self._sync_status_tech_signature_sizes()
                return

            self._teardown_menu_rust_badge()

            sb = self.statusBar()
            if sb is None:
                return

            box = QWidget()
            box.setObjectName("chronoTechSignature")
            row = QHBoxLayout(box)
            row.setContentsMargins(6, 0, 6, 0)
            row.setSpacing(6)

            self.btn_qt_logo = QtLogoButton()
            self.btn_qt_logo.setObjectName("statusQtLogoButton")
            self.btn_qt_logo.setToolTip("Qt UI Layer")
            self.btn_qt_logo.clicked.connect(lambda _=False: self._set_status("Qt UI Layer", 2000))

            py_btn = None
            tp = getattr(self, "toolbar_panel", None)
            if tp is not None:
                py_btn = getattr(tp, "btn_python", None)
            if py_btn is not None:
                try:
                    lay = tp.layout()
                    if lay is not None:
                        lay.removeWidget(py_btn)
                except Exception:
                    pass
                try:
                    py_btn.setParent(box)
                except Exception:
                    pass
                py_btn.setObjectName("statusPythonLogoButton")
                py_btn.setToolTip("Python App Layer")
                try:
                    py_btn.clicked.disconnect()
                except Exception:
                    pass
                py_btn.clicked.connect(lambda _=False: self._set_status("Python App Layer", 2000))

            self.btn_rust_logo = RustLogoButton()
            self.btn_rust_logo.setObjectName("statusRustLogoButton")
            self.btn_rust_logo.setToolTip("Rust Core")
            self.btn_rust_logo.clicked.connect(lambda _=False: self._set_status("Rust Core", 2000))

            row.addWidget(self.btn_qt_logo)
            if py_btn is not None:
                row.addWidget(py_btn)
            row.addWidget(self.btn_rust_logo)

            self._tech_signature_widget = box
            try:
                sb.addPermanentWidget(box)
            except Exception:
                sb.addWidget(box)

            self._sync_status_tech_signature_sizes()
            QTimer.singleShot(0, self._sync_status_tech_signature_sizes)
        except Exception:
            traceback.print_exc()

    def _sync_status_tech_signature_sizes(self) -> None:
        """Keep the status-strip logos consistent and at the approved Rust size."""
        try:
            sb = self.statusBar()
            base = 30
            if sb is not None:
                base = max(28, min(30, int(sb.height()) - 4))
            for name in ("btn_qt_logo", "btn_rust_logo"):
                btn = getattr(self, name, None)
                if btn is not None:
                    btn.setFixedSize(base, base)
            py_btn = None
            tp = getattr(self, "toolbar_panel", None)
            if tp is not None:
                py_btn = getattr(tp, "btn_python", None)
            if py_btn is not None:
                py_btn.setFixedSize(base, base)
        except Exception:
            traceback.print_exc()

    def _show_ai_orchestrator_dialog(self) -> None:
        """Open the multi-track AI Orchestrator tool."""
        try:
            from pydaw.ui.orchestrator_dialog import OrchestratorDialog
            dlg = OrchestratorDialog(self.services, parent=self)
            dlg.exec()
        except Exception:
            traceback.print_exc()
            try:
                QMessageBox.warning(self, "AI Orchestrator", "Konnte den AI Orchestrator nicht öffnen. Details siehe Terminal/Log.")
            except Exception:
                pass


    # --- layout


    # --- layout

    def _build_layout(self) -> None:
        """Pro-DAW-like main layout (Header + Left Tool Strip + Right Browser + Bottom Editor).

        Safety-first: keeps all existing logic/methods. Only rearranges widgets.
        """
        # ---- Multi-Project Tab Bar (Bitwig-Style: tabs at the top)
        try:
            self._project_tab_service = self.services.project_tabs
            self.project_tab_bar = ProjectTabBar(self._project_tab_service, parent=self)
            self.project_tab_bar.setObjectName("projectTabBarWidget")

            # Adopt the current project as Tab 0
            self._project_tab_service.adopt_existing_project(
                self.services.project.ctx,
                self.services.project.undo_stack,
            )

            # Wire tab bar signals
            self.project_tab_bar.request_switch_tab.connect(
                lambda idx: self._safe_call(self._on_project_tab_switch, idx)
            )
            self.project_tab_bar.request_new_project.connect(
                lambda: self._safe_call(self._on_project_tab_new)
            )
            self.project_tab_bar.request_open_project.connect(
                lambda: self._safe_call(self._on_project_tab_open)
            )
            self.project_tab_bar.request_close_tab.connect(
                lambda idx: self._safe_call(self._on_project_tab_close, idx)
            )
            self.project_tab_bar.request_save_tab.connect(
                lambda idx: self._safe_call(self._on_project_tab_save, idx)
            )
            self.project_tab_bar.request_save_tab_as.connect(
                lambda idx: self._safe_call(self._on_project_tab_save_as, idx)
            )
            self.project_tab_bar.request_rename_tab.connect(
                lambda idx, name: self._safe_call(self._project_tab_service.rename_tab, idx, name)
            )
            self.project_tab_bar.request_rust_badge_clicked.connect(
                lambda: self.statusBar().showMessage("Rust Core Badge", 2000)
            )

            # Add as top toolbar
            tab_toolbar = self.addToolBar("Projects")
            tab_toolbar.setObjectName("projectTabToolBar")
            tab_toolbar.setMovable(False)
            tab_toolbar.setFloatable(False)
            try:
                tab_toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
            except Exception:
                pass
            tab_toolbar.addWidget(self.project_tab_bar)
            self._project_tab_toolbar = tab_toolbar

            # v0.0.20.645: Keep project tabs on their own row so transport +
            # tools stay readable even on smaller widths. Without an explicit
            # break, Qt may squeeze all top toolbars into a single line.
            try:
                self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
            except Exception:
                pass
        except Exception:
            traceback.print_exc()
            self._project_tab_service = None
            self.project_tab_bar = None

        # ---- Top Menus + Toolbars (Pro-DAW hybrid)
        # We keep the classic QMenuBar (Datei/Bearbeiten/Ansicht/Projekt/Audio/Hilfe)
        # and add two compact toolbars below it: Transport + Tools/Grid.
        proj = self.services.project.ctx.project

        self.transport = TransportPanel()
        self.transport.setObjectName("transportPanel")

        # initialize transport UI from project
        try:
            self.transport.bpm.setValue(int(round(float(getattr(proj, "bpm", 120.0) or 120.0))))
        except Exception:
            pass
        ts = getattr(proj, "time_signature", "4/4") or "4/4"
        try:
            self.transport.set_time_signature(str(ts))
        except Exception:
            pass

        snap = getattr(proj, "snap_division", "1/16") or "1/16"

        # Transport row (like your reference screenshot)
        self.transport_toolbar = self.addToolBar("Transport")
        self.transport_toolbar.setObjectName("transportToolBar")
        self.transport_toolbar.setMovable(False)
        self.transport_toolbar.setFloatable(False)
        try:
            self.transport_toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        except Exception:
            pass
        self.transport_toolbar.addWidget(self.transport)

        # Tools/Grid row
        self.toolbar_panel = ToolBarPanel()
        self.toolbar_panel.setObjectName("toolBarPanel")
        try:
            # ensure snap exists in the combo
            items = [self.toolbar_panel.cmb_grid.itemText(i) for i in range(self.toolbar_panel.cmb_grid.count())]
            if str(snap) not in items:
                snap = "1/16"
            self.toolbar_panel.cmb_grid.setCurrentText(str(snap))
        except Exception:
            pass

        self.tools_toolbar = self.addToolBar("Tools")
        self.tools_toolbar.setObjectName("toolsToolBar")
        self.tools_toolbar.setMovable(False)
        self.tools_toolbar.setFloatable(False)
        try:
            self.tools_toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        except Exception:
            pass
        self.tools_toolbar.addWidget(self.toolbar_panel)

        # ---- Central area: Left tool strip + Arranger
        center = QWidget()
        center.setObjectName("chronoCenter")
        cl = QHBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Left tool strip (Pro-DAW-Style)
        tool_strip = QWidget()
        tool_strip.setObjectName("chronoToolStrip")
        tl = QVBoxLayout(tool_strip)
        tl.setContentsMargins(6, 6, 6, 6)
        tl.setSpacing(6)

        def _mk_tool(txt: str, tool_key: str, tip: str):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.setObjectName("chronoToolButton")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoRaise(True)
            b.setFixedSize(34, 34)
            b.clicked.connect(lambda _=False: self._on_tool_changed_from_toolbar(tool_key))
            return b

        tl.addWidget(_mk_tool("↖", "select", "Zeiger (Select)"))
        tl.addWidget(_mk_tool("✎", "draw", "Stift (Draw)"))
        tl.addWidget(_mk_tool("⌫", "erase", "Radiergummi (Erase)"))
        tl.addWidget(_mk_tool("✂", "knife", "Messer (Knife)"))
        tl.addStretch(1)
        tool_strip.setFixedWidth(48)

        self.arranger = ArrangerView(self.services.project)
        # Inject transport into arranger canvas for DAW-consistent loop behavior
        try:
            self.arranger.canvas.set_transport(self.services.transport)
            try:
                # v0.0.20.86: wire tab_service through ArrangerView → canvas + TrackList
                self.arranger.set_tab_service(getattr(self, '_project_tab_service', None))
            except Exception:
                pass
            try:
                # v0.0.20.608: wire MidiManager for MIDI input routing dropdown
                self.arranger.set_midi_manager(getattr(self.services, 'midi', None))
            except Exception:
                pass
            try:
                self.arranger.set_transport(self.services.transport)
            except Exception:
                pass
        except Exception:
            pass

        # Prewarm: let the service know which arranger range is currently visible
        try:
            self.arranger.view_range_changed.connect(self.services.prewarm.set_active_range)
            # seed initial range
            a, b = self.arranger.visible_range_beats()
            self.services.prewarm.set_active_range(a, b)
        except Exception:
            pass

        # automation panel lives inside arranger view
        self.automation = self.arranger.automation
        # v0.0.20.89: Wire AutomationManager for enhanced Bezier automation editor
        try:
            self.arranger.set_automation_manager(self.services.automation_manager)
        except Exception:
            pass
        try:
            self.arranger.set_snap_division(str(snap))
        except Exception:
            pass
        self.arranger.set_automation_visible(False)

        # Arranger wiring
        # NOTE: PyQt6 can abort the process on uncaught exceptions in slots.
        # Always use _safe_call wrappers for user-triggered interactions.
        self.arranger.clip_activated.connect(lambda cid: self._safe_call(self._on_clip_activated, cid))
        self.arranger.clip_selected.connect(lambda cid: self._safe_call(self._on_clip_selected, cid))
        self.arranger.request_rename_clip.connect(lambda cid: self._safe_call(self._rename_clip_dialog, cid))
        self.arranger.request_duplicate_clip.connect(lambda cid: self._safe_call(self.services.project.duplicate_clip, cid))
        self.arranger.request_delete_clip.connect(lambda cid: self._safe_call(self.services.project.delete_clip, cid))
        self.arranger.status_message.connect(lambda msg: self._safe_call(self._set_status, msg))

        # loop edits in arranger drive transport
        self.arranger.canvas.loop_region_committed.connect(
            lambda enabled, start, end: self._safe_call(self._on_arranger_loop_committed, enabled, start, end)
        )
        # v0.0.20.637: Punch region edits in arranger drive transport
        self.arranger.canvas.punch_region_committed.connect(
            lambda enabled, in_b, out_b: self._safe_call(self._on_arranger_punch_committed, enabled, in_b, out_b)
        )
        self.arranger.canvas.request_import_audio.connect(lambda pos: self._safe_call(self._import_audio_at_position, pos))
        self.arranger.canvas.request_add_track.connect(lambda kind: self._safe_call(self._add_track_from_context_menu, kind))
        self.arranger.canvas.request_smartdrop_new_instrument_track.connect(
            lambda payload: self._safe_call(self._on_arranger_smartdrop_new_instrument_track, payload)
        )
        self.arranger.canvas.request_smartdrop_instrument_to_track.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_instrument_to_track, track_id, payload)
        )
        self.arranger.canvas.request_smartdrop_fx_to_track.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_fx_to_track, track_id, payload)
        )
        self.arranger.canvas.request_smartdrop_instrument_morph_guard.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_instrument_morph_guard, track_id, payload)
        )
        self.arranger.tracks.request_smartdrop_instrument_to_track.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_instrument_to_track, track_id, payload)
        )
        self.arranger.tracks.request_smartdrop_fx_to_track.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_fx_to_track, track_id, payload)
        )
        self.arranger.tracks.request_smartdrop_instrument_morph_guard.connect(
            lambda track_id, payload: self._safe_call(self._on_arranger_smartdrop_instrument_morph_guard, track_id, payload)
        )

        # Synchronize automation editor time range with Arranger scroll/zoom
        self.arranger.view_range_changed.connect(self.automation.set_view_range)
        # v0.0.20.89: Also sync enhanced automation editor
        try:
            eap = getattr(self.arranger, '_enhanced_automation', None)
            if eap is not None:
                self.arranger.view_range_changed.connect(eap.set_view_range)
        except Exception:
            pass
        try:
            s, e = self.arranger.visible_range_beats()
            self.automation.set_view_range(s, e)
        except Exception:
            pass

        # Track selection drives parameter inspector
        self.arranger.tracks.selected_track_changed.connect(lambda tid: self._safe_call(self._on_track_selected, tid))
        # Phase 2: Track-Header ▾ requests (Routing/Arm/Monitor/Add Device) — UI-only, additiv
        try:
            self.arranger.tracks.request_open_browser_tab.connect(
                lambda tid, tab: self._safe_call(self._on_track_header_open_browser, tid, tab)
            )
            self.arranger.tracks.request_show_device_panel.connect(
                lambda tid: self._safe_call(self._on_track_header_show_device, tid)
            )
            # Phase 3: 1-click device insert directly from Track-Header ▾
            self.arranger.tracks.request_add_device.connect(
                lambda tid, kind, pid: self._safe_call(self._on_track_header_add_device, tid, kind, pid)
            )
        except Exception:
            pass

        cl.addWidget(tool_strip, 0)
        cl.addWidget(self.arranger, 1)
        self.setCentralWidget(center)

        # ---- Right Browser Dock (toggle with 'B')
        from .device_browser import DeviceBrowser
        self.library = DeviceBrowser(
                on_add_instrument=lambda pid: self._safe_call(self._add_instrument_to_device, pid),
                get_add_scope=lambda kind="": self._safe_call(self._browser_add_scope_info, kind) or ("Ziel: Spur", "Aktive Spur konnte nicht ermittelt werden."),
                # NOTE: callbacks accept optional (name, params) so external plugins can be inserted
                # as *placeholders* without touching hosting/audio engine.
                on_add_note_fx=lambda pid, name="", params=None: self._safe_call(
                    self.device_panel.add_note_fx_to_track, self._selected_track_id(), pid, name=name, params=params
                ),
                on_add_audio_fx=lambda pid, name="", params=None: self._safe_call(
                    self.device_panel.add_audio_fx_to_track, self._selected_track_id(), pid, name=name, params=params
                ),
                audio_engine=self.services.audio_engine,
                transport=self.services.transport,
                project_service=self.services.project,
            )

        # Browser Sample Drag → Arranger Overlay Clip-Launcher (v0.0.19.7.39)
        try:
            sb = getattr(self.library, 'samples_tab', None)
            if sb is not None:
                sb.audio_drag_started.connect(lambda lbl: self._safe_call(self._on_sample_drag_started, lbl))
                sb.audio_drag_ended.connect(lambda: self._safe_call(self._on_sample_drag_ended))
        except Exception:
            pass

        # Overlay drop → Import AudioClip + assign to Launcher slot (v0.0.19.7.39)
        try:
            self.arranger.request_import_audio_file.connect(
                lambda file_path, track_id, start_beats, slot_key: self._safe_call(
                    self._import_audio_file_to_slot, file_path, track_id, start_beats, slot_key
                )
            )
        except Exception:
            pass
        self.track_params = TrackParametersPanel(project=self.services.project)

        right_tabs = QTabWidget()
        right_tabs.addTab(self.library, "Browser")
        right_tabs.addTab(self.track_params, "Parameter")
        # Phase 2/3: keep a handle so Track-Header ▾ can switch Browser tabs safely
        self._right_tabs = right_tabs

        # Project Browser (Ableton-style: peek into closed projects)
        try:
            self._project_browser = ProjectBrowserWidget(
                tab_service=self._project_tab_service,
                parent=right_tabs,
            )
            right_tabs.addTab(self._project_browser, "Projekte")
            # Wire signals
            self._project_browser.request_open_in_tab.connect(
                lambda path_str: self._safe_call(self._on_project_browser_open, path_str)
            )
            self._project_browser.request_import_tracks.connect(
                lambda path_str, tids: self._safe_call(self._on_project_browser_import, path_str, tids)
            )
            self._project_browser.status_message.connect(
                lambda msg: self._set_status(msg)
            )
        except Exception:
            traceback.print_exc()
            self._project_browser = None
        right_tabs.setObjectName("chronoBrowserTabs")

        # Allow the right dock to be resized "almost closed".
        # We must neutralize minimum-size constraints coming from the tab bar and
        # internal widgets; otherwise the dock separator stops too early.
        try:
            from PyQt6.QtWidgets import QSizePolicy
            right_tabs.setMinimumWidth(0)
            right_tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            tb = right_tabs.tabBar()
            tb.setUsesScrollButtons(True)
            tb.setExpanding(False)
            try:
                tb.setElideMode(Qt.TextElideMode.ElideRight)
            except Exception:
                pass
            tb.setMinimumWidth(0)
            tb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self.browser_dock = QDockWidget("Browser", self)
        self.browser_dock.setObjectName("chronoBrowserDock")
        self.browser_dock.setWidget(right_tabs)
        self.browser_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        # Allow shrinking the Browser panel almost closed (user requested).
        # Any minimum constraints here will stop the dock separator early.
        try:
            from PyQt6.QtWidgets import QSizePolicy
            right_tabs.setMinimumSize(0, 0)
            self.library.setMinimumSize(0, 0)
            self.track_params.setMinimumSize(0, 0)
            self.browser_dock.setMinimumSize(0, 0)
            self.browser_dock.setMinimumWidth(0)
            self.browser_dock.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.browser_dock)

        self._shortcut_toggle_browser = QShortcut(QKeySequence("B"), self)
        self._shortcut_toggle_browser.activated.connect(lambda: self._safe_call(self._toggle_browser))

        # v0.0.20.98: Global Space shortcut for Play/Pause (DAW standard!)
        self._shortcut_space_play = QShortcut(QKeySequence("Space"), self)
        self._shortcut_space_play.activated.connect(lambda: self._safe_call(self._on_play_clicked))

        # Metadata for Hilfe → Arbeitsmappe (Shortcuts-Liste)
        try:
            self._shortcut_toggle_browser.setObjectName("shortcut_toggle_browser")
            self._shortcut_toggle_browser.setProperty("pydaw_desc", "Browser Panel ein/aus")
        except Exception:
            pass

        # ---- Bottom Editor Dock (Piano Roll / Notation)
        self.editor_tabs = EditorTabs(
            self.services.project,
            transport=self.services.transport,
            editor_timeline=getattr(self.services, 'editor_timeline', None),  # v0.0.20.613
            status_cb=lambda t, ms=1500: self.statusBar().showMessage(str(t), int(ms)),
            enable_notation_tab=bool(get_value(SettingsKeys.ui_enable_notation_tab, False)),
        )
        self.editor_dock = QDockWidget("Editor", self)
        self.editor_dock.setObjectName("chronoEditorDock")
        self.editor_dock.setWidget(self.editor_tabs)

        # Backwards-compatibility: older code expects separate docks.
        # We now host editors in a single dock with tabs.
        self.pianoroll_dock = self.editor_dock
        self.notation_dock = self.editor_dock
        self.editor_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.editor_dock.setMinimumHeight(150)  # v0.0.20.618: prevent full collapse
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.editor_dock)

        # Mixer as tab next to editor (Pro-DAW-like)
        _rt = getattr(self.services.audio_engine, "rt_params", None)
        _hb = getattr(self.services.audio_engine, "_hybrid_bridge", None)
        if _hb is None:
            _hb = getattr(self.services.audio_engine, "hybrid_bridge", None)
        self.mixer = MixerPanel(self.services.project, self.services.audio_engine, rt_params=_rt, hybrid_bridge=_hb)
        # v0.0.20.408: Wire audio engine to MIDI mapping for RT param access
        try:
            self.services.midi_mapping.set_audio_engine(self.services.audio_engine)
        except Exception:
            pass
        self.mixer_dock = QDockWidget("Mixer", self)
        self.mixer_dock.setObjectName("chronoMixerDock")
        self.mixer_dock.setWidget(self.mixer)
        self.mixer_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.mixer_dock)
        self.tabifyDockWidget(self.editor_dock, self.mixer_dock)
        self.mixer_dock.hide()  # start like Pro-DAW: editor visible

        # ---- Bottom Device Dock (Pro-DAW-like) – placeholder
        self.device_panel = DevicePanel(self.services)
        self.device_dock = QDockWidget("Device", self)
        self.device_dock.setObjectName("chronoDeviceDock")
        self.device_dock.setWidget(self.device_panel)
        self.device_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.device_dock.setMinimumHeight(0)  # v0.0.20.597: allow full collapse
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.device_dock)
        try:
            self.tabifyDockWidget(self.editor_dock, self.device_dock)
        except Exception:
            pass
        self.device_dock.hide()  # start hidden; becomes visible in "Device" view

        # ---- Bottom view tabs (Pro-Style): ARRANGE / MIX / EDIT
        # These tabs control which bottom dock is visible and give the Arranger full height in ARRANGE mode.
        self._build_bottom_view_tabs(initial_snap=str(snap))
        self._set_view_mode("arrange", force=True)


        # Keep editors in sync with the currently active clip.
        try:
            self.services.project.active_clip_changed.connect(self.editor_tabs.set_clip)
        except Exception:
            pass

        # Clip Launcher Dock (optional) – tabify with Browser
        self.launcher_panel = ClipLauncherPanel(
            self.services.project,
            self.services.launcher,
            self.services.clip_context  # NEU: ClipContextService
        )
        self.launcher_panel.clip_activated.connect(lambda cid: self._safe_call(self._on_clip_activated, cid))
        self.launcher_panel.clip_edit_requested.connect(lambda cid: self._safe_call(self._on_clip_edit_requested, cid))

        self.launcher_dock = QDockWidget("Clip Launcher", self)
        self.launcher_dock.setWidget(self.launcher_panel)
        self.launcher_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        # Important: the Browser dock is tabified with this launcher dock.
        # Any minimum width here will limit how far the right dock area can be collapsed.
        try:
            from PyQt6.QtWidgets import QSizePolicy
            self.launcher_panel.setMinimumSize(0, 0)
            self.launcher_dock.setMinimumSize(0, 0)
            self.launcher_dock.setMinimumWidth(0)
            self.launcher_dock.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.launcher_dock)
        try:
            self.tabifyDockWidget(self.browser_dock, self.launcher_dock)
        except Exception:
            pass
        self.launcher_dock.hide()

        # TransportService -> UI
        self.services.transport.playhead_changed.connect(lambda beat: self._safe_call(self._update_playhead, beat))
        self.services.transport.loop_changed.connect(
            lambda enabled, start, end: self._safe_call(self._on_transport_loop_changed, enabled, start, end)
        )
        self.services.transport.time_signature_changed.connect(lambda ts: self._safe_call(self._on_transport_ts_changed, ts))
        self.services.transport.metronome_tick.connect(lambda: self._safe_call(self._on_metronome_tick))

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self.services.transport.punch_changed.connect(
            lambda enabled, in_b, out_b: self._safe_call(self._on_transport_punch_changed, enabled, in_b, out_b)
        )
        self.services.transport.punch_triggered.connect(
            lambda boundary: self._safe_call(self._on_punch_triggered, boundary)
        )

        # v0.0.20.639: Loop-Recording / Take-Lanes (AP2 Phase 2D)
        self.services.transport.loop_boundary_reached.connect(
            lambda: self._safe_call(self._on_loop_boundary_reached)
        )

        # v0.0.20.639: Wire TakeService into arranger canvas
        try:
            self.arranger.canvas._take_service = getattr(self.services, 'take', None)
        except Exception:
            pass

        # Initialize TS into transport service
        try:
            self.services.transport.set_time_signature(str(ts))
        except Exception:
            pass

        # loop state into UI + arranger
        self._on_transport_loop_changed(
            self.services.transport.loop_enabled,
            self.services.transport.loop_start,
            self.services.transport.loop_end,
        )
        # v0.0.20.637: punch state into UI + arranger
        self._on_transport_punch_changed(
            self.services.transport.punch_enabled,
            self.services.transport.punch_in_beat,
            self.services.transport.punch_out_beat,
        )
        self._update_playhead(self.services.transport.current_beat)

        # Apply Pro-DAW-like dark theme
        self._apply_chrono_theme()

        # --- Screen Layout Manager (Bitwig-Style multi-monitor, v0.0.20.444) ---
        try:
            self._init_screen_layout_manager()
        except Exception:
            traceback.print_exc()
            self._screen_layout_mgr = None



    def _build_bottom_view_tabs(self, initial_snap: str = "1/16") -> None:
        """Create bottom navigation tabs wie Pro-DAW: Arranger / Mixer / Editor / Device.

        We keep this lightweight: it only toggles which bottom docks are visible.
        """
        sb = self.statusBar()
        try:
            sb.setSizeGripEnabled(False)
        except Exception:
            pass

        nav = QWidget()
        nav.setObjectName("chronoBottomNav")
        hl = QHBoxLayout(nav)
        # v0.0.20.651: the tech badges moved to the right status strip, so the
        # left navigation can breathe with a small but calm inset.
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(0)

        def mk_tab(text: str) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setObjectName("chronoViewTab")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        # View tabs (Pro-Style) – labels are user-facing.
        self.btn_view_arrange = mk_tab("Arranger")
        self.btn_view_mix = mk_tab("Mixer")
        self.btn_view_edit = mk_tab("Editor")
        self.btn_view_device = mk_tab("Device")

        self.btn_view_arrange.clicked.connect(lambda _=False: self._set_view_mode("arrange"))
        self.btn_view_mix.clicked.connect(lambda _=False: self._set_view_mode("mix"))
        self.btn_view_edit.clicked.connect(lambda _=False: self._set_view_mode("edit"))
        self.btn_view_device.clicked.connect(lambda _=False: self._set_view_mode("device"))

        hl.addWidget(self.btn_view_arrange)
        hl.addWidget(self.btn_view_mix)
        hl.addWidget(self.btn_view_edit)
        hl.addWidget(self.btn_view_device)

        # Left aligned nav
        try:
            sb.addWidget(nav, 1)
        except Exception:
            sb.addWidget(nav)

        # Snap indicator on the right
        self.lbl_snap = QLabel(str(initial_snap))
        self.lbl_snap.setObjectName("chronoSnapLabel")
        try:
            sb.addPermanentWidget(self.lbl_snap)
        except Exception:
            sb.addWidget(self.lbl_snap)

        # v0.0.20.651: group Qt/Python/Rust together as a compact tech signature
        # near the performance indicators, instead of scattering logos over the UI.
        self._build_status_tech_signature()

    def _set_view_mode(self, mode: str, force: bool = False) -> None:
        mode = (mode or "").strip().lower()
        if not force and getattr(self, "_view_mode", None) == mode:
            return
        self._view_mode = mode

        # Default: show arranger always
        try:
            self.arranger.setVisible(True)
        except Exception:
            pass

        if mode == "mix":
            try:
                self.editor_dock.hide()
            except Exception:
                pass
            try:
                self.device_dock.hide()
            except Exception:
                pass
            try:
                self.mixer_dock.show()
                self.mixer_dock.raise_()
            except Exception:
                pass
        elif mode == "edit":
            try:
                self.mixer_dock.hide()
            except Exception:
                pass
            try:
                self.device_dock.hide()
            except Exception:
                pass
            try:
                self.editor_dock.show()
                self.editor_dock.raise_()
            except Exception:
                pass
        elif mode == "device":
            try:
                self.mixer_dock.hide()
            except Exception:
                pass
            try:
                self.editor_dock.hide()
            except Exception:
                pass
            try:
                self.device_dock.show()
                self.device_dock.raise_()
            except Exception:
                pass
        else:  # arrange
            try:
                self.editor_dock.hide()
            except Exception:
                pass
            try:
                self.mixer_dock.hide()
            except Exception:
                pass
            try:
                self.device_dock.hide()
            except Exception:
                pass

        # Update tab checked states without recursion
        for btn, name in [
            (getattr(self, "btn_view_arrange", None), "arrange"),
            (getattr(self, "btn_view_mix", None), "mix"),
            (getattr(self, "btn_view_edit", None), "edit"),
            (getattr(self, "btn_view_device", None), "device"),
        ]:
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(mode == name)
                btn.blockSignals(False)
            except Exception:
                pass

        try:
            self.statusBar().showMessage(f"View: {mode}", 900)
        except Exception:
            pass

    def _add_instrument_to_device(self, plugin_id: str) -> None:
        """Add an instrument plugin to the selected track's device chain."""
        track_id = self._selected_track_id()
        if not track_id:
            try:
                self.statusBar().showMessage("Bitte zuerst einen Instrument-Track auswählen.", 3000)
            except Exception:
                pass
            return

        # v0.0.20.361: Actually wire through to device_panel (was missing!)
        ok = False
        try:
            ok = bool(self.device_panel.add_instrument_to_track(str(track_id), str(plugin_id)))
        except Exception:
            ok = False

        if ok:
            try:
                self.device_panel.show_track(str(track_id))
            except Exception:
                pass
            try:
                self._set_view_mode("device", force=True)
            except Exception:
                pass
            try:
                self._set_status(f"Instrument hinzugefügt: {plugin_id}", 2000)
            except Exception:
                pass

    def _build_smartdrop_audio_to_instrument_morph_plan(self, track_id: str, payload: dict | None = None) -> dict:
        """Build/validate the future Audio→Instrument morph plan without mutating state."""
        track_id = str(track_id or "").strip()
        try:
            payload = dict(payload or {})
        except Exception:
            payload = {}
        plugin_name = str(payload.get("name") or "").strip() or "Instrument"
        proj = getattr(self.services, "project", None)
        if proj is None:
            return {}
        try:
            return dict(proj.validate_audio_to_instrument_morph(track_id, plugin_name=plugin_name) or {})
        except Exception:
            return {}

    def _show_smartdrop_morph_guard_dialog(self, plan: dict | None) -> dict:
        """Show the central morph-guard dialog and return the user's intent.

        Today this still stays non-mutating because the guard-plan keeps
        ``can_apply=False``. The dialog/result contract is prepared so the same
        flow can later forward an explicit confirmation to the real apply phase
        without touching ArrangerCanvas/TrackList again.
        """
        try:
            plan = dict(plan or {})
        except Exception:
            plan = {}
        result = {
            "shown": False,
            "accepted": False,
            "can_apply": bool(plan.get("can_apply")),
            "requires_confirmation": bool(plan.get("requires_confirmation")),
        }
        if not bool(plan.get("requires_confirmation")):
            return result
        track_name = str(plan.get("track_name") or "Spur")
        plugin_name = str(plan.get("plugin_name") or "Instrument")
        track_summary = str(plan.get("summary") or "")
        blocked_reasons = [str(x).strip() for x in list(plan.get("blocked_reasons") or []) if str(x).strip()]
        rollback_lines = [str(x).strip() for x in list(plan.get("rollback_lines") or []) if str(x).strip()]
        future_apply_steps = [str(x).strip() for x in list(plan.get("future_apply_steps") or []) if str(x).strip()]
        required_snapshots = [str(x).strip() for x in list(plan.get("required_snapshots") or []) if str(x).strip()]
        snapshot_refs = []
        for item in list(plan.get("snapshot_refs") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            ref = str(item.get("ref") or "").strip()
            if name and ref:
                snapshot_refs.append((name, ref))
        readiness_checks = []
        for item in list(plan.get("readiness_checks") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            title = str(item.get("title") or "").strip()
            state = str(item.get("state") or "").strip().lower()
            detail = str(item.get("detail") or "").strip()
            if title:
                readiness_checks.append((title, state, detail))
        transaction_steps = [str(x).strip() for x in list(plan.get("transaction_steps") or []) if str(x).strip()]
        transaction_key = str(plan.get("transaction_key") or "").strip()
        transaction_summary = str(plan.get("transaction_summary") or "").strip()
        snapshot_ref_summary = str(plan.get("snapshot_ref_summary") or "").strip()
        runtime_snapshot_summary = str(plan.get("runtime_snapshot_summary") or "").strip()
        runtime_snapshot_handle_summary = str(plan.get("runtime_snapshot_handle_summary") or "").strip()
        runtime_snapshot_capture_summary = str(plan.get("runtime_snapshot_capture_summary") or "").strip()
        runtime_snapshot_instances = []
        for item in list(plan.get("runtime_snapshot_instances") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_instance_key = str(item.get("snapshot_instance_key") or "").strip()
            snapshot_instance_kind = str(item.get("snapshot_instance_kind") or "").strip()
            snapshot_state = str(item.get("snapshot_state") or "").strip().lower()
            owner_scope = str(item.get("owner_scope") or "").strip()
            owner_ids = [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()]
            snapshot_stub = str(item.get("snapshot_stub") or "").strip()
            snapshot_payload = dict(item.get("snapshot_payload") or {}) if isinstance(item.get("snapshot_payload"), dict) else {}
            snapshot_payload_entry_count = int(item.get("snapshot_payload_entry_count") or 0)
            payload_digest = str(item.get("payload_digest") or "").strip()
            if name:
                runtime_snapshot_instances.append((name, snapshot_instance_key, snapshot_instance_kind, snapshot_state, owner_scope, owner_ids, snapshot_stub, snapshot_payload_entry_count, payload_digest, snapshot_payload))
        runtime_snapshot_objects = []
        for item in list(plan.get("runtime_snapshot_objects") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            bind_state = str(item.get("bind_state") or "").strip().lower()
            owner_scope = str(item.get("owner_scope") or "").strip()
            owner_ids = [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()]
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            payload_digest = str(item.get("payload_digest") or "").strip()
            supports_capture = bool(item.get("supports_capture"))
            supports_restore = bool(item.get("supports_restore"))
            object_stub = str(item.get("object_stub") or "").strip()
            if name:
                runtime_snapshot_objects.append((name, snapshot_object_key, snapshot_object_class, bind_state, owner_scope, owner_ids, capture_method, restore_method, rollback_slot, payload_digest, supports_capture, supports_restore, object_stub))
        runtime_snapshot_instance_summary = str(plan.get("runtime_snapshot_instance_summary") or "").strip()
        runtime_snapshot_object_summary = str(plan.get("runtime_snapshot_object_summary") or "").strip()
        runtime_snapshot_stub_summary = str(plan.get("runtime_snapshot_stub_summary") or "").strip()
        runtime_snapshot_state_carrier_summary = str(plan.get("runtime_snapshot_state_carrier_summary") or "").strip()
        runtime_snapshot_stubs = []
        for item in list(plan.get("runtime_snapshot_stubs") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            bind_state = str(item.get("bind_state") or "").strip().lower()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            dispatch_state = str(item.get("dispatch_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_preview = bool(item.get("supports_capture_preview"))
            supports_restore_preview = bool(item.get("supports_restore_preview"))
            factory_method = str(item.get("factory_method") or "").strip()
            capture_stub = str(item.get("capture_stub") or "").strip()
            restore_stub = str(item.get("restore_stub") or "").strip()
            rollback_stub = str(item.get("rollback_stub") or "").strip()
            if name:
                runtime_snapshot_stubs.append((name, snapshot_object_key, snapshot_object_class, bind_state, stub_key, stub_class, dispatch_state, capture_method, restore_method, rollback_slot, supports_capture_preview, supports_restore_preview, factory_method, capture_stub, restore_stub, rollback_stub))
        runtime_snapshot_state_carriers = []
        for item in list(plan.get("runtime_snapshot_state_carriers") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            carrier_state = str(item.get("carrier_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_state = bool(item.get("supports_capture_state"))
            supports_restore_state = bool(item.get("supports_restore_state"))
            bind_method = str(item.get("bind_method") or "").strip()
            capture_state_stub = str(item.get("capture_state_stub") or "").strip()
            restore_state_stub = str(item.get("restore_state_stub") or "").strip()
            rollback_state_stub = str(item.get("rollback_state_stub") or "").strip()
            state_payload_preview = dict(item.get("state_payload_preview") or {}) if isinstance(item.get("state_payload_preview"), dict) else {}
            state_payload_entry_count = int(item.get("state_payload_entry_count") or 0)
            state_payload_digest = str(item.get("state_payload_digest") or "").strip()
            if name:
                runtime_snapshot_state_carriers.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, carrier_state, capture_method, restore_method, rollback_slot, supports_capture_state, supports_restore_state, bind_method, capture_state_stub, restore_state_stub, rollback_state_stub, state_payload_entry_count, state_payload_digest, state_payload_preview))
        runtime_snapshot_state_containers = []
        for item in list(plan.get("runtime_snapshot_state_containers") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            container_state = str(item.get("container_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_container = bool(item.get("supports_capture_container"))
            supports_restore_container = bool(item.get("supports_restore_container"))
            supports_runtime_state_container = bool(item.get("supports_runtime_state_container"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_container_stub = str(item.get("capture_container_stub") or "").strip()
            restore_container_stub = str(item.get("restore_container_stub") or "").strip()
            rollback_container_stub = str(item.get("rollback_container_stub") or "").strip()
            runtime_state_stub = str(item.get("runtime_state_stub") or "").strip()
            state_payload_entry_count = int(item.get("state_payload_entry_count") or 0)
            state_payload_digest = str(item.get("state_payload_digest") or "").strip()
            state_payload_preview = dict(item.get("state_payload_preview") or {}) if isinstance(item.get("state_payload_preview"), dict) else {}
            container_payload_entry_count = int(item.get("container_payload_entry_count") or 0)
            container_payload_digest = str(item.get("container_payload_digest") or "").strip()
            container_payload_preview = dict(item.get("container_payload_preview") or {}) if isinstance(item.get("container_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_containers.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, container_state, capture_method, restore_method, rollback_slot, supports_capture_container, supports_restore_container, supports_runtime_state_container, instantiate_method, capture_container_stub, restore_container_stub, rollback_container_stub, runtime_state_stub, state_payload_entry_count, state_payload_digest, state_payload_preview, container_payload_entry_count, container_payload_digest, container_payload_preview))
        runtime_snapshot_state_container_summary = str(plan.get("runtime_snapshot_state_container_summary") or "").strip()
        runtime_snapshot_state_holders = []
        for item in list(plan.get("runtime_snapshot_state_holders") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            holder_state = str(item.get("holder_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_holder = bool(item.get("supports_capture_holder"))
            supports_restore_holder = bool(item.get("supports_restore_holder"))
            supports_runtime_state_holder = bool(item.get("supports_runtime_state_holder"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_holder_stub = str(item.get("capture_holder_stub") or "").strip()
            restore_holder_stub = str(item.get("restore_holder_stub") or "").strip()
            rollback_holder_stub = str(item.get("rollback_holder_stub") or "").strip()
            runtime_holder_stub = str(item.get("runtime_holder_stub") or "").strip()
            container_payload_entry_count = int(item.get("container_payload_entry_count") or 0)
            container_payload_digest = str(item.get("container_payload_digest") or "").strip()
            container_payload_preview = dict(item.get("container_payload_preview") or {}) if isinstance(item.get("container_payload_preview"), dict) else {}
            holder_payload_entry_count = int(item.get("holder_payload_entry_count") or 0)
            holder_payload_digest = str(item.get("holder_payload_digest") or "").strip()
            holder_payload_preview = dict(item.get("holder_payload_preview") or {}) if isinstance(item.get("holder_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_holders.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, holder_state, capture_method, restore_method, rollback_slot, supports_capture_holder, supports_restore_holder, supports_runtime_state_holder, instantiate_method, capture_holder_stub, restore_holder_stub, rollback_holder_stub, runtime_holder_stub, container_payload_entry_count, container_payload_digest, container_payload_preview, holder_payload_entry_count, holder_payload_digest, holder_payload_preview))
        runtime_snapshot_state_slots = []
        for item in list(plan.get("runtime_snapshot_state_slots") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            slot_key = str(item.get("slot_key") or "").strip()
            slot_class = str(item.get("slot_class") or "").strip()
            slot_state = str(item.get("slot_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_slot = bool(item.get("supports_capture_slot"))
            supports_restore_slot = bool(item.get("supports_restore_slot"))
            supports_runtime_state_slot = bool(item.get("supports_runtime_state_slot"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_slot_stub = str(item.get("capture_slot_stub") or "").strip()
            restore_slot_stub = str(item.get("restore_slot_stub") or "").strip()
            rollback_slot_stub = str(item.get("rollback_slot_stub") or "").strip()
            runtime_state_slot_stub = str(item.get("runtime_state_slot_stub") or "").strip()
            holder_payload_entry_count = int(item.get("holder_payload_entry_count") or 0)
            holder_payload_digest = str(item.get("holder_payload_digest") or "").strip()
            holder_payload_preview = dict(item.get("holder_payload_preview") or {}) if isinstance(item.get("holder_payload_preview"), dict) else {}
            slot_payload_entry_count = int(item.get("slot_payload_entry_count") or 0)
            slot_payload_digest = str(item.get("slot_payload_digest") or "").strip()
            slot_payload_preview = dict(item.get("slot_payload_preview") or {}) if isinstance(item.get("slot_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_slots.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, slot_state, capture_method, restore_method, rollback_slot, supports_capture_slot, supports_restore_slot, supports_runtime_state_slot, instantiate_method, capture_slot_stub, restore_slot_stub, rollback_slot_stub, runtime_state_slot_stub, holder_payload_entry_count, holder_payload_digest, holder_payload_preview, slot_payload_entry_count, slot_payload_digest, slot_payload_preview))
        runtime_snapshot_state_slot_summary = str(plan.get("runtime_snapshot_state_slot_summary") or "").strip()
        runtime_snapshot_state_stores = []
        for item in list(plan.get("runtime_snapshot_state_stores") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            slot_key = str(item.get("slot_key") or "").strip()
            slot_class = str(item.get("slot_class") or "").strip()
            store_key = str(item.get("store_key") or "").strip()
            store_class = str(item.get("store_class") or "").strip()
            store_state = str(item.get("store_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_store = bool(item.get("supports_capture_store"))
            supports_restore_store = bool(item.get("supports_restore_store"))
            supports_runtime_state_store = bool(item.get("supports_runtime_state_store"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_store_stub = str(item.get("capture_store_stub") or "").strip()
            restore_store_stub = str(item.get("restore_store_stub") or "").strip()
            rollback_store_stub = str(item.get("rollback_store_stub") or "").strip()
            runtime_state_store_stub = str(item.get("runtime_state_store_stub") or "").strip()
            capture_handle_key = str(item.get("capture_handle_key") or "").strip()
            restore_handle_key = str(item.get("restore_handle_key") or "").strip()
            rollback_handle_key = str(item.get("rollback_handle_key") or "").strip()
            capture_handle_state = str(item.get("capture_handle_state") or "").strip().lower()
            slot_payload_entry_count = int(item.get("slot_payload_entry_count") or 0)
            slot_payload_digest = str(item.get("slot_payload_digest") or "").strip()
            slot_payload_preview = dict(item.get("slot_payload_preview") or {}) if isinstance(item.get("slot_payload_preview"), dict) else {}
            store_payload_entry_count = int(item.get("store_payload_entry_count") or 0)
            store_payload_digest = str(item.get("store_payload_digest") or "").strip()
            store_payload_preview = dict(item.get("store_payload_preview") or {}) if isinstance(item.get("store_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_stores.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, store_state, capture_method, restore_method, rollback_slot, supports_capture_store, supports_restore_store, supports_runtime_state_store, instantiate_method, capture_store_stub, restore_store_stub, rollback_store_stub, runtime_state_store_stub, capture_handle_key, restore_handle_key, rollback_handle_key, capture_handle_state, slot_payload_entry_count, slot_payload_digest, slot_payload_preview, store_payload_entry_count, store_payload_digest, store_payload_preview))
        runtime_snapshot_state_store_summary = str(plan.get("runtime_snapshot_state_store_summary") or "").strip()
        runtime_snapshot_state_registries = []
        for item in list(plan.get("runtime_snapshot_state_registries") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            slot_key = str(item.get("slot_key") or "").strip()
            slot_class = str(item.get("slot_class") or "").strip()
            store_key = str(item.get("store_key") or "").strip()
            store_class = str(item.get("store_class") or "").strip()
            registry_key = str(item.get("registry_key") or "").strip()
            registry_class = str(item.get("registry_class") or "").strip()
            registry_state = str(item.get("registry_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_registry = bool(item.get("supports_capture_registry"))
            supports_restore_registry = bool(item.get("supports_restore_registry"))
            supports_runtime_state_registry = bool(item.get("supports_runtime_state_registry"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_registry_stub = str(item.get("capture_registry_stub") or "").strip()
            restore_registry_stub = str(item.get("restore_registry_stub") or "").strip()
            rollback_registry_stub = str(item.get("rollback_registry_stub") or "").strip()
            runtime_state_registry_stub = str(item.get("runtime_state_registry_stub") or "").strip()
            capture_handle_key = str(item.get("capture_handle_key") or "").strip()
            restore_handle_key = str(item.get("restore_handle_key") or "").strip()
            rollback_handle_key = str(item.get("rollback_handle_key") or "").strip()
            handle_store_key = str(item.get("handle_store_key") or "").strip()
            handle_store_class = str(item.get("handle_store_class") or "").strip()
            handle_store_state = str(item.get("handle_store_state") or "").strip().lower()
            store_payload_entry_count = int(item.get("store_payload_entry_count") or 0)
            store_payload_digest = str(item.get("store_payload_digest") or "").strip()
            store_payload_preview = dict(item.get("store_payload_preview") or {}) if isinstance(item.get("store_payload_preview"), dict) else {}
            registry_payload_entry_count = int(item.get("registry_payload_entry_count") or 0)
            registry_payload_digest = str(item.get("registry_payload_digest") or "").strip()
            registry_payload_preview = dict(item.get("registry_payload_preview") or {}) if isinstance(item.get("registry_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_registries.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, registry_state, capture_method, restore_method, rollback_slot, supports_capture_registry, supports_restore_registry, supports_runtime_state_registry, instantiate_method, capture_registry_stub, restore_registry_stub, rollback_registry_stub, runtime_state_registry_stub, capture_handle_key, restore_handle_key, rollback_handle_key, handle_store_key, handle_store_class, handle_store_state, store_payload_entry_count, store_payload_digest, store_payload_preview, registry_payload_entry_count, registry_payload_digest, registry_payload_preview))
        runtime_snapshot_state_registry_summary = str(plan.get("runtime_snapshot_state_registry_summary") or "").strip()
        runtime_snapshot_state_registry_backends = []
        for item in list(plan.get("runtime_snapshot_state_registry_backends") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            slot_key = str(item.get("slot_key") or "").strip()
            slot_class = str(item.get("slot_class") or "").strip()
            store_key = str(item.get("store_key") or "").strip()
            store_class = str(item.get("store_class") or "").strip()
            registry_key = str(item.get("registry_key") or "").strip()
            registry_class = str(item.get("registry_class") or "").strip()
            backend_key = str(item.get("backend_key") or "").strip()
            backend_class = str(item.get("backend_class") or "").strip()
            backend_state = str(item.get("backend_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_backend = bool(item.get("supports_capture_backend"))
            supports_restore_backend = bool(item.get("supports_restore_backend"))
            supports_runtime_state_backend = bool(item.get("supports_runtime_state_backend"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_backend_stub = str(item.get("capture_backend_stub") or "").strip()
            restore_backend_stub = str(item.get("restore_backend_stub") or "").strip()
            rollback_backend_stub = str(item.get("rollback_backend_stub") or "").strip()
            runtime_state_backend_stub = str(item.get("runtime_state_backend_stub") or "").strip()
            handle_register_key = str(item.get("handle_register_key") or "").strip()
            handle_register_class = str(item.get("handle_register_class") or "").strip()
            handle_register_state = str(item.get("handle_register_state") or "").strip().lower()
            registry_slot_key = str(item.get("registry_slot_key") or "").strip()
            registry_slot_class = str(item.get("registry_slot_class") or "").strip()
            registry_slot_state = str(item.get("registry_slot_state") or "").strip().lower()
            registry_payload_entry_count = int(item.get("registry_payload_entry_count") or 0)
            registry_payload_digest = str(item.get("registry_payload_digest") or "").strip()
            registry_payload_preview = dict(item.get("registry_payload_preview") or {}) if isinstance(item.get("registry_payload_preview"), dict) else {}
            backend_payload_entry_count = int(item.get("backend_payload_entry_count") or 0)
            backend_payload_digest = str(item.get("backend_payload_digest") or "").strip()
            backend_payload_preview = dict(item.get("backend_payload_preview") or {}) if isinstance(item.get("backend_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_registry_backends.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, backend_key, backend_class, backend_state, capture_method, restore_method, rollback_slot, supports_capture_backend, supports_restore_backend, supports_runtime_state_backend, instantiate_method, capture_backend_stub, restore_backend_stub, rollback_backend_stub, runtime_state_backend_stub, handle_register_key, handle_register_class, handle_register_state, registry_slot_key, registry_slot_class, registry_slot_state, registry_payload_entry_count, registry_payload_digest, registry_payload_preview, backend_payload_entry_count, backend_payload_digest, backend_payload_preview))
        runtime_snapshot_state_registry_backend_summary = str(plan.get("runtime_snapshot_state_registry_backend_summary") or "").strip()
        runtime_snapshot_state_registry_backend_adapters = []
        for item in list(plan.get("runtime_snapshot_state_registry_backend_adapters") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            snapshot_object_key = str(item.get("snapshot_object_key") or "").strip()
            snapshot_object_class = str(item.get("snapshot_object_class") or "").strip()
            stub_key = str(item.get("stub_key") or "").strip()
            stub_class = str(item.get("stub_class") or "").strip()
            carrier_key = str(item.get("carrier_key") or "").strip()
            carrier_class = str(item.get("carrier_class") or "").strip()
            container_key = str(item.get("container_key") or "").strip()
            container_class = str(item.get("container_class") or "").strip()
            holder_key = str(item.get("holder_key") or "").strip()
            holder_class = str(item.get("holder_class") or "").strip()
            slot_key = str(item.get("slot_key") or "").strip()
            slot_class = str(item.get("slot_class") or "").strip()
            store_key = str(item.get("store_key") or "").strip()
            store_class = str(item.get("store_class") or "").strip()
            registry_key = str(item.get("registry_key") or "").strip()
            registry_class = str(item.get("registry_class") or "").strip()
            backend_key = str(item.get("backend_key") or "").strip()
            backend_class = str(item.get("backend_class") or "").strip()
            adapter_key = str(item.get("adapter_key") or "").strip()
            adapter_class = str(item.get("adapter_class") or "").strip()
            adapter_state = str(item.get("adapter_state") or "").strip().lower()
            capture_method = str(item.get("capture_method") or "").strip()
            restore_method = str(item.get("restore_method") or "").strip()
            rollback_slot = str(item.get("rollback_slot") or "").strip()
            supports_capture_backend_adapter = bool(item.get("supports_capture_backend_adapter"))
            supports_restore_backend_adapter = bool(item.get("supports_restore_backend_adapter"))
            supports_runtime_state_backend_adapter = bool(item.get("supports_runtime_state_backend_adapter"))
            instantiate_method = str(item.get("instantiate_method") or "").strip()
            capture_adapter_stub = str(item.get("capture_adapter_stub") or "").strip()
            restore_adapter_stub = str(item.get("restore_adapter_stub") or "").strip()
            rollback_adapter_stub = str(item.get("rollback_adapter_stub") or "").strip()
            runtime_state_backend_adapter_stub = str(item.get("runtime_state_backend_adapter_stub") or "").strip()
            backend_store_adapter_key = str(item.get("backend_store_adapter_key") or "").strip()
            backend_store_adapter_class = str(item.get("backend_store_adapter_class") or "").strip()
            backend_store_adapter_state = str(item.get("backend_store_adapter_state") or "").strip().lower()
            registry_slot_backend_key = str(item.get("registry_slot_backend_key") or "").strip()
            registry_slot_backend_class = str(item.get("registry_slot_backend_class") or "").strip()
            registry_slot_backend_state = str(item.get("registry_slot_backend_state") or "").strip().lower()
            backend_payload_entry_count = int(item.get("backend_payload_entry_count") or 0)
            backend_payload_digest = str(item.get("backend_payload_digest") or "").strip()
            backend_payload_preview = dict(item.get("backend_payload_preview") or {}) if isinstance(item.get("backend_payload_preview"), dict) else {}
            adapter_payload_entry_count = int(item.get("adapter_payload_entry_count") or 0)
            adapter_payload_digest = str(item.get("adapter_payload_digest") or "").strip()
            adapter_payload_preview = dict(item.get("adapter_payload_preview") or {}) if isinstance(item.get("adapter_payload_preview"), dict) else {}
            if name:
                runtime_snapshot_state_registry_backend_adapters.append((name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, backend_key, backend_class, adapter_key, adapter_class, adapter_state, capture_method, restore_method, rollback_slot, supports_capture_backend_adapter, supports_restore_backend_adapter, supports_runtime_state_backend_adapter, instantiate_method, capture_adapter_stub, restore_adapter_stub, rollback_adapter_stub, runtime_state_backend_adapter_stub, backend_store_adapter_key, backend_store_adapter_class, backend_store_adapter_state, registry_slot_backend_key, registry_slot_backend_class, registry_slot_backend_state, backend_payload_entry_count, backend_payload_digest, backend_payload_preview, adapter_payload_entry_count, adapter_payload_digest, adapter_payload_preview))
        runtime_snapshot_state_registry_backend_adapter_summary = str(plan.get("runtime_snapshot_state_registry_backend_adapter_summary") or "").strip()
        runtime_snapshot_bundle_summary = str(plan.get("runtime_snapshot_bundle_summary") or "").strip()
        runtime_snapshot_apply_runner_summary = str(plan.get("runtime_snapshot_apply_runner_summary") or "").strip()
        runtime_snapshot_dry_run_summary = str(plan.get("runtime_snapshot_dry_run_summary") or "").strip()
        first_minimal_case_summary = str(plan.get("first_minimal_case_summary") or "").strip()
        runtime_snapshot_precommit_contract_summary = str(plan.get("runtime_snapshot_precommit_contract_summary") or "").strip()
        runtime_snapshot_atomic_entrypoints_summary = str(plan.get("runtime_snapshot_atomic_entrypoints_summary") or "").strip()
        runtime_snapshot_mutation_gate_capsule_summary = str(plan.get("runtime_snapshot_mutation_gate_capsule_summary") or "").strip()
        runtime_snapshot_command_undo_shell_summary = str(plan.get("runtime_snapshot_command_undo_shell_summary") or "").strip()
        runtime_snapshot_command_factory_payload_summary = str(plan.get("runtime_snapshot_command_factory_payload_summary") or "").strip()
        runtime_snapshot_preview_command_construction_summary = str(plan.get("runtime_snapshot_preview_command_construction_summary") or "").strip()
        runtime_snapshot_dry_command_executor_summary = str(plan.get("runtime_snapshot_dry_command_executor_summary") or "").strip()
        runtime_snapshot_state_holder_summary = str(plan.get("runtime_snapshot_state_holder_summary") or "").strip()
        try:
            bundle_plan = dict(plan.get("runtime_snapshot_bundle") or {})
        except Exception:
            bundle_plan = {}
        runtime_snapshot_bundle = {
            "bundle_key": str(bundle_plan.get("bundle_key") or "").strip(),
            "transaction_key": str(bundle_plan.get("transaction_key") or "").strip(),
            "transaction_container_kind": str(bundle_plan.get("transaction_container_kind") or "").strip(),
            "bundle_state": str(bundle_plan.get("bundle_state") or "").strip().lower(),
            "object_count": int(bundle_plan.get("object_count") or 0),
            "ready_object_count": int(bundle_plan.get("ready_object_count") or 0),
            "required_snapshot_count": int(bundle_plan.get("required_snapshot_count") or 0),
            "snapshot_object_keys": [str(x).strip() for x in list(bundle_plan.get("snapshot_object_keys") or []) if str(x).strip()],
            "capture_methods": [str(x).strip() for x in list(bundle_plan.get("capture_methods") or []) if str(x).strip()],
            "restore_methods": [str(x).strip() for x in list(bundle_plan.get("restore_methods") or []) if str(x).strip()],
            "rollback_slots": [str(x).strip() for x in list(bundle_plan.get("rollback_slots") or []) if str(x).strip()],
            "payload_digests": [str(x).strip() for x in list(bundle_plan.get("payload_digests") or []) if str(x).strip()],
            "commit_stub": str(bundle_plan.get("commit_stub") or "").strip(),
            "rollback_stub": str(bundle_plan.get("rollback_stub") or "").strip(),
            "bundle_stub": str(bundle_plan.get("bundle_stub") or "").strip(),
        }
        try:
            apply_runner_plan = dict(plan.get("runtime_snapshot_apply_runner") or {})
        except Exception:
            apply_runner_plan = {}
        runtime_snapshot_apply_runner = {
            "runner_key": str(apply_runner_plan.get("runner_key") or "").strip(),
            "transaction_key": str(apply_runner_plan.get("transaction_key") or "").strip(),
            "bundle_key": str(apply_runner_plan.get("bundle_key") or "").strip(),
            "apply_mode": str(apply_runner_plan.get("apply_mode") or "").strip(),
            "runner_state": str(apply_runner_plan.get("runner_state") or "").strip().lower(),
            "phase_count": int(apply_runner_plan.get("phase_count") or 0),
            "ready_phase_count": int(apply_runner_plan.get("ready_phase_count") or 0),
            "apply_sequence": [str(x).strip() for x in list(apply_runner_plan.get("apply_sequence") or []) if str(x).strip()],
            "restore_sequence": [str(x).strip() for x in list(apply_runner_plan.get("restore_sequence") or []) if str(x).strip()],
            "rollback_sequence": [str(x).strip() for x in list(apply_runner_plan.get("rollback_sequence") or []) if str(x).strip()],
            "rehearsed_steps": [str(x).strip() for x in list(apply_runner_plan.get("rehearsed_steps") or []) if str(x).strip()],
            "phase_results": [dict(x or {}) for x in list(apply_runner_plan.get("phase_results") or []) if isinstance(x, dict)],
            "state_registry_backend_adapter_calls": [str(x).strip() for x in list(apply_runner_plan.get("state_registry_backend_adapter_calls") or []) if str(x).strip()],
            "state_registry_backend_adapter_summary": str(apply_runner_plan.get("state_registry_backend_adapter_summary") or "").strip(),
            "backend_store_adapter_calls": [str(x).strip() for x in list(apply_runner_plan.get("backend_store_adapter_calls") or []) if str(x).strip()],
            "backend_store_adapter_summary": str(apply_runner_plan.get("backend_store_adapter_summary") or "").strip(),
            "registry_slot_backend_calls": [str(x).strip() for x in list(apply_runner_plan.get("registry_slot_backend_calls") or []) if str(x).strip()],
            "registry_slot_backend_summary": str(apply_runner_plan.get("registry_slot_backend_summary") or "").strip(),
            "runner_dispatch_summary": str(apply_runner_plan.get("runner_dispatch_summary") or "").strip(),
            "commit_preview_only": bool(apply_runner_plan.get("commit_preview_only")),
            "rollback_rehearsed": bool(apply_runner_plan.get("rollback_rehearsed")),
            "apply_runner_stub": str(apply_runner_plan.get("apply_runner_stub") or "").strip(),
        }
        try:
            first_minimal_case_plan = dict(plan.get("first_minimal_case_report") or {})
        except Exception:
            first_minimal_case_plan = {}
        first_minimal_case_report = {
            "minimal_case_key": str(first_minimal_case_plan.get("minimal_case_key") or "").strip(),
            "transaction_key": str(first_minimal_case_plan.get("transaction_key") or "").strip(),
            "candidate_state": str(first_minimal_case_plan.get("candidate_state") or "").strip().lower(),
            "target_kind": str(first_minimal_case_plan.get("target_kind") or "").strip().lower(),
            "target_empty": bool(first_minimal_case_plan.get("target_empty")),
            "audio_clip_count": int(first_minimal_case_plan.get("audio_clip_count") or 0),
            "audio_fx_count": int(first_minimal_case_plan.get("audio_fx_count") or 0),
            "note_fx_count": int(first_minimal_case_plan.get("note_fx_count") or 0),
            "bundle_ready": bool(first_minimal_case_plan.get("bundle_ready")),
            "apply_runner_ready": bool(first_minimal_case_plan.get("apply_runner_ready")),
            "dry_run_ready": bool(first_minimal_case_plan.get("dry_run_ready")),
            "future_unlock_ready": bool(first_minimal_case_plan.get("future_unlock_ready")),
            "blocked_by": [str(x).strip() for x in list(first_minimal_case_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(first_minimal_case_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(first_minimal_case_plan.get("summary") or "").strip(),
        }
        try:
            precommit_contract_plan = dict(plan.get("runtime_snapshot_precommit_contract") or {})
        except Exception:
            precommit_contract_plan = {}
        runtime_snapshot_precommit_contract = {
            "contract_key": str(precommit_contract_plan.get("contract_key") or "").strip(),
            "transaction_key": str(precommit_contract_plan.get("transaction_key") or "").strip(),
            "minimal_case_key": str(precommit_contract_plan.get("minimal_case_key") or "").strip(),
            "contract_state": str(precommit_contract_plan.get("contract_state") or "").strip().lower(),
            "mutation_gate_state": str(precommit_contract_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(precommit_contract_plan.get("target_scope") or "").strip(),
            "target_empty": bool(precommit_contract_plan.get("target_empty")),
            "preview_phase_count": int(precommit_contract_plan.get("preview_phase_count") or 0),
            "ready_preview_phase_count": int(precommit_contract_plan.get("ready_preview_phase_count") or 0),
            "preview_commit_sequence": [str(x).strip() for x in list(precommit_contract_plan.get("preview_commit_sequence") or []) if str(x).strip()],
            "preview_rollback_sequence": [str(x).strip() for x in list(precommit_contract_plan.get("preview_rollback_sequence") or []) if str(x).strip()],
            "preview_phase_results": [dict(x or {}) for x in list(precommit_contract_plan.get("preview_phase_results") or []) if isinstance(x, dict)],
            "bundle_key": str(precommit_contract_plan.get("bundle_key") or "").strip(),
            "apply_runner_key": str(precommit_contract_plan.get("apply_runner_key") or "").strip(),
            "dry_run_key": str(precommit_contract_plan.get("dry_run_key") or "").strip(),
            "future_commit_stub": str(precommit_contract_plan.get("future_commit_stub") or "").strip(),
            "future_rollback_stub": str(precommit_contract_plan.get("future_rollback_stub") or "").strip(),
            "commit_preview_only": bool(precommit_contract_plan.get("commit_preview_only")),
            "project_mutation_enabled": bool(precommit_contract_plan.get("project_mutation_enabled")),
            "blocked_by": [str(x).strip() for x in list(precommit_contract_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(precommit_contract_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(precommit_contract_plan.get("summary") or "").strip(),
        }
        try:
            atomic_entrypoints_plan = dict(plan.get("runtime_snapshot_atomic_entrypoints") or {})
        except Exception:
            atomic_entrypoints_plan = {}
        runtime_snapshot_atomic_entrypoints = {
            "entrypoint_key": str(atomic_entrypoints_plan.get("entrypoint_key") or "").strip(),
            "transaction_key": str(atomic_entrypoints_plan.get("transaction_key") or "").strip(),
            "contract_key": str(atomic_entrypoints_plan.get("contract_key") or "").strip(),
            "entrypoint_state": str(atomic_entrypoints_plan.get("entrypoint_state") or "").strip().lower(),
            "mutation_gate_state": str(atomic_entrypoints_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(atomic_entrypoints_plan.get("target_scope") or "").strip(),
            "owner_class": str(atomic_entrypoints_plan.get("owner_class") or "").strip(),
            "total_entrypoint_count": int(atomic_entrypoints_plan.get("total_entrypoint_count") or 0),
            "ready_entrypoint_count": int(atomic_entrypoints_plan.get("ready_entrypoint_count") or 0),
            "entrypoints": [dict(x or {}) for x in list(atomic_entrypoints_plan.get("entrypoints") or []) if isinstance(x, dict)],
            "preview_dispatch_sequence": [str(x).strip() for x in list(atomic_entrypoints_plan.get("preview_dispatch_sequence") or []) if str(x).strip()],
            "future_apply_stub": str(atomic_entrypoints_plan.get("future_apply_stub") or "").strip(),
            "future_commit_stub": str(atomic_entrypoints_plan.get("future_commit_stub") or "").strip(),
            "future_rollback_stub": str(atomic_entrypoints_plan.get("future_rollback_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(atomic_entrypoints_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(atomic_entrypoints_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(atomic_entrypoints_plan.get("summary") or "").strip(),
        }
        try:
            mutation_gate_capsule_plan = dict(plan.get("runtime_snapshot_mutation_gate_capsule") or {})
        except Exception:
            mutation_gate_capsule_plan = {}
        runtime_snapshot_mutation_gate_capsule = {
            "capsule_key": str(mutation_gate_capsule_plan.get("capsule_key") or "").strip(),
            "transaction_key": str(mutation_gate_capsule_plan.get("transaction_key") or "").strip(),
            "contract_key": str(mutation_gate_capsule_plan.get("contract_key") or "").strip(),
            "entrypoint_key": str(mutation_gate_capsule_plan.get("entrypoint_key") or "").strip(),
            "capsule_state": str(mutation_gate_capsule_plan.get("capsule_state") or "").strip().lower(),
            "mutation_gate_state": str(mutation_gate_capsule_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(mutation_gate_capsule_plan.get("target_scope") or "").strip(),
            "owner_class": str(mutation_gate_capsule_plan.get("owner_class") or "").strip(),
            "total_capsule_step_count": int(mutation_gate_capsule_plan.get("total_capsule_step_count") or 0),
            "ready_capsule_step_count": int(mutation_gate_capsule_plan.get("ready_capsule_step_count") or 0),
            "capsule_steps": [dict(x or {}) for x in list(mutation_gate_capsule_plan.get("capsule_steps") or []) if isinstance(x, dict)],
            "preview_capsule_sequence": [str(x).strip() for x in list(mutation_gate_capsule_plan.get("preview_capsule_sequence") or []) if str(x).strip()],
            "future_gate_stub": str(mutation_gate_capsule_plan.get("future_gate_stub") or "").strip(),
            "future_capsule_stub": str(mutation_gate_capsule_plan.get("future_capsule_stub") or "").strip(),
            "future_commit_stub": str(mutation_gate_capsule_plan.get("future_commit_stub") or "").strip(),
            "future_rollback_stub": str(mutation_gate_capsule_plan.get("future_rollback_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(mutation_gate_capsule_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(mutation_gate_capsule_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(mutation_gate_capsule_plan.get("summary") or "").strip(),
        }
        try:
            command_undo_shell_plan = dict(plan.get("runtime_snapshot_command_undo_shell") or {})
        except Exception:
            command_undo_shell_plan = {}
        runtime_snapshot_command_undo_shell = {
            "shell_key": str(command_undo_shell_plan.get("shell_key") or "").strip(),
            "transaction_key": str(command_undo_shell_plan.get("transaction_key") or "").strip(),
            "capsule_key": str(command_undo_shell_plan.get("capsule_key") or "").strip(),
            "contract_key": str(command_undo_shell_plan.get("contract_key") or "").strip(),
            "shell_state": str(command_undo_shell_plan.get("shell_state") or "").strip().lower(),
            "mutation_gate_state": str(command_undo_shell_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(command_undo_shell_plan.get("target_scope") or "").strip(),
            "owner_class": str(command_undo_shell_plan.get("owner_class") or "").strip(),
            "command_class": str(command_undo_shell_plan.get("command_class") or "").strip(),
            "command_module": str(command_undo_shell_plan.get("command_module") or "").strip(),
            "total_shell_step_count": int(command_undo_shell_plan.get("total_shell_step_count") or 0),
            "ready_shell_step_count": int(command_undo_shell_plan.get("ready_shell_step_count") or 0),
            "shell_steps": [dict(x or {}) for x in list(command_undo_shell_plan.get("shell_steps") or []) if isinstance(x, dict)],
            "preview_shell_sequence": [str(x).strip() for x in list(command_undo_shell_plan.get("preview_shell_sequence") or []) if str(x).strip()],
            "future_command_stub": str(command_undo_shell_plan.get("future_command_stub") or "").strip(),
            "future_undo_stub": str(command_undo_shell_plan.get("future_undo_stub") or "").strip(),
            "future_commit_stub": str(command_undo_shell_plan.get("future_commit_stub") or "").strip(),
            "future_rollback_stub": str(command_undo_shell_plan.get("future_rollback_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(command_undo_shell_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(command_undo_shell_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(command_undo_shell_plan.get("summary") or "").strip(),
        }
        try:
            command_factory_payload_plan = dict(plan.get("runtime_snapshot_command_factory_payloads") or {})
        except Exception:
            command_factory_payload_plan = {}
        runtime_snapshot_command_factory_payloads = {
            "factory_key": str(command_factory_payload_plan.get("factory_key") or "").strip(),
            "transaction_key": str(command_factory_payload_plan.get("transaction_key") or "").strip(),
            "shell_key": str(command_factory_payload_plan.get("shell_key") or "").strip(),
            "capsule_key": str(command_factory_payload_plan.get("capsule_key") or "").strip(),
            "contract_key": str(command_factory_payload_plan.get("contract_key") or "").strip(),
            "payload_state": str(command_factory_payload_plan.get("payload_state") or "").strip().lower(),
            "mutation_gate_state": str(command_factory_payload_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(command_factory_payload_plan.get("target_scope") or "").strip(),
            "owner_class": str(command_factory_payload_plan.get("owner_class") or "").strip(),
            "command_class": str(command_factory_payload_plan.get("command_class") or "").strip(),
            "command_module": str(command_factory_payload_plan.get("command_module") or "").strip(),
            "label_preview": str(command_factory_payload_plan.get("label_preview") or "").strip(),
            "payload_delta_kind": str(command_factory_payload_plan.get("payload_delta_kind") or "").strip(),
            "materialized_payload_count": int(command_factory_payload_plan.get("materialized_payload_count") or 0),
            "before_payload_summary": dict(command_factory_payload_plan.get("before_payload_summary") or {}) if isinstance(command_factory_payload_plan.get("before_payload_summary"), dict) else {},
            "after_payload_summary": dict(command_factory_payload_plan.get("after_payload_summary") or {}) if isinstance(command_factory_payload_plan.get("after_payload_summary"), dict) else {},
            "total_factory_step_count": int(command_factory_payload_plan.get("total_factory_step_count") or 0),
            "ready_factory_step_count": int(command_factory_payload_plan.get("ready_factory_step_count") or 0),
            "factory_steps": [dict(x or {}) for x in list(command_factory_payload_plan.get("factory_steps") or []) if isinstance(x, dict)],
            "preview_factory_sequence": [str(x).strip() for x in list(command_factory_payload_plan.get("preview_factory_sequence") or []) if str(x).strip()],
            "future_factory_stub": str(command_factory_payload_plan.get("future_factory_stub") or "").strip(),
            "future_before_snapshot_stub": str(command_factory_payload_plan.get("future_before_snapshot_stub") or "").strip(),
            "future_after_snapshot_stub": str(command_factory_payload_plan.get("future_after_snapshot_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(command_factory_payload_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(command_factory_payload_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(command_factory_payload_plan.get("summary") or "").strip(),
        }
        try:
            preview_command_plan = dict(plan.get("runtime_snapshot_preview_command_construction") or {})
        except Exception:
            preview_command_plan = {}
        runtime_snapshot_preview_command_construction = {
            "preview_command_key": str(preview_command_plan.get("preview_command_key") or "").strip(),
            "transaction_key": str(preview_command_plan.get("transaction_key") or "").strip(),
            "factory_key": str(preview_command_plan.get("factory_key") or "").strip(),
            "shell_key": str(preview_command_plan.get("shell_key") or "").strip(),
            "capsule_key": str(preview_command_plan.get("capsule_key") or "").strip(),
            "contract_key": str(preview_command_plan.get("contract_key") or "").strip(),
            "preview_state": str(preview_command_plan.get("preview_state") or "").strip().lower(),
            "mutation_gate_state": str(preview_command_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(preview_command_plan.get("target_scope") or "").strip(),
            "owner_class": str(preview_command_plan.get("owner_class") or "").strip(),
            "command_class": str(preview_command_plan.get("command_class") or "").strip(),
            "command_module": str(preview_command_plan.get("command_module") or "").strip(),
            "command_constructor": str(preview_command_plan.get("command_constructor") or "").strip(),
            "label_preview": str(preview_command_plan.get("label_preview") or "").strip(),
            "apply_callback_name": str(preview_command_plan.get("apply_callback_name") or "").strip(),
            "apply_callback_owner_class": str(preview_command_plan.get("apply_callback_owner_class") or "").strip(),
            "payload_delta_kind": str(preview_command_plan.get("payload_delta_kind") or "").strip(),
            "materialized_payload_count": int(preview_command_plan.get("materialized_payload_count") or 0),
            "before_payload_summary": dict(preview_command_plan.get("before_payload_summary") or {}) if isinstance(preview_command_plan.get("before_payload_summary"), dict) else {},
            "after_payload_summary": dict(preview_command_plan.get("after_payload_summary") or {}) if isinstance(preview_command_plan.get("after_payload_summary"), dict) else {},
            "command_field_names": [str(x).strip() for x in list(preview_command_plan.get("command_field_names") or []) if str(x).strip()],
            "total_preview_step_count": int(preview_command_plan.get("total_preview_step_count") or 0),
            "ready_preview_step_count": int(preview_command_plan.get("ready_preview_step_count") or 0),
            "preview_steps": [dict(x or {}) for x in list(preview_command_plan.get("preview_steps") or []) if isinstance(x, dict)],
            "preview_command_sequence": [str(x).strip() for x in list(preview_command_plan.get("preview_command_sequence") or []) if str(x).strip()],
            "future_constructor_stub": str(preview_command_plan.get("future_constructor_stub") or "").strip(),
            "future_executor_stub": str(preview_command_plan.get("future_executor_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(preview_command_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(preview_command_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(preview_command_plan.get("summary") or "").strip(),
        }
        try:
            dry_command_executor_plan = dict(plan.get("runtime_snapshot_dry_command_executor") or {})
        except Exception:
            dry_command_executor_plan = {}
        runtime_snapshot_dry_command_executor = {
            "dry_executor_key": str(dry_command_executor_plan.get("dry_executor_key") or "").strip(),
            "transaction_key": str(dry_command_executor_plan.get("transaction_key") or "").strip(),
            "preview_command_key": str(dry_command_executor_plan.get("preview_command_key") or "").strip(),
            "factory_key": str(dry_command_executor_plan.get("factory_key") or "").strip(),
            "shell_key": str(dry_command_executor_plan.get("shell_key") or "").strip(),
            "capsule_key": str(dry_command_executor_plan.get("capsule_key") or "").strip(),
            "contract_key": str(dry_command_executor_plan.get("contract_key") or "").strip(),
            "dry_executor_state": str(dry_command_executor_plan.get("dry_executor_state") or "").strip().lower(),
            "mutation_gate_state": str(dry_command_executor_plan.get("mutation_gate_state") or "").strip().lower(),
            "target_scope": str(dry_command_executor_plan.get("target_scope") or "").strip(),
            "owner_class": str(dry_command_executor_plan.get("owner_class") or "").strip(),
            "command_class": str(dry_command_executor_plan.get("command_class") or "").strip(),
            "command_module": str(dry_command_executor_plan.get("command_module") or "").strip(),
            "command_constructor": str(dry_command_executor_plan.get("command_constructor") or "").strip(),
            "label_preview": str(dry_command_executor_plan.get("label_preview") or "").strip(),
            "apply_callback_name": str(dry_command_executor_plan.get("apply_callback_name") or "").strip(),
            "apply_callback_owner_class": str(dry_command_executor_plan.get("apply_callback_owner_class") or "").strip(),
            "payload_delta_kind": str(dry_command_executor_plan.get("payload_delta_kind") or "").strip(),
            "materialized_payload_count": int(dry_command_executor_plan.get("materialized_payload_count") or 0),
            "before_payload_summary": dict(dry_command_executor_plan.get("before_payload_summary") or {}) if isinstance(dry_command_executor_plan.get("before_payload_summary"), dict) else {},
            "after_payload_summary": dict(dry_command_executor_plan.get("after_payload_summary") or {}) if isinstance(dry_command_executor_plan.get("after_payload_summary"), dict) else {},
            "do_call_count": int(dry_command_executor_plan.get("do_call_count") or 0),
            "undo_call_count": int(dry_command_executor_plan.get("undo_call_count") or 0),
            "callback_call_count": int(dry_command_executor_plan.get("callback_call_count") or 0),
            "callback_trace": [str(x).strip() for x in list(dry_command_executor_plan.get("callback_trace") or []) if str(x).strip()],
            "callback_payload_digests": [str(x).strip() for x in list(dry_command_executor_plan.get("callback_payload_digests") or []) if str(x).strip()],
            "total_simulation_step_count": int(dry_command_executor_plan.get("total_simulation_step_count") or 0),
            "ready_simulation_step_count": int(dry_command_executor_plan.get("ready_simulation_step_count") or 0),
            "simulation_steps": [dict(x or {}) for x in list(dry_command_executor_plan.get("simulation_steps") or []) if isinstance(x, dict)],
            "simulation_sequence": [str(x).strip() for x in list(dry_command_executor_plan.get("simulation_sequence") or []) if str(x).strip()],
            "future_executor_stub": str(dry_command_executor_plan.get("future_executor_stub") or "").strip(),
            "future_live_executor_stub": str(dry_command_executor_plan.get("future_live_executor_stub") or "").strip(),
            "blocked_by": [str(x).strip() for x in list(dry_command_executor_plan.get("blocked_by") or []) if str(x).strip()],
            "pending_by": [str(x).strip() for x in list(dry_command_executor_plan.get("pending_by") or []) if str(x).strip()],
            "summary": str(dry_command_executor_plan.get("summary") or "").strip(),
        }
        try:
            dry_run_plan = dict(plan.get("runtime_snapshot_dry_run") or {})
        except Exception:
            dry_run_plan = {}
        runtime_snapshot_dry_run = {
            "runner_key": str(dry_run_plan.get("runner_key") or "").strip(),
            "transaction_key": str(dry_run_plan.get("transaction_key") or "").strip(),
            "bundle_key": str(dry_run_plan.get("bundle_key") or "").strip(),
            "dry_run_mode": str(dry_run_plan.get("dry_run_mode") or "").strip(),
            "runner_state": str(dry_run_plan.get("runner_state") or "").strip().lower(),
            "phase_count": int(dry_run_plan.get("phase_count") or 0),
            "ready_phase_count": int(dry_run_plan.get("ready_phase_count") or 0),
            "capture_sequence": [str(x).strip() for x in list(dry_run_plan.get("capture_sequence") or []) if str(x).strip()],
            "restore_sequence": [str(x).strip() for x in list(dry_run_plan.get("restore_sequence") or []) if str(x).strip()],
            "rollback_sequence": [str(x).strip() for x in list(dry_run_plan.get("rollback_sequence") or []) if str(x).strip()],
            "rehearsed_steps": [str(x).strip() for x in list(dry_run_plan.get("rehearsed_steps") or []) if str(x).strip()],
            "phase_results": [dict(x or {}) for x in list(dry_run_plan.get("phase_results") or []) if isinstance(x, dict)],
            "capture_method_calls": [str(x).strip() for x in list(dry_run_plan.get("capture_method_calls") or []) if str(x).strip()],
            "restore_method_calls": [str(x).strip() for x in list(dry_run_plan.get("restore_method_calls") or []) if str(x).strip()],
            "state_carrier_calls": [str(x).strip() for x in list(dry_run_plan.get("state_carrier_calls") or []) if str(x).strip()],
            "state_carrier_summary": str(dry_run_plan.get("state_carrier_summary") or "").strip(),
            "state_container_calls": [str(x).strip() for x in list(dry_run_plan.get("state_container_calls") or []) if str(x).strip()],
            "state_container_summary": str(dry_run_plan.get("state_container_summary") or "").strip(),
            "state_holder_calls": [str(x).strip() for x in list(dry_run_plan.get("state_holder_calls") or []) if str(x).strip()],
            "state_holder_summary": str(dry_run_plan.get("state_holder_summary") or "").strip(),
            "state_slot_calls": [str(x).strip() for x in list(dry_run_plan.get("state_slot_calls") or []) if str(x).strip()],
            "state_slot_summary": str(dry_run_plan.get("state_slot_summary") or "").strip(),
            "state_store_calls": [str(x).strip() for x in list(dry_run_plan.get("state_store_calls") or []) if str(x).strip()],
            "state_store_summary": str(dry_run_plan.get("state_store_summary") or "").strip(),
            "state_registry_calls": [str(x).strip() for x in list(dry_run_plan.get("state_registry_calls") or []) if str(x).strip()],
            "state_registry_summary": str(dry_run_plan.get("state_registry_summary") or "").strip(),
            "state_registry_backend_calls": [str(x).strip() for x in list(dry_run_plan.get("state_registry_backend_calls") or []) if str(x).strip()],
            "state_registry_backend_summary": str(dry_run_plan.get("state_registry_backend_summary") or "").strip(),
            "state_registry_backend_adapter_calls": [str(x).strip() for x in list(dry_run_plan.get("state_registry_backend_adapter_calls") or []) if str(x).strip()],
            "state_registry_backend_adapter_summary": str(dry_run_plan.get("state_registry_backend_adapter_summary") or "").strip(),
            "runner_dispatch_summary": str(dry_run_plan.get("runner_dispatch_summary") or "").strip(),
            "commit_rehearsed": bool(dry_run_plan.get("commit_rehearsed")),
            "rollback_rehearsed": bool(dry_run_plan.get("rollback_rehearsed")),
            "dry_run_stub": str(dry_run_plan.get("dry_run_stub") or "").strip(),
        }
        runtime_snapshot_preview = []
        for item in list(plan.get("runtime_snapshot_preview") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            ref = str(item.get("ref") or "").strip()
            item_summary = str(item.get("summary") or "").strip()
            available = bool(item.get("available"))
            if name:
                runtime_snapshot_preview.append((name, ref, available, item_summary))
        runtime_snapshot_handles = []
        for item in list(plan.get("runtime_snapshot_handles") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            handle_key = str(item.get("handle_key") or "").strip()
            capture_state = str(item.get("capture_state") or "").strip().lower()
            owner_scope = str(item.get("owner_scope") or "").strip()
            owner_ids = [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()]
            item_summary = str(item.get("summary") or "").strip()
            capture_stub = str(item.get("capture_stub") or "").strip()
            if name:
                runtime_snapshot_handles.append((name, handle_key, capture_state, owner_scope, owner_ids, item_summary, capture_stub))
        runtime_snapshot_captures = []
        for item in list(plan.get("runtime_snapshot_captures") or []):
            try:
                item = dict(item or {})
            except Exception:
                item = {}
            name = str(item.get("name") or "").strip()
            capture_key = str(item.get("capture_key") or "").strip()
            capture_object_kind = str(item.get("capture_object_kind") or "").strip()
            capture_state = str(item.get("capture_state") or "").strip().lower()
            owner_scope = str(item.get("owner_scope") or "").strip()
            owner_ids = [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()]
            capture_stub = str(item.get("capture_stub") or "").strip()
            payload_preview = dict(item.get("payload_preview") or {}) if isinstance(item.get("payload_preview"), dict) else {}
            payload_entry_count = int(item.get("payload_entry_count") or 0)
            if name:
                runtime_snapshot_captures.append((name, capture_key, capture_object_kind, capture_state, owner_scope, owner_ids, capture_stub, payload_entry_count, payload_preview))
        readiness_summary = str(plan.get("readiness_summary") or "").strip()
        impact_summary = str(plan.get("impact_summary") or "").strip()
        message = str(plan.get("blocked_message") or "SmartDrop noch gesperrt: Audio->Instrument-Morphing ist noch nicht freigeschaltet.")
        can_apply = bool(plan.get("can_apply"))
        try:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("SmartDrop Sicherheitspruefung")
            if can_apply:
                box.setText(f"{plugin_name} wirklich auf {track_name} morphen?")
            else:
                box.setText(f"{plugin_name} kann noch nicht direkt auf {track_name} gemorpht werden.")
            info_lines = [message]
            if track_summary:
                info_lines.append(f"Zielspur: {track_summary}")
            if impact_summary:
                info_lines.append(impact_summary)
            if transaction_summary:
                info_lines.append(transaction_summary)
            if snapshot_ref_summary:
                info_lines.append(snapshot_ref_summary)
            if runtime_snapshot_summary:
                info_lines.append(runtime_snapshot_summary)
            if runtime_snapshot_handle_summary:
                info_lines.append(runtime_snapshot_handle_summary)
            if runtime_snapshot_capture_summary:
                info_lines.append(runtime_snapshot_capture_summary)
            if runtime_snapshot_instance_summary:
                info_lines.append(runtime_snapshot_instance_summary)
            if runtime_snapshot_object_summary:
                info_lines.append(runtime_snapshot_object_summary)
            if runtime_snapshot_stub_summary:
                info_lines.append(runtime_snapshot_stub_summary)
            if runtime_snapshot_state_carrier_summary:
                info_lines.append(runtime_snapshot_state_carrier_summary)
            if runtime_snapshot_state_holder_summary:
                info_lines.append(runtime_snapshot_state_holder_summary)
            if runtime_snapshot_state_slot_summary:
                info_lines.append(runtime_snapshot_state_slot_summary)
            if runtime_snapshot_state_store_summary:
                info_lines.append(runtime_snapshot_state_store_summary)
            if runtime_snapshot_state_registry_summary:
                info_lines.append(runtime_snapshot_state_registry_summary)
            if runtime_snapshot_state_registry_backend_summary:
                info_lines.append(runtime_snapshot_state_registry_backend_summary)
            if runtime_snapshot_state_registry_backend_adapter_summary:
                info_lines.append(runtime_snapshot_state_registry_backend_adapter_summary)
            if runtime_snapshot_bundle_summary:
                info_lines.append(runtime_snapshot_bundle_summary)
            if runtime_snapshot_apply_runner_summary:
                info_lines.append(runtime_snapshot_apply_runner_summary)
            if runtime_snapshot_dry_run_summary:
                info_lines.append(runtime_snapshot_dry_run_summary)
            if first_minimal_case_summary:
                info_lines.append(first_minimal_case_summary)
            if runtime_snapshot_precommit_contract_summary:
                info_lines.append(runtime_snapshot_precommit_contract_summary)
            if runtime_snapshot_atomic_entrypoints_summary:
                info_lines.append(runtime_snapshot_atomic_entrypoints_summary)
            if runtime_snapshot_mutation_gate_capsule_summary:
                info_lines.append(runtime_snapshot_mutation_gate_capsule_summary)
            if runtime_snapshot_command_undo_shell_summary:
                info_lines.append(runtime_snapshot_command_undo_shell_summary)
            if runtime_snapshot_command_factory_payload_summary:
                info_lines.append(runtime_snapshot_command_factory_payload_summary)
            if runtime_snapshot_preview_command_construction_summary:
                info_lines.append(runtime_snapshot_preview_command_construction_summary)
            if runtime_snapshot_dry_command_executor_summary:
                info_lines.append(runtime_snapshot_dry_command_executor_summary)
            if readiness_summary:
                info_lines.append(readiness_summary)
            if can_apply:
                info_lines.append("Bitte nur bestaetigen, wenn die Sicherheitspruefung nachvollziehbar ist.")
            else:
                info_lines.append("Dieser Dialog ist aktuell nur eine Sicherheitsvorschau - es wird noch nichts veraendert.")
            box.setInformativeText("\n\n".join([ln for ln in info_lines if ln]))
            detail_sections = []
            if blocked_reasons:
                detail_sections.append(
                    "Risiken / Blocker:\n" + "\n".join([f"- {reason}" for reason in blocked_reasons])
                )
            if rollback_lines:
                detail_sections.append(
                    "Rueckbau vor echter Freigabe:\n" + "\n".join([f"- {line}" for line in rollback_lines])
                )
            if future_apply_steps:
                detail_sections.append(
                    "Spaetere atomare Apply-Phase:\n" + "\n".join(future_apply_steps)
                )
            if required_snapshots:
                detail_sections.append(
                    "Noetige Snapshots:\n" + "\n".join([f"- {item}" for item in required_snapshots])
                )
            if snapshot_refs:
                detail_sections.append(
                    "Geplante Snapshot-Referenzen:\n" + "\n".join([f"- {name} -> {ref}" for (name, ref) in snapshot_refs])
                )
            if runtime_snapshot_preview:
                runtime_lines = []
                for (name, ref, available, summary) in runtime_snapshot_preview:
                    prefix = "READY" if available else "PENDING"
                    line = f"- [{prefix}] {name}"
                    if ref:
                        line += f" -> {ref}"
                    if summary:
                        line += f" — {summary}"
                    runtime_lines.append(line)
                detail_sections.append(
                    "Aktuelle Runtime-Snapshot-Vorschau:\n" + "\n".join(runtime_lines)
                )
            if runtime_snapshot_handles:
                handle_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                handle_lines = []
                for (name, handle_key, capture_state, owner_scope, owner_ids, summary, capture_stub) in runtime_snapshot_handles:
                    prefix = handle_state_label.get(capture_state, capture_state.upper() or "INFO")
                    scope_text = f"scope={owner_scope}" if owner_scope else "scope=unbekannt"
                    owner_text = f"targets={len(owner_ids)}"
                    line = f"- [{prefix}] {name} -> {handle_key} ({scope_text}, {owner_text})"
                    if capture_stub:
                        line += f" · stub={capture_stub}"
                    if summary:
                        line += f" — {summary}"
                    handle_lines.append(line)
                detail_sections.append(
                    "Runtime-Snapshot-Handle-Vorschau:\n" + "\n".join(handle_lines)
                )
            if runtime_snapshot_captures:
                capture_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                capture_lines = []
                for (name, capture_key, capture_object_kind, capture_state, owner_scope, owner_ids, capture_stub, payload_entry_count, payload_preview) in runtime_snapshot_captures:
                    prefix = capture_state_label.get(capture_state, capture_state.upper() or "INFO")
                    scope_text = f"scope={owner_scope}" if owner_scope else "scope=unbekannt"
                    owner_text = f"targets={len(owner_ids)}"
                    line = f"- [{prefix}] {name} -> {capture_key} ({capture_object_kind or 'capture'}, {scope_text}, {owner_text})"
                    if capture_stub:
                        line += f" · stub={capture_stub}"
                    if payload_entry_count > 0:
                        line += f" · payload={payload_entry_count}"
                    preview_parts = []
                    for p_key, p_val in list((payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    capture_lines.append(line)
                detail_sections.append(
                    "Runtime-Capture-Objekt-Vorschau:\n" + "\n".join(capture_lines)
                )
            if runtime_snapshot_instances:
                instance_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                instance_lines = []
                for (name, snapshot_instance_key, snapshot_instance_kind, snapshot_state, owner_scope, owner_ids, snapshot_stub, snapshot_payload_entry_count, payload_digest, snapshot_payload) in runtime_snapshot_instances:
                    prefix = instance_state_label.get(snapshot_state, snapshot_state.upper() or "INFO")
                    scope_text = f"scope={owner_scope}" if owner_scope else "scope=unbekannt"
                    owner_text = f"targets={len(owner_ids)}"
                    line = f"- [{prefix}] {name} -> {snapshot_instance_key} ({snapshot_instance_kind or 'instance'}, {scope_text}, {owner_text})"
                    if snapshot_stub:
                        line += f" · stub={snapshot_stub}"
                    if snapshot_payload_entry_count > 0:
                        line += f" · payload={snapshot_payload_entry_count}"
                    if payload_digest:
                        line += f" · digest={payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((snapshot_payload or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    instance_lines.append(line)
                detail_sections.append(
                    "Runtime-Snapshot-Instanz-Vorschau:\n" + "\n".join(instance_lines)
                )
            if runtime_snapshot_stubs:
                stub_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                stub_lines = []
                for (name, snapshot_object_key, snapshot_object_class, bind_state, stub_key, stub_class, dispatch_state, capture_method, restore_method, rollback_slot, supports_capture_preview, supports_restore_preview, factory_method, capture_stub, restore_stub, rollback_stub) in runtime_snapshot_stubs:
                    prefix = stub_state_label.get(dispatch_state, dispatch_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {stub_key} ({stub_class or 'RuntimeSnapshotStub'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if factory_method:
                        line += f" · factory={factory_method}"
                    method_parts = []
                    if capture_method:
                        method_parts.append(f"capture={capture_method}")
                    if restore_method:
                        method_parts.append(f"restore={restore_method}")
                    if rollback_slot:
                        method_parts.append(f"rollback={rollback_slot}")
                    if method_parts:
                        line += " — " + "; ".join(method_parts)
                    stub_parts = []
                    if supports_capture_preview:
                        stub_parts.append("capture-preview")
                    if supports_restore_preview:
                        stub_parts.append("restore-preview")
                    if capture_stub:
                        stub_parts.append(capture_stub)
                    if restore_stub:
                        stub_parts.append(restore_stub)
                    if rollback_stub:
                        stub_parts.append(rollback_stub)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:4])}"
                    stub_lines.append(line)
                detail_sections.append(
                    "Runtime-Snapshot-Stubs / Klassenkopplung:\n" + "\n".join(stub_lines)
                )
            if runtime_snapshot_state_carriers:
                carrier_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                carrier_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, carrier_state, capture_method, restore_method, rollback_slot, supports_capture_state, supports_restore_state, bind_method, capture_state_stub, restore_state_stub, rollback_state_stub, state_payload_entry_count, state_payload_digest, state_payload_preview) in runtime_snapshot_state_carriers:
                    prefix = carrier_state_label.get(carrier_state, carrier_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {carrier_key} ({carrier_class or 'RuntimeSnapshotStateCarrier'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if stub_key:
                        line += f" · stub={stub_key}"
                    if stub_class:
                        line += f" · stub-class={stub_class}"
                    if bind_method:
                        line += f" · bind={bind_method}"
                    method_parts = []
                    if capture_method:
                        method_parts.append(f"capture={capture_method}")
                    if restore_method:
                        method_parts.append(f"restore={restore_method}")
                    if rollback_slot:
                        method_parts.append(f"rollback={rollback_slot}")
                    if method_parts:
                        line += " — " + "; ".join(method_parts)
                    stub_parts = []
                    if supports_capture_state:
                        stub_parts.append("capture-state")
                    if supports_restore_state:
                        stub_parts.append("restore-state")
                    if capture_state_stub:
                        stub_parts.append(capture_state_stub)
                    if restore_state_stub:
                        stub_parts.append(restore_state_stub)
                    if rollback_state_stub:
                        stub_parts.append(rollback_state_stub)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:4])}"
                    if state_payload_entry_count > 0:
                        line += f" · payload={state_payload_entry_count}"
                    if state_payload_digest:
                        line += f" · digest={state_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((state_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    carrier_lines.append(line)
                detail_sections.append(
                    "Runtime-Zustandstraeger / State-Carrier:\n" + "\n".join(carrier_lines)
                )
            if runtime_snapshot_state_containers:
                container_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                container_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, container_state, capture_method, restore_method, rollback_slot, supports_capture_container, supports_restore_container, supports_runtime_state_container, instantiate_method, capture_container_stub, restore_container_stub, rollback_container_stub, runtime_state_stub, state_payload_entry_count, state_payload_digest, state_payload_preview, container_payload_entry_count, container_payload_digest, container_payload_preview) in runtime_snapshot_state_containers:
                    prefix = container_state_label.get(container_state, container_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {container_key} ({container_class or 'RuntimeSnapshotStateContainer'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if carrier_key:
                        line += f" · carrier={carrier_key}"
                    if carrier_class:
                        line += f" · carrier-class={carrier_class}"
                    if stub_key:
                        line += f" · stub={stub_key}"
                    if stub_class:
                        line += f" · stub-class={stub_class}"
                    if instantiate_method:
                        line += f" · bind={instantiate_method}"
                    method_parts = []
                    if capture_method:
                        method_parts.append(f"capture={capture_method}")
                    if restore_method:
                        method_parts.append(f"restore={restore_method}")
                    if rollback_slot:
                        method_parts.append(f"rollback={rollback_slot}")
                    if method_parts:
                        line += " — " + "; ".join(method_parts)
                    stub_parts = []
                    if supports_capture_container:
                        stub_parts.append("capture-container")
                    if supports_restore_container:
                        stub_parts.append("restore-container")
                    if supports_runtime_state_container:
                        stub_parts.append("runtime-state")
                    if capture_container_stub:
                        stub_parts.append(capture_container_stub)
                    if restore_container_stub:
                        stub_parts.append(restore_container_stub)
                    if rollback_container_stub:
                        stub_parts.append(rollback_container_stub)
                    if runtime_state_stub:
                        stub_parts.append(runtime_state_stub)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if container_payload_entry_count > 0:
                        line += f" · payload={container_payload_entry_count}"
                    if container_payload_digest:
                        line += f" · digest={container_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((container_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    container_lines.append(line)
                detail_sections.append(
                    "Separate Runtime-State-Container:\n" + "\n".join(container_lines)
                )
            if runtime_snapshot_state_holders:
                holder_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                holder_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, holder_state, capture_method, restore_method, rollback_slot, supports_capture_holder, supports_restore_holder, supports_runtime_state_holder, instantiate_method, capture_holder_stub, restore_holder_stub, rollback_holder_stub, runtime_holder_stub, container_payload_entry_count, container_payload_digest, container_payload_preview, holder_payload_entry_count, holder_payload_digest, holder_payload_preview) in runtime_snapshot_state_holders:
                    prefix = holder_state_label.get(holder_state, holder_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {holder_key} ({holder_class or 'RuntimeSnapshotStateHolder'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if container_key:
                        line += f" · container={container_key}"
                    if container_class:
                        line += f" · container-class={container_class}"
                    if carrier_key:
                        line += f" · carrier={carrier_key}"
                    if carrier_class:
                        line += f" · carrier-class={carrier_class}"
                    if stub_key:
                        line += f" · stub={stub_key}"
                    if stub_class:
                        line += f" · stub-class={stub_class}"
                    if instantiate_method:
                        line += f" · bind={instantiate_method}"
                    method_parts = []
                    if capture_method:
                        method_parts.append(f"capture={capture_method}")
                    if restore_method:
                        method_parts.append(f"restore={restore_method}")
                    if rollback_slot:
                        method_parts.append(f"rollback={rollback_slot}")
                    if method_parts:
                        line += " — " + "; ".join(method_parts)
                    stub_parts = []
                    if supports_capture_holder:
                        stub_parts.append("capture-holder")
                    if supports_restore_holder:
                        stub_parts.append("restore-holder")
                    if supports_runtime_state_holder:
                        stub_parts.append("runtime-holder")
                    if capture_holder_stub:
                        stub_parts.append(capture_holder_stub)
                    if restore_holder_stub:
                        stub_parts.append(restore_holder_stub)
                    if rollback_holder_stub:
                        stub_parts.append(rollback_holder_stub)
                    if runtime_holder_stub:
                        stub_parts.append(runtime_holder_stub)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if holder_payload_entry_count > 0:
                        line += f" · payload={holder_payload_entry_count}"
                    if holder_payload_digest:
                        line += f" · digest={holder_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((holder_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    holder_lines.append(line)
                detail_sections.append(
                    "Separate Runtime-State-Halter:\n" + "\n".join(holder_lines)
                )

            if runtime_snapshot_state_slots:
                slot_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                slot_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, slot_state, capture_method, restore_method, rollback_slot, supports_capture_slot, supports_restore_slot, supports_runtime_state_slot, instantiate_method, capture_slot_stub, restore_slot_stub, rollback_slot_stub, runtime_state_slot_stub, holder_payload_entry_count, holder_payload_digest, holder_payload_preview, slot_payload_entry_count, slot_payload_digest, slot_payload_preview) in runtime_snapshot_state_slots:
                    prefix = slot_state_label.get(slot_state, slot_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {slot_key} ({slot_class or 'RuntimeSnapshotStateSlot'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if holder_key:
                        line += f" · holder={holder_key}"
                    if holder_class:
                        line += f" · holder-class={holder_class}"
                    if container_key:
                        line += f" · container={container_key}"
                    if container_class:
                        line += f" · container-class={container_class}"
                    if carrier_key:
                        line += f" · carrier={carrier_key}"
                    if carrier_class:
                        line += f" · carrier-class={carrier_class}"
                    if stub_key:
                        line += f" · stub={stub_key}"
                    if stub_class:
                        line += f" · stub-class={stub_class}"
                    if instantiate_method:
                        line += f" · bind={instantiate_method}"
                    method_parts = []
                    if capture_method:
                        method_parts.append(f"capture={capture_method}")
                    if restore_method:
                        method_parts.append(f"restore={restore_method}")
                    if rollback_slot:
                        method_parts.append(f"rollback={rollback_slot}")
                    if method_parts:
                        line += " — " + "; ".join(method_parts)
                    stub_parts = []
                    if supports_capture_slot:
                        stub_parts.append("capture-slot")
                    if supports_restore_slot:
                        stub_parts.append("restore-slot")
                    if supports_runtime_state_slot:
                        stub_parts.append("runtime-slot")
                    for stub_text in (capture_slot_stub, restore_slot_stub, rollback_slot_stub, runtime_state_slot_stub):
                        if stub_text:
                            stub_parts.append(stub_text)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if slot_payload_entry_count > 0:
                        line += f" · payload={slot_payload_entry_count}"
                    if slot_payload_digest:
                        line += f" · digest={slot_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((slot_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    slot_lines.append(line)
                detail_sections.append(
                    "Runtime-State-Slots / Snapshot-State-Speicher:\n" + "\n".join(slot_lines)
                )

            if runtime_snapshot_state_stores:
                store_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                store_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, store_state, capture_method, restore_method, rollback_slot, supports_capture_store, supports_restore_store, supports_runtime_state_store, instantiate_method, capture_store_stub, restore_store_stub, rollback_store_stub, runtime_state_store_stub, capture_handle_key, restore_handle_key, rollback_handle_key, capture_handle_state, slot_payload_entry_count, slot_payload_digest, slot_payload_preview, store_payload_entry_count, store_payload_digest, store_payload_preview) in runtime_snapshot_state_stores:
                    prefix = store_state_label.get(store_state, store_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {store_key} ({store_class or 'RuntimeSnapshotStateStore'})"
                    if snapshot_object_key:
                        line += f" · obj={snapshot_object_key}"
                    if snapshot_object_class:
                        line += f" · class={snapshot_object_class}"
                    if slot_key:
                        line += f" · slot={slot_key}"
                    if slot_class:
                        line += f" · slot-class={slot_class}"
                    if holder_key:
                        line += f" · holder={holder_key}"
                    if holder_class:
                        line += f" · holder-class={holder_class}"
                    if instantiate_method:
                        line += f" · bind={instantiate_method}"
                    handle_parts = []
                    if capture_handle_key:
                        handle_parts.append(f"capture-handle={capture_handle_key}")
                    if restore_handle_key:
                        handle_parts.append(f"restore-handle={restore_handle_key}")
                    if rollback_handle_key:
                        handle_parts.append(f"rollback-handle={rollback_handle_key}")
                    if capture_handle_state:
                        handle_parts.append(f"handle-state={capture_handle_state}")
                    if handle_parts:
                        line += " — " + "; ".join(handle_parts[:4])
                    stub_parts = []
                    if supports_capture_store:
                        stub_parts.append("capture-store")
                    if supports_restore_store:
                        stub_parts.append("restore-store")
                    if supports_runtime_state_store:
                        stub_parts.append("runtime-store")
                    for stub_text in (capture_store_stub, restore_store_stub, rollback_store_stub, runtime_state_store_stub):
                        if stub_text:
                            stub_parts.append(stub_text)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if store_payload_entry_count > 0:
                        line += f" · payload={store_payload_entry_count}"
                    if store_payload_digest:
                        line += f" · digest={store_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((store_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    store_lines.append(line)
                detail_sections.append(
                    "Runtime-State-Stores / Capture-Handles:\n" + "\n".join(store_lines)
                )

            if runtime_snapshot_state_registries:
                registry_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, registry_state, capture_method, restore_method, rollback_slot, supports_capture_registry, supports_restore_registry, supports_runtime_state_registry, instantiate_method, capture_registry_stub, restore_registry_stub, rollback_registry_stub, runtime_state_registry_stub, capture_handle_key, restore_handle_key, rollback_handle_key, handle_store_key, handle_store_class, handle_store_state, store_payload_entry_count, store_payload_digest, store_payload_preview, registry_payload_entry_count, registry_payload_digest, registry_payload_preview) in runtime_snapshot_state_registries:
                    prefix = state_label.get(registry_state, registry_state.upper() if registry_state else "INFO")
                    line = f"- [{prefix}] {name} ({snapshot_object_class or 'snapshot'}) -> {registry_key or 'registry'}"
                    key_parts = []
                    for key_name, key_val in (("stub", stub_key), ("carrier", carrier_key), ("container", container_key), ("holder", holder_key), ("slot", slot_key), ("store", store_key), ("handle-store", handle_store_key)):
                        if key_val:
                            key_parts.append(f"{key_name}={key_val}")
                    if key_parts:
                        line += " — " + "; ".join(key_parts[:7])
                    handle_parts = []
                    for key_name, key_val in (("capture-handle", capture_handle_key), ("restore-handle", restore_handle_key), ("rollback-handle", rollback_handle_key), ("handle-store-class", handle_store_class)):
                        if key_val:
                            handle_parts.append(f"{key_name}={key_val}")
                    if handle_store_state:
                        handle_parts.append(f"handle-store-state={handle_store_state}")
                    if handle_parts:
                        line += " · " + " | ".join(handle_parts[:5])
                    stub_parts = []
                    if supports_capture_registry:
                        stub_parts.append("capture-registry")
                    if supports_restore_registry:
                        stub_parts.append("restore-registry")
                    if supports_runtime_state_registry:
                        stub_parts.append("runtime-registry")
                    for stub_text in (capture_registry_stub, restore_registry_stub, rollback_registry_stub, runtime_state_registry_stub):
                        if stub_text:
                            stub_parts.append(stub_text)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if registry_payload_entry_count > 0:
                        line += f" · payload={registry_payload_entry_count}"
                    if registry_payload_digest:
                        line += f" · digest={registry_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((registry_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    registry_lines.append(line)
                detail_sections.append(
                    "Runtime-State-Registries / Handle-Speicher\n" + "\n".join(registry_lines)
                )

            if runtime_snapshot_state_registry_backends:
                backend_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                backend_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, backend_key, backend_class, backend_state, capture_method, restore_method, rollback_slot, supports_capture_backend, supports_restore_backend, supports_runtime_state_backend, instantiate_method, capture_backend_stub, restore_backend_stub, rollback_backend_stub, runtime_state_backend_stub, handle_register_key, handle_register_class, handle_register_state, registry_slot_key, registry_slot_class, registry_slot_state, registry_payload_entry_count, registry_payload_digest, registry_payload_preview, backend_payload_entry_count, backend_payload_digest, backend_payload_preview) in runtime_snapshot_state_registry_backends:
                    prefix = backend_state_label.get(backend_state, backend_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {backend_class or 'backend'}"
                    id_parts = []
                    if backend_key:
                        id_parts.append(f"backend={backend_key}")
                    if registry_key:
                        id_parts.append(f"registry={registry_key}")
                    if handle_register_key:
                        id_parts.append(f"handle-register={handle_register_key}")
                    if registry_slot_key:
                        id_parts.append(f"registry-slot={registry_slot_key}")
                    if id_parts:
                        line += " · " + " | ".join(id_parts[:5])
                    stub_parts = []
                    if supports_capture_backend:
                        stub_parts.append("capture-backend")
                    if supports_restore_backend:
                        stub_parts.append("restore-backend")
                    if supports_runtime_state_backend:
                        stub_parts.append("runtime-backend")
                    for stub_text in (capture_backend_stub, restore_backend_stub, rollback_backend_stub, runtime_state_backend_stub):
                        if stub_text:
                            stub_parts.append(stub_text)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if backend_payload_entry_count > 0:
                        line += f" · payload={backend_payload_entry_count}"
                    if backend_payload_digest:
                        line += f" · digest={backend_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((backend_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    backend_lines.append(line)
                detail_sections.append(
                    "Runtime-State-Registry-Backends / Handle-Register / Registry-Slots\n" + "\n".join(backend_lines)
                )

            if runtime_snapshot_state_registry_backend_adapters:
                adapter_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                adapter_lines = []
                for (name, snapshot_object_key, snapshot_object_class, stub_key, stub_class, carrier_key, carrier_class, container_key, container_class, holder_key, holder_class, slot_key, slot_class, store_key, store_class, registry_key, registry_class, backend_key, backend_class, adapter_key, adapter_class, adapter_state, capture_method, restore_method, rollback_slot, supports_capture_backend_adapter, supports_restore_backend_adapter, supports_runtime_state_backend_adapter, instantiate_method, capture_adapter_stub, restore_adapter_stub, rollback_adapter_stub, runtime_state_backend_adapter_stub, backend_store_adapter_key, backend_store_adapter_class, backend_store_adapter_state, registry_slot_backend_key, registry_slot_backend_class, registry_slot_backend_state, backend_payload_entry_count, backend_payload_digest, backend_payload_preview, adapter_payload_entry_count, adapter_payload_digest, adapter_payload_preview) in runtime_snapshot_state_registry_backend_adapters:
                    prefix = adapter_state_label.get(adapter_state, adapter_state.upper() or "INFO")
                    line = f"- [{prefix}] {name} -> {adapter_class or 'backend-adapter'}"
                    id_parts = []
                    if adapter_key:
                        id_parts.append(f"adapter={adapter_key}")
                    if backend_key:
                        id_parts.append(f"backend={backend_key}")
                    if backend_store_adapter_key:
                        id_parts.append(f"backend-store-adapter={backend_store_adapter_key}")
                    if registry_slot_backend_key:
                        id_parts.append(f"registry-slot-backend={registry_slot_backend_key}")
                    if id_parts:
                        line += " · " + " | ".join(id_parts[:5])
                    stub_parts = []
                    if supports_capture_backend_adapter:
                        stub_parts.append("capture-backend-adapter")
                    if supports_restore_backend_adapter:
                        stub_parts.append("restore-backend-adapter")
                    if supports_runtime_state_backend_adapter:
                        stub_parts.append("runtime-backend-adapter")
                    for stub_text in (capture_adapter_stub, restore_adapter_stub, rollback_adapter_stub, runtime_state_backend_adapter_stub):
                        if stub_text:
                            stub_parts.append(stub_text)
                    if stub_parts:
                        line += f" · {' | '.join(stub_parts[:5])}"
                    if adapter_payload_entry_count > 0:
                        line += f" · payload={adapter_payload_entry_count}"
                    if adapter_payload_digest:
                        line += f" · digest={adapter_payload_digest}"
                    preview_parts = []
                    for p_key, p_val in list((adapter_payload_preview or {}).items())[:4]:
                        if isinstance(p_val, list):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        elif isinstance(p_val, dict):
                            preview_parts.append(f"{p_key}={len(p_val)}")
                        else:
                            preview_parts.append(f"{p_key}={p_val}")
                    if preview_parts:
                        line += f" — {'; '.join(preview_parts)}"
                    adapter_lines.append(line)
                detail_sections.append(
                    "Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends\n" + "\n".join(adapter_lines)
                )

            if runtime_snapshot_bundle.get("bundle_key"):
                bundle_prefix = bundle_state_label.get(str(runtime_snapshot_bundle.get("bundle_state") or "").strip().lower(), str(runtime_snapshot_bundle.get("bundle_state") or "").upper() or "INFO")
                bundle_lines = [
                    f"- [{bundle_prefix}] key={runtime_snapshot_bundle.get('bundle_key')}",
                    f"- type={runtime_snapshot_bundle.get('transaction_container_kind') or 'transaction-bundle'}",
                    f"- objektbindungen={runtime_snapshot_bundle.get('ready_object_count', 0)}/{runtime_snapshot_bundle.get('object_count', 0)}",
                    f"- benoetigte snapshots={runtime_snapshot_bundle.get('required_snapshot_count', 0)}",
                ]
                if runtime_snapshot_bundle.get("bundle_stub"):
                    bundle_lines.append(f"- bundle-stub={runtime_snapshot_bundle.get('bundle_stub')}")
                if runtime_snapshot_bundle.get("commit_stub"):
                    bundle_lines.append(f"- commit-stub={runtime_snapshot_bundle.get('commit_stub')}")
                if runtime_snapshot_bundle.get("rollback_stub"):
                    bundle_lines.append(f"- rollback-stub={runtime_snapshot_bundle.get('rollback_stub')}")
                if runtime_snapshot_bundle.get("capture_methods"):
                    bundle_lines.append(f"- capture-methoden={', '.join(runtime_snapshot_bundle.get('capture_methods')[:4])}")
                if runtime_snapshot_bundle.get("restore_methods"):
                    bundle_lines.append(f"- restore-methoden={', '.join(runtime_snapshot_bundle.get('restore_methods')[:4])}")
                if runtime_snapshot_bundle.get("rollback_slots"):
                    bundle_lines.append(f"- rollback-slots={', '.join(runtime_snapshot_bundle.get('rollback_slots')[:4])}")
                if runtime_snapshot_bundle.get("snapshot_object_keys"):
                    bundle_lines.append(f"- snapshot-objekte={len(runtime_snapshot_bundle.get('snapshot_object_keys'))}")
                if runtime_snapshot_bundle.get("payload_digests"):
                    bundle_lines.append(f"- payload-digests={', '.join(runtime_snapshot_bundle.get('payload_digests')[:3])}")
                detail_sections.append(
                    "Snapshot-Bundle / Transaktions-Container:\n" + "\n".join(bundle_lines)
                )
            if runtime_snapshot_apply_runner.get("runner_key"):
                apply_runner_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                apply_runner_prefix = apply_runner_state_label.get(str(runtime_snapshot_apply_runner.get("runner_state") or "").strip().lower(), str(runtime_snapshot_apply_runner.get("runner_state") or "").upper() or "INFO")
                apply_runner_lines = [
                    f"- [{apply_runner_prefix}] key={runtime_snapshot_apply_runner.get('runner_key')}",
                    f"- mode={runtime_snapshot_apply_runner.get('apply_mode') or 'read-only-snapshot-transaction-dispatch'}",
                    f"- bundle={runtime_snapshot_apply_runner.get('bundle_key') or runtime_snapshot_bundle.get('bundle_key') or 'n/a'}",
                    f"- phasen={runtime_snapshot_apply_runner.get('ready_phase_count', 0)}/{runtime_snapshot_apply_runner.get('phase_count', 0)}",
                ]
                if runtime_snapshot_apply_runner.get("apply_runner_stub"):
                    apply_runner_lines.append(f"- runner-stub={runtime_snapshot_apply_runner.get('apply_runner_stub')}")
                if runtime_snapshot_apply_runner.get("apply_sequence"):
                    apply_runner_lines.append(f"- apply-sequenz={', '.join(runtime_snapshot_apply_runner.get('apply_sequence')[:4])}")
                if runtime_snapshot_apply_runner.get("restore_sequence"):
                    apply_runner_lines.append(f"- restore-sequenz={', '.join(runtime_snapshot_apply_runner.get('restore_sequence')[:4])}")
                if runtime_snapshot_apply_runner.get("rollback_sequence"):
                    apply_runner_lines.append(f"- rollback-sequenz={', '.join(runtime_snapshot_apply_runner.get('rollback_sequence')[:4])}")
                if runtime_snapshot_apply_runner.get("rehearsed_steps"):
                    apply_runner_lines.append(f"- rehearsed-steps={len(runtime_snapshot_apply_runner.get('rehearsed_steps'))}")
                if runtime_snapshot_apply_runner.get("state_registry_backend_adapter_calls"):
                    apply_runner_lines.append(f"- state-registry-backend-adapter-calls={', '.join(runtime_snapshot_apply_runner.get('state_registry_backend_adapter_calls')[:4])}")
                if runtime_snapshot_apply_runner.get("state_registry_backend_adapter_summary"):
                    apply_runner_lines.append(f"- state-registry-backend-adapter={runtime_snapshot_apply_runner.get('state_registry_backend_adapter_summary')}")
                if runtime_snapshot_apply_runner.get("backend_store_adapter_calls"):
                    apply_runner_lines.append(f"- backend-store-adapter-calls={', '.join(runtime_snapshot_apply_runner.get('backend_store_adapter_calls')[:4])}")
                if runtime_snapshot_apply_runner.get("backend_store_adapter_summary"):
                    apply_runner_lines.append(f"- backend-store-adapter={runtime_snapshot_apply_runner.get('backend_store_adapter_summary')}")
                if runtime_snapshot_apply_runner.get("registry_slot_backend_calls"):
                    apply_runner_lines.append(f"- registry-slot-backend-calls={', '.join(runtime_snapshot_apply_runner.get('registry_slot_backend_calls')[:4])}")
                if runtime_snapshot_apply_runner.get("registry_slot_backend_summary"):
                    apply_runner_lines.append(f"- registry-slot-backend={runtime_snapshot_apply_runner.get('registry_slot_backend_summary')}")
                if runtime_snapshot_apply_runner.get("runner_dispatch_summary"):
                    apply_runner_lines.append(f"- dispatch={runtime_snapshot_apply_runner.get('runner_dispatch_summary')}")
                phase_results = runtime_snapshot_apply_runner.get("phase_results") or []
                for item in phase_results[:6]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    phase = str(item.get("phase") or "").strip() or "phase"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {phase} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    apply_runner_lines.append(line)
                detail_sections.append(
                    "Read-only Snapshot-Transaktions-Dispatch / Apply-Runner:\n" + "\n".join(apply_runner_lines)
                )
            if runtime_snapshot_dry_run.get("runner_key"):
                dry_run_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                dry_run_prefix = dry_run_state_label.get(str(runtime_snapshot_dry_run.get("runner_state") or "").strip().lower(), str(runtime_snapshot_dry_run.get("runner_state") or "").upper() or "INFO")
                dry_run_lines = [
                    f"- [{dry_run_prefix}] key={runtime_snapshot_dry_run.get('runner_key')}",
                    f"- mode={runtime_snapshot_dry_run.get('dry_run_mode') or 'read-only-transaction-rehearsal'}",
                    f"- bundle={runtime_snapshot_dry_run.get('bundle_key') or runtime_snapshot_bundle.get('bundle_key') or 'n/a'}",
                    f"- phasen={runtime_snapshot_dry_run.get('ready_phase_count', 0)}/{runtime_snapshot_dry_run.get('phase_count', 0)}",
                ]
                if runtime_snapshot_dry_run.get("dry_run_stub"):
                    dry_run_lines.append(f"- runner-stub={runtime_snapshot_dry_run.get('dry_run_stub')}")
                if runtime_snapshot_dry_run.get("capture_sequence"):
                    dry_run_lines.append(f"- capture-sequenz={', '.join(runtime_snapshot_dry_run.get('capture_sequence')[:4])}")
                if runtime_snapshot_dry_run.get("restore_sequence"):
                    dry_run_lines.append(f"- restore-sequenz={', '.join(runtime_snapshot_dry_run.get('restore_sequence')[:4])}")
                if runtime_snapshot_dry_run.get("rollback_sequence"):
                    dry_run_lines.append(f"- rollback-sequenz={', '.join(runtime_snapshot_dry_run.get('rollback_sequence')[:4])}")
                if runtime_snapshot_dry_run.get("rehearsed_steps"):
                    dry_run_lines.append(f"- rehearsed-steps={len(runtime_snapshot_dry_run.get('rehearsed_steps'))}")
                if runtime_snapshot_dry_run.get("capture_method_calls"):
                    dry_run_lines.append(f"- capture-calls={', '.join(runtime_snapshot_dry_run.get('capture_method_calls')[:4])}")
                if runtime_snapshot_dry_run.get("restore_method_calls"):
                    dry_run_lines.append(f"- restore-calls={', '.join(runtime_snapshot_dry_run.get('restore_method_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_carrier_calls"):
                    dry_run_lines.append(f"- state-carrier-calls={', '.join(runtime_snapshot_dry_run.get('state_carrier_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_carrier_summary"):
                    dry_run_lines.append(f"- state-carrier={runtime_snapshot_dry_run.get('state_carrier_summary')}")
                if runtime_snapshot_dry_run.get("state_container_calls"):
                    dry_run_lines.append(f"- state-container-calls={', '.join(runtime_snapshot_dry_run.get('state_container_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_container_summary"):
                    dry_run_lines.append(f"- state-container={runtime_snapshot_dry_run.get('state_container_summary')}")
                if runtime_snapshot_dry_run.get("state_holder_calls"):
                    dry_run_lines.append(f"- state-holder-calls={', '.join(runtime_snapshot_dry_run.get('state_holder_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_holder_summary"):
                    dry_run_lines.append(f"- state-holder={runtime_snapshot_dry_run.get('state_holder_summary')}")
                if runtime_snapshot_dry_run.get("state_slot_calls"):
                    dry_run_lines.append(f"- state-slot-calls={', '.join(runtime_snapshot_dry_run.get('state_slot_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_slot_summary"):
                    dry_run_lines.append(f"- state-slot={runtime_snapshot_dry_run.get('state_slot_summary')}")
                if runtime_snapshot_dry_run.get("state_store_calls"):
                    dry_run_lines.append(f"- state-store-calls={', '.join(runtime_snapshot_dry_run.get('state_store_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_store_summary"):
                    dry_run_lines.append(f"- state-store={runtime_snapshot_dry_run.get('state_store_summary')}")
                if runtime_snapshot_dry_run.get("state_registry_calls"):
                    dry_run_lines.append(f"- state-registry-calls={', '.join(runtime_snapshot_dry_run.get('state_registry_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_registry_summary"):
                    dry_run_lines.append(f"- state-registry={runtime_snapshot_dry_run.get('state_registry_summary')}")
                if runtime_snapshot_dry_run.get("state_registry_backend_calls"):
                    dry_run_lines.append(f"- state-registry-backend-calls={', '.join(runtime_snapshot_dry_run.get('state_registry_backend_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_registry_backend_summary"):
                    dry_run_lines.append(f"- state-registry-backend={runtime_snapshot_dry_run.get('state_registry_backend_summary')}")
                if runtime_snapshot_dry_run.get("state_registry_backend_adapter_calls"):
                    dry_run_lines.append(f"- state-registry-backend-adapter-calls={', '.join(runtime_snapshot_dry_run.get('state_registry_backend_adapter_calls')[:4])}")
                if runtime_snapshot_dry_run.get("state_registry_backend_adapter_summary"):
                    dry_run_lines.append(f"- state-registry-backend-adapter={runtime_snapshot_dry_run.get('state_registry_backend_adapter_summary')}")
                if runtime_snapshot_dry_run.get("runner_dispatch_summary"):
                    dry_run_lines.append(f"- dispatch={runtime_snapshot_dry_run.get('runner_dispatch_summary')}")
                phase_results = runtime_snapshot_dry_run.get("phase_results") or []
                for item in phase_results[:6]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    phase = str(item.get("phase") or "").strip() or "phase"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {phase} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    dry_run_lines.append(line)
                detail_sections.append(
                    "Read-only Dry-Run / Transaktions-Runner:\n" + "\n".join(dry_run_lines)
                )
            if runtime_snapshot_precommit_contract.get("contract_key"):
                precommit_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                precommit_prefix = precommit_state_label.get(str(runtime_snapshot_precommit_contract.get("contract_state") or "").strip().lower(), str(runtime_snapshot_precommit_contract.get("contract_state") or "").upper() or "INFO")
                precommit_lines = [
                    f"- [{precommit_prefix}] key={runtime_snapshot_precommit_contract.get('contract_key')}",
                    f"- scope={runtime_snapshot_precommit_contract.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- mutation-gate={runtime_snapshot_precommit_contract.get('mutation_gate_state') or 'blocked'}",
                    f"- vorschauphasen={runtime_snapshot_precommit_contract.get('ready_preview_phase_count', 0)}/{runtime_snapshot_precommit_contract.get('preview_phase_count', 0)}",
                    f"- bundle={runtime_snapshot_precommit_contract.get('bundle_key') or runtime_snapshot_bundle.get('bundle_key') or 'n/a'}",
                    f"- apply-runner={runtime_snapshot_precommit_contract.get('apply_runner_key') or runtime_snapshot_apply_runner.get('runner_key') or 'n/a'}",
                    f"- dry-run={runtime_snapshot_precommit_contract.get('dry_run_key') or runtime_snapshot_dry_run.get('runner_key') or 'n/a'}",
                ]
                if runtime_snapshot_precommit_contract.get("future_commit_stub"):
                    precommit_lines.append(f"- future-commit-stub={runtime_snapshot_precommit_contract.get('future_commit_stub')}")
                if runtime_snapshot_precommit_contract.get("future_rollback_stub"):
                    precommit_lines.append(f"- future-rollback-stub={runtime_snapshot_precommit_contract.get('future_rollback_stub')}")
                if runtime_snapshot_precommit_contract.get("preview_commit_sequence"):
                    precommit_lines.append(f"- commit-sequenz={', '.join(runtime_snapshot_precommit_contract.get('preview_commit_sequence')[:4])}")
                if runtime_snapshot_precommit_contract.get("preview_rollback_sequence"):
                    precommit_lines.append(f"- rollback-sequenz={', '.join(runtime_snapshot_precommit_contract.get('preview_rollback_sequence')[:4])}")
                if runtime_snapshot_precommit_contract.get("blocked_by"):
                    precommit_lines.append(f"- blocked-by={', '.join(runtime_snapshot_precommit_contract.get('blocked_by')[:6])}")
                if runtime_snapshot_precommit_contract.get("pending_by"):
                    precommit_lines.append(f"- pending-by={', '.join(runtime_snapshot_precommit_contract.get('pending_by')[:6])}")
                phase_results = runtime_snapshot_precommit_contract.get("preview_phase_results") or []
                for item in phase_results[:6]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    phase = str(item.get("phase") or "").strip() or "phase"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {phase} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    precommit_lines.append(line)
                detail_sections.append(
                    "Leere Audio-Spur: read-only Pre-Commit-Vertrag:\n" + "\n".join(precommit_lines)
                )
            if runtime_snapshot_atomic_entrypoints.get("entrypoint_key"):
                atomic_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                atomic_prefix = atomic_state_label.get(str(runtime_snapshot_atomic_entrypoints.get("entrypoint_state") or "").strip().lower(), str(runtime_snapshot_atomic_entrypoints.get("entrypoint_state") or "").upper() or "INFO")
                atomic_lines = [
                    f"- [{atomic_prefix}] key={runtime_snapshot_atomic_entrypoints.get('entrypoint_key')}",
                    f"- scope={runtime_snapshot_atomic_entrypoints.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_atomic_entrypoints.get('owner_class') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_atomic_entrypoints.get('mutation_gate_state') or 'blocked'}",
                    f"- entry-points={runtime_snapshot_atomic_entrypoints.get('ready_entrypoint_count', 0)}/{runtime_snapshot_atomic_entrypoints.get('total_entrypoint_count', 0)}",
                ]
                if runtime_snapshot_atomic_entrypoints.get("future_apply_stub"):
                    atomic_lines.append(f"- future-apply-stub={runtime_snapshot_atomic_entrypoints.get('future_apply_stub')}")
                if runtime_snapshot_atomic_entrypoints.get("future_commit_stub"):
                    atomic_lines.append(f"- future-commit-stub={runtime_snapshot_atomic_entrypoints.get('future_commit_stub')}")
                if runtime_snapshot_atomic_entrypoints.get("future_rollback_stub"):
                    atomic_lines.append(f"- future-rollback-stub={runtime_snapshot_atomic_entrypoints.get('future_rollback_stub')}")
                if runtime_snapshot_atomic_entrypoints.get("preview_dispatch_sequence"):
                    atomic_lines.append(f"- dispatch-sequenz={', '.join(runtime_snapshot_atomic_entrypoints.get('preview_dispatch_sequence')[:6])}")
                if runtime_snapshot_atomic_entrypoints.get("blocked_by"):
                    atomic_lines.append(f"- blocked-by={', '.join(runtime_snapshot_atomic_entrypoints.get('blocked_by')[:6])}")
                if runtime_snapshot_atomic_entrypoints.get("pending_by"):
                    atomic_lines.append(f"- pending-by={', '.join(runtime_snapshot_atomic_entrypoints.get('pending_by')[:6])}")
                for item in (runtime_snapshot_atomic_entrypoints.get("entrypoints") or [])[:10]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "entry-point"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    atomic_lines.append(line)
                detail_sections.append(
                    "Read-only atomare Commit-/Undo-/Routing-Entry-Points:\n" + "\n".join(atomic_lines)
                )
            if runtime_snapshot_mutation_gate_capsule.get("capsule_key"):
                capsule_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                capsule_prefix = capsule_state_label.get(str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").strip().lower(), str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").upper() or "INFO")
                capsule_lines = [
                    f"- [{capsule_prefix}] key={runtime_snapshot_mutation_gate_capsule.get('capsule_key')}",
                    f"- scope={runtime_snapshot_mutation_gate_capsule.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_mutation_gate_capsule.get('owner_class') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_mutation_gate_capsule.get('mutation_gate_state') or 'blocked'}",
                    f"- kapselschritte={runtime_snapshot_mutation_gate_capsule.get('ready_capsule_step_count', 0)}/{runtime_snapshot_mutation_gate_capsule.get('total_capsule_step_count', 0)}",
                ]
                if runtime_snapshot_mutation_gate_capsule.get("future_gate_stub"):
                    capsule_lines.append(f"- future-gate-stub={runtime_snapshot_mutation_gate_capsule.get('future_gate_stub')}")
                if runtime_snapshot_mutation_gate_capsule.get("future_capsule_stub"):
                    capsule_lines.append(f"- future-capsule-stub={runtime_snapshot_mutation_gate_capsule.get('future_capsule_stub')}")
                if runtime_snapshot_mutation_gate_capsule.get("future_commit_stub"):
                    capsule_lines.append(f"- future-commit-stub={runtime_snapshot_mutation_gate_capsule.get('future_commit_stub')}")
                if runtime_snapshot_mutation_gate_capsule.get("future_rollback_stub"):
                    capsule_lines.append(f"- future-rollback-stub={runtime_snapshot_mutation_gate_capsule.get('future_rollback_stub')}")
                if runtime_snapshot_mutation_gate_capsule.get("preview_capsule_sequence"):
                    capsule_lines.append(f"- kapsel-sequenz={', '.join(runtime_snapshot_mutation_gate_capsule.get('preview_capsule_sequence')[:8])}")
                if runtime_snapshot_mutation_gate_capsule.get("blocked_by"):
                    capsule_lines.append(f"- blocked-by={', '.join(runtime_snapshot_mutation_gate_capsule.get('blocked_by')[:6])}")
                if runtime_snapshot_mutation_gate_capsule.get("pending_by"):
                    capsule_lines.append(f"- pending-by={', '.join(runtime_snapshot_mutation_gate_capsule.get('pending_by')[:6])}")
                for item in (runtime_snapshot_mutation_gate_capsule.get("capsule_steps") or [])[:12]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "capsule-step"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    capsule_lines.append(line)
                detail_sections.append(
                    "Read-only Mutation-Gate / Transaction-Capsule:\n" + "\n".join(capsule_lines)
                )
            if runtime_snapshot_command_undo_shell.get("shell_key"):
                shell_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                shell_prefix = shell_state_label.get(str(runtime_snapshot_command_undo_shell.get("shell_state") or "").strip().lower(), str(runtime_snapshot_command_undo_shell.get("shell_state") or "").upper() or "INFO")
                shell_lines = [
                    f"- [{shell_prefix}] key={runtime_snapshot_command_undo_shell.get('shell_key')}",
                    f"- scope={runtime_snapshot_command_undo_shell.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_command_undo_shell.get('owner_class') or 'n/a'}",
                    f"- command={runtime_snapshot_command_undo_shell.get('command_class') or 'ProjectSnapshotEditCommand'}",
                    f"- command-module={runtime_snapshot_command_undo_shell.get('command_module') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_command_undo_shell.get('mutation_gate_state') or 'blocked'}",
                    f"- huellenschritte={runtime_snapshot_command_undo_shell.get('ready_shell_step_count', 0)}/{runtime_snapshot_command_undo_shell.get('total_shell_step_count', 0)}",
                ]
                if runtime_snapshot_command_undo_shell.get("future_command_stub"):
                    shell_lines.append(f"- future-command-stub={runtime_snapshot_command_undo_shell.get('future_command_stub')}")
                if runtime_snapshot_command_undo_shell.get("future_undo_stub"):
                    shell_lines.append(f"- future-undo-stub={runtime_snapshot_command_undo_shell.get('future_undo_stub')}")
                if runtime_snapshot_command_undo_shell.get("future_commit_stub"):
                    shell_lines.append(f"- future-commit-stub={runtime_snapshot_command_undo_shell.get('future_commit_stub')}")
                if runtime_snapshot_command_undo_shell.get("future_rollback_stub"):
                    shell_lines.append(f"- future-rollback-stub={runtime_snapshot_command_undo_shell.get('future_rollback_stub')}")
                if runtime_snapshot_command_undo_shell.get("preview_shell_sequence"):
                    shell_lines.append(f"- huellen-sequenz={', '.join(runtime_snapshot_command_undo_shell.get('preview_shell_sequence')[:8])}")
                if runtime_snapshot_command_undo_shell.get("blocked_by"):
                    shell_lines.append(f"- blocked-by={', '.join(runtime_snapshot_command_undo_shell.get('blocked_by')[:6])}")
                if runtime_snapshot_command_undo_shell.get("pending_by"):
                    shell_lines.append(f"- pending-by={', '.join(runtime_snapshot_command_undo_shell.get('pending_by')[:6])}")
                for item in (runtime_snapshot_command_undo_shell.get("shell_steps") or [])[:12]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "shell-step"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    shell_lines.append(line)
                detail_sections.append(
                    "Read-only ProjectSnapshotEditCommand / Undo-Huelle:\n" + "\n".join(shell_lines)
                )
            if runtime_snapshot_command_factory_payloads.get("factory_key"):
                payload_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                payload_prefix = payload_state_label.get(str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").strip().lower(), str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").upper() or "INFO")
                before_payload_summary = dict(runtime_snapshot_command_factory_payloads.get("before_payload_summary") or {})
                after_payload_summary = dict(runtime_snapshot_command_factory_payloads.get("after_payload_summary") or {})
                payload_lines = [
                    f"- [{payload_prefix}] key={runtime_snapshot_command_factory_payloads.get('factory_key')}",
                    f"- scope={runtime_snapshot_command_factory_payloads.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_command_factory_payloads.get('owner_class') or 'n/a'}",
                    f"- command={runtime_snapshot_command_factory_payloads.get('command_class') or 'ProjectSnapshotEditCommand'}",
                    f"- command-module={runtime_snapshot_command_factory_payloads.get('command_module') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_command_factory_payloads.get('mutation_gate_state') or 'blocked'}",
                    f"- factory-schritte={runtime_snapshot_command_factory_payloads.get('ready_factory_step_count', 0)}/{runtime_snapshot_command_factory_payloads.get('total_factory_step_count', 0)}",
                    f"- payloads={runtime_snapshot_command_factory_payloads.get('materialized_payload_count', 0)}/2",
                    f"- delta-kind={runtime_snapshot_command_factory_payloads.get('payload_delta_kind') or 'n/a'}",
                ]
                if runtime_snapshot_command_factory_payloads.get("label_preview"):
                    payload_lines.append(f"- label-preview={runtime_snapshot_command_factory_payloads.get('label_preview')}")
                if runtime_snapshot_command_factory_payloads.get("future_factory_stub"):
                    payload_lines.append(f"- future-factory-stub={runtime_snapshot_command_factory_payloads.get('future_factory_stub')}")
                if runtime_snapshot_command_factory_payloads.get("future_before_snapshot_stub"):
                    payload_lines.append(f"- future-before-stub={runtime_snapshot_command_factory_payloads.get('future_before_snapshot_stub')}")
                if runtime_snapshot_command_factory_payloads.get("future_after_snapshot_stub"):
                    payload_lines.append(f"- future-after-stub={runtime_snapshot_command_factory_payloads.get('future_after_snapshot_stub')}")
                if runtime_snapshot_command_factory_payloads.get("preview_factory_sequence"):
                    payload_lines.append(f"- factory-sequenz={', '.join(runtime_snapshot_command_factory_payloads.get('preview_factory_sequence')[:8])}")
                if before_payload_summary:
                    payload_lines.append(
                        f"- before-payload=digest {before_payload_summary.get('payload_digest') or 'n/a'}, bytes {before_payload_summary.get('payload_size_bytes', 0)}, entries {before_payload_summary.get('payload_entry_count', 0)}, keys {', '.join(before_payload_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if after_payload_summary:
                    payload_lines.append(
                        f"- after-payload=digest {after_payload_summary.get('payload_digest') or 'n/a'}, bytes {after_payload_summary.get('payload_size_bytes', 0)}, entries {after_payload_summary.get('payload_entry_count', 0)}, keys {', '.join(after_payload_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if runtime_snapshot_command_factory_payloads.get("blocked_by"):
                    payload_lines.append(f"- blocked-by={', '.join(runtime_snapshot_command_factory_payloads.get('blocked_by')[:6])}")
                if runtime_snapshot_command_factory_payloads.get("pending_by"):
                    payload_lines.append(f"- pending-by={', '.join(runtime_snapshot_command_factory_payloads.get('pending_by')[:6])}")
                for item in (runtime_snapshot_command_factory_payloads.get("factory_steps") or [])[:12]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "factory-step"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    payload_lines.append(line)
                detail_sections.append(
                    "Read-only Before-/After-Snapshot-Command-Factory:\n" + "\n".join(payload_lines)
                )
            if runtime_snapshot_preview_command_construction.get("preview_command_key"):
                preview_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                preview_prefix = preview_state_label.get(str(runtime_snapshot_preview_command_construction.get("preview_state") or "").strip().lower(), str(runtime_snapshot_preview_command_construction.get("preview_state") or "").upper() or "INFO")
                before_preview_summary = dict(runtime_snapshot_preview_command_construction.get("before_payload_summary") or {})
                after_preview_summary = dict(runtime_snapshot_preview_command_construction.get("after_payload_summary") or {})
                preview_lines = [
                    f"- [{preview_prefix}] key={runtime_snapshot_preview_command_construction.get('preview_command_key')}",
                    f"- scope={runtime_snapshot_preview_command_construction.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_preview_command_construction.get('owner_class') or 'n/a'}",
                    f"- command={runtime_snapshot_preview_command_construction.get('command_class') or 'ProjectSnapshotEditCommand'}",
                    f"- command-module={runtime_snapshot_preview_command_construction.get('command_module') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_preview_command_construction.get('mutation_gate_state') or 'blocked'}",
                    f"- preview-schritte={runtime_snapshot_preview_command_construction.get('ready_preview_step_count', 0)}/{runtime_snapshot_preview_command_construction.get('total_preview_step_count', 0)}",
                    f"- payloads={runtime_snapshot_preview_command_construction.get('materialized_payload_count', 0)}/2",
                    f"- constructor={runtime_snapshot_preview_command_construction.get('command_constructor') or 'n/a'}",
                ]
                if runtime_snapshot_preview_command_construction.get("label_preview"):
                    preview_lines.append(f"- label-preview={runtime_snapshot_preview_command_construction.get('label_preview')}")
                if runtime_snapshot_preview_command_construction.get("apply_callback_name"):
                    preview_lines.append(
                        f"- apply-callback={runtime_snapshot_preview_command_construction.get('apply_callback_owner_class') or 'n/a'}.{runtime_snapshot_preview_command_construction.get('apply_callback_name')}"
                    )
                if runtime_snapshot_preview_command_construction.get("command_field_names"):
                    preview_lines.append(f"- command-felder={', '.join(runtime_snapshot_preview_command_construction.get('command_field_names')[:8])}")
                if runtime_snapshot_preview_command_construction.get("future_constructor_stub"):
                    preview_lines.append(f"- future-constructor-stub={runtime_snapshot_preview_command_construction.get('future_constructor_stub')}")
                if runtime_snapshot_preview_command_construction.get("future_executor_stub"):
                    preview_lines.append(f"- future-executor-stub={runtime_snapshot_preview_command_construction.get('future_executor_stub')}")
                if runtime_snapshot_preview_command_construction.get("preview_command_sequence"):
                    preview_lines.append(f"- preview-sequenz={', '.join(runtime_snapshot_preview_command_construction.get('preview_command_sequence')[:8])}")
                if before_preview_summary:
                    preview_lines.append(
                        f"- before-payload=digest {before_preview_summary.get('payload_digest') or 'n/a'}, bytes {before_preview_summary.get('payload_size_bytes', 0)}, entries {before_preview_summary.get('payload_entry_count', 0)}, keys {', '.join(before_preview_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if after_preview_summary:
                    preview_lines.append(
                        f"- after-payload=digest {after_preview_summary.get('payload_digest') or 'n/a'}, bytes {after_preview_summary.get('payload_size_bytes', 0)}, entries {after_preview_summary.get('payload_entry_count', 0)}, keys {', '.join(after_preview_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if runtime_snapshot_preview_command_construction.get("blocked_by"):
                    preview_lines.append(f"- blocked-by={', '.join(runtime_snapshot_preview_command_construction.get('blocked_by')[:6])}")
                if runtime_snapshot_preview_command_construction.get("pending_by"):
                    preview_lines.append(f"- pending-by={', '.join(runtime_snapshot_preview_command_construction.get('pending_by')[:6])}")
                for item in (runtime_snapshot_preview_command_construction.get("preview_steps") or [])[:12]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "preview-step"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    preview_lines.append(line)
                detail_sections.append(
                    "Read-only Preview-Command-Konstruktion:\n" + "\n".join(preview_lines)
                )
            if runtime_snapshot_dry_command_executor.get("dry_executor_key"):
                dry_state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                dry_prefix = dry_state_label.get(str(runtime_snapshot_dry_command_executor.get("dry_executor_state") or "").strip().lower(), str(runtime_snapshot_dry_command_executor.get("dry_executor_state") or "").upper() or "INFO")
                before_dry_summary = dict(runtime_snapshot_dry_command_executor.get("before_payload_summary") or {})
                after_dry_summary = dict(runtime_snapshot_dry_command_executor.get("after_payload_summary") or {})
                dry_lines = [
                    f"- [{dry_prefix}] key={runtime_snapshot_dry_command_executor.get('dry_executor_key')}",
                    f"- scope={runtime_snapshot_dry_command_executor.get('target_scope') or 'empty-audio-track-minimal-case'}",
                    f"- owner={runtime_snapshot_dry_command_executor.get('owner_class') or 'n/a'}",
                    f"- command={runtime_snapshot_dry_command_executor.get('command_class') or 'ProjectSnapshotEditCommand'}",
                    f"- command-module={runtime_snapshot_dry_command_executor.get('command_module') or 'n/a'}",
                    f"- mutation-gate={runtime_snapshot_dry_command_executor.get('mutation_gate_state') or 'blocked'}",
                    f"- simulationsschritte={runtime_snapshot_dry_command_executor.get('ready_simulation_step_count', 0)}/{runtime_snapshot_dry_command_executor.get('total_simulation_step_count', 0)}",
                    f"- do/undo={runtime_snapshot_dry_command_executor.get('do_call_count', 0)}/{runtime_snapshot_dry_command_executor.get('undo_call_count', 0)}",
                    f"- callbacks={runtime_snapshot_dry_command_executor.get('callback_call_count', 0)}",
                    f"- constructor={runtime_snapshot_dry_command_executor.get('command_constructor') or 'n/a'}",
                ]
                if runtime_snapshot_dry_command_executor.get("label_preview"):
                    dry_lines.append(f"- label-preview={runtime_snapshot_dry_command_executor.get('label_preview')}")
                if runtime_snapshot_dry_command_executor.get("apply_callback_name"):
                    dry_lines.append(
                        f"- apply-callback={runtime_snapshot_dry_command_executor.get('apply_callback_owner_class') or 'n/a'}.{runtime_snapshot_dry_command_executor.get('apply_callback_name')}"
                    )
                if runtime_snapshot_dry_command_executor.get("future_executor_stub"):
                    dry_lines.append(f"- future-executor-stub={runtime_snapshot_dry_command_executor.get('future_executor_stub')}")
                if runtime_snapshot_dry_command_executor.get("future_live_executor_stub"):
                    dry_lines.append(f"- future-live-executor-stub={runtime_snapshot_dry_command_executor.get('future_live_executor_stub')}")
                if runtime_snapshot_dry_command_executor.get("simulation_sequence"):
                    dry_lines.append(f"- simulations-sequenz={', '.join(runtime_snapshot_dry_command_executor.get('simulation_sequence')[:8])}")
                if runtime_snapshot_dry_command_executor.get("callback_trace"):
                    dry_lines.append(f"- callback-trace={', '.join(runtime_snapshot_dry_command_executor.get('callback_trace')[:8])}")
                if runtime_snapshot_dry_command_executor.get("callback_payload_digests"):
                    dry_lines.append(f"- callback-digests={', '.join(runtime_snapshot_dry_command_executor.get('callback_payload_digests')[:8])}")
                if before_dry_summary:
                    dry_lines.append(
                        f"- before-payload=digest {before_dry_summary.get('payload_digest') or 'n/a'}, bytes {before_dry_summary.get('payload_size_bytes', 0)}, entries {before_dry_summary.get('payload_entry_count', 0)}, keys {', '.join(before_dry_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if after_dry_summary:
                    dry_lines.append(
                        f"- after-payload=digest {after_dry_summary.get('payload_digest') or 'n/a'}, bytes {after_dry_summary.get('payload_size_bytes', 0)}, entries {after_dry_summary.get('payload_entry_count', 0)}, keys {', '.join(after_dry_summary.get('top_level_keys', [])[:8]) or 'n/a'}"
                    )
                if runtime_snapshot_dry_command_executor.get("blocked_by"):
                    dry_lines.append(f"- blocked-by={', '.join(runtime_snapshot_dry_command_executor.get('blocked_by')[:6])}")
                if runtime_snapshot_dry_command_executor.get("pending_by"):
                    dry_lines.append(f"- pending-by={', '.join(runtime_snapshot_dry_command_executor.get('pending_by')[:6])}")
                for item in (runtime_snapshot_dry_command_executor.get("simulation_steps") or [])[:12]:
                    try:
                        item = dict(item or {})
                    except Exception:
                        item = {}
                    label = str(item.get("label") or "").strip() or "simulation-step"
                    target = str(item.get("target") or "").strip() or "target"
                    method = str(item.get("method") or "").strip() or "method"
                    state = str(item.get("state") or "").strip().upper() or "INFO"
                    detail = str(item.get("detail") or "").strip()
                    line = f"- [{state}] {label} -> {target} via {method}"
                    if detail:
                        line += f" — {detail}"
                    dry_lines.append(line)
                detail_sections.append(
                    "Read-only Dry-Command-Executor / do()-undo()-Simulations-Harness:\n" + "\n".join(dry_lines)
                )
            if readiness_checks:
                state_label = {"ready": "READY", "pending": "PENDING", "blocked": "BLOCKED"}
                detail_sections.append(
                    "Apply-Readiness-Checkliste:\n" + "\n".join([
                        f"- [{state_label.get(state, state.upper() or 'INFO')}] {title}" + (f" — {detail}" if detail else "")
                        for (title, state, detail) in readiness_checks
                    ])
                )
            if transaction_steps:
                transaction_block = "Geplanter atomarer Ablauf:\n" + "\n".join(transaction_steps)
                if transaction_key:
                    transaction_block += f"\n\nTransaction-Key: {transaction_key}"
                detail_sections.append(transaction_block)
            if detail_sections:
                detail_sections.append(
                    "Erst danach darf Audio->Instrument-Morphing Undo-/Routing-sicher aktiviert werden."
                )
                box.setDetailedText("\n\n".join(detail_sections))
            if can_apply:
                box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                box.setDefaultButton(QMessageBox.StandardButton.Cancel)
                try:
                    ok_btn = box.button(QMessageBox.StandardButton.Ok)
                    if ok_btn is not None:
                        ok_btn.setText("Morphing bestaetigen")
                    cancel_btn = box.button(QMessageBox.StandardButton.Cancel)
                    if cancel_btn is not None:
                        cancel_btn.setText("Abbrechen")
                except Exception:
                    pass
            else:
                box.setStandardButtons(QMessageBox.StandardButton.Ok)
                box.setDefaultButton(QMessageBox.StandardButton.Ok)
            clicked = box.exec()
            result["shown"] = True
            result["accepted"] = bool(can_apply and clicked == int(QMessageBox.StandardButton.Ok))
            return result
        except Exception:
            return result

    def _migrate_automation_for_device_move(self, source_track_id: str, target_track_id: str, device_id: str, device_kind: str, copy: bool = False) -> int:
        """Migrate automation lanes when a device is moved between tracks (Bitwig-style).

        v0.0.20.524: FIXED — also replaces afx device_ids in keys.
        VST instruments have keys like "afx:{track_id}:{device_id}:vst3:Cutoff".
        When copied/moved, the target track gets a NEW device_id. This function
        builds a device_id mapping from source→target audio_fx_chains and replaces
        both track_id and device_id in the key string.
        Internal instruments (Bach Orgel) use "trk:{track_id}:bach_orgel:param"
        which has no device_id — those work with just track_id replacement.
        """
        migrated = 0
        try:
            source_track_id = str(source_track_id or "").strip()
            target_track_id = str(target_track_id or "").strip()
            device_id = str(device_id or "").strip()
            device_kind = str(device_kind or "").strip().lower()
            if not source_track_id or not target_track_id or source_track_id == target_track_id:
                return 0

            # Access AutomationManager
            am = None
            try:
                am = getattr(self.services, "automation_manager", None)
                if am is None:
                    am = getattr(getattr(self.services, "audio_engine", None), "_automation_manager", None)
                if am is None:
                    am = getattr(getattr(self.services, "container", None), "automation_manager", None)
            except Exception:
                am = None
            if am is None or not hasattr(am, "_lanes"):
                return 0

            # v524: Build device_id mapping from source→target audio_fx_chains
            # This maps old afx device IDs to new ones by matching plugin_id.
            device_id_map: dict[str, str] = {}  # old_device_id -> new_device_id
            try:
                proj = getattr(self.services, "project", None)
                project_obj = getattr(getattr(proj, "ctx", None), "project", None)
                if project_obj is not None:
                    tracks_list = list(getattr(project_obj, "tracks", []) or [])
                    src_trk = next((t for t in tracks_list if str(getattr(t, "id", "")) == source_track_id), None)
                    tgt_trk = next((t for t in tracks_list if str(getattr(t, "id", "")) == target_track_id), None)
                    if src_trk is not None and tgt_trk is not None:
                        src_chain = getattr(src_trk, "audio_fx_chain", None) or {}
                        tgt_chain = getattr(tgt_trk, "audio_fx_chain", None) or {}
                        src_devs = list(src_chain.get("devices", []) or []) if isinstance(src_chain, dict) else []
                        tgt_devs = list(tgt_chain.get("devices", []) or []) if isinstance(tgt_chain, dict) else []
                        # Match devices by plugin_id (order-preserving)
                        tgt_by_plugin: dict[str, list] = {}
                        for d in tgt_devs:
                            if isinstance(d, dict):
                                pid = str(d.get("plugin_id", "") or "")
                                if pid:
                                    tgt_by_plugin.setdefault(pid, []).append(str(d.get("id", "") or ""))
                        for d in src_devs:
                            if isinstance(d, dict):
                                old_did = str(d.get("id", "") or "")
                                pid = str(d.get("plugin_id", "") or "")
                                if old_did and pid and pid in tgt_by_plugin:
                                    candidates = tgt_by_plugin[pid]
                                    if candidates:
                                        new_did = candidates.pop(0)
                                        if new_did and new_did != old_did:
                                            device_id_map[old_did] = new_did
            except Exception:
                pass

            # Find lanes to migrate
            lanes_to_migrate: list[tuple[str, str]] = []  # (old_pid, new_pid)

            for pid, lane in list(am._lanes.items()):
                lane_tid = str(getattr(lane, "track_id", "") or "").strip()
                if lane_tid != source_track_id and source_track_id not in pid:
                    continue

                pid_lower = pid.lower()
                if pid_lower.endswith(":volume") or pid_lower.endswith(":pan"):
                    continue

                if device_kind in ("audio_fx", "note_fx") and device_id:
                    if device_id not in pid:
                        continue
                elif device_kind == "instrument":
                    pass
                else:
                    continue

                # Build new key: replace track_id AND device_ids
                new_pid = pid.replace(source_track_id, target_track_id)
                for old_did, new_did in device_id_map.items():
                    new_pid = new_pid.replace(old_did, new_did)
                if new_pid == pid:
                    continue
                lanes_to_migrate.append((pid, new_pid))

            # Perform migration (move or copy)
            import copy as _copy_mod
            for old_pid, new_pid in lanes_to_migrate:
                try:
                    if new_pid in am._lanes:
                        continue
                    old_lane = am._lanes.get(old_pid)
                    if old_lane is None:
                        continue
                    if copy:
                        new_lane = _copy_mod.deepcopy(old_lane)
                        new_lane.parameter_id = new_pid
                        new_lane.track_id = target_track_id
                        am._lanes[new_pid] = new_lane
                    else:
                        am._lanes.pop(old_pid, None)
                        old_lane.parameter_id = new_pid
                        old_lane.track_id = target_track_id
                        am._lanes[new_pid] = old_lane
                    migrated += 1
                except Exception:
                    pass

            if migrated > 0:
                try:
                    am.lane_data_changed.emit("")
                except Exception:
                    pass
        except Exception:
            pass
        return migrated

    def _smartdrop_remove_from_source(self, source_track_id: str, source_device_id: str, device_kind: str, plugin_name: str = "") -> None:
        """Remove a device from its source track after a successful cross-track SmartDrop move.

        v0.0.20.516: Bitwig-style cross-track device move
        v0.0.20.517: Auto track-type adjustment after instrument removal
        Safe: if removal fails, the device stays on both tracks (user can manually clean up).
        """
        source_track_id = str(source_track_id or "").strip()
        source_device_id = str(source_device_id or "").strip()
        device_kind = str(device_kind or "").strip().lower()
        if not source_track_id:
            return
        try:
            if device_kind == "instrument":
                self.device_panel._remove_instrument(source_track_id)
                # v517: Auto track-type adjustment — if source track was an instrument
                # track and now has no instrument, convert back to audio track
                try:
                    proj = getattr(self.services, "project", None)
                    project_obj = getattr(getattr(proj, "ctx", None), "project", None)
                    src_trk = next((t for t in (getattr(project_obj, "tracks", []) or []) if str(getattr(t, "id", "") or "") == source_track_id), None)
                    if src_trk is not None:
                        src_kind = str(getattr(src_trk, "kind", "") or "").strip().lower()
                        src_plugin = str(getattr(src_trk, "plugin_type", "") or "").strip()
                        if src_kind == "instrument" and not src_plugin:
                            proj.set_track_kind(source_track_id, "audio")
                except Exception:
                    pass
            elif device_kind == "note_fx" and source_device_id:
                self.device_panel.remove_note_fx_device(source_track_id, source_device_id)
            elif device_kind == "audio_fx" and source_device_id:
                self.device_panel.remove_audio_fx_device(source_track_id, source_device_id)
        except Exception:
            pass

    @staticmethod
    def _is_ctrl_held() -> bool:
        """Check if Ctrl/Cmd modifier is currently held (for copy-on-drag, Bitwig-style)."""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import Qt
            mods = QApplication.keyboardModifiers()
            return bool(mods & Qt.KeyboardModifier.ControlModifier)
        except Exception:
            return False

    def _on_arranger_smartdrop_instrument_morph_guard(self, track_id: str, payload: dict) -> None:
        """Route Instrument→Audio drops through the central preview/validate/apply guard.

        For the minimal case (empty audio track), this now performs the real
        atomic mutation: track.kind change + instrument insertion + undo push.
        For all other cases, it stays non-mutating with a guard dialog.
        """
        plan = self._build_smartdrop_audio_to_instrument_morph_plan(track_id, payload)
        if not plan:
            try:
                self._set_status("SmartDrop noch gesperrt: Audio→Instrument-Morphing-Plan konnte nicht erstellt werden.", 3600)
            except Exception:
                pass
            return
        dialog_result = self._show_smartdrop_morph_guard_dialog(plan)
        dialog_shown = bool(dialog_result.get("shown"))
        dialog_accepted = bool(dialog_result.get("accepted"))
        proj = getattr(self.services, "project", None)
        result: dict
        if bool(plan.get("can_apply")):
            if dialog_shown and not dialog_accepted:
                result = dict(plan)
                result["message"] = "Morphing abgebrochen. Es wurde nichts veraendert."
            else:
                try:
                    result = dict(proj.apply_audio_to_instrument_morph(plan) or {}) if proj is not None else dict(plan)
                except Exception:
                    result = dict(plan)
                # Stage 2+3: If the atomic morph succeeded, insert the instrument
                if bool(result.get("ok")) and bool(result.get("applied")):
                    try:
                        payload_dict = dict(payload or {})
                        plugin_id = str(payload_dict.get("plugin_id") or "").strip()
                        plugin_name = str(payload_dict.get("plugin_name") or payload_dict.get("name") or "").strip() or "Instrument"
                        morph_track_id = str(result.get("track_id") or track_id or "").strip()
                        # v516: cross-track move detection / v517: Ctrl = copy
                        source_track_id = str(payload_dict.get("source_track_id") or "").strip()
                        is_cross_track = bool(source_track_id and source_track_id != morph_track_id)
                        is_copy = self._is_ctrl_held()
                        if plugin_id and morph_track_id:
                            try:
                                self.device_panel.add_instrument_to_track(morph_track_id, plugin_id)
                            except Exception:
                                pass
                            # v516: Remove from source / v517: skip if Ctrl (copy)
                            # v519: Migrate automation lanes with the device
                            # v522: Always migrate automation (copy or move)
                            if is_cross_track and source_track_id:
                                self._migrate_automation_for_device_move(source_track_id, morph_track_id, "", "instrument", copy=is_copy)
                            if is_cross_track and source_track_id and not is_copy:
                                self._smartdrop_remove_from_source(source_track_id, "", "instrument", plugin_name)
                            try:
                                self.arranger.tracks.select_track(morph_track_id)
                            except Exception:
                                pass
                            try:
                                self.device_panel.show_track(morph_track_id)
                            except Exception:
                                pass
                            try:
                                self._set_view_mode("device", force=True)
                            except Exception:
                                pass
                            try:
                                proj._emit_updated()
                            except Exception:
                                pass
                            try:
                                proj.project_changed.emit()
                            except Exception:
                                pass
                            result["message"] = (
                                f"SmartDrop ausgefuehrt: Audio-Spur → Instrument-Spur ({plugin_name})"
                                + (f" (kopiert von {source_track_id[:8]})" if (is_cross_track and is_copy)
                                   else (f" (verschoben von {source_track_id[:8]})" if is_cross_track else ""))
                                + ". Undo mit Ctrl+Z."
                            )
                    except Exception:
                        pass
        else:
            try:
                result = dict(proj.apply_audio_to_instrument_morph(plan) or {}) if proj is not None else dict(plan)
            except Exception:
                result = dict(plan)
        message = str(result.get("message") or plan.get("blocked_message") or "SmartDrop noch gesperrt: Audio→Instrument-Morphing ist noch nicht freigeschaltet.")
        if dialog_shown and bool(plan.get("requires_confirmation")) and not bool(plan.get("can_apply")):
            message = f"Sicherheitspruefung geoeffnet - {message}"
        try:
            self._set_status(message, 4200 if dialog_shown else 3800)
        except Exception:
            pass

    def _on_arranger_smartdrop_instrument_to_track(self, track_id: str, payload: dict) -> None:
        """Insert/replace an instrument on an existing instrument track.

        v0.0.20.479: handles drops onto EXISTING instrument tracks
        v0.0.20.516: also handles cross-track moves from DevicePanel (Bitwig-style)
        """
        track_id = str(track_id or "").strip()
        if not track_id:
            return
        try:
            payload = dict(payload or {})
        except Exception:
            payload = {}
        plugin_id = str(payload.get("plugin_id") or "").strip()
        plugin_name = str(payload.get("name") or "").strip() or "Instrument"
        params = dict(payload.get("params") or {}) if isinstance(payload.get("params"), dict) else {}
        raw_kind = str(payload.get("kind") or "").strip().lower()
        device_kind = str(payload.get("device_kind") or raw_kind or "").strip().lower()
        if device_kind != "instrument" or not plugin_id:
            return

        # v516: cross-track move detection / v517: Ctrl = copy
        source_track_id = str(payload.get("source_track_id") or "").strip()
        source_device_id = str(payload.get("device_id") or "").strip()
        is_cross_track = bool(source_track_id and source_track_id != track_id)
        is_copy = self._is_ctrl_held()  # v517: Ctrl+Drag = Copy

        proj = getattr(self.services, "project", None)
        project_obj = getattr(getattr(proj, "ctx", None), "project", None)
        track = None
        try:
            tracks = list(getattr(project_obj, "tracks", []) or [])
            track = next((t for t in tracks if str(getattr(t, "id", "") or "") == track_id), None)
        except Exception:
            track = None
        if track is None or str(getattr(track, "kind", "") or "") != "instrument":
            return

        track_name = str(getattr(track, "name", "") or track_id)
        try:
            verb = "kopieren" if is_copy else "verschieben"
            if is_cross_track:
                proj._auto_undo_pending_label = f"SmartDrop: Instrument {verb} → {track_name} ({plugin_name})"
            else:
                proj._auto_undo_pending_label = f"SmartDrop: Instrument auf Spur ({plugin_name})"
        except Exception:
            pass

        ok = False
        try:
            if raw_kind == "instrument":
                ok = bool(self.device_panel.add_instrument_to_track(track_id, plugin_id))
            else:
                ok = bool(self.device_panel.add_audio_fx_to_track(track_id, plugin_id, name=plugin_name, params=params))
        except Exception:
            ok = False

        if not ok:
            try:
                self._set_status(f"SmartDrop fehlgeschlagen: {plugin_name} konnte nicht auf {track_name} eingefügt werden.", 3200)
            except Exception:
                pass
            return

        # v522: Always migrate automation (copy or move), only remove source on move
        if is_cross_track and source_track_id:
            self._migrate_automation_for_device_move(source_track_id, track_id, source_device_id, "instrument", copy=is_copy)
        if is_cross_track and source_track_id and not is_copy:
            self._smartdrop_remove_from_source(source_track_id, source_device_id, "instrument", plugin_name)

        try:
            self.arranger.tracks.select_track(track_id)
        except Exception:
            pass
        try:
            self.device_panel.show_track(track_id)
        except Exception:
            pass
        try:
            self._set_view_mode("device", force=True)
        except Exception:
            pass
        try:
            verb = "kopiert" if (is_cross_track and is_copy) else ("verschoben" if is_cross_track else "gesetzt")
            self._set_status(f"SmartDrop: Instrument {verb} — {track_name} · {plugin_name}", 2600)
        except Exception:
            pass

    def _on_arranger_smartdrop_fx_to_track(self, track_id: str, payload: dict) -> None:
        """Insert compatible FX on an existing compatible track.

        v0.0.20.480: Note-FX/Audio-FX on compatible tracks
        v0.0.20.516: also handles cross-track moves from DevicePanel (Bitwig-style)
        """
        track_id = str(track_id or "").strip()
        if not track_id:
            return
        try:
            payload = dict(payload or {})
        except Exception:
            payload = {}
        plugin_id = str(payload.get("plugin_id") or "").strip()
        plugin_name = str(payload.get("name") or "").strip() or "Effekt"
        params = dict(payload.get("params") or {}) if isinstance(payload.get("params"), dict) else {}
        device_kind = str(payload.get("device_kind") or payload.get("kind") or "").strip().lower()
        if device_kind not in ("audio_fx", "note_fx") or not plugin_id:
            return

        # v516: cross-track move detection / v517: Ctrl = copy
        source_track_id = str(payload.get("source_track_id") or "").strip()
        source_device_id = str(payload.get("device_id") or "").strip()
        is_cross_track = bool(source_track_id and source_track_id != track_id)
        is_copy = self._is_ctrl_held()  # v517: Ctrl+Drag = Copy

        proj = getattr(self.services, "project", None)
        project_obj = getattr(getattr(proj, "ctx", None), "project", None)
        track = None
        try:
            tracks = list(getattr(project_obj, "tracks", []) or [])
            track = next((t for t in tracks if str(getattr(t, "id", "") or "") == track_id), None)
        except Exception:
            track = None
        if track is None:
            return

        track_kind = str(getattr(track, "kind", "") or "").strip().lower()
        move_verb = "kopieren" if (is_cross_track and is_copy) else ("verschieben" if is_cross_track else "gesetzt")
        t_name = str(getattr(track, 'name', '') or track_id)
        if device_kind == "note_fx":
            compatible = track_kind == "instrument"
            undo_label = f"SmartDrop: Note-FX {move_verb} ({plugin_name})"
            ok_call = lambda: bool(self.device_panel.add_note_fx_to_track(track_id, plugin_id, name=plugin_name, params=params))
            status_ok = f"SmartDrop: Note-FX {move_verb} — {t_name} · {plugin_name}"
            status_fail = f"SmartDrop fehlgeschlagen: {plugin_name} konnte nicht als Note-FX auf {t_name} eingefügt werden."
        else:
            compatible = track_kind in ("instrument", "audio", "bus", "group", "fx")
            undo_label = f"SmartDrop: Audio-FX {move_verb} ({plugin_name})"
            ok_call = lambda: bool(self.device_panel.add_audio_fx_to_track(track_id, plugin_id, name=plugin_name, params=params))
            status_ok = f"SmartDrop: Audio-FX {move_verb} — {t_name} · {plugin_name}"
            status_fail = f"SmartDrop fehlgeschlagen: {plugin_name} konnte nicht als Audio-FX auf {t_name} eingefügt werden."
        if not compatible:
            return

        try:
            proj._auto_undo_pending_label = undo_label
        except Exception:
            pass

        ok = False
        try:
            ok = bool(ok_call())
        except Exception:
            ok = False
        if not ok:
            try:
                self._set_status(status_fail, 3200)
            except Exception:
                pass
            return

        # v522: Always migrate automation (copy or move), only remove source on move
        if is_cross_track and source_track_id and source_device_id:
            self._migrate_automation_for_device_move(source_track_id, track_id, source_device_id, device_kind, copy=is_copy)
        if is_cross_track and source_track_id and source_device_id and not is_copy:
            self._smartdrop_remove_from_source(source_track_id, source_device_id, device_kind, plugin_name)

        try:
            self.arranger.tracks.select_track(track_id)
        except Exception:
            pass
        try:
            self.device_panel.show_track(track_id)
        except Exception:
            pass
        try:
            self._set_view_mode("device", force=True)
        except Exception:
            pass
        try:
            self._set_status(status_ok, 2600)
        except Exception:
            pass

    def _on_arranger_smartdrop_new_instrument_track(self, payload: dict) -> None:
        """Create a new instrument track from an empty-space Arranger plugin drop.

        Safety-first MVP for v0.0.20.478:
        - only handles instrument-capable payloads
        - only creates a NEW track at the end
        - no track morphing of existing tracks
        - uses the existing add_track + device-panel insert paths
        """
        try:
            payload = dict(payload or {})
        except Exception:
            payload = {}
        plugin_id = str(payload.get("plugin_id") or "").strip()
        plugin_name = str(payload.get("name") or "").strip() or "Instrument Track"
        params = dict(payload.get("params") or {}) if isinstance(payload.get("params"), dict) else {}
        raw_kind = str(payload.get("kind") or "").strip().lower()
        device_kind = str(payload.get("device_kind") or raw_kind or "").strip().lower()
        if device_kind != "instrument" or not plugin_id:
            return

        proj = getattr(self.services, "project", None)
        if proj is None:
            return

        try:
            proj._auto_undo_pending_label = f"SmartDrop: Neue Instrument-Spur ({plugin_name})"
        except Exception:
            pass

        new_track = None
        try:
            new_track = proj.add_track("instrument", name=plugin_name)
        except Exception:
            new_track = None
        new_track_id = str(getattr(new_track, "id", "") or "")
        if not new_track_id:
            try:
                self._set_status("SmartDrop fehlgeschlagen: Spur konnte nicht angelegt werden.", 2600)
            except Exception:
                pass
            return

        ok = False
        try:
            if raw_kind == "instrument":
                ok = bool(self.device_panel.add_instrument_to_track(new_track_id, plugin_id))
            else:
                ok = bool(self.device_panel.add_audio_fx_to_track(new_track_id, plugin_id, name=plugin_name, params=params))
        except Exception:
            ok = False

        if not ok:
            try:
                proj.remove_track(new_track_id)
            except Exception:
                pass
            try:
                self._set_status(f"SmartDrop fehlgeschlagen: {plugin_name} konnte nicht in die neue Spur eingefügt werden.", 3200)
            except Exception:
                pass
            return

        try:
            self.arranger.tracks.select_track(new_track_id)
        except Exception:
            pass
        try:
            self.device_panel.show_track(new_track_id)
        except Exception:
            pass
        try:
            self._set_view_mode("device", force=True)
        except Exception:
            pass
        try:
            self._set_status(f"SmartDrop: Neue Instrument-Spur angelegt — {plugin_name}", 2600)
        except Exception:
            pass


    # --- Phase 2/3: Track-Header ▾ helpers (UI-only) ---

    def _on_track_header_open_browser(self, track_id: str, tab_key: str) -> None:
        """Open the Browser dock and select a tab (instruments/effects/samples)."""
        try:
            self.browser_dock.setVisible(True)
        except Exception:
            pass

        # Ensure Browser tab is active in the right dock
        try:
            rt = getattr(self, "_right_tabs", None)
            if rt is not None:
                rt.setCurrentIndex(0)
        except Exception:
            pass

        # Switch inside DeviceBrowser
        try:
            idx = {"samples": 0, "instruments": 1, "effects": 2}.get(str(tab_key).lower(), 0)
            self.library.tabs.setCurrentIndex(int(idx))
        except Exception:
            pass

        try:
            self._set_status(f"Browser: {tab_key}", 1200)
        except Exception:
            pass


    def _on_track_header_show_device(self, track_id: str) -> None:
        """Show the Device panel and bind it to the given track."""
        try:
            self.device_panel.show_track(str(track_id))
        except Exception:
            pass
        try:
            self._set_view_mode("device", force=True)
        except Exception:
            pass


    def _on_track_header_add_device(self, track_id: str, kind: str, plugin_id: str) -> None:
        """Insert a device directly to the given track (1-click)."""
        tid = str(track_id)
        k = str(kind).lower()
        pid = str(plugin_id)
        ok = False
        try:
            if k in ("instrument", "instr"):
                ok = bool(self.device_panel.add_instrument_to_track(tid, pid))
            elif k in ("note_fx", "notefx", "note"):
                ok = bool(self.device_panel.add_note_fx_to_track(tid, pid))
            elif k in ("audio_fx", "audiofx", "fx"):
                ok = bool(self.device_panel.add_audio_fx_to_track(tid, pid))
        except Exception:
            ok = False

        if ok:
            try:
                self.device_panel.show_track(tid)
            except Exception:
                pass
            try:
                self._set_view_mode("device", force=True)
            except Exception:
                pass
            try:
                self._set_status(f"Added {k}: {pid}", 1800)
            except Exception:
                pass
            return
        try:
            ok = bool(self.device_panel.add_instrument_to_track(track_id, plugin_id))
        except Exception:
            ok = False
        if ok:
            try:
                self._set_view_mode("device", force=True)
            except Exception:
                pass
            # v0.0.20.42: Register new sampler in global registry for MIDI routing
            try:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                registry = get_sampler_registry()
                if not registry.has_sampler(track_id):
                    devices = self.device_panel.get_track_devices(track_id)
                    for dev in devices:
                        engine = getattr(dev, "engine", None)
                        if engine is not None and hasattr(engine, "trigger_note"):
                            registry.register(track_id, engine, dev)
                            
                            # v0.0.20.46: Set plugin_type on track for Pro-DAW-Style routing
                            try:
                                track = self.services.project.ctx.project.tracks_by_id().get(track_id)
                                if track:
                                    # Detect plugin type from plugin_id
                                    if "sampler" in str(plugin_id).lower():
                                        track.plugin_type = "sampler"
                                    elif "drum" in str(plugin_id).lower():
                                        track.plugin_type = "drum_machine"
                                    self.services.project.mark_dirty()
                            except Exception:
                                pass
                            
                            break
            except Exception:
                pass


    def _toggle_browser(self) -> None:
        try:
            vis = bool(self.browser_dock.isVisible())
            self.browser_dock.setVisible(not vis)
        except Exception:
            pass


    def _apply_chrono_theme(self) -> None:
        """Minimal dark QSS so the whole UI feels like a single Pro-DAW-Style frame."""
        self.setStyleSheet(
            """
            QMainWindow { background: #212121; color: #BBBBBB; }
            QWidget { color: #BBBBBB; }

            /* Classic menu bar (exact like reference screenshot) */
            QMenuBar { background: #1E1E1E; border: none; padding: 2px 6px; }
            QMenuBar::item { background: transparent; padding: 6px 10px; margin: 0px 2px; border-radius: 4px; }
            QMenuBar::item:selected { background: #b000b0; color: #FFFFFF; }
            QMenu { background: #1E1E1E; border: 1px solid #2A2A2A; }
            QMenu::item { padding: 6px 28px 6px 16px; }
            QMenu::separator { height: 1px; background: #2A2A2A; margin: 4px 8px; }
            QMenu::item:selected { background: #b000b0; color: #FFFFFF; }

            /* Toolbars below menu bar */
            QToolBar { background: #232323; border: none; spacing: 6px; padding: 2px 6px; }
            QToolBar::separator { background: #2A2A2A; width: 1px; margin: 0 6px; }

            /* Transport row */
            #transportPanel QPushButton {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 6px;
                padding: 4px 8px;
                min-width: 28px;
            }
            #transportPanel QPushButton:hover { background: #333333; border-color: #3F3F3F; }
            #transportPanel QLabel { color: #BBBBBB; }
            #transportPanel QSpinBox, #transportPanel QComboBox {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 6px;
                padding: 2px 6px;
                min-height: 24px;
            }

            /* Tools row */
            #toolBarPanel QComboBox {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 6px;
                padding: 2px 8px;
                min-height: 24px;
            }
            #toolBarPanel QToolButton {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 6px;
                padding: 4px 10px;
            }
            #toolBarPanel QToolButton:hover { background: #333333; border-color: #3F3F3F; }

            /* Python logo button styling (the button now lives in the status signature) */
            #toolBarPanel QToolButton#pythonLogoBtn {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 999px;
                padding: 0px;
            }
            #toolBarPanel QToolButton#pythonLogoBtn:hover {
                background: rgba(255,255,255,0.06);
                border-color: #3F3F3F;
            }


            #chronoHeader { background: #1E1E1E; border-bottom: 1px solid #2A2A2A; }
            #chronoLogo { background: #2A2A2A; border: 1px solid #343434; border-radius: 6px; }
            #chronoSep { color: #555555; }

            QToolButton#chronoHeaderButton {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 6px;
                padding: 2px 8px;
            }
            QToolButton#chronoHeaderButton:hover { background: #333333; border-color: #3F3F3F; }

            #chronoToolStrip { background: #1C1C1C; border-right: 1px solid #2A2A2A; }
            QToolButton#chronoToolButton {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 8px;
                font-size: 14px;
            }
            QToolButton#chronoToolButton:hover { background: #333333; border-color: #3F3F3F; }

            QDockWidget::title {
                background: #1E1E1E;
                border: 1px solid #2A2A2A;
                padding: 4px;
            }
            QDockWidget { border: 1px solid #2A2A2A; }

            QTabWidget::pane { border: 1px solid #2A2A2A; }
            QTabBar::tab { background: #2A2A2A; border: 1px solid #343434; padding: 6px 10px; margin: 1px; }
            QTabBar::tab:selected { background: #333333; }

            QComboBox { background: #2A2A2A; border: 1px solid #343434; padding: 4px 8px; border-radius: 6px; }
            QComboBox::drop-down { border: none; }

            QToolButton#chronoMenuButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 2px 8px;
            }
            QToolButton#chronoMenuButton:hover { background: #2A2A2A; border-color: #343434; }

            #chronoBottomNav { background: #1E1E1E; border-top: 1px solid #2A2A2A; }
            QWidget#chronoTechSignature { background: transparent; }
            QToolButton#statusQtLogoButton,
            QToolButton#statusPythonLogoButton,
            QToolButton#statusRustLogoButton {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QToolButton#chronoViewTab {
                background: #2A2A2A;
                border: 1px solid #343434;
                border-radius: 8px;
                padding: 4px 10px;
                margin-right: 6px;
                font-weight: 600;
            }
            QToolButton#chronoViewTab:checked {
                background: #333333;
                border-color: #D77A00;
                color: #EEEEEE;
            }
            QLabel#chronoSnapLabel { color: #9E9E9E; padding-right: 6px; }

            /* Device panel placeholder */
            #devicePanel { background: #212121; }
            QLabel#devicePanelTitle { color: #DDDDDD; font-weight: 700; font-size: 14px; }
            QLabel#devicePanelHint { color: #9E9E9E; }
            QLabel#devicePanelEmpty { color: #7E7E7E; }
            #devicePanelSep { background: #2A2A2A; }
            """
        )


    def _fit_to_screen(self) -> None:

        """Resize and center the window to fit the active desktop."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        if geo.width() <= 0 or geo.height() <= 0:
            return

        # Use a conservative default size that still leaves room for panels.
        target_w = int(geo.width() * 0.92)
        target_h = int(geo.height() * 0.9)
        self.resize(max(900, min(target_w, geo.width())), max(600, min(target_h, geo.height())))
        # v0.0.20.597: Allow user to resize the window freely (small minimum)
        self.setMinimumSize(400, 300)

        # v0.0.20.606: Set right dock to ~30% width (compact Clip Launcher)
        try:
            right_w = max(200, int(target_w * 0.28))
            self.resizeDocks([self.browser_dock], [right_w], Qt.Orientation.Horizontal)
        except Exception:
            pass

        # Center on screen
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

    # --- transport sync

    def _init_screen_layout_manager(self) -> None:
        """Initialize the Bitwig-style multi-monitor layout system (v0.0.20.444).

        Registers all detachable panels and populates the Ansicht → Bildschirm-Layout menu.
        """
        self._screen_layout_mgr = ScreenLayoutManager(self)

        # --- Register panels ---
        # Each panel needs a restore callback that puts the widget back
        # in its original dock position when re-docked.

        # Editor panel
        editor_widget = self.editor_tabs
        editor_dock = self.editor_dock

        def _restore_editor(w):
            try:
                editor_dock.setWidget(w)
            except Exception:
                pass

        self._screen_layout_mgr.register_panel(
            PanelId.EDITOR, "Editor", editor_widget,
            dock_parent=editor_dock,
            dock_restore_cb=_restore_editor,
        )

        # Mixer panel
        mixer_widget = self.mixer
        mixer_dock = self.mixer_dock

        def _restore_mixer(w):
            try:
                mixer_dock.setWidget(w)
            except Exception:
                pass

        self._screen_layout_mgr.register_panel(
            PanelId.MIXER, "Mixer", mixer_widget,
            dock_parent=mixer_dock,
            dock_restore_cb=_restore_mixer,
        )

        # Device panel
        device_widget = self.device_panel
        device_dock = self.device_dock

        def _restore_device(w):
            try:
                device_dock.setWidget(w)
            except Exception:
                pass

        self._screen_layout_mgr.register_panel(
            PanelId.DEVICE, "Device", device_widget,
            dock_parent=device_dock,
            dock_restore_cb=_restore_device,
        )

        # Browser panel (right dock)
        browser_tabs = getattr(self, '_right_tabs', None)
        browser_dock = self.browser_dock
        if browser_tabs is not None:
            def _restore_browser(w):
                try:
                    browser_dock.setWidget(w)
                except Exception:
                    pass

            self._screen_layout_mgr.register_panel(
                PanelId.BROWSER, "Browser", browser_tabs,
                dock_parent=browser_dock,
                dock_restore_cb=_restore_browser,
            )

        # v0.0.20.624: Clip Launcher panel (right dock, tabified with Browser)
        launcher_widget = self.launcher_panel
        launcher_dock = self.launcher_dock

        def _restore_launcher(w):
            try:
                launcher_dock.setWidget(w)
            except Exception:
                pass

        self._screen_layout_mgr.register_panel(
            PanelId.CLIP_LAUNCHER, "Clip Launcher", launcher_widget,
            dock_parent=launcher_dock,
            dock_restore_cb=_restore_launcher,
        )

        # Automation panel (inside the arranger's vertical splitter)
        auto_widget = getattr(self.arranger, '_enhanced_automation', None)
        if auto_widget is None:
            auto_widget = self.automation
        _auto_splitter = auto_widget.parentWidget() if auto_widget else None
        _auto_splitter_idx = -1
        if _auto_splitter and hasattr(_auto_splitter, 'indexOf'):
            try:
                _auto_splitter_idx = _auto_splitter.indexOf(auto_widget)
            except Exception:
                _auto_splitter_idx = -1

        def _restore_automation(w):
            try:
                if _auto_splitter is not None and hasattr(_auto_splitter, 'insertWidget') and _auto_splitter_idx >= 0:
                    _auto_splitter.insertWidget(_auto_splitter_idx, w)
                elif _auto_splitter is not None and hasattr(_auto_splitter, 'addWidget'):
                    _auto_splitter.addWidget(w)
            except Exception:
                pass

        if auto_widget is not None:
            self._screen_layout_mgr.register_panel(
                PanelId.AUTOMATION, "Automation", auto_widget,
                dock_parent=_auto_splitter,
                dock_restore_cb=_restore_automation,
            )

        # --- Populate the menu ---
        self._populate_screen_layout_menu()

        # v0.0.20.534: Keyboard shortcuts for layout presets (Ctrl+Alt+1..8)
        try:
            _preset_keys = [p.key for p in LAYOUT_PRESETS]
            for i, pkey in enumerate(_preset_keys[:8]):
                sc = QShortcut(QKeySequence(f"Ctrl+Alt+{i + 1}"), self)
                sc.activated.connect(lambda _k=pkey: self._safe_call(self._apply_screen_layout, _k))
                # Keep reference alive
                setattr(self, f"_layout_shortcut_{i}", sc)
        except Exception:
            pass

    def _populate_screen_layout_menu(self) -> None:
        """Build the Ansicht → Bildschirm-Layout submenu.

        Groups presets by screen count. Shows which presets are available
        based on the number of connected monitors.
        """
        menu = getattr(self, '_screen_layout_menu', None)
        if menu is None:
            return

        menu.clear()

        mgr = getattr(self, '_screen_layout_mgr', None)
        if mgr is None:
            menu.addAction("(Layout-System nicht verfügbar)")
            return

        n_screens = mgr.available_screens()

        # Info header
        act_info = menu.addAction(f"Bildschirme erkannt: {n_screens}")
        act_info.setEnabled(False)
        menu.addSeparator()

        # Group presets by min_screens
        groups: dict[str, list] = {}
        for preset in LAYOUT_PRESETS:
            if preset.min_screens == 1 and preset.max_screens == 1:
                grp = "1_only"
            elif preset.min_screens == 1:
                grp = "1"
            elif preset.min_screens == 2:
                grp = "2"
            elif preset.min_screens == 3:
                grp = "3"
            else:
                grp = "other"
            groups.setdefault(grp, []).append(preset)

        # 1 Monitor
        for grp_key, grp_label in [("1", "Ein Bildschirm"), ("1_only", None), ("2", "Zwei Bildschirme"), ("3", "Drei Bildschirme")]:
            presets = groups.get(grp_key, [])
            if not presets:
                continue
            if grp_label:
                menu.addSeparator()
            for preset in presets:
                available = (preset.min_screens <= n_screens)
                # v0.0.20.534: Show keyboard shortcut hint
                _all_keys = [p.key for p in LAYOUT_PRESETS]
                _idx = _all_keys.index(preset.key) if preset.key in _all_keys else -1
                _sc_hint = f"  (Ctrl+Alt+{_idx + 1})" if 0 <= _idx < 8 else ""
                act = menu.addAction(f"{preset.label}{_sc_hint}")
                act.setEnabled(available)
                act.setToolTip(f"{preset.description}{_sc_hint}")
                if not available:
                    act.setText(f"{preset.label}  (benötigt {preset.min_screens} Monitore)")
                # Checkmark for active preset
                if mgr.active_preset_key == preset.key:
                    act.setCheckable(True)
                    act.setChecked(True)
                # Connect
                key = preset.key
                act.triggered.connect(lambda _=False, k=key: self._safe_call(self._apply_screen_layout, k))

        # Separator + detach toggles for individual panels
        menu.addSeparator()
        detach_menu = menu.addMenu("Panel abkoppeln…")
        for pid, dp in mgr.panels.items():
            act = detach_menu.addAction(f"{'✓ ' if dp.is_detached else ''}{dp.title}")
            act.setCheckable(True)
            act.setChecked(dp.is_detached)
            _pid = pid
            act.triggered.connect(lambda _=False, p=_pid: self._safe_call(self._toggle_panel_detach, p))

        # Dock all
        menu.addSeparator()
        act_dock_all = menu.addAction("Alle Panels andocken")
        act_dock_all.triggered.connect(lambda _=False: self._safe_call(self._dock_all_panels))

    def _apply_screen_layout(self, preset_key: str) -> None:
        """Apply a screen layout preset."""
        mgr = getattr(self, '_screen_layout_mgr', None)
        if mgr is None:
            return
        ok = mgr.apply_preset(preset_key)
        if ok:
            self._set_status(f"Layout angewendet: {preset_key}", 2500)
            # Re-populate menu to update checkmarks
            self._populate_screen_layout_menu()
        else:
            self._set_status(f"Layout '{preset_key}' konnte nicht angewendet werden.", 3000)

    def _toggle_panel_detach(self, panel_id: PanelId) -> None:
        """Toggle detach for a single panel."""
        mgr = getattr(self, '_screen_layout_mgr', None)
        if mgr is None:
            return
        dp = mgr.get_panel(panel_id)
        if dp is None:
            return
        dp.toggle()
        self._populate_screen_layout_menu()
        state = "abgekoppelt" if dp.is_detached else "angedockt"
        self._set_status(f"{dp.title}: {state}", 1800)

    def _dock_all_panels(self) -> None:
        """Re-dock all floating panels."""
        mgr = getattr(self, '_screen_layout_mgr', None)
        if mgr is None:
            return
        mgr.dock_all()
        self._populate_screen_layout_menu()
        self._set_status("Alle Panels angedockt.", 1800)

    def _on_arranger_loop_committed(self, enabled: bool, start: float, end: float) -> None:
        self.services.transport.set_loop(bool(enabled))
        self.services.transport.set_loop_region(float(start), float(end))

    # ──────────────────────────────────────────────────────
    # v0.0.20.637: Punch In/Out handlers (AP2 Phase 2C)
    # ──────────────────────────────────────────────────────

    def _on_arranger_punch_committed(self, enabled: bool, in_beat: float, out_beat: float) -> None:
        """Arranger canvas punch region edit → TransportService + Project Model."""
        self.services.transport.set_punch_region(float(in_beat), float(out_beat))
        if enabled:
            self.services.transport.set_punch(True)
        else:
            self.services.transport.set_punch(False)
        # Persist to project model
        try:
            proj = self.services.project.ctx.project
            proj.punch_enabled = bool(enabled)
            proj.punch_in_beat = float(in_beat)
            proj.punch_out_beat = float(out_beat)
        except Exception:
            pass

    def _on_transport_punch_changed(self, enabled: bool, in_beat: float, out_beat: float) -> None:
        """TransportService punch change → Arranger + Transport panel UI."""
        self.arranger.canvas.set_punch_region(bool(enabled), float(in_beat), float(out_beat))
        try:
            self.transport.set_punch(bool(enabled))
        except Exception:
            pass
        # Sync RecordingService punch state
        rec = getattr(self.services, 'recording', None)
        if rec:
            try:
                rec.set_punch(bool(enabled), float(in_beat), float(out_beat))
            except Exception:
                pass

    def _on_punch_toggled_from_ui(self, enabled: bool) -> None:
        """Transport panel punch checkbox → TransportService."""
        self.services.transport.set_punch(bool(enabled))
        # Persist
        try:
            self.services.project.ctx.project.punch_enabled = bool(enabled)
        except Exception:
            pass

    def _on_punch_triggered(self, boundary: str) -> None:
        """TransportService fires when playhead crosses punch_in or punch_out.

        Forwards to RecordingService for automatic punch record start/stop.
        """
        rec = getattr(self.services, 'recording', None)
        if rec and rec.is_recording():
            try:
                rec.on_punch_triggered(boundary)
            except Exception:
                pass
        if boundary == "out":
            self.statusBar().showMessage("Punch Out — Recording gestoppt", 2000)
            try:
                self.transport.btn_rec.blockSignals(True)
                self.transport.btn_rec.setChecked(False)
                self.transport.btn_rec.blockSignals(False)
                self._recording_active = False
            except Exception:
                pass

    def _on_pre_roll_changed(self, bars: int) -> None:
        """Transport panel pre-roll spinbox → TransportService + Project."""
        self.services.transport.set_pre_roll_bars(int(bars))
        try:
            self.services.project.ctx.project.pre_roll_bars = int(bars)
        except Exception:
            pass

    def _on_post_roll_changed(self, bars: int) -> None:
        """Transport panel post-roll spinbox → TransportService + Project."""
        self.services.transport.set_post_roll_bars(int(bars))
        try:
            self.services.project.ctx.project.post_roll_bars = int(bars)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────
    # v0.0.20.639: Loop-Recording / Take-Lanes (AP2 Phase 2D)
    # ──────────────────────────────────────────────────────

    def _on_loop_boundary_reached(self) -> None:
        """Transport loop wraps → save current take, start new pass."""
        rec = getattr(self.services, 'recording', None)
        if rec and rec.is_loop_recording():
            try:
                rec.on_loop_boundary()
            except Exception:
                pass

    def _setup_loop_recording_for_record_start(self) -> None:
        """Enable loop-recording if transport loop is active when Record starts.

        Called from _on_record_toggled() before start_recording().
        """
        rec = getattr(self.services, 'recording', None)
        if not rec:
            return
        try:
            t = self.services.transport
            take_svc = getattr(self.services, 'take', None)

            if t.loop_enabled:
                rec.set_loop_recording(True)
                if take_svc:
                    rec.set_take_service(take_svc)

                # Set up take-creation callback
                def _on_take_created(wav_path, track_id, start_beat, tkg_id, take_idx):
                    try:
                        clip_id = self.services.project.add_audio_clip_from_file_at(
                            track_id=track_id,
                            path=wav_path,
                            start_beats=start_beat,
                        )
                        if clip_id and take_svc:
                            # Find the created clip and assign take metadata
                            for c in self.services.project.ctx.project.clips:
                                if str(getattr(c, 'id', '')) == str(clip_id):
                                    take_svc.add_take_to_group(tkg_id, c, make_active=True)
                                    c.label = f"Take {take_idx + 1}"
                                    break
                            # Show take lanes on this track
                            for trk in self.services.project.ctx.project.tracks:
                                if str(getattr(trk, 'id', '')) == str(track_id):
                                    trk.take_lanes_visible = True
                                    break
                        self.statusBar().showMessage(
                            f"Take {take_idx + 1} gespeichert: {wav_path.name}", 2000
                        )
                    except Exception as e:
                        self.statusBar().showMessage(f"Take-Import fehlgeschlagen: {e}", 4000)

                rec.set_on_take_created(_on_take_created)
            else:
                rec.set_loop_recording(False)
        except Exception:
            pass

    def _on_transport_loop_changed(self, enabled: bool, start: float, end: float) -> None:
        self.arranger.canvas.set_loop_region(bool(enabled), float(start), float(end))
        if self.transport.chk_loop.isChecked() != bool(enabled):
            self.transport.chk_loop.blockSignals(True)
            self.transport.chk_loop.setChecked(bool(enabled))
            self.transport.chk_loop.blockSignals(False)
        # v0.0.20.438: Sync toolbar loop fields
        try:
            if hasattr(self, "toolbar_panel") and self.toolbar_panel is not None:
                self.toolbar_panel.set_loop_from_transport(bool(enabled), float(start), float(end))
        except Exception:
            pass

    def _on_follow_changed(self, follow: bool) -> None:
        """v0.0.20.438: Toggle Bitwig-style playhead follow in arranger."""
        try:
            self.arranger.canvas._follow_playhead = bool(follow)
        except Exception:
            pass

    def _on_toolbar_loop_changed(self, enabled: bool, start_beat: float, end_beat: float) -> None:
        """v0.0.20.438: Loop fields in toolbar → Transport + Arranger."""
        try:
            self.services.transport.set_loop(bool(enabled))
            self.services.transport.set_loop_region(float(start_beat), float(end_beat))
            self.arranger.canvas.set_loop_region(bool(enabled), float(start_beat), float(end_beat))
            # Sync transport panel checkbox
            if self.transport.chk_loop.isChecked() != bool(enabled):
                self.transport.chk_loop.blockSignals(True)
                self.transport.chk_loop.setChecked(bool(enabled))
                self.transport.chk_loop.blockSignals(False)
        except Exception:
            pass

    def _on_transport_ts_changed(self, ts: str) -> None:
        self.transport.set_time_signature(ts)
        self.arranger.canvas.update()

    def _update_playhead(self, beat: float) -> None:
        self.arranger.canvas.set_playhead(float(beat))
        self.transport.set_time(float(beat), self.services.transport.bpm)
        try:
            self.automation.set_playhead(float(beat))
        except Exception:
            pass
        # v0.0.20.89: Enhanced automation playhead + tick
        try:
            eap = getattr(self.arranger, '_enhanced_automation', None)
            if eap is not None:
                eap.set_playhead(float(beat))
        except Exception:
            pass
        try:
            self.services.automation_manager.tick(float(beat))
        except Exception:
            pass

    # --- metronome click

    def _on_metronome_tick(self, bar_index: int, beat_in_bar: int, is_countin: bool) -> None:
        prefix = "Count-In" if is_countin else "Metronom"
        self.statusBar().showMessage(f"{prefix}: Bar {bar_index + 1}, Beat {beat_in_bar}", 350)

        # audio click (best effort): accent on downbeat
        accent = (beat_in_bar == 1)
        try:
            self.services.metronome.play_click(accent=accent)
        except Exception:
            pass

    # --- wiring

    def _wire_actions(self) -> None:
        # File
        self.actions.file_new.triggered.connect(lambda _=False: self._safe_call(self._new_project))
        self.actions.file_open.triggered.connect(lambda _=False: self._safe_call(self._open_project))
        self.actions.file_save.triggered.connect(lambda _=False: self._safe_call(self._save_project))
        self.actions.file_save_as.triggered.connect(lambda _=False: self._safe_call(self._save_project_as))
        self.actions.file_import_audio.triggered.connect(lambda _=False: self._safe_call(self._import_audio))
        self.actions.file_import_midi.triggered.connect(lambda _=False: self._safe_call(self._import_midi))
        self.actions.file_import_dawproject.triggered.connect(lambda _=False: self._safe_call(self._import_dawproject))
        self.actions.file_export_dawproject.triggered.connect(lambda _=False: self._safe_call(self._export_dawproject))
        self.actions.file_export.triggered.connect(lambda _=False: self._safe_call(self._export_audio_placeholder))
        self.actions.file_export_midi_clip.triggered.connect(lambda _=False: self._safe_call(self._export_midi_clip))  # FIXED v0.0.19.7.15
        self.actions.file_export_midi_track.triggered.connect(lambda _=False: self._safe_call(self._export_midi_track))  # FIXED v0.0.19.7.15
        self.actions.file_exit.triggered.connect(lambda _=False: self._safe_call(self.close))

        # View
        self.actions.view_dummy.triggered.connect(lambda _=False: self._safe_call(self.statusBar().showMessage, "Ansicht (Platzhalter)", 2000))
        self.actions.view_toggle_pianoroll.toggled.connect(lambda checked: self._safe_call(self._toggle_pianoroll, checked))
        self.actions.view_toggle_notation.toggled.connect(lambda checked: self._safe_call(self._toggle_notation, checked))
        self.actions.view_toggle_cliplauncher.toggled.connect(lambda checked: self._safe_call(self._toggle_cliplauncher, checked))
        self.actions.view_toggle_drop_overlay.toggled.connect(lambda checked: self._safe_call(self._toggle_drop_overlay, checked))
        self.actions.view_toggle_gpu_waveforms.toggled.connect(lambda checked: self._safe_call(self._toggle_gpu_waveforms, checked))
        self.actions.view_toggle_cpu_meter.toggled.connect(lambda checked: self._safe_call(self._toggle_cpu_meter, checked))
        # v0.0.20.696: Rust Engine toggle
        self.actions.audio_toggle_rust_engine.toggled.connect(lambda checked: self._safe_call(self._toggle_rust_engine, checked))
        # v0.0.20.701: Plugin Sandbox toggle
        self.actions.audio_toggle_plugin_sandbox.toggled.connect(lambda checked: self._safe_call(self._toggle_plugin_sandbox, checked))
        self.actions.view_toggle_automation.toggled.connect(lambda checked: self._safe_call(self._toggle_automation, checked))

        # Edit (Undo/Redo)
        self.actions.edit_undo.triggered.connect(lambda _=False: self._safe_call(self.services.project.undo))
        self.actions.edit_redo.triggered.connect(lambda _=False: self._safe_call(self.services.project.redo))
        self.actions.edit_cut.triggered.connect(lambda _=False: self._safe_call(self._dispatch_edit, 'cut'))
        self.actions.edit_copy.triggered.connect(lambda _=False: self._safe_call(self._dispatch_edit, 'copy'))
        self.actions.edit_paste.triggered.connect(lambda _=False: self._safe_call(self._dispatch_edit, 'paste'))
        self.actions.edit_select_all.triggered.connect(lambda _=False: self._safe_call(self._dispatch_edit, 'select_all'))

        # Project / tracks
        self.actions.project_add_audio_track.triggered.connect(lambda _=False: self._safe_project_call('add_track', 'audio'))
        self.actions.project_add_instrument_track.triggered.connect(lambda _=False: self._safe_project_call('add_track', 'instrument'))
        self.actions.project_add_bus_track.triggered.connect(lambda _=False: self._safe_project_call('add_track', 'bus'))
        self.actions.project_add_placeholder_clip.triggered.connect(lambda _=False: self._safe_call(self._add_clip_to_selected_track))
        self.actions.project_remove_selected_track.triggered.connect(lambda _=False: self._safe_call(self._remove_selected_track))
        self.actions.project_time_signature.triggered.connect(lambda _=False: self._safe_call(self._show_time_signature))
        self.actions.project_settings.triggered.connect(lambda _=False: self._safe_call(self._show_project_settings))
        self.actions.project_save_snapshot.triggered.connect(lambda _=False: self._safe_call(self._save_snapshot))
        self.actions.project_load_snapshot.triggered.connect(lambda _=False: self._safe_call(self._load_snapshot))

        # Audio + MIDI dialogs
        self.actions.audio_settings.triggered.connect(lambda _=False: self._safe_call(self._show_audio_settings))
        self.actions.audio_prerender_midi.triggered.connect(lambda _=False: self._safe_call(self._start_midi_prerender, show_dialog=True))
        self.actions.audio_prerender_selected_clip.triggered.connect(lambda _=False: self._safe_call(self._on_prerender_selected_clips))
        self.actions.audio_prerender_selected_track.triggered.connect(lambda _=False: self._safe_call(self._on_prerender_selected_track))
        self.actions.midi_settings.triggered.connect(lambda _=False: self._safe_call(self._show_midi_settings))
        self.actions.midi_mapping.triggered.connect(lambda _=False: self._safe_call(self._show_midi_mapping))
        self.actions.midi_panic.triggered.connect(lambda _=False: self._safe_call(self.services.midi.panic_all, 'user'))

        # Help
        self.actions.help_workbook.triggered.connect(lambda _=False: self._safe_call(self._show_workbook))
        self.actions.help_toggle_python_animation.toggled.connect(lambda checked: self._safe_call(self._on_python_logo_animation_toggled, checked))

        # Transport panel
        self.transport.bpm_changed.connect(lambda bpm: self._safe_call(self._on_bpm_changed_from_ui, bpm))
        self.transport.play_clicked.connect(lambda: self._safe_call(self._on_play_clicked))
        self.transport.stop_clicked.connect(lambda: self._safe_call(self._on_stop_clicked))
        self.transport.rew_clicked.connect(lambda: self._safe_call(self.services.transport.rewind))
        self.transport.ff_clicked.connect(lambda: self._safe_call(self.services.transport.fast_forward))
        self.transport.record_clicked.connect(lambda checked: self._safe_call(self._on_record_toggled, checked))
        self.transport.loop_toggled.connect(lambda enabled: self._safe_call(self.services.transport.set_loop, enabled))
        self.transport.time_signature_changed.connect(lambda ts: self._safe_call(self._on_ts_changed_from_ui, ts))

        self.transport.metronome_toggled.connect(lambda enabled: self._safe_call(self._on_metronome_enabled, enabled))
        self.transport.count_in_changed.connect(lambda v: self._safe_call(self._on_count_in_changed, v))

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self.transport.punch_toggled.connect(lambda enabled: self._safe_call(self._on_punch_toggled_from_ui, enabled))
        self.transport.pre_roll_changed.connect(lambda v: self._safe_call(self._on_pre_roll_changed, v))
        self.transport.post_roll_changed.connect(lambda v: self._safe_call(self._on_post_roll_changed, v))

        # Grid/Tools (toolbar row + optional left strip)
        try:
            if hasattr(self, "toolbar_panel") and self.toolbar_panel is not None:
                self.toolbar_panel.grid_changed.connect(self._on_grid_changed_from_ui)
                self.toolbar_panel.tool_changed.connect(self._on_tool_changed_from_toolbar)
                self.toolbar_panel.automation_toggled.connect(self._toggle_automation)
        except Exception:
            pass

        # v0.0.20.438: Wire Follow Playhead toggle
        try:
            if hasattr(self, "toolbar_panel") and self.toolbar_panel is not None:
                self.toolbar_panel.follow_changed.connect(self._on_follow_changed)
        except Exception:
            pass

        # v0.0.20.438: Wire Loop fields ↔ Transport
        try:
            if hasattr(self, "toolbar_panel") and self.toolbar_panel is not None:
                self.toolbar_panel.loop_changed.connect(self._on_toolbar_loop_changed)
        except Exception:
            pass

        # Live MIDI edits while playing: restart arrangement playback so the
        # rendered MIDI->WAV cache is refreshed without requiring manual stop/play.
        self._recording_active = False
        self._recording_track_id = None
        self._recording_start_beat = 0.0
        self._recording_wav_path = None

        self._midi_refresh_timer = QTimer(self)
        self._midi_refresh_timer.setSingleShot(True)
        self._midi_refresh_timer.timeout.connect(self._restart_playback_if_playing)
        try:
            self.services.project.midi_notes_committed.connect(self._on_midi_notes_committed)
        except Exception:
            pass

        # FIXED v0.0.19.7.2: Sync BPM and Time Signature when project loads!
        try:
            self.services.project.project_opened.connect(self._on_project_opened)
        except Exception:
            pass

        # Project open/lifecycle: optionally start pre-render so playback is snappy.
        try:
            self.services.project.project_opened.connect(self._maybe_autoprerender_after_load)
        except Exception:
            pass

        # Pre-render progress hooks (used by Ready-for-Bach progress dialog)
        self._prerender_dialog = None
        self._play_after_prerender = False
        try:
            self.services.project.prerender_label.connect(self._on_prerender_label)
            self.services.project.prerender_progress.connect(self._on_prerender_progress)
            self.services.project.prerender_finished.connect(self._on_prerender_finished)
        except Exception:
            pass



    def _update_undo_redo_actions(self) -> None:
        try:
            can_undo = bool(self.services.project.can_undo())
            can_redo = bool(self.services.project.can_redo())
            ulab = self.services.project.undo_label()
            rlab = self.services.project.redo_label()
        except Exception:
            can_undo = False
            can_redo = False
            ulab = ""
            rlab = ""

        self.actions.edit_undo.setEnabled(can_undo)
        self.actions.edit_redo.setEnabled(can_redo)

        # Pro-DAW-like: show operation name in menu
        self.actions.edit_undo.setText("Rückgängig" + (f" ({ulab})" if ulab else ""))
        self.actions.edit_redo.setText("Wiederholen" + (f" ({rlab})" if rlab else ""))


    # --- handlers

    def _on_bpm_changed_from_ui(self, bpm: float) -> None:
        self.services.transport.set_bpm(bpm)
        self.services.project.ctx.project.bpm = float(bpm)
        self.services.project.project_updated.emit()

    def _on_ts_changed_from_ui(self, ts: str) -> None:
        self.services.project.set_time_signature(ts)
        self.services.transport.set_time_signature(ts)
        self.statusBar().showMessage(f"Time Signature gesetzt: {ts}", 2000)

    def _on_grid_changed_from_ui(self, div: str) -> None:
        self.services.project.set_snap_division(div)
        self.arranger.set_snap_division(div)
        self.statusBar().showMessage(f"Grid/Snap gesetzt: {div}", 1500)

        try:
            if hasattr(self, "lbl_snap") and self.lbl_snap is not None:
                self.lbl_snap.setText(str(div))
        except Exception:
            pass


    def _on_tool_changed_from_toolbar(self, tool: str) -> None:
        """Propagate tool change to Arranger + Editor (Piano Roll).

        Tools:
        - select, draw, erase, knife, time_select
        PianoRoll expects: select, pen, erase, knife, time
        """
        tool = (tool or "").strip()

        # Arranger
        try:
            if hasattr(self.arranger, "canvas"):
                self.arranger.canvas.set_tool(str(tool))
        except Exception:
            pass

        # PianoRoll (best effort)
        try:
            et = getattr(self, "editor_tabs", None)
            pr = getattr(et, "pianoroll", None) if et is not None else None
            canvas = getattr(pr, "canvas", None) if pr is not None else None
            if canvas is not None:
                mapping = {
                    "select": "select",
                    "draw": "pen",
                    "erase": "erase",
                    "knife": "knife",
                    "time_select": "time",
                }
                canvas.set_tool_mode(mapping.get(tool, tool))
        except Exception:
            pass

        try:
            self.statusBar().showMessage(f"Tool: {tool}", 900)
        except Exception:
            pass

    def _on_metronome_enabled(self, enabled: bool) -> None:
        self.services.transport.set_metronome(bool(enabled))
        # Enable click service either when metronome enabled or count-in > 0
        enabled_click = bool(enabled) or int(self.services.transport.count_in_bars) > 0
        self.services.metronome.set_enabled(enabled_click)

    def _on_count_in_changed(self, bars: int) -> None:
        self.services.transport.set_count_in_bars(int(bars))
        enabled_click = self.transport.chk_met.isChecked() or int(bars) > 0
        self.services.metronome.set_enabled(enabled_click)

    def _on_record_toggled(self, enabled: bool) -> None:
        """Start/stop audio recording (v0.0.20.636 — AP2 Phase 2B).

        Uses RecordingService which auto-detects backend:
        JACK > PipeWire > sounddevice.  Falls back to legacy JACK path
        if RecordingService is not wired.

        v0.0.20.636: Supports multiple armed tracks simultaneously.
        """
        enabled = bool(enabled)

        rec = getattr(self.services, 'recording', None)
        if rec is None:
            # Legacy fallback: JACK-only (pre-v0.0.20.632)
            self._on_record_toggled_legacy(enabled)
            return

        if enabled and not rec.is_recording():
            # --- START RECORDING ---

            # v0.0.20.636: Collect ALL armed tracks (multi-track recording)
            armed_tracks = []  # list of (track_id, input_pair)
            try:
                for t in self.services.project.ctx.project.tracks:
                    if bool(getattr(t, "record_arm", False)):
                        tid = str(t.id)
                        pair = max(1, int(getattr(t, "input_pair", 1) or 1))
                        armed_tracks.append((tid, pair))
            except Exception:
                pass

            if not armed_tracks:
                # Fallback: ensure at least one audio track
                tid = None
                try:
                    tid = str(self.services.project.ensure_audio_track())
                except Exception:
                    pass
                if not tid:
                    self.statusBar().showMessage("Recording: Kein Track verfügbar.", 2500)
                    try:
                        self.transport.btn_rec.blockSignals(True)
                        self.transport.btn_rec.setChecked(False)
                        self.transport.btn_rec.blockSignals(False)
                    except Exception:
                        pass
                    return
                armed_tracks = [(tid, 1)]

            # Configure recording service
            rec.set_transport(self.services.transport)

            # Disarm previous state, then arm all tracks
            rec.disarm_track(None)  # clear all
            for tid, pair in armed_tracks:
                rec.arm_track(tid, pair)

            # Set project media path if available
            try:
                proj_path = getattr(self.services.project.ctx, 'project_path', None)
                if proj_path:
                    from pathlib import Path
                    media_dir = Path(proj_path).parent / "media" / "recordings"
                    rec.set_project_media_path(media_dir)
            except Exception:
                pass

            # Set auto clip creation callback (fires per track)
            def _on_rec_complete(wav_path, track_id, start_beat):
                try:
                    self.services.project.add_audio_clip_from_file_at(
                        track_id=track_id,
                        path=wav_path,
                        start_beats=start_beat,
                    )
                    self.statusBar().showMessage(f"Recording importiert: {wav_path.name}", 3000)
                except Exception as e:
                    self.statusBar().showMessage(f"Recording Import fehlgeschlagen: {e}", 4000)

            rec.set_on_recording_complete(_on_rec_complete)

            # Determine sample rate from audio engine
            sr = 48000
            try:
                sr = int(getattr(self.services.audio_engine, 'sample_rate', 48000) or 48000)
            except Exception:
                pass

            # v0.0.20.636: Sync buffer size from audio settings
            try:
                _keys = SettingsKeys()
                _buf = int(get_value(_keys.buffer_size, 512))
                _buf = int(get_value(_keys.buffer_size, 512))
                rec.set_buffer_size(_buf)
            except Exception:
                pass

            # v0.0.20.637: Sync punch state to RecordingService
            try:
                t = self.services.transport
                rec.set_punch(
                    bool(t.punch_enabled),
                    float(t.punch_in_beat),
                    float(t.punch_out_beat),
                )
            except Exception:
                pass

            # v0.0.20.638: Pre-Roll Auto-Seek (Pro Tools/Logic style)
            # When punch+record: seek playhead to punch_in minus pre-roll bars
            try:
                t = self.services.transport
                if t.punch_enabled:
                    seek_beat = t.get_punch_play_start_beat()
                    t.seek(seek_beat)
            except Exception:
                pass

            # v0.0.20.639: Setup loop-recording if transport loop is active
            self._setup_loop_recording_for_record_start()

            # Start recording (uses all armed tracks)
            success = rec.start_recording(
                sample_rate=sr,
                channels=2,
            )

            if success:
                self._recording_active = True
                self._recording_track_id = armed_tracks[0][0]  # compat: first track
                self._recording_start_beat = float(
                    getattr(self.services.transport, "current_beat", 0.0) or 0.0
                )
                backend = rec.get_backend()
                n_tracks = len(armed_tracks)
                self.statusBar().showMessage(
                    f"Recording: {n_tracks} Track(s), {backend}, Buffer {rec.get_buffer_size()}",
                    2000,
                )
            else:
                self.statusBar().showMessage(
                    f"Recording Start fehlgeschlagen ({rec.get_backend()})", 4000
                )
                try:
                    self.transport.btn_rec.blockSignals(True)
                    self.transport.btn_rec.setChecked(False)
                    self.transport.btn_rec.blockSignals(False)
                except Exception:
                    pass
            return

        if (not enabled) and rec.is_recording():
            # --- STOP RECORDING ---
            n_armed = len(rec.get_armed_track_ids())
            wav_path = rec.stop_recording()
            self._recording_active = False

            if wav_path:
                self.statusBar().showMessage(
                    f"Recording gespeichert: {n_armed} Track(s)", 3000
                )
            else:
                self.statusBar().showMessage("Recording: Keine Daten aufgenommen.", 3000)

            self._recording_track_id = None
            self._recording_wav_path = None
            self._recording_start_beat = 0.0
            return

    def _on_record_toggled_legacy(self, enabled: bool) -> None:
        """Legacy JACK-only recording path (pre-v0.0.20.632)."""
        enabled = bool(enabled)
        # Only JACK backend for now
        if str(self.services.audio_engine.backend) != "jack":
            self.statusBar().showMessage("Recording: aktuell nur im JACK-Backend (Audio → Einstellungen) unterstützt.", 3000)
            try:
                self.transport.btn_rec.blockSignals(True)
                self.transport.btn_rec.setChecked(False)
                self.transport.btn_rec.blockSignals(False)
            except Exception:
                pass
            return

        if enabled and not self._recording_active:
            # choose armed track
            tid = None
            try:
                for t in self.services.project.ctx.project.tracks:
                    if bool(getattr(t, "record_arm", False)):
                        tid = str(t.id)
                        break
            except Exception:
                tid = None
            if not tid:
                # fallback: ensure audio track
                try:
                    tid = str(self.services.project.ensure_audio_track())
                except Exception:
                    tid = None
            if not tid:
                self.statusBar().showMessage("Recording: Kein Track verfügbar.", 2500)
                return

            self._recording_track_id = tid
            self._recording_start_beat = float(getattr(self.services.transport, "current_beat", 0.0) or 0.0)

            # temp wav path (project import happens on stop)
            import os
            from pathlib import Path
            import time
            cache = Path(os.path.expanduser("~/.cache/Py_DAW/recordings"))
            cache.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            wav_path = cache / f"rec_{ts}.wav"
            self._recording_wav_path = str(wav_path)

            # Determine stereo input pair from the armed track (defaults to 1)
            pair = 1
            try:
                trk = next((t for t in self.services.project.ctx.project.tracks if str(getattr(t, "id", "")) == str(tid)), None)
                pair = max(1, int(getattr(trk, "input_pair", 1) or 1)) if trk is not None else 1
            except Exception:
                pair = 1

            # Push per-track monitoring routes so input monitoring works immediately
            try:
                self._update_jack_monitor_routes()
            except Exception:
                pass

            try:
                self.services.jack.start_async(client_name="PyDAW")
                self.services.jack.start_recording(str(wav_path), stereo_pair=pair)
                self._recording_active = True
                self.statusBar().showMessage(f"Recording: läuft (Stereo {pair})…", 2000)
            except Exception as e:
                self._recording_active = False
                self.statusBar().showMessage(f"Recording Start fehlgeschlagen: {e}", 4000)
                try:
                    self.transport.btn_rec.blockSignals(True)
                    self.transport.btn_rec.setChecked(False)
                    self.transport.btn_rec.blockSignals(False)
                except Exception:
                    pass
            return

        if (not enabled) and self._recording_active:
            # stop recording and create clip
            try:
                self.services.jack.stop_recording()
            except Exception:
                pass
            self._recording_active = False

            try:
                from pathlib import Path
                wav_path = Path(str(self._recording_wav_path or ""))
                if wav_path.exists():
                    self.services.project.add_audio_clip_from_file_at(
                        track_id=str(self._recording_track_id or ""),
                        path=wav_path,
                        start_beats=float(self._recording_start_beat or 0.0),
                    )
                    self.statusBar().showMessage("Recording: Import läuft…", 2000)
                else:
                    self.statusBar().showMessage("Recording: WAV-Datei nicht gefunden.", 3000)
            except Exception as e:
                self.statusBar().showMessage(f"Recording Import fehlgeschlagen: {e}", 4000)

            self._recording_track_id = None
            self._recording_wav_path = None
            self._recording_start_beat = 0.0
            return

    def _on_play_clicked(self) -> None:
        """Play button handler.

        If MIDI pre-render is enabled, we optionally build cache..."""
        try:
            if bool(self.services.transport.playing):
                self.services.transport.toggle_play()
                return
        except Exception:
            pass

        # Not currently playing: optional MIDI pre-render gate (performance mode)
        try:
            keys = SettingsKeys()
            wait = self._setting_bool(keys.prerender_wait_before_play, True)
            show = self._setting_bool(keys.prerender_show_progress_on_play, True)
        except Exception:
            wait = True
            show = True

        if wait:
            started = False
            try:
                started = self._start_midi_prerender(show_dialog=show, play_after=True)
            except Exception:
                started = False
            if started:
                return

        try:
            self.services.transport.toggle_play()
        except Exception:
            pass

    def _on_stop_clicked(self) -> None:
        """DAW-style stop: first press stops, second press resets to 0."""
        try:
            if bool(self.services.transport.playing):
                self.services.transport.stop()
                # Fail-safe: Audio-Engine immer hart stoppen (sounddevice *und* JACK).
                # Hintergrund: In manchen Versionen ist die Transport->Audio-Bindung
                # nicht vollständig, oder JACK-Playback läuft ohne Engine-Thread.
                try:
                    self.services.audio_engine.stop()
                except Exception:
                    pass
            else:
                self.services.transport.reset()
        except Exception:
            # Fallback: stop only
            try:
                self.services.transport.stop()
            except Exception:
                pass

        # Zweiter Fail-safe: falls noch JACK-Render aktiv ist, sicher entfernen.
        try:
            if hasattr(self.services, "jack"):
                self.services.jack.clear_render_callback()
        except Exception:
            pass

    def _on_midi_notes_committed(self, clip_id: str) -> None:
        """When MIDI edits are committed, refresh playback while playing."""
        try:
            if bool(self.services.transport.playing):
                # Debounce to avoid restart storms during rapid edits.
                self._midi_refresh_timer.start(80)
        except Exception:
            pass

    def _restart_playback_if_playing(self) -> None:
        try:
            if bool(self.services.transport.playing):
                # Keep transport running; rebuild engine snapshot.
                self.services.audio_engine.start_arrangement_playback()
        except Exception:
            pass

    # --- performance / pre-render

    def _setting_bool(self, key: str, default: bool) -> bool:
        """Read a bool-like value from SettingsStore."""
        try:
            v = str(get_value(key, "1" if default else "0")).strip().lower()
            return v in ("1", "true", "yes", "on")
        except Exception:
            return bool(default)

    def _on_project_opened(self) -> None:
        """Sync BPM and Time Signature from loaded project to Transport Service.
        
        FIXED v0.0.19.7.2: Loop Bug Fix!
        
        PROBLEM:
        - Project saved at 181 BPM
        - On load: Transport still at 120 BPM (DEFAULT!)
        - Loop at Bar 6: 
          - At 181 BPM = 7.95 seconds
          - At 120 BPM = 7.95 seconds = Bar 4! ❌
        
        SOLUTION:
        - Load BPM from project FIRST
        - Then loop calculations are correct! ✅
        """
        try:
            project = self.services.project.ctx.project
            
            # Set BPM from loaded project
            bpm = float(getattr(project, "bpm", 120.0))
            self.services.transport.set_bpm(bpm)
            print(f"[MainWindow._on_project_opened] Set BPM to {bpm} from project")
            
            # Set Time Signature from loaded project
            ts = str(getattr(project, "time_signature", "4/4"))
            self.services.transport.set_time_signature(ts)
            print(f"[MainWindow._on_project_opened] Set Time Signature to {ts} from project")
            
            # Update Transport Bar UI
            self.transport.set_bpm(bpm)
            self.transport.set_time_signature(ts)
            
        except Exception as e:
            print(f"[MainWindow._on_project_opened] Error syncing BPM/TS: {e}")
            import traceback
            traceback.print_exc()

    def _maybe_autoprerender_after_load(self) -> None:
        """Optionally start background pre-render after project/stand load."""
        try:
            keys = SettingsKeys()
            if not self._setting_bool(keys.prerender_auto_on_load, True):
                return
            show = self._setting_bool(keys.prerender_show_progress_on_load, False)
        except Exception:
            show = False
        try:
            self._start_midi_prerender(show_dialog=show, play_after=False)
        except Exception:
            pass

    def _on_prerender_selected_clips(self) -> None:
        """Pre-render only the currently selected MIDI clips (Arranger selection)."""
        clip_ids = []
        try:
            clip_ids = list(getattr(self.arranger.canvas, "selected_clip_ids", set()) or [])
        except Exception:
            clip_ids = []

        if not clip_ids:
            try:
                self.statusBar().showMessage("Pre-Render: keine Clips ausgewählt.", 2000)
            except Exception:
                pass
            return

        self._start_midi_prerender(show_dialog=True, play_after=False, clip_ids=clip_ids)

    def _on_prerender_selected_track(self) -> None:
        """Pre-render only the currently selected track (all its MIDI clips)."""
        try:
            tid = str(getattr(self.services.project, "selected_track_id", "") or "")
        except Exception:
            tid = ""

        if not tid:
            try:
                self.statusBar().showMessage("Pre-Render: kein Track ausgewählt.", 2000)
            except Exception:
                pass
            return

        self._start_midi_prerender(show_dialog=True, play_after=False, track_id=tid)

    def _start_midi_prerender(
        self,
        show_dialog: bool = False,
        play_after: bool = False,
        clip_ids: list[str] | None = None,
        track_id: str | None = None,
    ) -> bool:
        """Start background MIDI->WAV pre-render.

        Returns True if a job was started.
        """
        ps = self.services.project
        try:
            # Avoid duplicate runs
            if bool(getattr(ps, "_prerender_running", False)):
                if show_dialog:
                    self.statusBar().showMessage("Pre-Render läuft bereits…", 1500)
                return True
        except Exception:
            pass

        try:
            total = int(ps.midi_prerender_job_count(clip_ids=clip_ids, track_id=track_id))
        except Exception:
            total = 0

        if total <= 0:
            if show_dialog:
                self.statusBar().showMessage("Pre-Render: keine MIDI-Clips zum Rendern.", 2000)
            return False

        if play_after:
            self._play_after_prerender = True

        if show_dialog and self._prerender_dialog is None:
            try:
                from PyQt6.QtWidgets import QProgressDialog
                scope = "alle MIDI-Clips"
                if clip_ids:
                    scope = f"{len(clip_ids)} Clip(s)"
                elif track_id:
                    scope = "ausgewählter Track"
                dlg = QProgressDialog(f"MIDI Pre-Render: {scope}…", "Abbrechen", 0, 100, self)
                dlg.setWindowTitle("Ready for Bach")
                dlg.setMinimumDuration(0)
                dlg.setAutoClose(True)
                dlg.setAutoReset(True)
                dlg.setValue(0)
                try:
                    dlg.canceled.connect(ps.cancel_prerender)
                except Exception:
                    pass
                dlg.show()
                self._prerender_dialog = dlg
            except Exception:
                self._prerender_dialog = None

        try:
            ps.prerender_midi_clips(clip_ids=clip_ids, track_id=track_id)
            return True
        except Exception as e:
            if show_dialog:
                self.statusBar().showMessage(f"Pre-Render Start fehlgeschlagen: {e}", 4000)
            return False

    def _on_prerender_label(self, text: str) -> None:
        try:
            if self._prerender_dialog is not None:
                self._prerender_dialog.setLabelText(str(text))
                return
        except Exception:
            pass
        try:
            self.statusBar().showMessage(str(text), 1500)
        except Exception:
            pass

    def _on_prerender_progress(self, percent: int) -> None:
        try:
            if self._prerender_dialog is not None:
                self._prerender_dialog.setValue(int(percent))
        except Exception:
            pass

    def _on_prerender_finished(self, ok: bool) -> None:
        try:
            if self._prerender_dialog is not None:
                try:
                    self._prerender_dialog.setValue(100)
                except Exception:
                    pass
                try:
                    self._prerender_dialog.close()
                except Exception:
                    pass
                self._prerender_dialog = None
        except Exception:
            self._prerender_dialog = None

        if ok:
            try:
                self.statusBar().showMessage("Pre-Render fertig.", 2000)
            except Exception:
                pass
        else:
            try:
                self.statusBar().showMessage("Pre-Render abgebrochen/fehlgeschlagen.", 3000)
            except Exception:
                pass

        if bool(self._play_after_prerender):
            self._play_after_prerender = False
            try:
                self.services.transport.toggle_play()
            except Exception:
                pass

    # --- dialogs

    def _show_midi_settings(self) -> None:
        dlg = MidiSettingsDialog(self.services.midi, self)
        dlg.exec()

    def _show_midi_mapping(self) -> None:
        try:
            dlg = MidiMappingDialog(self.services.project, self.services.midi_mapping, parent=self)
            dlg.exec()
        except Exception as e:
            try:
                self.statusBar().showMessage(f"MIDI-Mapping konnte nicht geöffnet werden: {e}", 4000)
            except Exception:
                pass

    def _show_time_signature(self) -> None:
        cur = getattr(self.services.project.ctx.project, "time_signature", "4/4")
        dlg = TimeSignatureDialog(current=cur, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._on_ts_changed_from_ui(dlg.value())

    def _show_project_settings(self) -> None:
        proj = self.services.project.ctx.project
        dlg = ProjectSettingsDialog(
            bpm=float(getattr(proj, "bpm", 120.0)),
            time_signature=str(getattr(proj, "time_signature", "4/4")),
            snap_division=str(getattr(proj, "snap_division", "1/16")),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            bpm, ts, grid = dlg.values()
            self.transport.bpm.setValue(int(round(bpm)))
            self._on_ts_changed_from_ui(ts)
            try:
                self.toolbar_panel.cmb_grid.blockSignals(True)
                self.toolbar_panel.cmb_grid.setCurrentText(grid)
            finally:
                self.toolbar_panel.cmb_grid.blockSignals(False)
            self._on_grid_changed_from_ui(grid)
            self.statusBar().showMessage("Project Settings angewendet.", 2000)

    def _restart_app(self, via_pw_jack: bool = False) -> None:
        """Startet PyDAW neu (bei JACK/PipeWire Wechseln nötig).

        Unter PipeWire ist JACK oftmals nur mit `pw-jack` erreichbar.
        """
        # Wichtig: Restart muss das aktuelle Terminal behalten (stdout/stderr),
        # damit Debug-Ausgaben sichtbar bleiben. Daher kein subprocess.Popen()+quit,
        # sondern Prozess-Ersetzung via exec.
        main_script = os.path.abspath(sys.argv[0] or "main.py")
        argv = [sys.executable, main_script] + sys.argv[1:]
        env = os.environ.copy()
        # Unbuffered, damit Logs nicht verschwinden.
        env.setdefault("PYTHONUNBUFFERED", "1")
        if via_pw_jack:
            env["PYDAW_PWJACK"] = "1"

        # Aktuelles Projekt nach Restart wieder öffnen.
        try:
            cur = getattr(self.services.project.ctx, "path", None)
            if cur:
                env["PYDAW_REOPEN_PROJECT"] = str(cur)
        except Exception:
            pass

        def _do_exec() -> None:
            try:
                try:
                    import sys as _sys
                    _sys.stdout.flush()
                    _sys.stderr.flush()
                except Exception:
                    pass
                if via_pw_jack:
                    os.execvpe("pw-jack", ["pw-jack"] + argv, env)
                else:
                    os.execvpe(sys.executable, argv, env)
            except Exception as e:
                self.statusBar().showMessage(f"Neustart fehlgeschlagen: {e}", 8000)

        # Kurz in die Eventloop zurück, damit Dialog/Statusbar noch zeichnen kann.
        QTimer.singleShot(50, _do_exec)

    def _show_workbook(self) -> None:
        """Open TEAM workbook dialog (Help -> Arbeitsmappe)."""
        try:
            from .workbook_dialog import WorkbookDialog
            dlg = WorkbookDialog(parent=self)
            dlg.exec()
        except Exception as e:
            try:
                self._show_error(f"Arbeitsmappe konnte nicht geöffnet werden: {e}")
            except Exception:
                pass

    def _show_project_compare_dialog(self) -> None:
        """Open Project Compare dialog (Projekt -> Projekt vergleichen…)."""
        try:
            svc = getattr(self.services, "project_tabs", None)
            if svc is None:
                self.statusBar().showMessage("Project Tabs Service nicht verfügbar.", 4000)
                return
            from .project_compare_dialog import ProjectCompareDialog

            dlg = ProjectCompareDialog(tab_service=svc, parent=self)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception as e:
            try:
                self._show_error(f"Projekt vergleichen konnte nicht geöffnet werden: {e}")
            except Exception:
                pass

    def _init_python_logo_animation(self) -> None:
        """Initialize Python logo button animation state from persistent settings."""
        try:
            raw = get_value(SettingsKeys.ui_python_logo_animation_enabled, default="1")
            enabled = str(raw).strip().lower() not in ("0", "false", "no", "off", "")
        except Exception:
            enabled = True

        # Update menu check state without re-entering handler.
        try:
            self.actions.help_toggle_python_animation.blockSignals(True)
            self.actions.help_toggle_python_animation.setChecked(enabled)
        finally:
            try:
                self.actions.help_toggle_python_animation.blockSignals(False)
            except Exception:
                pass

        # Apply to toolbar
        self._apply_python_logo_animation_state(enabled)

    def _on_python_logo_animation_toggled(self, checked: bool) -> None:
        self._apply_python_logo_animation_state(bool(checked))
        try:
            set_value(SettingsKeys.ui_python_logo_animation_enabled, "1" if checked else "0")
        except Exception:
            pass

    def _apply_python_logo_animation_state(self, enabled: bool) -> None:
        try:
            if hasattr(self, "toolbar_panel") and self.toolbar_panel is not None:
                self.toolbar_panel.set_python_logo_animation_enabled(enabled)
        except Exception:
            pass

    def _show_audio_settings(self) -> None:
        dlg = AudioSettingsDialog(self.services.audio_engine, jack=self.services.jack, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            if getattr(dlg, "restart_requested", False):
                via_pw = bool(getattr(dlg, "restart_via_pw_jack", False))
                self.statusBar().showMessage("Audio-Einstellungen: Neustart wird durchgeführt...", 2000)
                self._restart_app(via_pw_jack=via_pw)
                return
            self.statusBar().showMessage("Audio-Einstellungen gespeichert.", 2000)

    def _on_engine_migration_dialog(self) -> None:
        """Open the Engine Migration Dialog (Rust ↔ Python).

        v0.0.20.665 — Wired from Audio menu action.
        """
        try:
            from pydaw.ui.engine_migration_settings import EngineMigrationDialog
            dlg = EngineMigrationDialog(parent=self)
            dlg.exec()
        except Exception as exc:
            self.statusBar().showMessage(
                f"Engine Migration Dialog konnte nicht geöffnet werden: {exc}", 5000
            )

    # --- file actions

    def _new_project(self) -> None:
        self.services.project.new_project("Neues Projekt")
        proj = self.services.project.ctx.project
        self.transport.bpm.setValue(int(round(proj.bpm)))
        self._on_ts_changed_from_ui(getattr(proj, "time_signature", "4/4"))
        try:
            self.toolbar_panel.cmb_grid.blockSignals(True)
            self.toolbar_panel.cmb_grid.setCurrentText(getattr(proj, "snap_division", "1/16"))
        finally:
            self.toolbar_panel.cmb_grid.blockSignals(False)
        self.arranger.set_snap_division(getattr(proj, "snap_division", "1/16"))

    def _update_jack_monitor_routes(self) -> None:
        """Push per-track monitoring routes into the JACK client.

        - Each audio/bus track can enable monitoring ("I")
        - Each track chooses an input stereo pair (Stereo 1..N)
        - Output pair is reserved for future submix routing (defaults to Out 1)
        """
        try:
            if str(getattr(self.services.audio_engine, "backend", "")) != "jack":
                return
        except Exception:
            return

        routes: list[tuple[int, int, float]] = []
        try:
            for t in self.services.project.ctx.project.tracks:
                if getattr(t, "kind", "") not in ("audio", "bus"):
                    continue
                if not bool(getattr(t, "monitor", False)):
                    continue
                ip = max(1, int(getattr(t, "input_pair", 1) or 1))
                op = max(1, int(getattr(t, "output_pair", 1) or 1))
                gain = float(getattr(t, "volume", 1.0) or 1.0)
                routes.append((ip, op, gain))
        except Exception:
            routes = []

        try:
            self.services.jack.set_monitor_routes(routes)
        except Exception:
            pass

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Projekt öffnen",
            "",
            "Py DAW Projekt (*.pydaw.json *.json);;Alle Dateien (*)",
        )
        if not path:
            return
        self.services.project.open_project(Path(path))

    def _save_project(self) -> None:
        ctx = self.services.project.ctx
        if ctx.path:
            self.services.project.save_project_as(ctx.path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Projekt speichern",
            "",
            "Py DAW Projekt (*.pydaw.json);;JSON (*.json);;Alle Dateien (*)",
        )
        if not path:
            return
        self.services.project.save_project_as(Path(path))

    def _save_snapshot(self) -> None:
        """Speichert einen Projektstand (Snapshot) in <Projektordner>/stamps."""
        ctx = self.services.project.ctx
        if not ctx.path:
            self._set_status("Bitte zuerst das Projekt speichern (Datei → Speichern).")
            return

        label, ok = QInputDialog.getText(
            self,
            "Projektstand speichern",
            "Name/Notiz (optional):",
        )
        if not ok:
            return
        self.services.project.save_snapshot(str(label).strip())

    def _load_snapshot(self) -> None:
        """Lädt einen Projektstand (Snapshot) aus <Projektordner>/stamps."""
        ctx = self.services.project.ctx
        if not ctx.path:
            self._set_status("Kein Projektpfad vorhanden. Bitte zuerst ein Projekt speichern/öffnen.")
            return

        stamps_dir = ctx.path.parent / "stamps"
        stamps_dir.mkdir(parents=True, exist_ok=True)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Projektstand laden",
            str(stamps_dir),
            "Projektstände (*.pydaw.json *.json);;Alle Dateien (*)",
        )
        if not path:
            return
        self.services.project.load_snapshot(Path(path))

    def _import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Audio importieren",
            "",
            "Audio (*.wav *.flac *.ogg *.mp3 *.m4a *.aac *.mp4);;Alle Dateien (*)",
        )
        if not path:
            return
        self._safe_project_call('import_audio', Path(path))

    
    def _import_audio_file_to_slot(self, file_path: str, track_id: str, start_beats: float, slot_key: str) -> None:
        """Import a specific audio file into the given track at the given position.

        Used by the clip-launcher overlay drop target.
        """
        from pathlib import Path
        p = Path(str(file_path))
        if not p.exists():
            self._set_status(f"Audio-Datei nicht gefunden: {p}", 4500)
            return
        try:
            self._safe_project_call(
                "add_audio_clip_from_file_at",
                str(track_id),
                p,
                float(start_beats),
                launcher_slot_key=str(slot_key) if slot_key else None,
                place_in_arranger=False,
            )
        except Exception as e:
            self._set_status(f"Import fehlgeschlagen: {e}", 5000)

    def _import_audio_at_position(self, track_id: str, start_beats: float) -> None:
        """Import an audio file and place it at (track_id, start_beats)."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Audio importieren",
            "",
            "Audio (*.wav *.flac *.ogg *.mp3 *.m4a *.aac *.mp4);;Alle Dateien (*)",
        )
        if not path:
            return
        self._safe_project_call('import_audio_to_track_at', Path(path), track_id=str(track_id), start_beats=float(start_beats))

    def _import_midi(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "MIDI importieren",
            "",
            "MIDI (*.mid *.midi);;Alle Dateien (*)",
        )
        if not path:
            return
        self._safe_project_call(
            'import_midi',
            Path(path),
            track_id=self.services.project.active_track_id,
            start_beats=0.0,
        )

    def _add_track_from_context_menu(self, track_kind: str) -> None:
        """FIXED v0.0.19.7.19: Add track from arranger context menu.
        
        Args:
            track_kind: "audio", "instrument", or "bus"
        """
        self._safe_project_call('add_track', track_kind)
        self.statusBar().showMessage(f"{track_kind.capitalize()} Track hinzugefügt", 2000)

    # --- DAWproject Export (v0.0.20.359) ---

    def _export_dawproject(self) -> None:
        """Export the current project as .dawproject via the safe snapshot exporter."""
        from PyQt6.QtWidgets import QFileDialog, QProgressDialog, QMessageBox
        from PyQt6.QtCore import Qt

        if bool(getattr(self, "_dawproject_export_running", False)):
            self._set_status("DAWproject Export läuft bereits …", 2500)
            return

        try:
            from pydaw.fileio import build_dawproject_export_request, DawProjectExportRunnable
            from pydaw.version import __version__
        except Exception as exc:
            QMessageBox.critical(
                self,
                "DAWproject Export Fehler",
                f"Exporter konnte nicht geladen werden:\n{exc}",
            )
            self._set_status(f"DAWproject Export initialisierung fehlgeschlagen: {exc}", 5000)
            return

        ctx = self.services.project.ctx
        project = getattr(ctx, "project", None)
        if project is None:
            self._set_status("Kein Projekt zum Exportieren geladen.", 3500)
            return

        default_dir = ctx.path.parent if getattr(ctx, "path", None) else Path.home()
        default_name = getattr(project, "name", "Py_DAW_Projekt") or "Py_DAW_Projekt"
        try:
            if getattr(ctx, "path", None):
                default_name = str(ctx.path.name)
                if default_name.endswith(".pydaw.json"):
                    default_name = default_name[:-11]
                else:
                    default_name = Path(default_name).stem
        except Exception:
            default_name = str(default_name)
        default_name = str(default_name).strip() or "Py_DAW_Projekt"
        default_target = default_dir / f"{default_name}.dawproject"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "DAWproject exportieren",
            str(default_target),
            "DAWproject (*.dawproject);;Alle Dateien (*)",
        )
        if not path:
            return

        target_path = Path(path)
        project_root = ctx.path.parent if getattr(ctx, "path", None) else ctx.resolve_media_dir().parent

        request = build_dawproject_export_request(
            live_project=project,
            target_path=target_path,
            project_root=project_root,
            include_media=True,
            validate_archive=True,
            metadata={
                "title": str(getattr(project, "name", "Py_DAW Export") or "Py_DAW Export"),
                "comment": f"Exported by ChronoScaleStudio {__version__}",
            },
        )

        progress = QProgressDialog("DAWproject exportieren …", "", 0, 100, self)
        progress.setWindowTitle("DAWproject Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.setLabelText(f"Erzeuge {target_path.name} …")
        progress.show()

        runnable = DawProjectExportRunnable(request)
        self._dawproject_export_running = True
        self._dawproject_export_dialog = progress
        self._dawproject_export_runnable = runnable

        def _cleanup() -> None:
            self._dawproject_export_running = False
            self._dawproject_export_runnable = None
            self._dawproject_export_dialog = None

        def _on_progress(percent: int, message: str) -> None:
            try:
                progress.setValue(int(percent))
                progress.setLabelText(str(message))
            except Exception:
                pass

        def _on_finished(result) -> None:
            try:
                progress.setValue(100)
                progress.close()
            except Exception:
                pass
            _cleanup()
            warnings = list(getattr(result, "warnings", []) or [])
            summary_lines = [
                f"Ziel: {Path(getattr(result, 'output_path', target_path)).name}",
                f"Spuren exportiert: {getattr(result, 'tracks_exported', 0)}",
                f"Clips exportiert: {getattr(result, 'clips_exported', 0)}",
                f"Noten exportiert: {getattr(result, 'notes_exported', 0)}",
                f"Audio-Dateien eingebettet: {getattr(result, 'audio_files_embedded', 0)}",
                f"Plugin-States eingebettet: {getattr(result, 'plugin_states_embedded', 0)}",
            ]
            if warnings:
                summary_lines.append("")
                summary_lines.append(f"Warnungen ({len(warnings)}):")
                for warning in warnings[:5]:
                    summary_lines.append(f"  • {warning}")
                if len(warnings) > 5:
                    summary_lines.append(f"  … und {len(warnings) - 5} weitere")
            QMessageBox.information(
                self,
                "DAWproject Export abgeschlossen",
                "\n".join(summary_lines),
            )
            self._set_status(f"DAWproject exportiert: {Path(getattr(result, 'output_path', target_path)).name}", 5000)

        def _on_error(message: str) -> None:
            try:
                progress.close()
            except Exception:
                pass
            _cleanup()
            QMessageBox.critical(
                self,
                "DAWproject Export Fehler",
                f"Export fehlgeschlagen:\n{message}",
            )
            self._set_status(f"DAWproject Export fehlgeschlagen: {message}", 5000)

        runnable.signals.progress.connect(_on_progress)
        runnable.signals.finished.connect(_on_finished)
        runnable.signals.error.connect(_on_error)
        self.services.threadpool.pool.start(runnable)


    # --- DAWproject Import (v0.0.20.88) ---

    def _import_dawproject(self) -> None:
        """Import a .dawproject file (Bitwig/Studio One/Cubase exchange format)."""
        from PyQt6.QtWidgets import QFileDialog, QProgressDialog, QMessageBox, QCheckBox
        from PyQt6.QtCore import Qt

        path, _ = QFileDialog.getOpenFileName(
            self,
            "DAWproject importieren",
            "",
            "DAWproject (*.dawproject);;Alle Dateien (*)",
        )
        if not path:
            return

        dawproject_path = Path(path)

        # Ask user about transport settings
        update_transport = True
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("DAWproject Import")
        msg_box.setText(
            f"DAWproject importieren:\n{dawproject_path.name}\n\n"
            "Soll BPM und Taktart aus dem Projekt übernommen werden?"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        reply = msg_box.exec()
        update_transport = (reply == QMessageBox.StandardButton.Yes)

        # Progress dialog
        progress = QProgressDialog("DAWproject importieren…", "Abbrechen", 0, 100, self)
        progress.setWindowTitle("DAWproject Import")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(pct: int, msg: str):
            if progress.wasCanceled():
                return
            progress.setValue(pct)
            progress.setLabelText(msg)
            # Process events to keep UI responsive
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

        try:
            from pydaw.fileio.dawproject_importer import import_dawproject

            project = self.services.project.ctx.project
            media_dir = self.services.project.ctx.resolve_media_dir()

            result = import_dawproject(
                dawproject_path=dawproject_path,
                project=project,
                media_dir=media_dir,
                update_transport=update_transport,
                progress_cb=on_progress,
            )

            progress.close()

            # Trigger UI refresh
            self.services.project._emit_updated()

            # Summary dialog
            summary_lines = [
                f"Import aus: {result.source_app or 'Unbekannt'}",
                f"Projekt: {result.project_name}",
                "",
                f"Spuren erstellt: {result.tracks_created}",
                f"Clips erstellt: {result.clips_created}",
                f"MIDI-Noten importiert: {result.notes_imported}",
                f"Audio-Dateien kopiert: {result.audio_files_copied}",
            ]
            if result.warnings:
                summary_lines.append("")
                summary_lines.append(f"Warnungen ({len(result.warnings)}):")
                for w in result.warnings[:5]:
                    summary_lines.append(f"  • {w}")
                if len(result.warnings) > 5:
                    summary_lines.append(f"  … und {len(result.warnings) - 5} weitere")

            QMessageBox.information(
                self,
                "DAWproject Import abgeschlossen",
                "\n".join(summary_lines),
            )

            self._set_status(
                f"DAWproject Import: {result.tracks_created} Spuren, "
                f"{result.clips_created} Clips, {result.notes_imported} Noten",
                5000,
            )

        except Exception as e:
            progress.close()
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "DAWproject Import Fehler",
                f"Import fehlgeschlagen:\n{e}",
            )
            self._set_status(f"DAWproject Import fehlgeschlagen: {e}", 5000)



    def load_sf2_for_selected_track(self) -> None:
        """Load a SoundFont (SF2) for an INSTRUMENT track (with selection dialog).
        
        FIXED v0.0.19.7.3: Wenn mehrere Instrument Tracks existieren,
        zeigt Dialog zur Track-Auswahl!
        """
        # Get all instrument tracks
        tracks = self.services.project.ctx.project.tracks
        instrument_tracks = [t for t in tracks if getattr(t, "kind", "") == "instrument"]
        
        if not instrument_tracks:
            self._set_status("Keine Instrument-Tracks vorhanden. Bitte zuerst einen erstellen.")
            return
        
        # If only one instrument track, use it directly
        if len(instrument_tracks) == 1:
            tid = instrument_tracks[0].id
            trk = instrument_tracks[0]
        else:
            # Multiple instrument tracks - show selection dialog
            # FIXED v0.0.19.7.6: Show only track names (no IDs)
            track_names = []
            name_count = {}  # Track duplicate names
            
            for t in instrument_tracks:
                name = getattr(t, 'name', 'Instrument Track')
                
                # If duplicate name, add number suffix
                if name in name_count:
                    name_count[name] += 1
                    display_name = f"{name} ({name_count[name]})"
                else:
                    name_count[name] = 1
                    display_name = name
                
                track_names.append(display_name)
            
            # Try to find currently selected track as default
            current_tid = getattr(self.services.project, "active_track_id", "") or \
                         getattr(self.services.project, "selected_track_id", "") or ""
            default_idx = 0
            for i, t in enumerate(instrument_tracks):
                if t.id == current_tid:
                    default_idx = i
                    break
            
            selected_name, ok = QInputDialog.getItem(
                self,
                "Track auswählen",
                "Für welchen Instrument-Track SF2 laden?",
                track_names,
                default_idx,
                False
            )
            
            if not ok or not selected_name:
                return
            
            # Find selected track
            selected_idx = track_names.index(selected_name)
            trk = instrument_tracks[selected_idx]
            tid = trk.id
        
        # File picker for SF2
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "SoundFont (SF2) auswählen", 
            "", 
            "SoundFont (*.sf2);;Alle Dateien (*)"
        )
        if not path:
            return
        
        # Bank and Preset selection
        bank, ok1 = QInputDialog.getInt(
            self, 
            "Bank", 
            "SoundFont Bank (CC0):", 
            int(getattr(trk, "sf2_bank", 0)), 
            0, 127, 1
        )
        if not ok1:
            return
            
        preset, ok2 = QInputDialog.getInt(
            self, 
            "Preset", 
            "Program/Preset (0-127):", 
            int(getattr(trk, "sf2_preset", 0)), 
            0, 127, 1
        )
        if not ok2:
            return
        
        # Apply SF2 to track
        self.services.project.set_track_soundfont(tid, path, bank=bank, preset=preset)
        
        # v0.0.20.46: Set plugin_type for Pro-DAW-Style routing
        try:
            track = self.services.project.ctx.project.tracks_by_id().get(tid)
            if track:
                track.plugin_type = "sf2"
                self.services.project.mark_dirty()
        except Exception:
            pass
        
        self._set_status(f"SF2 geladen auf Track: {getattr(trk, 'name', 'Instrument')}")

    def _export_audio_placeholder(self) -> None:
        """FIXED v0.0.19.7.16: Professional Audio Export Dialog (Pro-DAW-Style!)"""
        from .audio_export_dialog import AudioExportDialog
        
        dialog = AudioExportDialog(self.services.project, self)
        dialog.exec()
    
    def _export_midi_clip(self) -> None:
        """FIXED v0.0.19.7.15: Export selected MIDI clip to .mid file."""
        from pydaw.audio.midi_export import export_midi_clip
        
        # Get selected clip from arranger
        if not hasattr(self.arranger, 'canvas') or not hasattr(self.arranger.canvas, 'selected_clip_id'):
            self.statusBar().showMessage("Kein Clip ausgewählt!", 3000)
            return
        
        clip_id = self.arranger.canvas.selected_clip_id
        if not clip_id:
            self.statusBar().showMessage("Bitte MIDI Clip auswählen!", 3000)
            return
        
        # Get clip
        clip = next((c for c in self.services.project.ctx.project.clips if c.id == clip_id), None)
        if not clip or getattr(clip, "kind", "") != "midi":
            self.statusBar().showMessage("Nur MIDI Clips können exportiert werden!", 3000)
            return
        
        # Get notes
        notes = self.services.project.ctx.project.midi_notes.get(clip_id, [])
        if not notes:
            self.statusBar().showMessage("Clip hat keine Noten zum Exportieren!", 3000)
            return
        
        # Ask for save location
        clip_name = getattr(clip, "name", "midi_clip")
        default_filename = f"{clip_name}.mid"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "MIDI Clip exportieren",
            default_filename,
            "MIDI Files (*.mid);;All Files (*)"
        )
        
        if not filepath:
            return
        
        # Ensure .mid extension
        if not filepath.lower().endswith('.mid'):
            filepath += '.mid'
        
        # Export
        bpm = float(getattr(self.services.project.ctx.project, "bpm", 120.0))
        success = export_midi_clip(clip, notes, Path(filepath), bpm)
        
        if success:
            self.statusBar().showMessage(f"MIDI exportiert: {Path(filepath).name}", 3000)
        else:
            self.statusBar().showMessage("MIDI Export fehlgeschlagen!", 3000)
    
    def _export_midi_track(self) -> None:
        """FIXED v0.0.19.7.15: Export all MIDI clips from selected track to .mid file."""
        from pydaw.audio.midi_export import export_midi_track
        
        # Get selected track
        track_id = self._selected_track_id()
        if not track_id:
            self.statusBar().showMessage("Bitte Track auswählen!", 3000)
            return
        
        track = next((t for t in self.services.project.ctx.project.tracks if t.id == track_id), None)
        if not track:
            self.statusBar().showMessage("Track nicht gefunden!", 3000)
            return
        
        # Get all MIDI clips for this track
        clips = [c for c in self.services.project.ctx.project.clips 
                if getattr(c, 'track_id', '') == track_id and getattr(c, 'kind', '') == 'midi']
        
        if not clips:
            self.statusBar().showMessage("Track hat keine MIDI Clips zum Exportieren!", 3000)
            return
        
        # Ask for save location
        track_name = getattr(track, "name", "track")
        default_filename = f"{track_name}.mid"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "MIDI Track exportieren",
            default_filename,
            "MIDI Files (*.mid);;All Files (*)"
        )
        
        if not filepath:
            return
        
        # Ensure .mid extension
        if not filepath.lower().endswith('.mid'):
            filepath += '.mid'
        
        # Export
        bpm = float(getattr(self.services.project.ctx.project, "bpm", 120.0))
        midi_notes_map = self.services.project.ctx.project.midi_notes
        success = export_midi_track(track, self.services.project.ctx.project.clips, midi_notes_map, Path(filepath), bpm)
        
        if success:
            self.statusBar().showMessage(f"Track exportiert: {Path(filepath).name}", 3000)
        else:
            self.statusBar().showMessage("MIDI Track Export fehlgeschlagen!", 3000)

    # --- selection helpers

    def _selected_track_id(self) -> str:
        try:
            return self.arranger.tracks.selected_track_id()
        except Exception:
            return ""

    def _browser_add_scope_info(self, kind: str = ""):
        try:
            dp = getattr(self, "device_panel", None)
            if dp is not None and hasattr(dp, "browser_add_scope"):
                return dp.browser_add_scope(kind)
        except Exception:
            pass
        return ("Ziel: Spur", "Aktive Spur konnte nicht sicher ermittelt werden.")

    def _on_track_selected(self, track_id: str) -> None:
        try:
            self.services.project._selected_track_id = str(track_id or "")
        except Exception:
            pass
        # Drive the parameter inspector.
        try:
            self.track_params.set_track(self.services.project, track_id)
        except Exception:
            pass

        # Switch device panel to selected track (Pro-DAW-Style per-track binding)
        try:
            self.device_panel.show_track(track_id)
        except Exception:
            pass

        try:
            self.library.set_selected_track(track_id)
        except Exception:
            pass

        # v0.0.20.42: Instrument tracks start EMPTY (Ableton/Pro-DAW behavior).
        # The user adds instruments explicitly via Browser → Instruments → 'Add to Device'.
        # We still register existing samplers in the global registry for note routing.
        try:
            trk = next(
                (t for t in self.services.project.ctx.project.tracks if t.id == track_id),
                None,
            )
            if trk and getattr(trk, "kind", "") == "instrument":
                # Register sampler in global registry for unified note routing
                try:
                    from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                    registry = get_sampler_registry()
                    if not registry.has_sampler(track_id):
                        devices = self.device_panel.get_track_devices(track_id)
                        for dev in devices:
                            engine = getattr(dev, "engine", None)
                            if engine is not None and hasattr(engine, "trigger_note"):
                                registry.register(track_id, engine, dev)
                                break
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_selected_track(self) -> None:
        tid = self._selected_track_id()
        if not tid:
            return
        # Unregister from sampler registry before deleting
        try:
            if self._sampler_registry:
                self._sampler_registry.unregister(tid)
        except Exception:
            pass
        self.services.project.remove_track(tid)

    def _on_note_preview_routed(self, pitch: int, velocity: int,
                                 duration_ms: int) -> None:
        """Route note_preview to the selected track's sampler via registry.
        v0.0.20.43: Ensures preview output is active after triggering.
        """
        try:
            tid = self._selected_track_id() or ""
            triggered = False
            if tid and self._sampler_registry:
                if self._sampler_registry.trigger_note(tid, pitch, velocity,
                                                        duration_ms):
                    triggered = True
            # Fallback: broadcast to all registered samplers
            if not triggered and self._sampler_registry:
                for t in self._sampler_registry.all_track_ids():
                    if self._sampler_registry.trigger_note(t, pitch, velocity,
                                                             duration_ms):
                        triggered = True
                        break
            # v0.0.20.43: Ensure audio engine output is active for preview
            if triggered:
                try:
                    self.services.audio_engine.ensure_preview_output()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_midi_panic(self, _reason: str = "") -> None:
        """Stop all sampler voices and clear stuck notes."""
        try:
            if getattr(self, "_sampler_registry", None):
                self._sampler_registry.all_notes_off()
        except Exception:
            pass


    def _on_live_note_on_route_to_sampler(self, clip_id: str, track_id: str, pitch: int,
                                         velocity: int, channel: int, start_beats: float) -> None:
        """Route live MIDI key-down to sampler registry AND VST instruments (sustained).

        v0.0.20.398: Also routes to VST2/VST3 instrument engines.
        """
        try:
            if getattr(self, "_sampler_registry", None):
                ok = bool(self._sampler_registry.note_on(str(track_id), int(pitch), int(velocity)))
                if not ok:
                    # Try VST instrument engines
                    ok = self._route_live_note_to_vst(track_id, pitch, velocity, is_on=True)
                if not ok:
                    import time
                    now = time.time()
                    last = float(getattr(self, "_last_no_sample_warn_ts", 0.0) or 0.0)
                    if (now - last) > 1.25:
                        self._last_no_sample_warn_ts = now
                        try:
                            self.statusBar().showMessage(
                                "Kein Sound: Im Device-Tab den Sampler öffnen und ein Sample laden (oder Audio-Backend prüfen).",
                                3000,
                            )
                        except Exception:
                            pass
            else:
                # No sampler registry — try VST instruments directly
                self._route_live_note_to_vst(track_id, pitch, velocity, is_on=True)
        except Exception:
            pass

    def _on_live_note_off_route_to_sampler(self, clip_id: str, track_id: str, pitch: int, channel: int) -> None:
        """Route live MIDI key-up to sampler registry AND VST instruments (release).

        v0.0.20.398: Also routes to VST2/VST3 instrument engines.
        """
        try:
            if getattr(self, "_sampler_registry", None):
                self._sampler_registry.note_off(str(track_id), pitch=int(pitch))
            # Always also try VST instruments
            self._route_live_note_to_vst(track_id, pitch, 0, is_on=False)
        except Exception:
            pass

    def _route_live_note_to_vst(self, track_id: str, pitch: int, velocity: int, is_on: bool) -> bool:
        """Route live MIDI to VST2/VST3 instrument engines.

        v0.0.20.398: Enables live keyboard → VST instrument sound.
        Returns True if an engine was found and the note was sent.
        """
        try:
            ae = getattr(self.services, "audio_engine", None)
            if ae is None:
                return False
            engines = getattr(ae, "_vst_instrument_engines", None)
            if not isinstance(engines, dict):
                return False
            engine = engines.get(str(track_id))
            if engine is None:
                return False
            # v0.0.20.557: Skip layer dispatchers — SamplerRegistry handles them
            if getattr(engine, "_is_layer_dispatcher", False):
                return False
            if is_on:
                engine.note_on(int(pitch), int(velocity))
            else:
                engine.note_off(int(pitch))
            return True
        except Exception:
            return False


    def _add_clip_to_selected_track(self) -> None:
        tid = self._selected_track_id()
        if not tid:
            return
        trk = next((t for t in self.services.project.ctx.project.tracks if t.id == tid), None)
        kind = "midi" if (trk and trk.kind == "instrument") else "audio"
        before = [c.id for c in self.services.project.ctx.project.clips]
        self.services.project.add_placeholder_clip_to_track(tid, kind=kind)
        after = [c.id for c in self.services.project.ctx.project.clips]
        new_ids = [x for x in after if x not in before]
        if kind == "midi" and new_ids:
            self._safe_call(self._on_clip_activated, new_ids[-1])

    # --- Arranger selection + context actions

    def _on_clip_selected(self, clip_id: str) -> None:
        self._safe_project_call('select_clip', clip_id or "")
        try:
            clip = next((c for c in (self.services.project.ctx.project.clips or []) if str(getattr(c, "id", "") or "") == str(clip_id or "")), None)
            track_id = str(getattr(clip, "track_id", "") or "") if clip is not None else ""
            if track_id and hasattr(self.arranger, 'tracks') and hasattr(self.arranger.tracks, 'select_track'):
                self.arranger.tracks.select_track(track_id)
        except Exception:
            pass

    def _rename_clip_dialog(self, clip_id: str) -> None:
        clip = next((c for c in self.services.project.ctx.project.clips if c.id == clip_id), None)
        if not clip:
            return
        text, ok = QInputDialog.getText(self, "Clip umbenennen", "Neuer Name:", text=clip.label)
        if ok and text.strip():
            self.services.project.rename_clip(clip_id, text.strip())

    # --- docks / panels

    def _toggle_pianoroll(self, checked: bool) -> None:
        self.pianoroll_dock.setVisible(bool(checked))

    def _toggle_notation(self, checked: bool) -> None:
        """Enable/disable the Notation tab (WIP).

        This toggles the Notation editor tab (WIP). The editor is lightweight and safe.
        """
        checked = bool(checked)
        try:
            set_value(SettingsKeys.ui_enable_notation_tab, checked)
        except Exception:
            # settings failure should not block the UI
            pass
        try:
            self.editor_tabs.set_notation_tab_visible(checked)
            if checked:
                self.editor_tabs.show_notation()
        except Exception:
            # Do not crash the app if something goes wrong
            pass

    def _toggle_cliplauncher(self, checked: bool) -> None:
        checked = bool(checked)
        self.launcher_dock.setVisible(checked)
        # Persist
        try:
            set_value(SettingsKeys.ui_cliplauncher_visible, checked)
        except Exception:
            pass
        # Enable/disable overlay toggle based on visibility
        try:
            self.actions.view_toggle_drop_overlay.setEnabled(checked)
        except Exception:
            pass
        # If launcher is hidden, ensure overlay can't block arranger
        if not checked:
            try:
                self.arranger.deactivate_clip_overlay()
            except Exception:
                pass

    def _toggle_drop_overlay(self, checked: bool) -> None:
        checked = bool(checked)
        # Persist
        try:
            set_value(SettingsKeys.ui_cliplauncher_overlay_enabled, checked)
        except Exception:
            pass
        # If disabled, ensure overlay is not active
        if not checked:
            try:
                self.arranger.deactivate_clip_overlay()
            except Exception:
                pass

    def _toggle_gpu_waveforms(self, checked: bool) -> None:
        """Enable/disable the optional GPU waveform overlay in the Arranger.

        Safety: the overlay is opt-in. On some compositors/drivers an OpenGL
        overlay can hide the grid if it paints an opaque background.
        """
        checked = bool(checked)
        try:
            set_value(SettingsKeys.ui_gpu_waveforms_enabled, checked)
        except Exception:
            pass

        # Apply to ArrangerCanvas
        try:
            if hasattr(self, "arranger") and hasattr(self.arranger, "canvas"):
                self.arranger.canvas.set_gpu_waveforms_enabled(checked)
        except Exception:
            pass

        # Visible indicator
        try:
            if getattr(self, "_gpu_status_label", None) is not None:
                self._gpu_status_label.setText("GPU: ON" if checked else "GPU: OFF")
        except Exception:
            pass
        try:
            self.statusBar().showMessage("GPU Waveforms: ON" if checked else "GPU Waveforms: OFF", 2000)
        except Exception:
            pass

    def _toggle_cpu_meter(self, checked: bool) -> None:
        """Enable/disable a tiny CPU indicator in the status bar.

        This is intentionally very cheap:
        - QTimer in GUI thread (default 1000ms)
        - `time.process_time()` deltas / wall deltas
        - No audio-thread involvement

        Default is OFF (opt-in), to keep the UI minimal.
        """
        self._apply_cpu_meter_state(bool(checked), persist=True)

    def _apply_cpu_meter_state(self, enabled: bool, persist: bool = True) -> None:
        enabled = bool(enabled)

        if persist:
            try:
                set_value(SettingsKeys.ui_cpu_meter_enabled, enabled)
            except Exception:
                pass

        # Label visibility
        try:
            if getattr(self, "_cpu_status_label", None) is not None:
                self._cpu_status_label.setVisible(enabled)
                if not enabled:
                    self._cpu_status_label.setText("")
        except Exception:
            pass

        if not enabled:
            try:
                if getattr(self, "_cpu_monitor", None) is not None:
                    self._cpu_monitor.stop()
            except Exception:
                pass
            try:
                self.statusBar().showMessage("CPU Anzeige: OFF", 1500)
            except Exception:
                pass
            return

        # Lazy create monitor
        if getattr(self, "_cpu_monitor", None) is None:
            try:
                self._cpu_monitor = CpuUsageMonitor(interval_ms=1000, parent=self)
                self._cpu_monitor.updated.connect(self._on_cpu_meter_updated)
            except Exception:
                self._cpu_monitor = None

        try:
            if self._cpu_monitor is not None:
                self._cpu_monitor.start()
        except Exception:
            pass

        try:
            self.statusBar().showMessage("CPU Anzeige: ON", 1500)
        except Exception:
            pass

    def _on_cpu_meter_updated(self, pct: float) -> None:
        try:
            if getattr(self, "_cpu_status_label", None) is None:
                return
            # round for stability; avoid flicker
            val = int(round(float(pct)))
            if val < 0:
                val = 0
            # very high values can happen on weird timers; clamp for display
            if val > 999:
                val = 999
            self._cpu_status_label.setText(f"CPU: {val}%")
        except Exception:
            pass

    # ── v0.0.20.696: Rust Audio-Engine Toggle ──────────────────────────────

    def _toggle_rust_engine(self, checked: bool) -> None:
        """Toggle the Rust Audio-Engine on/off.

        Persists to QSettings AND sets the USE_RUST_ENGINE env var so the
        engine_migration controller and rust_engine_bridge pick it up
        immediately. Takes effect on next playback start.
        """
        self._apply_rust_engine_state(bool(checked), persist=True)

    def _apply_rust_engine_state(self, enabled: bool, persist: bool = True) -> None:
        import os
        enabled = bool(enabled)

        # Persist to QSettings
        if persist:
            try:
                set_value(SettingsKeys.audio_rust_engine_enabled, enabled)
            except Exception:
                pass

        # Set env var for immediate effect
        os.environ["USE_RUST_ENGINE"] = "1" if enabled else "0"

        # Update status label
        try:
            lbl = getattr(self, "_rust_status_label", None)
            if lbl is not None:
                if enabled:
                    lbl.setText("R: ON")
                    lbl.setStyleSheet(
                        "QLabel { color: #ff6e40; font-weight: bold; "
                        "padding: 0 4px; }"
                    )
                else:
                    lbl.setText("R: OFF")
                    lbl.setStyleSheet(
                        "QLabel { color: #666; padding: 0 4px; }"
                    )
        except Exception:
            pass

        # Status bar feedback
        try:
            if enabled:
                self.statusBar().showMessage(
                    "🦀 Rust Audio-Engine: AKTIV — wird beim nächsten Play wirksam", 3000
                )
            else:
                self.statusBar().showMessage(
                    "🐍 Python Audio-Engine — Rust deaktiviert", 3000
                )
        except Exception:
            pass

    # ── v0.0.20.701: Plugin Sandbox Toggle ─────────────────────────────────

    def _toggle_plugin_sandbox(self, checked: bool) -> None:
        """Toggle plugin sandbox (crash-safe subprocess hosting)."""
        checked = bool(checked)
        try:
            set_value(SettingsKeys.audio_plugin_sandbox_enabled, checked)
        except Exception:
            pass

        try:
            if checked:
                self.statusBar().showMessage(
                    "🛡️ Plugin Sandbox: AN — Plugins werden crash-sicher geladen (beim nächsten Laden)", 3000
                )
                self._start_sandbox_monitor()
            else:
                self.statusBar().showMessage(
                    "Plugin Sandbox: AUS — Plugins laufen im Hauptprozess", 3000
                )
                self._stop_sandbox_monitor()
        except Exception:
            pass

    # ── v0.0.20.702: Sandbox Status Monitor ────────────────────────────────

    def _start_sandbox_monitor(self) -> None:
        """Start periodic sandbox status polling (2 Hz)."""
        # v0.0.20.704: Initialize crash log
        if not hasattr(self, '_crash_log') or self._crash_log is None:
            try:
                from pydaw.ui.crash_indicator_widget import CrashLog
                self._crash_log = CrashLog()
            except Exception:
                self._crash_log = None

        # v0.0.20.704: Wire crash callback to log entries
        try:
            from pydaw.services.sandbox_process_manager import get_process_manager
            mgr = get_process_manager()
            if self._crash_log is not None:
                def _on_crash(track_id, slot_id, error_msg,
                              log=self._crash_log):
                    try:
                        from pydaw.ui.crash_indicator_widget import CrashLogEntry
                        entry = CrashLogEntry(
                            track_id=track_id, slot_id=slot_id,
                            error_message=error_msg)
                        log.add(entry)
                    except Exception:
                        pass
                mgr.set_crash_callback(_on_crash)
        except Exception:
            pass

        if not hasattr(self, '_sandbox_timer') or self._sandbox_timer is None:
            from PyQt6.QtCore import QTimer
            self._sandbox_timer = QTimer(self)
            self._sandbox_timer.setInterval(500)  # 2 Hz
            self._sandbox_timer.timeout.connect(self._poll_sandbox_status)
        if not self._sandbox_timer.isActive():
            self._sandbox_timer.start()

    def _stop_sandbox_monitor(self) -> None:
        """Stop sandbox status polling."""
        if hasattr(self, '_sandbox_timer') and self._sandbox_timer is not None:
            self._sandbox_timer.stop()
        # Hide status widget
        if hasattr(self, '_sandbox_status') and self._sandbox_status is not None:
            self._sandbox_status.setVisible(False)

    def _poll_sandbox_status(self) -> None:
        """Poll sandbox process manager and update statusbar + mixer strips."""
        try:
            from pydaw.services.sandbox_process_manager import get_process_manager
            mgr = get_process_manager()
            status_list = mgr.get_all_status()
            if not status_list:
                if hasattr(self, '_sandbox_status') and self._sandbox_status:
                    self._sandbox_status.update_status(0, 0, 0)
                return

            total = len(status_list)
            crashed = sum(1 for s in status_list if s.get("crashed", False))
            alive = sum(1 for s in status_list if s.get("alive", False))

            if hasattr(self, '_sandbox_status') and self._sandbox_status:
                self._sandbox_status.update_status(total, crashed, alive)

            # v0.0.20.704: Update mixer strips with crash state
            try:
                mixer = getattr(self, 'mixer', None)
                if mixer is not None and hasattr(mixer, '_strips'):
                    # Build map: track_id → status
                    crash_map = {}
                    for s in status_list:
                        tid = s.get("track_id", "")
                        if not tid:
                            continue
                        if s.get("crashed", False):
                            crash_map[tid] = ("crashed", s.get("error", ""),
                                              s.get("crash_count", 0))
                        elif s.get("alive", False):
                            crash_map[tid] = ("running", "", 0)
                        else:
                            crash_map[tid] = ("disabled", s.get("error", ""), 0)

                    for tid, strip in mixer._strips.items():
                        if tid in crash_map:
                            state, err, cc = crash_map[tid]
                            if hasattr(strip, 'set_sandbox_state'):
                                strip.set_sandbox_state(state, err, cc)
                        else:
                            if hasattr(strip, 'set_sandbox_state'):
                                strip.set_sandbox_state("hidden")
            except Exception:
                pass
        except Exception:
            pass

    # ── v0.0.20.704: Sandbox Dialog Handlers (P6C) ────────────────────────

    def _on_sandbox_restart_all(self) -> None:
        """Restart all sandboxed plugin workers."""
        try:
            from pydaw.services.sandbox_process_manager import get_process_manager
            mgr = get_process_manager()
            status_list = mgr.get_all_status()
            count = 0
            for s in status_list:
                tid = s.get("track_id", "")
                sid = s.get("slot_id", "")
                if tid and sid:
                    mgr.restart(tid, sid)
                    count += 1
            self.statusBar().showMessage(
                f"🔄 {count} Plugin-Worker werden neu gestartet…", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Fehler: {e}", 3000)

    def _on_sandbox_status_dialog(self) -> None:
        """Open the Sandbox Status Dialog (P6C)."""
        try:
            from pydaw.ui.sandbox_status_dialog import SandboxStatusDialog
            dlg = SandboxStatusDialog(parent=self)
            dlg.show()
        except Exception as e:
            self.statusBar().showMessage(f"Sandbox-Status Fehler: {e}", 3000)

    def _on_crash_log_dialog(self) -> None:
        """Open the Crash Log Dialog (P6B/P6C)."""
        try:
            from pydaw.ui.sandbox_status_dialog import CrashLogDialog
            crash_log = getattr(self, '_crash_log', None)
            if crash_log is None:
                try:
                    from pydaw.ui.crash_indicator_widget import CrashLog
                    self._crash_log = CrashLog()
                    crash_log = self._crash_log
                except Exception:
                    pass
            dlg = CrashLogDialog(crash_log=crash_log, parent=self)
            dlg.show()
        except Exception as e:
            self.statusBar().showMessage(f"Crash-Log Fehler: {e}", 3000)

    def _on_plugin_blacklist_dialog(self) -> None:
        """Open the Plugin Blacklist Dialog (v0.0.20.725)."""
        try:
            from pydaw.ui.plugin_blacklist_dialog import PluginBlacklistDialog
            dlg = PluginBlacklistDialog(parent=self)
            dlg.exec()
        except Exception as e:
            self.statusBar().showMessage(f"Blacklist-Dialog Fehler: {e}", 3000)

    def _on_sample_drag_started(self, label: str) -> None:
        """Called when a sample drag starts in the Browser.

        Important: Only activate the Clip-Launcher overlay if:
        - Clip Launcher view is enabled
        - Overlay toggle is enabled
        Otherwise: keep overlay off so normal Arranger drops work.
        """
        try:
            if not bool(self.actions.view_toggle_cliplauncher.isChecked()):
                # safety: ensure overlay is off
                try:
                    self.arranger.deactivate_clip_overlay()
                except Exception:
                    pass
                return
            if hasattr(self.actions, 'view_toggle_drop_overlay') and not bool(self.actions.view_toggle_drop_overlay.isChecked()):
                try:
                    self.arranger.deactivate_clip_overlay()
                except Exception:
                    pass
                return
        except Exception:
            # In doubt, do not block arranger
            try:
                self.arranger.deactivate_clip_overlay()
            except Exception:
                pass
            return

        self.arranger.activate_clip_overlay(str(label))

    def _on_sample_drag_ended(self) -> None:
        try:
            self.arranger.deactivate_clip_overlay()
        except Exception:
            pass

    def _toggle_automation(self, checked: bool) -> None:
        self.arranger.set_automation_visible(bool(checked))
        # keep actions + toolbar in sync
        if self.actions.view_toggle_automation.isChecked() != bool(checked):
            self.actions.view_toggle_automation.blockSignals(True)
            self.actions.view_toggle_automation.setChecked(bool(checked))
            self.actions.view_toggle_automation.blockSignals(False)

        # keep toolbar "Automation" button in sync (if present)
        try:
            tp = getattr(self, "toolbar_panel", None)
            btn = getattr(tp, "btn_auto", None) if tp is not None else None
            if btn is not None and btn.isChecked() != bool(checked):
                btn.blockSignals(True)
                btn.setChecked(bool(checked))
                btn.blockSignals(False)
        except Exception:
            pass

    def _on_clip_activated(self, clip_id: str) -> None:
        clip = next((c for c in self.services.project.ctx.project.clips if c.id == clip_id), None)
        if not clip:
            return

        self.services.project.select_clip(clip_id)

        # v0.0.20.612: Dual-Clock Phase D — Arranger-Fokus setzen
        # NUR wenn der Fokus nicht bereits vom Launcher für denselben Clip gesetzt wurde
        try:
            cc = getattr(self.services, 'clip_context', None)
            if cc is not None:
                existing = cc.get_editor_focus()
                # Überspringen wenn Launcher bereits Fokus für diesen Clip gesetzt hat
                if not (existing and existing.is_launcher and existing.clip_id == clip_id):
                    ctx = cc.build_arranger_focus(clip_id)
                    if ctx is not None:
                        cc.set_editor_focus(ctx)
        except Exception:
            pass

        if clip.kind == "midi":
            # Switch to edit view (was missing!)
            self._set_view_mode("edit", force=True)
            self.editor_dock.show()
            self.editor_dock.raise_()
            try:
                # Prefer notation if it's the current tab, otherwise piano roll
                if (self.editor_tabs.is_notation_tab_visible()
                        and self.editor_tabs.tabs.currentWidget() == getattr(self.editor_tabs, 'notation', None)):
                    self.editor_tabs.show_notation()
                else:
                    self.editor_tabs.show_pianoroll()
            except Exception:
                pass
            self.actions.view_toggle_pianoroll.setChecked(True)
        elif clip.kind == "audio":
            self._set_view_mode("edit", force=True)
            self.editor_dock.show()
            self.editor_dock.raise_()
            try:
                self.editor_tabs.show_audio()
            except Exception:
                pass
        else:
            self.statusBar().showMessage("Unbekannter Clip-Typ.", 2000)

    # --- Drag & Drop import (WAV/AIFF/MID)

    def _on_clip_edit_requested(self, clip_id: str) -> None:
        """Open the dedicated editor on double click (Clip Launcher)."""
        clip = next((c for c in self.services.project.ctx.project.clips if c.id == clip_id), None)
        if not clip:
            return

        self.services.project.select_clip(clip_id)

        # ensure editor dock visible
        self.editor_dock.show()
        self.actions.view_toggle_pianoroll.setChecked(True)

        if getattr(clip, "kind", "") == "midi":
            # prefer current editor if it's Notation and enabled; otherwise PianoRoll
            try:
                if self.editor_tabs.is_notation_tab_visible() and self.editor_tabs.tabs.currentWidget() == self.editor_tabs.notation:
                    self.editor_tabs.show_notation()
                else:
                    self.editor_tabs.show_pianoroll()
            except Exception:
                pass
            return

        if getattr(clip, "kind", "") == "audio":
            try:
                self.editor_tabs.show_audio()
            except Exception:
                pass
            return

        self.statusBar().showMessage("Unbekannter Clip-Typ.", 2000)


    def dragEnterEvent(self, event):  # type: ignore[override]
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = event.mimeData()
            if md and md.hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    def dropEvent(self, event):  # type: ignore[override]
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = event.mimeData()
            if not md or not md.hasUrls():
                event.ignore(); return

            paths: list[Path] = []
            for url in md.urls():
                try:
                    p = Path(url.toLocalFile())
                except Exception:
                    continue
                if p.exists() and p.is_file():
                    paths.append(p)

            if not paths:
                self.statusBar().showMessage("Keine Datei erkannt.", 2000)
                return

            imported = 0
            for p in paths:
                suf = p.suffix.lower()
                try:
                    if suf in (".mid", ".midi"):
                        self.services.project.import_midi(p)
                        imported += 1
                    elif suf in (".wav", ".aif", ".aiff", ".flac", ".ogg"):
                        self.services.project.import_audio(p)
                        imported += 1
                except Exception as e:  # noqa: BLE001
                    self.statusBar().showMessage(f"Import-Fehler ({p.name}): {e}", 4000)

            if imported:
                self.statusBar().showMessage(f"Importiert: {imported} Datei(en)", 3000)
            else:
                self.statusBar().showMessage("Keine unterstützten Formate (wav/aiff/flac/ogg/mid).", 4000)
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    # --- Multi-Project Tab Handlers (v0.0.20.77) ---

    def _on_project_tab_switch(self, idx: int) -> None:
        """Switch to a different project tab.

        Key behavior: Only the active project uses the audio engine.
        When switching:
        1. Stop transport on old project
        2. Save old project state into its tab
        3. Swap ProjectService.ctx to the new tab's context
        4. Rebind audio engine to new project
        5. Refresh all UI panels
        """
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        old_tab = ts.active_tab
        if old_tab:
            # Save current state into old tab
            old_tab.ctx = self.services.project.ctx
            old_tab.undo_stack = self.services.project.undo_stack

        # Stop transport before switch
        try:
            self.services.transport.stop()
        except Exception:
            pass

        # Switch
        ts.switch_to(idx)
        new_tab = ts.active_tab
        if not new_tab:
            return

        # Swap project context
        self.services.project.ctx = new_tab.ctx
        self.services.project.undo_stack = new_tab.undo_stack
        self.services.project._selected_track_id = ""

        # Rebind audio engine
        try:
            self.services.audio_engine.bind_transport(
                self.services.project, self.services.transport
            )
        except Exception:
            pass

        # Sync transport to new project's BPM/TS
        try:
            proj = new_tab.project
            self.services.transport.set_bpm(float(proj.bpm))
            self.services.transport.set_time_signature(str(proj.time_signature))
            self.transport.set_bpm(float(proj.bpm))
            self.transport.set_time_signature(str(proj.time_signature))
        except Exception:
            pass

        # v0.0.20.637: Restore punch state from project
        try:
            proj = new_tab.project
            self.services.transport.set_punch_region(
                float(getattr(proj, 'punch_in_beat', 4.0)),
                float(getattr(proj, 'punch_out_beat', 16.0)),
            )
            self.services.transport.set_punch(bool(getattr(proj, 'punch_enabled', False)))
            self.services.transport.set_pre_roll_bars(int(getattr(proj, 'pre_roll_bars', 0)))
            self.services.transport.set_post_roll_bars(int(getattr(proj, 'post_roll_bars', 0)))
            self.transport.set_pre_roll(int(getattr(proj, 'pre_roll_bars', 0)))
            self.transport.set_post_roll(int(getattr(proj, 'post_roll_bars', 0)))
        except Exception:
            pass

        # Refresh all UI panels
        try:
            self.services.project._emit_changed()
            self.services.project.project_opened.emit()
        except Exception:
            pass

        # Update window title
        try:
            self._update_window_title(new_tab.display_name)
        except Exception:
            pass

        self._set_status(f"Tab gewechselt: {new_tab.display_name}")

    def _on_tab_next(self) -> None:
        """Ctrl+Tab → switch to next project tab (wrapping)."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts or ts.count <= 1:
            return
        nxt = (ts.active_index + 1) % ts.count
        self._on_project_tab_switch(nxt)

    def _on_tab_prev(self) -> None:
        """Ctrl+Shift+Tab → switch to previous project tab (wrapping)."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts or ts.count <= 1:
            return
        prev = (ts.active_index - 1) % ts.count
        self._on_project_tab_switch(prev)

    def _on_project_tab_new(self) -> None:
        """Create a new empty project in a new tab."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        # Save current tab state first
        old_tab = ts.active_tab
        if old_tab:
            old_tab.ctx = self.services.project.ctx
            old_tab.undo_stack = self.services.project.undo_stack

        # Create new tab
        idx = ts.add_new_project("Neues Projekt", activate=False)
        # Switch to it (this triggers the full rebind)
        self._on_project_tab_switch(idx)

    def _on_project_tab_open(self) -> None:
        """Open a project file in a new tab."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Projekt in neuem Tab öffnen", "",
            "Py DAW Projekt (*.pydaw.json *.json);;Alle Dateien (*)",
        )
        if not path:
            return

        # Save current tab state first
        old_tab = ts.active_tab
        if old_tab:
            old_tab.ctx = self.services.project.ctx
            old_tab.undo_stack = self.services.project.undo_stack

        idx = ts.open_project_in_tab(Path(path), activate=False)
        if idx >= 0:
            self._on_project_tab_switch(idx)

    def _on_project_tab_close(self, idx: int) -> None:
        """Close a project tab with dirty check."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        # Don't allow closing the last tab
        if ts.count <= 1:
            self._set_status("Letzter Tab kann nicht geschlossen werden.")
            return

        tab = ts.tab_at(idx)
        if not tab:
            return

        # Check for unsaved changes
        if tab.dirty:
            reply = QMessageBox.question(
                self, "Ungespeicherte Änderungen",
                f"Projekt '{tab.display_name}' hat ungespeicherte Änderungen.\n"
                "Trotzdem schließen?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Save:
                if not ts.save_tab(idx):
                    return  # Save failed

        # If closing the active tab, switch first
        was_active = (idx == ts.active_index)
        ts.close_tab(idx)

        if was_active and ts.count > 0:
            self._on_project_tab_switch(ts.active_index)

    def _on_project_tab_save(self, idx: int) -> None:
        """Save a specific project tab."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        tab = ts.tab_at(idx)
        if not tab:
            return

        # Sync current state if saving active tab
        if idx == ts.active_index:
            tab.ctx = self.services.project.ctx

        if tab.path:
            ts.save_tab(idx)
        else:
            self._on_project_tab_save_as(idx)

    def _on_project_tab_save_as(self, idx: int) -> None:
        """Save a project tab with file dialog."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        tab = ts.tab_at(idx)
        if not tab:
            return

        # Sync current state if saving active tab
        if idx == ts.active_index:
            tab.ctx = self.services.project.ctx

        path, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern", "",
            "Py DAW Projekt (*.pydaw.json);;JSON (*.json);;Alle Dateien (*)",
        )
        if path:
            ts.save_tab(idx, Path(path))

    def _on_project_browser_open(self, path_str: str) -> None:
        """Open a project from the project browser in a new tab."""
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        # Save current tab state
        old_tab = ts.active_tab
        if old_tab:
            old_tab.ctx = self.services.project.ctx
            old_tab.undo_stack = self.services.project.undo_stack

        idx = ts.open_project_in_tab(Path(path_str), activate=False)
        if idx >= 0:
            self._on_project_tab_switch(idx)

    def _on_project_browser_import(self, path_str: str, track_ids: list) -> None:
        """Import tracks from a browsed project into the active project.

        Opens the source project temporarily, copies tracks, then closes it.
        Full State Transfer: device chains, automations, routing preserved.
        """
        ts = getattr(self, '_project_tab_service', None)
        if not ts:
            return

        # Open source project temporarily (don't activate)
        src_idx = ts.open_project_in_tab(Path(path_str), activate=False)
        if src_idx < 0:
            return

        tgt_idx = ts.active_index
        new_ids = ts.copy_tracks_between_tabs(
            src_idx, tgt_idx, track_ids,
            include_clips=True,
            include_device_chains=True,
        )

        # Close the temporary source tab
        ts.close_tab(src_idx)

        if new_ids:
            # Refresh UI
            self.services.project._emit_changed()
            self._set_status(f"{len(new_ids)} Track(s) importiert.")

    # --- misc

    def _update_window_title(self, text: str | None = None, *args) -> None:
        if not text:
            try:
                text = self.services.project.display_name()
            except Exception:
                text = "Projekt"
        # Add tab count if multi-project tabs are active
        try:
            ts = getattr(self, '_project_tab_service', None)
            if ts and ts.count > 1:
                tab_info = f" [Tab {ts.active_index + 1}/{ts.count}]"
                self.setWindowTitle(f"Py DAW — {text}{tab_info}")
                return
        except Exception:
            pass
        self.setWindowTitle(f"Py DAW — {text}")

    def _show_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Py DAW", msg)

    def _on_active_slot_changed(self, scene_idx: int, track_id: str, clip_id: str) -> None:
        """Handle aktiven Slot-Wechsel - Pro-DAW-Style Deep Integration.
        
        Wenn ein Slot im Clip-Launcher angeklickt wird:
        1. Piano-Roll wechselt auf den Clip (wenn MIDI)
        2. Notation folgt dem Clip (wenn MIDI)
        3. Mixer fokussiert den Track
        4. Audio Event Editor kann geöffnet werden (wenn Audio)
        """
        if not clip_id:
            return
            
        try:
            # Clip-Art ermitteln
            clip = self.services.project.get_clip(clip_id)
            if not clip:
                return
                
            kind = str(getattr(clip, 'kind', ''))
            
            # MIDI Clip -> Piano-Roll + Notation
            if kind == 'midi':
                # Piano-Roll auf Clip setzen
                try:
                    if hasattr(self.editor_tabs, 'pianoroll'):
                        # Trigger Clip-Wechsel im Piano-Roll
                        self.services.project.set_active_clip(clip_id)
                except Exception as e:
                    print(f"Piano-Roll Update fehlgeschlagen: {e}")
                    
                # Notation auf Clip setzen
                try:
                    if hasattr(self.editor_tabs, 'notation'):
                        # Notation folgt automatisch via active_clip_changed Signal
                        pass
                except Exception as e:
                    print(f"Notation Update fehlgeschlagen: {e}")
                    
            # Audio Clip -> Kann in Audio Event Editor bearbeitet werden
            # (wird bei Doppelklick im Launcher geöffnet)
            
            # Status-Message
            try:
                label = str(getattr(clip, 'label', 'Clip'))
                self.statusBar().showMessage(f"Aktiver Slot: {label} (Track: {track_id})", 2000)
            except Exception:
                pass
                
        except Exception as e:
            print(f"Fehler in _on_active_slot_changed: {e}")

    # --- crash recovery / autosave (v0.0.20.173) ---

    def _init_recovery(self) -> None:
        """Install autosave timer + show restore prompt if last session was unclean."""
        from PyQt6.QtCore import QTimer

        # periodic autosave (safe JSON only)
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setInterval(60_000)  # 60 seconds
        self._recovery_timer.timeout.connect(self._autosave_tick)
        self._recovery_timer.start()

        # prompt once after the window is shown
        QTimer.singleShot(400, self._prompt_recovery_if_needed)

    def _autosave_tick(self) -> None:
        try:
            from pydaw.fileio import recovery
            ctx = getattr(self.services, 'project', None).ctx if getattr(self, 'services', None) else None
            if ctx is None:
                return
            p = getattr(ctx, 'path', None)
            if not p:
                return
            # ensure enhanced automation lanes are persisted into the project dict
            try:
                self.services.project._sync_automation_manager_to_project()  # type: ignore[attr-defined]
            except Exception:
                pass
            recovery.write_autosave(p, ctx.project)
        except Exception:
            pass

    def _prompt_recovery_if_needed(self) -> None:
        try:
            from pydaw.fileio import recovery
            from PyQt6.QtWidgets import QMessageBox
            from datetime import datetime
            from pathlib import Path

            proj_path, autosave_path = recovery.should_prompt_restore()
            if proj_path is None or autosave_path is None:
                return

            try:
                ts = datetime.fromtimestamp(autosave_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                ts = str(autosave_path.name)

            msg = (
                "Beim letzten Start wurde ChronoScaleStudio nicht sauber beendet.\n\n"
                f"Projekt: {Path(proj_path).name}\n"
                f"Autosave: {ts}\n\n"
                "Wollen Sie den letzten Autosave wiederherstellen?"
            )
            res = QMessageBox.question(
                self,
                "Projekt wiederherstellen?",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if res == QMessageBox.StandardButton.Yes:
                # Open original project, then load the autosave snapshot into it.
                ps = self.services.project

                def _once():
                    try:
                        ps.project_opened.disconnect(_once)
                    except Exception:
                        pass
                    try:
                        ps.load_snapshot(Path(autosave_path))
                    except Exception:
                        pass

                try:
                    ps.project_opened.connect(_once)
                except Exception:
                    pass
                try:
                    ps.open_project(Path(proj_path))
                except Exception:
                    # fallback: open autosave directly
                    try:
                        ps.open_project(Path(autosave_path))
                    except Exception:
                        pass
            else:
                try:
                    self.services.project.new_project("Neues Projekt")
                except Exception:
                    pass
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: ANN001, N802
        """Reposition overlays and keep the status-strip tech signature sized."""
        super().resizeEvent(event)
        try:
            overlay = getattr(self, '_ckb_overlay', None)
            if overlay is not None:
                ow = self.width() - 20
                oh = overlay.height()
                sb_h = self.statusBar().height() if self.statusBar() else 22
                overlay.setGeometry(10, self.height() - oh - sb_h - 4, ow, oh)
                overlay.raise_()
        except Exception:
            pass
        try:
            self._sync_status_tech_signature_sizes()
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: ANN001
        # v0.0.20.625: Save + clean shutdown to prevent SIP SEGFAULT at exit
        try:
            mgr = getattr(self, '_screen_layout_mgr', None)
            if mgr is not None:
                mgr.save_state()
                mgr.shutdown()
                self._screen_layout_mgr = None
        except Exception:
            pass
        # v0.0.20.173: mark clean exit for crash-recovery
        try:
            from pydaw.fileio import recovery
            recovery.mark_clean_exit()
        except Exception:
            pass
        try:
            t = getattr(self, '_recovery_timer', None)
            if t is not None:
                t.stop()
        except Exception:
            pass
        try:
            self.services.metronome.shutdown()
        except Exception:
            pass
        try:
            self.services.midi.shutdown()
        except Exception:
            pass
        try:
            self.services.jack.shutdown()
        except Exception:
            pass
        try:
            self.services.audio_engine.stop()
        except Exception:
            pass
        try:
            # Newer containers expose a global shutdown hook.
            if hasattr(self.services, "shutdown"):
                self.services.shutdown()  # type: ignore[attr-defined]
        except Exception:
            pass
        # v0.0.20.702: Shutdown sandbox process manager (kill all plugin workers)
        try:
            self._stop_sandbox_monitor()
            from pydaw.services.sandbox_process_manager import get_process_manager
            get_process_manager().shutdown()
        except Exception:
            pass
        super().closeEvent(event)
