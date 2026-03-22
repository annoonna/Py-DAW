"""Lightweight Notation editor (WIP).

Goal: behave like Piano Roll (responsive, no heavy init, no blocking loops).
This editor intentionally starts minimal: staff + status text.
It can be extended incrementally (tools, grid/snap, clip binding).
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QFont, QPainter, QBrush
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QButtonGroup,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from pydaw.model.midi import MidiNote


class _NotationView(QGraphicsView):
    """QGraphicsView mit Tool-Interaktion (Pencil/Erase/Select/Time/Knife).

    Die eigentliche Logik bleibt im Editor (damit wir später problemlos
    auf QWidget-Paint umstellen könnten).
    """

    def __init__(self, editor: "NotationEditorLite", scene: QGraphicsScene):
        super().__init__(scene)
        self._ed = editor

    def mousePressEvent(self, event):  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos: QPointF = self.mapToScene(int(event.position().x()), int(event.position().y()))
            if self._ed.handle_left_click(scene_pos):
                event.accept()
                return
        super().mousePressEvent(event)

    def wheelEvent(self, event):  # noqa: N802 (Qt API)
        # Plain Wheel = Zoom horizontal (DAW style)
        # Ctrl+Wheel = Pass to parent for scrolling
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Let parent handle scroll
            super().wheelEvent(event)
            return
        
        # Plain wheel = Zoom (hauptsächlich horizontal in Notation)
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self._ed.apply_zoom(factor)
        event.accept()


class NotationEditorLite(QWidget):
    """Safe, minimal Notation editor.

    - No background image loading
    - No big scene rendering
    - No external project imports
    """

    def __init__(self, project_service, *, transport=None):
        super().__init__()
        self._project_service = project_service
        self._transport = transport
        self._clip_id: str | None = None
        self._tool: str = "select"
        self._grid_mode: str = "fixed"
        self._snap: str = "1/16"

        # Leichtgewichtiges Layout-Mapping (Treble-Staff).
        # Referenz: Bottom line E4.
        self._staff_cfg = {
            "left": 40.0,
            "top": 80.0,
            "spacing": 12.0,
            "ppb": 120.0,  # pixels per beat (zoom beeinflusst View-Transform)
        }

        self._scene = QGraphicsScene(self)
        self._zoom = 1.0
        self._view = _NotationView(self, self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)

        # Note graphics cache (rebuilt on clip change / project change)
        self._note_items: list[QGraphicsEllipseItem] = []
        self._selected_item: QGraphicsEllipseItem | None = None

        # Refresh whenever project updates (e.g., piano roll edits)
        try:
            self._project_service.project_updated.connect(self.refresh)
        except Exception:
            # project_service might be a test stub
            pass

        # Lightweight header toolbar (WIP)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self._lbl = QLabel("Notation (WIP)")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._lbl)

        top.addStretch(1)

        self._btn_zoom_in = QToolButton()
        self._btn_zoom_in.setText("+")
        self._btn_zoom_in.clicked.connect(lambda: self._view.scale(1.10, 1.10))
        top.addWidget(self._btn_zoom_in)

        self._btn_zoom_out = QToolButton()
        self._btn_zoom_out.setText("-")
        self._btn_zoom_out.clicked.connect(lambda: self._view.scale(1/1.10, 1/1.10))
        top.addWidget(self._btn_zoom_out)

        self._btn_zoom_reset = QToolButton()
        self._btn_zoom_reset.setText("100%")
        self._btn_zoom_reset.clicked.connect(self._reset_zoom)
        top.addWidget(self._btn_zoom_reset)

        # Tools row (UI-only WIP): mirrors Piano Roll layout; safe/no heavy logic.
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(6)

        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        def mk_tool(text: str, name: str, checked: bool = False) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setChecked(checked)
            b.setProperty("tool_name", name)
            self._tool_group.addButton(b)
            b.clicked.connect(lambda: self._on_tool_changed(name))
            return b

        tools.addWidget(mk_tool("Select", "select", checked=True))
        tools.addWidget(mk_tool("Time", "time"))
        tools.addWidget(mk_tool("Pencil", "pencil"))
        tools.addWidget(mk_tool("Erase", "erase"))
        tools.addWidget(mk_tool("Knife", "knife"))

        tools.addSpacing(10)
        tools.addWidget(QLabel("Grid:"))
        self._grid_combo = QComboBox()
        self._grid_combo.addItems(["fixed", "adaptive"])
        self._grid_combo.setCurrentText(self._grid_mode)
        self._grid_combo.currentTextChanged.connect(self._on_grid_changed)
        tools.addWidget(self._grid_combo)

        tools.addSpacing(10)
        self._snap_label = QLabel("Snap")
        tools.addWidget(self._snap_label)
        self._snap_combo = QComboBox()
        self._snap_combo.addItems(["1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"])
        self._snap_combo.setCurrentText(self._snap)
        self._snap_combo.currentTextChanged.connect(self._on_snap_changed)
        tools.addWidget(self._snap_combo)

        tools.addStretch(1)
        # Placeholder action buttons (no functionality yet)
        for txt in ("Automation", "Record", "Loop", "Undo", "Redo"):
            b = QToolButton()
            b.setText(txt)
            b.setEnabled(False)
            tools.addWidget(b)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addLayout(tools)
        lay.addWidget(self._view, 1)

        # Scene content
        self._status_item: QGraphicsTextItem | None = None
        self._draw_base_scene()

        # Sync: Wenn sich Noten/Clips ändern (Undo/Redo, PianoRoll-Edits,
        # Clip-Auswahl etc.), spiegeln wir das in Notation.
        try:
            self._project_service.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

    def _reset_zoom(self) -> None:
        self._view.resetTransform()

    def _on_tool_changed(self, name: str) -> None:
        self._tool = name
        self._update_status()

    def _on_grid_changed(self, mode: str) -> None:
        self._grid_mode = mode
        self._update_status()

    def _on_snap_changed(self, snap: str) -> None:
        self._snap = snap
        self._update_status()

    def _draw_base_scene(self) -> None:
        """Draw a small staff area + status text. Never heavy."""
        self._scene.clear()

        # reset graphics cache
        self._note_items.clear()
        self._selected_item = None

        # Staff lines (small, fixed width) – prevents huge rendering.
        left = float(self._staff_cfg.get("left", 40.0))
        top = float(self._staff_cfg.get("top", 60.0))
        width = float(self._staff_cfg.get("width", 1400.0))
        spacing = float(self._staff_cfg.get("spacing", 12.0))
        ppb = float(self._staff_cfg.get("ppb", 120.0))
        self._staff_cfg.update({"left": left, "top": top, "width": width, "spacing": spacing, "ppb": ppb})

        pen = QPen(Qt.GlobalColor.darkGray)
        for i in range(5):
            y = top + i * spacing
            self._scene.addLine(left, y, left + width, y, pen)

        # Status text
        self._status_item = QGraphicsTextItem()
        self._status_item.setDefaultTextColor(Qt.GlobalColor.white)
        f = QFont()
        f.setPointSize(10)
        self._status_item.setFont(f)
        self._status_item.setPos(20, top + 5 * spacing + 30)
        self._scene.addItem(self._status_item)

        self._update_status()

        # Notes (from MIDI-Clip; light WIP rendering)
        self._render_notes()

        # Keep scene rect small and stable
        self._scene.setSceneRect(0, 0, left + width + 60, max(260, top + 5 * spacing + 160))

    def _update_status(self) -> None:
        if not self._status_item:
            return
        if self._clip_id:
            self._status_item.setPlainText(
                f"Aktiver Clip: {self._clip_id}\n"
                "WIP: Notation-Editor ist als leichtes Modul integriert.\n"
                f"Tool: {self._tool} | Grid: {self._grid_mode} | Snap: {self._snap}\n"
                "Nächste Schritte: echte Notenanzeige/-edit, Kontextmenüs, Audio-Editor als Tab."
            )
        else:
            self._status_item.setPlainText(
                "Kein MIDI-Clip ausgewählt.\n"
                "Wähle im Arranger einen MIDI-Clip, um Noten hier zu bearbeiten (WIP)."
            )

    def set_clip(self, clip_id: str | None) -> None:
        self._clip_id = clip_id
        self.refresh()

    # ---------------------------------------------------------------------
    # Zoom / Refresh
    # ---------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild scene for current clip (lightweight)."""
        self._draw_base_scene()
        self._update_status()

    def _on_project_updated(self) -> None:
        # Only redraw if we're visible / have an active clip.
        if self._clip_id is None:
            # still redraw to keep status consistent
            self._draw_base_scene()
            self._update_status()
            return
        self.refresh()

    def apply_zoom(self, factor: float) -> None:
        # clamp
        if factor <= 0:
            return
        self._zoom = max(0.25, min(4.0, self._zoom * factor))
        self._view.resetTransform()
        self._view.scale(self._zoom, self._zoom)
        self._zoom_label.setText(f"{int(self._zoom*100)}%")

    def _zoom_by(self, factor: float) -> None:
        self.apply_zoom(factor)

    # ---------------------------------------------------------------------
    # Coordinate mapping & snap
    # ---------------------------------------------------------------------
    def _snap_step_beats(self) -> float:
        # Snap string like "1/16" -> 4/16 beats
        try:
            denom = int(str(self._snap).split("/")[1])
            if denom <= 0:
                raise ValueError
            return 4.0 / float(denom)
        except Exception:
            return 0.25

    def _snap_beat(self, beat: float) -> float:
        step = self._snap_step_beats()
        if step <= 0:
            return beat
        return round(beat / step) * step

    def _beat_to_x(self, beat: float) -> float:
        return float(self._staff_cfg["left"]) + beat * float(self._staff_cfg["ppb"])

    def _x_to_beat(self, x: float) -> float:
        return max(0.0, (x - float(self._staff_cfg["left"])) / float(self._staff_cfg["ppb"]))

    @staticmethod
    def _pitchclass_to_letter_index(pc: int) -> int:
        # Sharp spelling collapsed to base letter.
        # C,C#,D,D#,E,F,F#,G,G#,A,A#,B
        return [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][pc % 12]

    @staticmethod
    def _diatonic_to_midi_natural(diatonic: int) -> int:
        octave = diatonic // 7
        letter = diatonic % 7
        pc_map = [0, 2, 4, 5, 7, 9, 11]
        pc = pc_map[letter]
        return (octave + 1) * 12 + pc

    def _midi_to_diatonic(self, pitch: int) -> int:
        octave = (pitch // 12) - 1
        pc = pitch % 12
        letter = self._pitchclass_to_letter_index(pc)
        return octave * 7 + letter

    def _pitch_to_y(self, pitch: int) -> float:
        # Treble: bottom line E4.
        spacing = float(self._staff_cfg["spacing"])
        half = spacing / 2.0
        y_e4 = float(self._staff_cfg["top"]) + 4.0 * spacing
        base = 4 * 7 + 2  # E4
        diat = self._midi_to_diatonic(pitch)
        steps = diat - base
        return y_e4 - steps * half

    def _y_to_pitch_natural(self, y: float) -> int:
        spacing = float(self._staff_cfg["spacing"])
        half = spacing / 2.0
        y_e4 = float(self._staff_cfg["top"]) + 4.0 * spacing
        base = 4 * 7 + 2
        steps = (y_e4 - y) / half
        diat = int(round(base + steps))
        midi = self._diatonic_to_midi_natural(diat)
        return int(max(0, min(127, midi)))

    # ---------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------
    def _render_notes(self) -> None:
        if not self._clip_id:
            return
        notes = list(self._project_service.get_midi_notes(self._clip_id))
        if not notes:
            return

        pen = QPen(Qt.GlobalColor.lightGray)
        pen.setWidth(1)
        brush = QBrush(Qt.GlobalColor.lightGray)
        accidental_brush = QBrush(Qt.GlobalColor.white)

        for n in notes:
            x = self._beat_to_x(float(n.start_beats))
            y = self._pitch_to_y(int(n.pitch))
            item = QGraphicsEllipseItem(x - 6.0, y - 4.0, 12.0, 8.0)
            item.setPen(pen)
            item.setBrush(brush)
            item.setData(0, n)
            item.setData(1, "note")
            self._scene.addItem(item)
            self._note_items.append(item)

            # accidental indicator for sharp pitch classes (WIP)
            if int(n.pitch) % 12 in {1, 3, 6, 8, 10}:
                acc = QGraphicsTextItem("#")
                acc.setDefaultTextColor(Qt.GlobalColor.white)
                acc.setFont(QFont("Sans", 10))
                acc.setPos(x - 16.0, y - 12.0)
                self._scene.addItem(acc)

    # ---------------------------------------------------------------------
    # Interaction
    # ---------------------------------------------------------------------
    def _find_note_item_at(self, scene_pos: QPointF) -> QGraphicsEllipseItem | None:
        for it in self._scene.items(scene_pos):
            try:
                if it.data(1) == "note":
                    return it  # type: ignore[return-value]
            except Exception:
                continue
        return None

    def _handle_left_click(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        if not self._clip_id:
            return
        if self._tool == "pencil":
            self._pencil_add(scene_pos)
        elif self._tool == "erase":
            self._erase(scene_pos)
        elif self._tool == "knife":
            self._knife_split(scene_pos)
        elif self._tool == "time":
            self._time_seek(scene_pos)
        else:  # select
            self._select(scene_pos)

    def _pencil_add(self, scene_pos: QPointF) -> None:
        beat = self._snap_beat(self._x_to_beat(scene_pos.x()))
        length = self._snap_step_beats()
        pitch = self._y_to_pitch_natural(scene_pos.y())

        note = MidiNote(pitch=pitch, start_beats=float(beat), length_beats=float(length), velocity=100)
        self._project_service.snapshot(f"Notation: Add note")
        self._project_service.add_midi_note(self._clip_id, note)
        self._project_service.commit(f"Notation: Add note")

    def _erase(self, scene_pos: QPointF) -> None:
        item = self._find_note_item_at(scene_pos)
        if not item:
            return
        note = item.data(0)
        if not isinstance(note, MidiNote):
            return
        self._project_service.snapshot("Notation: Delete note")
        self._project_service.remove_midi_note(self._clip_id, note)
        self._project_service.commit("Notation: Delete note")

    def _select(self, scene_pos: QPointF) -> None:
        item = self._find_note_item_at(scene_pos)
        # reset old
        if self._selected_item and self._selected_item is not item:
            self._selected_item.setBrush(QBrush(Qt.GlobalColor.lightGray))
        self._selected_item = item
        if item:
            item.setBrush(QBrush(Qt.GlobalColor.darkMagenta))

    def _knife_split(self, scene_pos: QPointF) -> None:
        item = self._find_note_item_at(scene_pos)
        if not item:
            return
        note = item.data(0)
        if not isinstance(note, MidiNote):
            return
        split = self._snap_beat(self._x_to_beat(scene_pos.x()))
        start = float(note.start_beats)
        end = start + float(note.length_beats)
        if split <= start + 1e-6 or split >= end - 1e-6:
            return

        left_len = split - start
        right_len = end - split
        n1 = MidiNote(pitch=note.pitch, start_beats=start, length_beats=left_len, velocity=note.velocity)
        n2 = MidiNote(pitch=note.pitch, start_beats=split, length_beats=right_len, velocity=note.velocity)
        self._project_service.snapshot("Notation: Split note")
        self._project_service.remove_midi_note(self._clip_id, note)
        self._project_service.add_midi_note(self._clip_id, n1)
        self._project_service.add_midi_note(self._clip_id, n2)
        self._project_service.commit("Notation: Split note")

    def _time_seek(self, scene_pos: QPointF) -> None:
        if not self.transport:
            return
        beat = self._snap_beat(self._x_to_beat(scene_pos.x()))
        try:
            self.transport.current_beat = float(beat)
            self.transport.playhead_changed.emit(self.transport.current_beat)
        except Exception:
            pass
