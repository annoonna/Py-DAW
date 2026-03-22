"""ChronoScaleStudio Integration für Py DAW.

Dieses Modul integriert die ScoreView-Komponente von ChronoScaleStudio
mit vollständiger Notationsdarstellung.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QPushButton,
    QComboBox,
    QMessageBox,
    QScrollArea,
)


class ChronoScaleNotationWidget(QWidget):
    """Integriertes Notation-Widget basierend auf ChronoScaleStudio.
    
    Lädt die vollständige ScoreView mit Notenlinien und allen Features.
    """
    
    status_message = Signal(str)
    
    def __init__(self, project_service, transport=None):
        super().__init__()
        self._project_service = project_service
        self._transport = transport
        self._clip_id = None
        self._sync_in_progress = False  # Verhindere Rekursion
        
        # ChronoScale-Komponenten
        self._score_view = None
        self._scale_browser = None
        self._toolbox = None
        self._available = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Versuche ChronoScale zu laden
        success, message = self._load_chronoscale()
        
        if not success:
            # Fallback: Zeige aussagekräftigen Fehler
            placeholder = QLabel(
                f"<h2>ChronoScaleStudio-Notation</h2>"
                f"<p><b>Status:</b> {message}</p>"
                f"<p>Mögliche Lösungen:</p>"
                f"<ul>"
                f"<li>PySide6 installieren: <code>pip install PySide6</code></li>"
                f"<li>ChronoScale-Modul prüfen: <code>ls pydaw/notation/gui/</code></li>"
                f"</ul>"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("padding: 40px;")
            layout.addWidget(placeholder)
        else:
            # ChronoScale erfolgreich geladen
            # Wrap ScoreView in ScrollArea für große Partituren
            scroll = QScrollArea()
            scroll.setWidget(self._score_view)
            scroll.setWidgetResizable(True)
            layout.addWidget(scroll)
            
            # Verbinde Score-Änderungen mit MIDI-Sync
            try:
                # Wenn ScoreView ein Signal für Änderungen hat
                if hasattr(self._score_view, 'sequence_changed'):
                    self._score_view.sequence_changed.connect(self._on_score_changed)
                # Alternativ: Nutze Undo-Stack
                elif hasattr(self._score_view, 'undo_stack'):
                    self._score_view.undo_stack.indexChanged.connect(self._on_score_changed)
            except Exception as e:
                print(f"Score-Change-Handler nicht verfügbar: {e}")
            
            self.status_message.emit(f"ChronoScale geladen: {message}")
        
        # Verbinde mit Projekt-Updates
        try:
            self._project_service.project_updated.connect(self._on_project_updated)
        except Exception:
            pass
    
    def _create_toolbar(self) -> QWidget:
        """Erstelle Toolbar für Notation-Steuerung."""
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        
        # Titel
        title = QLabel("<b>Notation (ChronoScaleStudio)</b>")
        layout.addWidget(title)
        
        layout.addSpacing(10)
        
        # Tool-Buttons
        self._btn_pencil = QToolButton()
        self._btn_pencil.setText("✏️ Pencil")
        self._btn_pencil.setCheckable(True)
        self._btn_pencil.setToolTip("Noten hinzufügen (Insert-Modus)")
        layout.addWidget(self._btn_pencil)
        
        self._btn_erase = QToolButton()
        self._btn_erase.setText("🗑️ Erase")
        self._btn_erase.setCheckable(True)
        self._btn_erase.setToolTip("Noten löschen")
        layout.addWidget(self._btn_erase)
        
        self._btn_select = QToolButton()
        self._btn_select.setText("🔍 Select")
        self._btn_select.setCheckable(True)
        self._btn_select.setChecked(True)
        self._btn_select.setToolTip("Noten auswählen und verschieben")
        layout.addWidget(self._btn_select)
        
        layout.addWidget(QLabel("|"))
        
        # Scale-Selector
        layout.addWidget(QLabel("Scale:"))
        self._scale_combo = QComboBox()
        self._scale_combo.setMinimumWidth(200)
        self._scale_combo.addItem("Chromatic (All Notes)")
        self._scale_combo.setEnabled(False)
        self._scale_combo.setToolTip("Wähle eine Skala aus 500+ verfügbaren")
        layout.addWidget(self._scale_combo)
        
        layout.addWidget(QLabel("|"))
        
        # Playback
        self._btn_play = QToolButton()
        self._btn_play.setText("▶ Play")
        self._btn_play.setToolTip("Spiele Notation ab (mit FluidSynth/MIDI)")
        layout.addWidget(self._btn_play)
        
        self._btn_stop = QToolButton()
        self._btn_stop.setText("■ Stop")
        self._btn_stop.setToolTip("Stoppe Wiedergabe")
        layout.addWidget(self._btn_stop)
        
        layout.addStretch()
        
        # Status-Label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self._status_label)
        
        # Keyboard Shortcuts Hint
        shortcuts_btn = QToolButton()
        shortcuts_btn.setText("⌨️")
        shortcuts_btn.setToolTip(
            "Tastenkombinationen:\n\n"
            "Zeichnen:\n"
            "  D - Note-Tool\n"
            "  E - Radierer\n"
            "  Esc - Select-Tool\n\n"
            "Bearbeiten:\n"
            "  Ctrl+C - Kopieren\n"
            "  Ctrl+V - Einfügen\n"
            "  Ctrl+X - Ausschneiden\n"
            "  Del/Backspace - Löschen\n\n"
            "Navigation:\n"
            "  Pfeiltasten - Noten verschieben\n"
            "  +/- - Notenlänge ändern\n\n"
            "Undo/Redo:\n"
            "  Ctrl+Z - Rückgängig\n"
            "  Ctrl+Shift+Z - Wiederholen"
        )
        layout.addWidget(shortcuts_btn)
        
        return toolbar
    
    def _load_chronoscale(self) -> tuple[bool, str]:
        """Lade ChronoScale-Komponenten.
        
        Returns:
            (success, message)
        """
        try:
            # Stelle sicher, dass notation/ im Path ist
            notation_path = Path(__file__).parent.parent / "notation"
            if str(notation_path) not in sys.path:
                sys.path.insert(0, str(notation_path))
            
            # Versuche Qt-Compat zu laden (PySide6 → PyQt6)
            try:
                from pydaw.notation import qt_compat
                qt_backend = qt_compat.QT_BACKEND
            except Exception:
                qt_backend = "unknown"
            
            # Importiere ChronoScale-Komponenten
            from pydaw.notation.gui.score_view import ScoreView
            from pydaw.notation.gui.scale_browser import ScaleBrowser
            
            # Erstelle ScoreView
            self._score_view = ScoreView()
            self._score_view.setMinimumHeight(400)
            
            # Erstelle ScaleBrowser (Backend für Playback)
            self._scale_browser = ScaleBrowser(self._score_view)
            self._scale_browser.setVisible(False)
            
            # Verbinde Tool-Buttons
            self._connect_tools()
            
            # Lade Skalen
            self._load_scales()
            
            self._available = True
            return True, f"ScoreView geladen (Backend: {qt_backend})"
            
        except ImportError as e:
            import traceback
            traceback.print_exc()
            return False, f"Import-Fehler: {e}"
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Ladefehler: {e}"
    
    def _connect_tools(self):
        """Verbinde Toolbar-Buttons mit ScoreView."""
        if not self._score_view:
            return
        
        try:
            # Tool-Modus wechseln
            self._btn_pencil.clicked.connect(
                lambda: self._set_tool_mode("insert")
            )
            self._btn_erase.clicked.connect(
                lambda: self._set_tool_mode("erase")
            )
            self._btn_select.clicked.connect(
                lambda: self._set_tool_mode("select")
            )
            
            # Playback-Steuerung
            if self._scale_browser:
                self._btn_play.clicked.connect(self._play_notation)
                self._btn_stop.clicked.connect(self._stop_notation)
        
        except Exception as e:
            print(f"Tool-Verbindung fehlgeschlagen: {e}")
    
    def _set_tool_mode(self, mode: str):
        """Setze Tool-Modus in ScoreView."""
        if not self._score_view:
            return
        
        try:
            # Uncheck alle anderen
            self._btn_pencil.setChecked(mode == "insert")
            self._btn_erase.setChecked(mode == "erase")
            self._btn_select.setChecked(mode == "select")
            
            # Setze Modus
            self._score_view.set_mode(mode)
            self._status_label.setText(f"Modus: {mode}")
            
        except Exception as e:
            print(f"Modus-Wechsel fehlgeschlagen: {e}")
    
    def _play_notation(self):
        """Spiele Notation ab."""
        if not self._scale_browser:
            return
        
        try:
            self._scale_browser.play_sequence()
            self._status_label.setText("Wiedergabe...")
        except Exception as e:
            print(f"Playback fehlgeschlagen: {e}")
    
    def _stop_notation(self):
        """Stoppe Wiedergabe."""
        if not self._scale_browser:
            return
        
        try:
            self._scale_browser.stop_playback()
            self._status_label.setText("Gestoppt")
        except Exception as e:
            print(f"Stop fehlgeschlagen: {e}")
    
    def _load_scales(self):
        """Lade verfügbare Skalen in Combo-Box."""
        if not self._scale_browser:
            return
        
        try:
            # Hole Skalen-Systeme
            system_box = getattr(self._scale_browser, 'system_box', None)
            if not system_box:
                return
            
            self._scale_combo.clear()
            for i in range(system_box.count()):
                scale_name = system_box.itemText(i)
                self._scale_combo.addItem(scale_name)
            
            self._scale_combo.setEnabled(True)
            self._scale_combo.currentTextChanged.connect(self._on_scale_changed)
            
            # Setze Default auf "Keine Einschränkung" (Chromatic)
            idx = self._scale_combo.findText("Keine Einschränkung")
            if idx >= 0:
                self._scale_combo.setCurrentIndex(idx)
            
            count = self._scale_combo.count()
            self._status_label.setText(f"{count} Skalen verfügbar")
            
        except Exception as e:
            print(f"Skalen-Laden fehlgeschlagen: {e}")
    
    def _on_scale_changed(self, scale_name: str):
        """Skala wurde geändert."""
        if not self._scale_browser:
            return
        
        try:
            # Setze Skala im Browser
            system_box = self._scale_browser.system_box
            idx = system_box.findText(scale_name)
            if idx >= 0:
                system_box.setCurrentIndex(idx)
                self._scale_browser.update_scales(scale_name)
                self.status_message.emit(f"Skala: {scale_name}")
                self._status_label.setText(f"Skala: {scale_name}")
        except Exception as e:
            print(f"Skala-Wechsel fehlgeschlagen: {e}")
    
    def set_clip(self, clip_id: str | None):
        """Setze aktiven MIDI-Clip."""
        self._clip_id = clip_id
        self._sync_clip_to_score()
    
    def _sync_clip_to_score(self):
        """Synchronisiere MIDI-Clip mit Score-View."""
        if not self._available or not self._score_view or not self._clip_id or self._sync_in_progress:
            return
        
        self._sync_in_progress = True
        try:
            # Hole MIDI-Noten aus Clip
            notes = list(self._project_service.get_midi_notes(self._clip_id))
            
            if not notes:
                self._status_label.setText("Keine Noten im Clip")
                return
            
            # Konvertiere PyDAW MidiNote → ChronoScale NoteEvent
            from pydaw.notation.music.events import NoteEvent
            from pydaw.notation.music.sequence import NoteSequence
            
            # Erstelle neue Sequence
            sequence = NoteSequence()
            
            # Konvertiere alle Noten
            for midi_note in notes:
                sequence.add_note(
                    pitch=midi_note.pitch,
                    start=midi_note.start_beats,
                    duration=midi_note.length_beats,
                    velocity=midi_note.velocity,
                    track_id=1
                )
            
            # Setze Sequence in ScoreView
            self._score_view.sequence = sequence
            
            # Redraw
            self._score_view.redraw_events()
            
            # AUTO-SCROLL zu den Noten!
            try:
                # Finde min/max Beat
                min_beat = min(e.start for e in sequence.events)
                max_beat = max(e.start + e.duration for e in sequence.events)
                
                # Berechne Scroll-Position (100 Pixel = 1 Beat ungefähr)
                scroll_pos = int(min_beat * 100)
                
                # Scroll zu den Noten
                h_scrollbar = self._score_view.horizontalScrollBar()
                h_scrollbar.setValue(scroll_pos)
                
                # Status mit Beat-Info
                self._status_label.setText(f"✓ {len(notes)} Noten @ Beat {min_beat:.1f}-{max_beat:.1f}")
                
            except Exception as e:
                print(f"[Notation] Auto-scroll failed: {e}")
            
            self.status_message.emit(f"✓ {len(notes)} Noten synchronisiert")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_message.emit(f"Sync-Fehler: {e}")
            self._status_label.setText(f"✗ Fehler: {e}")
            print(f"Clip-Sync fehlgeschlagen: {e}")
        finally:
            self._sync_in_progress = False
    
    def _on_score_changed(self):
        """Notation wurde geändert - schreibe zurück zu MIDI."""
        # Prevent recursion
        if getattr(self, "_sync_in_progress", False):
            return
        if not getattr(self, "_clip_id", None):
            return
        if not self._available or not self._score_view:
            return
        
        try:
            from pydaw.model.midi import MidiNote
            from pydaw.notation.music.events import NoteEvent
            
            seq = getattr(self._score_view, "sequence", None)
            if seq is None:
                return
            
            # Konvertiere ChronoScale → PyDAW MidiNote
            midi_notes = []
            events = getattr(seq, "events", [])
            
            for ev in events:
                if not isinstance(ev, NoteEvent):
                    continue
                
                pitch = int(getattr(ev, "pitch", 60))
                start = float(getattr(ev, "start", 0.0))
                length = float(getattr(ev, "duration", 0.25))
                vel = int(getattr(ev, "velocity", 90))
                
                # Validierung
                if length <= 0:
                    length = 0.25
                pitch = max(0, min(127, pitch))
                vel = max(1, min(127, vel))
                
                midi_notes.append(MidiNote(
                    pitch=pitch,
                    start_beats=start,
                    length_beats=length,
                    velocity=vel
                ))
            
            # Schreibe zurück ins Projekt
            self._sync_in_progress = True
            self._project_service.set_midi_notes(self._clip_id, midi_notes)
            self._status_label.setText(f"↻ {len(midi_notes)} Noten → MIDI")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Notation] Score→MIDI failed: {e}")
        finally:
            self._sync_in_progress = False
    
    def _on_project_updated(self):
        """Projekt wurde aktualisiert."""
        if self._clip_id:
            self._sync_clip_to_score()
    
    def refresh(self):
        """Aktualisiere Anzeige."""
        self._sync_clip_to_score()
    
    def is_available(self) -> bool:
        """Prüfe ob ChronoScale verfügbar ist."""
        return self._available
