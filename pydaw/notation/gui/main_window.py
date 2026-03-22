
from __future__ import annotations

import json
from pathlib import Path

from pydaw.notation.qt_compat import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QDockWidget, QFileDialog, QMessageBox, QScrollArea
)
from pydaw.notation.qt_compat import Qt

from pydaw.notation.gui.score_view import ScoreView
from pydaw.notation.gui.scale_browser import ScaleBrowser
from pydaw.notation.gui.toolbox import NotationToolbox
from pydaw.notation.gui.automation_editor import AutomationEditor
from pydaw.notation.gui.scale_settings_dialog import ScaleSettingsDialog
from pydaw.notation.gui.tracks_panel import TracksPanel
from pydaw.notation.gui.transport_bar import TransportBar
from pydaw.notation.gui.symbol_palette import SymbolPaletteWidget
from pydaw.notation.midi.midi_io import import_midi, export_sequence


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._version = self._read_version()
        self.setWindowTitle(f"ChronoScaleStudio – Notation & Skalen (Version {self._version})")

        # Default size (Editor feeling)
        self.resize(1700, 950)
        self.setMinimumSize(1200, 720)

        # Central
        central = QWidget()
        layout = QVBoxLayout(central)

        self.score_view = ScoreView()
        # ScaleBrowser bleibt als Controller/Playback-Backend erhalten, wird aber nicht mehr als UI-Block
        # im Hauptlayout angezeigt (Aufräumen wie in einer DAW).
        self.scale_browser = ScaleBrowser(self.score_view)
        self.scale_browser.setVisible(False)

        # Default: keine Einschränkung (Chromatic / frei)
        try:
            idx_sys = self.scale_browser.system_box.findText("Keine Einschränkung")
            if idx_sys >= 0:
                self.scale_browser.system_box.setCurrentIndex(idx_sys)
                self.scale_browser.update_scales("Keine Einschränkung")
                # prefer "Alle Noten" if present
                idx_sc = self.scale_browser.scale_box.findText("Alle Noten")
                if idx_sc >= 0:
                    self.scale_browser.scale_box.setCurrentIndex(idx_sc)
        except Exception:
            pass

        # ScoreView muss die aktuelle Skala kennen (für optionale Restriktion)
        self._sync_scale_to_score()
        try:
            self.scale_browser.system_box.currentTextChanged.connect(lambda _=None: self._sync_scale_to_score())
            self.scale_browser.scale_box.currentTextChanged.connect(lambda _=None: self._sync_scale_to_score())
        except Exception:
            pass

        layout.addWidget(QLabel("Notenansicht"))
        self.transport_bar = TransportBar(self.score_view, self.scale_browser)
        layout.addWidget(self.transport_bar)
        layout.addWidget(self.score_view)

        layout.setStretchFactor(self.score_view, 10)
        self.setCentralWidget(central)

        # Left Dock: Tracks
        self.tracks_panel = TracksPanel(self.score_view)
        tracks_dock = QDockWidget("Spuren", self)
        tracks_dock.setWidget(self.tracks_panel)
        tracks_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        tracks_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.LeftDockWidgetArea, tracks_dock)

        # Right Dock: Toolbox (scrollable)
        self.toolbox = NotationToolbox(self.score_view, open_automation_editor_cb=self.open_automation_editor)
        toolbox_scroll = QScrollArea()
        toolbox_scroll.setWidgetResizable(True)
        toolbox_scroll.setWidget(self.toolbox)

        dock = QDockWidget("Toolbox", self)
        dock.setWidget(toolbox_scroll)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMinimumWidth(360)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # Symbol-Palette als echtes Panel (Dock) – standardmäßig versteckt
        self._palette_dock = QDockWidget("Symbol-Palette", self)
        self._palette_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._palette_dock.setMinimumWidth(280)
        self.symbol_palette = SymbolPaletteWidget(self.score_view, compact=False)
        # Verdrahtung: Palette steuert direkt den ScoreView (DAW-Style)
        self.symbol_palette.toolModeRequested.connect(self.score_view.set_mode)
        self.symbol_palette.durationRequested.connect(self.score_view.set_duration)
        self.symbol_palette.dotsRequested.connect(self.score_view.set_dots)
        self.symbol_palette.accidentalRequested.connect(self.score_view.set_accidental)
        # Edit-Aktionen (nur wenn ScoreView diese Methoden hat)
        if hasattr(self.score_view, "split_selected_at_playhead"):
            self.symbol_palette.splitRequested.connect(self.score_view.split_selected_at_playhead)
        if hasattr(self.score_view, "glue_selected"):
            self.symbol_palette.glueRequested.connect(self.score_view.glue_selected)
        if hasattr(self.score_view, "quantize_selected"):
            self.symbol_palette.quantizeRequested.connect(self.score_view.quantize_selected)
        if hasattr(self.score_view, "humanize_selected"):
            self.symbol_palette.humanizeRequested.connect(self.score_view.humanize_selected)
        if hasattr(self.score_view, "transpose_selected"):
            self.symbol_palette.transposeRequested.connect(self.score_view.transpose_selected)
        self._palette_dock.setWidget(self.symbol_palette)
        self.addDockWidget(Qt.RightDockWidgetArea, self._palette_dock)
        self._palette_dock.hide()

        # Menu
        self._build_menu()

        self._last_project_path: str | None = None

    def _build_menu(self):
        bar = self.menuBar()

        # Datei
        m_file = bar.addMenu("Datei")
        act_open = m_file.addAction("Projekt öffnen…")
        act_open.setShortcut("Ctrl+O")
        act_save = m_file.addAction("Projekt speichern…")
        act_save.setShortcut("Ctrl+S")
        m_file.addSeparator()
        act_midi_in = m_file.addAction("MIDI importieren…")
        act_midi_out = m_file.addAction("MIDI exportieren…")
        m_file.addSeparator()
        act_exit = m_file.addAction("Beenden")

        act_open.triggered.connect(self.project_open)
        act_save.triggered.connect(self.project_save)
        act_midi_in.triggered.connect(self.midi_import)
        act_midi_out.triggered.connect(self.midi_export)
        act_exit.triggered.connect(self.close)

        # Bearbeiten
        m_edit = bar.addMenu("Bearbeiten")
        act_undo = m_edit.addAction("Undo")
        act_undo.setShortcut("Ctrl+Z")
        act_redo = m_edit.addAction("Redo")
        act_redo.setShortcut("Ctrl+Shift+Z")
        m_edit.addSeparator()
        act_cut = m_edit.addAction("Ausschneiden")
        act_cut.setShortcut("Ctrl+X")
        act_copy = m_edit.addAction("Kopieren")
        act_copy.setShortcut("Ctrl+C")
        act_paste = m_edit.addAction("Einfügen")
        act_paste.setShortcut("Ctrl+V")
        m_edit.addSeparator()
        m_ops = m_edit.addMenu("Edit-Tools")
        act_split = m_ops.addAction("Split (am Playhead)")
        act_glue = m_ops.addAction("Glue (Merge)")
        m_q = m_ops.addMenu("Quantize")
        act_q1 = m_q.addAction("Start")
        act_q2 = m_q.addAction("Start + Länge")
        act_hum = m_ops.addAction("Humanize")
        m_tr = m_ops.addMenu("Transpose")
        act_tn12 = m_tr.addAction("-12")
        act_tn1 = m_tr.addAction("-1")
        act_tp1 = m_tr.addAction("+1")
        act_tp12 = m_tr.addAction("+12")
        m_edit.addSeparator()
        act_clear = m_edit.addAction("Alles löschen")

        act_undo.triggered.connect(lambda: (self.score_view.undo.undo(), self.score_view.redraw_events()))
        act_redo.triggered.connect(lambda: (self.score_view.undo.redo(), self.score_view.redraw_events()))
        act_cut.triggered.connect(self.score_view.cut_selection)
        act_copy.triggered.connect(self.score_view.copy_selection)
        act_paste.triggered.connect(self.score_view.paste)
        act_split.triggered.connect(self.score_view.split_selected_at_playhead)
        act_glue.triggered.connect(self.score_view.glue_selected)
        act_q1.triggered.connect(lambda: self.score_view.quantize_selected(False))
        act_q2.triggered.connect(lambda: self.score_view.quantize_selected(True))
        act_hum.triggered.connect(self.score_view.humanize_selected)
        act_tn12.triggered.connect(lambda: self.score_view.transpose_selected(-12))
        act_tn1.triggered.connect(lambda: self.score_view.transpose_selected(-1))
        act_tp1.triggered.connect(lambda: self.score_view.transpose_selected(+1))
        act_tp12.triggered.connect(lambda: self.score_view.transpose_selected(+12))
        act_clear.triggered.connect(self.score_view.clear_all)

        # Ansicht
        m_view = bar.addMenu("Ansicht")
        act_bg = m_view.addAction("Hintergrundbild laden…")
        act_bg_clear = m_view.addAction("Hintergrund entfernen")
        m_view.addSeparator()
        act_zoom_reset = m_view.addAction("Zoom zurücksetzen")
        m_view.addSeparator()
        self.act_symbol_palette = m_view.addAction("Symbol-Palette anzeigen")
        self.act_symbol_palette.setCheckable(True)
        self.act_symbol_palette.setChecked(False)  # Standard: versteckt
        m_view.addSeparator()
        self.act_scale_restrict = m_view.addAction("Skalenrestriktion (nur Skala-Noten)")
        self.act_scale_restrict.setCheckable(True)
        self.act_scale_restrict.setChecked(False)

        act_bg.triggered.connect(self.background_load)
        act_bg_clear.triggered.connect(lambda: self.score_view.clear_background_image())
        act_zoom_reset.triggered.connect(lambda: self.score_view.zoom_reset())
        self.act_symbol_palette.toggled.connect(lambda v: self.set_symbol_palette_visible(bool(v)))
        self.act_scale_restrict.toggled.connect(lambda v: self.score_view.set_scale_restriction_enabled(bool(v)))

        # Transport
        m_transport = bar.addMenu("Transport")
        act_play = m_transport.addAction("Play / Stop (Eigene Noten)")
        act_play.setShortcut("Ctrl+P")
        act_play.triggered.connect(self.toggle_play)
        act_play_scale = m_transport.addAction("Skala abspielen")
        act_stop = m_transport.addAction("Stop")
        m_transport.addSeparator()
        act_loop = m_transport.addAction("Loop an/aus")
        act_loop_a = m_transport.addAction("Loop A setzen")
        act_loop_b = m_transport.addAction("Loop B setzen")
        act_loop_clear = m_transport.addAction("Loop löschen")

        act_play_scale.triggered.connect(lambda: self.scale_browser.play_scale_notes())
        act_stop.triggered.connect(lambda: self.scale_browser.stop_all())
        act_loop.triggered.connect(lambda: self.transport_bar.chk_loop.toggle())
        act_loop_a.triggered.connect(lambda: self.transport_bar._set_loop_a())
        act_loop_b.triggered.connect(lambda: self.transport_bar._set_loop_b())
        act_loop_clear.triggered.connect(lambda: self.transport_bar._clear_loop())

        # Werkzeuge
        m_tools = bar.addMenu("Werkzeuge")
        act_scale_settings = m_tools.addAction("System & Skala…")
        act_auto = m_tools.addAction("Automationen (Volume)…")

        act_scale_settings.triggered.connect(self.open_scale_settings)
        act_auto.triggered.connect(self.open_automation_editor)

        # Hilfe
        m_help = bar.addMenu("Hilfe")
        m_help.addAction("LMB: Klick=Auswahl, Ziehen=Move/Resize, ALT+Ziehen=Velocity, Drag im leeren Bereich=Lasso")
        m_help.addAction("Ctrl + Lasso: Auswahl addieren; Ctrl+C/X/V: Copy/Cut/Paste; Ctrl+Z / Ctrl+Shift+Z: Undo/Redo")
        m_help.addAction("Mausrad: Zoom")

    # ---------- UI helpers ----------
    def _read_version(self) -> str:
        try:
            root = Path(__file__).resolve().parents[2]
            p = root / "VERSION.txt"
            if p.exists():
                return p.read_text(encoding="utf-8").strip() or "unknown"
        except Exception:
            pass
        return "unknown"

    def set_symbol_palette_visible(self, visible: bool):
        try:
            self._palette_dock.setVisible(bool(visible))
        except Exception:
            return
        # Menü-Check stabil halten
        try:
            if hasattr(self, "act_symbol_palette"):
                self.act_symbol_palette.blockSignals(True)
                self.act_symbol_palette.setChecked(bool(visible))
                self.act_symbol_palette.blockSignals(False)
        except Exception:
            pass

    def is_symbol_palette_visible(self) -> bool:
        try:
            return bool(self._palette_dock.isVisible())
        except Exception:
            return False

    
    def _sync_scale_to_score(self):
        try:
            sys = self.scale_browser.system_box.currentText()
            sc = self.scale_browser.scale_box.currentText()
            self.score_view.set_scale_selection(sys, sc)
        except Exception:
            pass


    # ---------- Project ----------
    def project_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern", self._last_project_path or "projekt.chronoscale.json", "ChronoScaleStudio Project (*.chronoscale.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            state = self.score_view.serialize_state()
            Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")
            self._last_project_path = path
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte Projekt nicht speichern:\n{e}")

    def project_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Projekt öffnen", self._last_project_path or "", "ChronoScaleStudio Project (*.chronoscale.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.score_view.deserialize_state(data)
            self.score_view.undo.init()
            self.tracks_panel.refresh()
            try:
                self.act_scale_restrict.blockSignals(True)
                self.act_scale_restrict.setChecked(bool(self.score_view.get_scale_restriction_enabled()))
                self.act_scale_restrict.blockSignals(False)
            except Exception:
                pass
            # Scale UI auf Projektzustand setzen (und danach ScoreView daraus synchronisieren)
            try:
                sys = getattr(self.score_view, "scale_system", "Keine Einschränkung")
                sc = getattr(self.score_view, "scale_name", "Alle Noten")
                idx_sys = self.scale_browser.system_box.findText(sys)
                if idx_sys >= 0:
                    self.scale_browser.system_box.setCurrentIndex(idx_sys)
                    self.scale_browser.update_scales(sys)
                idx_sc = self.scale_browser.scale_box.findText(sc)
                if idx_sc >= 0:
                    self.scale_browser.scale_box.setCurrentIndex(idx_sc)
            except Exception:
                pass
            self._sync_scale_to_score()
            self._last_project_path = path
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte Projekt nicht öffnen:\n{e}")

    # ---------- MIDI ----------
    def midi_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "MIDI importieren", "", "MIDI (*.mid *.midi)")
        if not path:
            return
        try:
            seq, tempo = import_midi(path, quant_step=self.score_view.quantize_step)
            self.score_view.sequence = seq
            # keep view settings
            self.tracks_panel.refresh()
            self.score_view.set_active_track(seq.tracks[0].id if seq.tracks else 1)
            self.score_view.redraw_events()
            self.score_view.undo.init()
            # tempo in Transport (ScaleBrowser)
            try:
                self.scale_browser.tempo.setValue(int(tempo))
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"MIDI Import fehlgeschlagen:\n{e}")

    def midi_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "MIDI exportieren", "export.mid", "MIDI (*.mid *.midi)")
        if not path:
            return
        try:
            tempo = int(self.scale_browser.tempo.value())
            export_sequence(self.score_view.sequence, path, tempo_bpm=tempo)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"MIDI Export fehlgeschlagen:\n{e}")

    
    def toggle_play(self):
        try:
            w = getattr(self.scale_browser, "worker", None)
            if w is not None and getattr(w, "isRunning", lambda: False)():
                self.scale_browser.stop_all()
            else:
                self.scale_browser.play_sequence()
        except Exception:
            pass


    # ---------- Ansicht ----------
    def background_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Hintergrundbild auswählen",
            "",
            "Bilder (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Alle Dateien (*.*)",
        )
        if not path:
            return
        ok = self.score_view.set_background_image(path)
        if not ok:
            QMessageBox.warning(self, "Hinweis", "Bild konnte nicht geladen werden.")

    # ---------- Tools ----------
    def open_automation_editor(self):
        lane = self.score_view.get_volume_automation_lane()
        dlg = AutomationEditor(
            lane=lane,
            length_beats=self.score_view.total_beats,
            quant_step=self.score_view.quantize_step,
            parent=self,
        )
        dlg.exec()
        self.score_view.viewport().update()

    def open_scale_settings(self):
        dlg = ScaleSettingsDialog(self.scale_browser, parent=self)
        dlg.exec()
        self._sync_scale_to_score()
        # Transportbar-Status aktualisieren (Skalenname etc.)
        try:
            self.transport_bar.refresh_scale_label()
        except Exception:
            pass

    def closeEvent(self, event):
        # Threads sauber stoppen
        self.scale_browser.stop_all()
        event.accept()
