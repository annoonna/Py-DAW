from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QRect, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pydaw.services.project_service import ProjectService
from pydaw.services.transport_service import TransportService

from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value, set_value
from pydaw.music.scales import allowed_pitch_classes
from pydaw.ui.pianoroll_canvas import PianoRollCanvas
from pydaw.ui.note_expression_lane import NoteExpressionLane

# Ghost Notes / Layered Editing Support
from pydaw.ui.layer_panel import LayerPanel

# Scale Lock / Scale Menu (shared with Notation)
from pydaw.ui.scale_menu_button import ScaleMenuButton

from pydaw.ui.widgets.ruler_zoom_handle import paint_magnifier


@dataclass
class _PianoRollUiConstants:
    ruler_h: int = 22
    keyboard_w: int = 66


class _PianoRollRuler(QWidget):
    """Top ruler that follows the canvas horizontal scroll."""

    def __init__(self, canvas: PianoRollCanvas, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.scroll_area = scroll_area
        self.setFixedHeight(_PianoRollUiConstants().ruler_h)
        self.setAutoFillBackground(True)

        # Ruler zoom handle (magnifier)
        self._default_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
        self._zoom_handle_rect = QRect(6, 3, 16, 16)
        self._zoom_drag = False
        self._zoom_origin_y = 0.0
        self._zoom_origin_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
        self._zoom_anchor_beat = 0.0
        self._zoom_anchor_x = 0.0

        # v0.0.20.592: Right-click loop drag state
        self._loop_dragging = False
        self._loop_drag_start = 0.0

        # update when scroll changes
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.update)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update)

    def paintEvent(self, event):  # noqa: N802
        from PySide6.QtGui import QPainter, QPen, QColor

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.palette().window())

        # Zoom handle icon (magnifier)
        try:
            paint_magnifier(p, self._zoom_handle_rect, color=self.palette().text().color())
        except Exception:
            pass

        scroll_x = self.scroll_area.horizontalScrollBar().value()
        ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)

        w = self.width()
        h = self.height()
        start_beat = max(0, int(scroll_x / max(1e-6, ppb)) - 1)
        end_beat = int((scroll_x + w) / max(1e-6, ppb)) + 2

        # v0.0.20.592: Loop region band (Bitwig-style orange)
        try:
            clip = self._get_clip()
            if clip is not None:
                ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
                le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
                if le > ls + 0.01:
                    lx1 = int(ls * ppb) - scroll_x
                    lx2 = int(le * ppb) - scroll_x
                    # Orange band (bottom half of ruler)
                    band_h = max(4, h // 3)
                    band_y = h - band_h
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(255, 140, 0, 60))
                    p.drawRect(lx1, band_y, lx2 - lx1, band_h)
                    # Left/Right handles
                    p.setBrush(QColor(255, 140, 0, 200))
                    p.drawRect(lx1 - 1, band_y, 3, band_h)
                    p.drawRect(lx2 - 1, band_y, 3, band_h)
                    # "L" label
                    p.setPen(QColor(255, 140, 0))
                    p.drawText(lx1 + 4, band_y - 2, "L")
        except Exception:
            pass

        pen_major = QPen(Qt.GlobalColor.lightGray)
        pen_minor = QPen(Qt.GlobalColor.darkGray)

        for beat in range(start_beat, end_beat + 1):
            x = int(beat * ppb) - scroll_x
            if x < 0 or x > w:
                continue
            is_bar = (beat % 4 == 0)
            p.setPen(pen_major if is_bar else pen_minor)
            p.drawLine(x, 0, x, self.height())
            if is_bar:
                bar_idx = beat // 4
                tx = x + 4
                try:
                    if self._zoom_handle_rect.intersects(QRect(tx, 0, 60, self.height())):
                        tx = self._zoom_handle_rect.right() + 6
                except Exception:
                    pass
                p.drawText(tx, self.height() - 6, f"Bar {bar_idx+1}")

    def _get_clip(self):
        """Get current clip from canvas (safe)."""
        try:
            cid = str(getattr(self.canvas, 'clip_id', '') or '')
            if not cid:
                return None
            proj = getattr(self.canvas, 'project', None)
            if proj is None:
                return None
            return next((c for c in proj.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
        except Exception:
            return None

    # ---- zoom handling (horizontal)

    def _apply_ppb(self, new_ppb: float, anchor_beat: float, anchor_x: float) -> None:
        """Apply horizontal zoom (pixels_per_beat) while keeping *anchor_beat* under *anchor_x*."""
        try:
            # Keep bounds aligned with PianoRollCanvas._set_zoom
            new_ppb = float(max(20.0, min(360.0, new_ppb)))
            old_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
            if abs(new_ppb - old_ppb) < 1e-6:
                return
            self.canvas.pixels_per_beat = new_ppb
            try:
                self.canvas._update_canvas_size()  # type: ignore[attr-defined]
            except Exception:
                pass

            # Keep anchor beat stable
            sb = self.scroll_area.horizontalScrollBar()
            new_scroll_x = int(max(0.0, anchor_beat * new_ppb - anchor_x))
            sb.setValue(new_scroll_x)

            self.canvas.update()
            self.update()
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: ANN001
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore


        # v0.0.20.592: Right-click drag → set loop region
        if event.button() == Qt.MouseButton.RightButton:
            try:
                scroll_x = self.scroll_area.horizontalScrollBar().value()
                ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
                beat = max(0.0, (float(pos.x()) + scroll_x) / max(1e-6, ppb))
                self._loop_drag_start = float(beat)
                self._loop_dragging = True
                event.accept()
                return
            except Exception:
                pass

        if event.button() == Qt.MouseButton.LeftButton:
            try:
                if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                    self._zoom_drag = True
                    self._zoom_origin_y = float(pos.y())
                    self._zoom_origin_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
                    scroll_x = float(self.scroll_area.horizontalScrollBar().value())
                    self._zoom_anchor_x = float(pos.x())
                    self._zoom_anchor_beat = (scroll_x + self._zoom_anchor_x) / max(1e-6, self._zoom_origin_ppb)
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                    event.accept()
                    return
            except Exception:
                pass

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: ANN001
        # v0.0.20.592: Loop region drag (right-click)
        if getattr(self, '_loop_dragging', False):
            try:
                pos = event.position()
                scroll_x = self.scroll_area.horizontalScrollBar().value()
                ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
                beat = max(0.0, (float(pos.x()) + scroll_x) / max(1e-6, ppb))
                clip = self._get_clip()
                if clip is not None:
                    s = min(self._loop_drag_start, beat)
                    e = max(self._loop_drag_start, beat)
                    bpb = 4.0
                    try:
                        editor = self.parent()
                        if hasattr(editor, '_beats_per_bar'):
                            bpb = editor._beats_per_bar()
                    except Exception:
                        pass
                    s = round(s / bpb) * bpb
                    e = max(s + bpb, round(e / bpb) * bpb)
                    clip.loop_start_beats = float(s)
                    clip.loop_end_beats = float(e)
                    self.update()
                    try:
                        editor = self.parent()
                        if hasattr(editor, '_refresh_loop_controls'):
                            editor._refresh_loop_controls()
                    except Exception:
                        pass
                event.accept()
                return
            except Exception:
                pass

        # Zoom drag (left-click on magnifier)
        if getattr(self, '_zoom_drag', False):
            try:
                pos = event.position()
            except Exception:
                pos = event.posF()  # type: ignore
            try:
                dy = float(pos.y()) - float(self._zoom_origin_y)
                factor = 1.0 + (-dy / 160.0)
                factor = max(0.25, min(4.0, factor))
                new_ppb = float(self._zoom_origin_ppb) * factor
                self._apply_ppb(new_ppb, float(self._zoom_anchor_beat), float(self._zoom_anchor_x))
                event.accept()
                return
            except Exception:
                pass

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        # v0.0.20.592: Loop drag release
        if getattr(self, '_loop_dragging', False):
            self._loop_dragging = False
            self._loop_drag_start = 0.0
            try:
                editor = self.parent()
                if hasattr(editor, 'project'):
                    editor.project.project_updated.emit()
                if hasattr(editor, '_refresh_loop_controls'):
                    editor._refresh_loop_controls()
            except Exception:
                pass
            self.update()
            event.accept()
            return

        if getattr(self, '_zoom_drag', False):
            self._zoom_drag = False
            try:
                self.unsetCursor()
            except Exception:
                pass
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore

        try:
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                # Reset to default horizontal zoom
                scroll_x = float(self.scroll_area.horizontalScrollBar().value())
                anchor_x = float(pos.x())
                old_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
                anchor_beat = (scroll_x + anchor_x) / max(1e-6, old_ppb)
                self._apply_ppb(float(getattr(self, '_default_ppb', 90.0) or 90.0), anchor_beat, anchor_x)
                event.accept()
                return
        except Exception:
            pass

        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):  # noqa: ANN001
        """Wheel on magnifier = horizontal zoom (like Ableton/Bitwig ruler handle)."""
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore

        try:
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                dy = float(event.angleDelta().y())
                factor = 1.15 if dy > 0 else 1.0 / 1.15
                old_ppb = float(getattr(self.canvas, 'pixels_per_beat', 90.0) or 90.0)
                scroll_x = float(self.scroll_area.horizontalScrollBar().value())
                anchor_x = float(pos.x())
                anchor_beat = (scroll_x + anchor_x) / max(1e-6, old_ppb)
                self._apply_ppb(old_ppb * factor, anchor_beat, anchor_x)
                event.accept()
                return
        except Exception:
            pass

        super().wheelEvent(event)


class _PianoRollKeyboard(QWidget):
    """Left keyboard that follows the canvas vertical scroll."""

    def __init__(self, canvas: PianoRollCanvas, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.scroll_area = scroll_area
        self.setFixedWidth(_PianoRollUiConstants().keyboard_w)
        self.setAutoFillBackground(True)

        # Vertical zoom handle (magnifier)
        self._default_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
        self._zoom_handle_rect = QRect(6, 3, 16, 16)
        self._zoom_drag = False
        self._zoom_origin_y = 0.0
        self._zoom_origin_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
        self._zoom_anchor_st = 0.0  # semitones-from-top (scroll space)
        self._zoom_anchor_y = 0.0

        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update)

    @staticmethod
    def _is_black(midi_pitch: int) -> bool:
        return (midi_pitch % 12) in {1, 3, 6, 8, 10}

    def _apply_pps(self, new_pps: float, anchor_st: float, anchor_y: float) -> None:
        """Apply vertical zoom (pixels_per_semitone) while keeping *anchor_st* under *anchor_y*."""
        try:
            # Keep bounds aligned with PianoRollCanvas._set_zoom
            new_pps = float(max(8.0, min(26.0, new_pps)))
            old_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
            if abs(new_pps - old_pps) < 1e-6:
                return

            self.canvas.pixels_per_semitone = new_pps
            try:
                self.canvas._update_canvas_size()  # type: ignore[attr-defined]
            except Exception:
                pass

            sb = self.scroll_area.verticalScrollBar()
            new_scroll_y = int(max(0.0, anchor_st * new_pps - anchor_y))
            sb.setValue(new_scroll_y)

            self.canvas.update()
            self.update()
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: ANN001
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore

        if event.button() == Qt.MouseButton.LeftButton:
            try:
                if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                    self._zoom_drag = True
                    self._zoom_origin_y = float(pos.y())
                    self._zoom_origin_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
                    scroll_y = float(self.scroll_area.verticalScrollBar().value())
                    self._zoom_anchor_y = float(pos.y())
                    self._zoom_anchor_st = (scroll_y + self._zoom_anchor_y) / max(1e-6, self._zoom_origin_pps)
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                    event.accept()
                    return
            except Exception:
                pass

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if getattr(self, '_zoom_drag', False):
            try:
                pos = event.position()
            except Exception:
                pos = event.posF()  # type: ignore
            try:
                dy = float(pos.y()) - float(self._zoom_origin_y)
                factor = 1.0 + (-dy / 160.0)
                factor = max(0.25, min(4.0, factor))
                new_pps = float(self._zoom_origin_pps) * factor
                self._apply_pps(new_pps, float(self._zoom_anchor_st), float(self._zoom_anchor_y))
                event.accept()
                return
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        if getattr(self, '_zoom_drag', False):
            self._zoom_drag = False
            try:
                self.unsetCursor()
            except Exception:
                pass
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore

        try:
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                scroll_y = float(self.scroll_area.verticalScrollBar().value())
                anchor_y = float(pos.y())
                old_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
                anchor_st = (scroll_y + anchor_y) / max(1e-6, old_pps)
                self._apply_pps(float(getattr(self, '_default_pps', 14.0) or 14.0), anchor_st, anchor_y)
                event.accept()
                return
        except Exception:
            pass

        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):  # noqa: ANN001
        """Wheel on magnifier = vertical zoom in/out."""
        try:
            pos = event.position()
        except Exception:
            pos = event.posF()  # type: ignore

        try:
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                dy = float(event.angleDelta().y())
                factor = 1.15 if dy > 0 else 1.0 / 1.15
                old_pps = float(getattr(self.canvas, 'pixels_per_semitone', 14.0) or 14.0)
                scroll_y = float(self.scroll_area.verticalScrollBar().value())
                anchor_y = float(pos.y())
                anchor_st = (scroll_y + anchor_y) / max(1e-6, old_pps)
                self._apply_pps(old_pps * factor, anchor_st, anchor_y)
                event.accept()
                return
        except Exception:
            pass

        super().wheelEvent(event)

    def paintEvent(self, event):  # noqa: N802
        from PySide6.QtGui import QPainter

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.palette().window())

        # Zoom handle icon (magnifier)
        try:
            paint_magnifier(p, self._zoom_handle_rect, color=self.palette().text().color())
        except Exception:
            pass

        scroll_y = self.scroll_area.verticalScrollBar().value()
        pps = float(self.canvas.pixels_per_semitone)
        lo, hi = self.canvas.visible_pitches

        viewport_h = self.height()
        start_y = scroll_y
        end_y = scroll_y + viewport_h

        pitch_top = hi - int(start_y / pps) - 1
        pitch_bottom = hi - int(end_y / pps) + 1
        pitch_top = min(hi, max(lo, pitch_top))
        pitch_bottom = min(hi, max(lo, pitch_bottom))

        # Scale hints (Pro-DAW-like cyan dots) on the keyboard
        allowed_pcs = None
        try:
            keys = SettingsKeys()
            if bool(get_value(keys.scale_visualize, True)) and bool(get_value(keys.scale_enabled, False)):
                cat = str(get_value(keys.scale_category, "Keine Einschränkung"))
                name = str(get_value(keys.scale_name, "Alle Noten"))
                if cat != "Keine Einschränkung":
                    root = int(get_value(keys.scale_root_pc, 0) or 0)
                    allowed_pcs = set(int(x) % 12 for x in allowed_pitch_classes(category=cat, name=name, root_pc=root))
        except Exception:
            allowed_pcs = None

        if allowed_pcs:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for pitch in range(pitch_top, pitch_bottom - 1, -1):
            y = int((hi - pitch) * pps) - scroll_y
            r_h = int(pps)

            if self._is_black(pitch):
                p.fillRect(0, y, self.width(), r_h, Qt.GlobalColor.black)
                p.setPen(Qt.GlobalColor.darkGray)
            else:
                p.fillRect(0, y, self.width(), r_h, Qt.GlobalColor.white)
                p.setPen(Qt.GlobalColor.gray)

            p.drawRect(0, y, self.width() - 1, r_h)

            if pitch % 12 == 0:
                octave = pitch // 12 - 1
                p.setPen(Qt.GlobalColor.darkBlue)
                p.drawText(6, y + r_h - 4, f"C{octave}")

            # Scale hint dot (cyan)
            if allowed_pcs and (int(pitch) % 12) in allowed_pcs:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(Qt.GlobalColor.cyan)
                cx = int(self.width() - 12)
                cy = int(y + (r_h / 2))
                p.drawEllipse(cx - 3, cy - 3, 6, 6)
class PianoRollEditor(QWidget):
    """Piano roll editor with BachOrgelForge-like tool strip (UI-first)."""

    status_message = Signal(str, int)
    # MIDI live-record toggle (writes notes into clip)
    record_toggled = Signal(bool)

    def __init__(self, project: ProjectService, transport: TransportService | None = None,
                 editor_timeline=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.transport = transport
        self._editor_timeline = editor_timeline  # v0.0.20.613: Dual-Clock Phase C

        # v0.0.20.618: PianoRoll muss vertikal expandieren um Dock-Platz zu füllen
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)
        self.setMinimumWidth(0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # --- Header + local tool strip (v0.0.20.607: compact with dropdown menus)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)
        header_row.setSpacing(3)

        self.header = QLabel("Piano Roll")
        self.header.setObjectName("PianoRollHeader")
        self.header.setMaximumWidth(120)
        self.header.setStyleSheet("font-size: 10px;")
        header_row.addWidget(self.header, 0)

        # ── Tool group (direct buttons, always visible) ──
        self._btn_select = self._mk_tool("Select", "select", shortcut="1")
        self._btn_time = self._mk_tool("Time", "time", shortcut="2")
        self._btn_pen = self._mk_tool("Pencil", "pen", shortcut="3")
        self._btn_erase = self._mk_tool("Erase", "erase", shortcut="4")
        self._btn_knife = self._mk_tool("Knife", "knife", shortcut="5")
        self._tool_widgets = [self._btn_select, self._btn_time, self._btn_pen, self._btn_erase, self._btn_knife]
        for b in self._tool_widgets:
            header_row.addWidget(b)

        # ── Grid (compact: no label, tooltip on combos) ──
        header_row.addSpacing(4)
        self._cmb_grid_mode = QComboBox()
        self._cmb_grid_mode.addItems(["fixed", "adaptive"])
        self._cmb_grid_mode.setToolTip("Grid Mode: fixed = konstant; adaptive = gröber beim Herauszoomen")
        self._cmb_grid_mode.currentTextChanged.connect(self._on_grid_mode)
        self._cmb_grid_mode.setFixedWidth(80)  # v0.0.20.607: fits "adaptive"
        header_row.addWidget(self._cmb_grid_mode)

        self._cmb_grid_div = QComboBox()
        self._grid_denoms = [1, 2, 4, 8, 16, 32, 64]
        for d in self._grid_denoms:
            self._cmb_grid_div.addItem(f"1/{d}", d)
        self._cmb_grid_div.setCurrentIndex(self._grid_denoms.index(16))
        self._cmb_grid_div.currentIndexChanged.connect(self._on_grid_div)
        self._cmb_grid_div.setFixedWidth(62)  # v0.0.20.607: shows "1/16" fully
        header_row.addWidget(self._cmb_grid_div)

        # ── Essential toggles (Snap, Record, Loop) ──
        header_row.addSpacing(4)
        self._btn_snap = self._mk_toggle("Snap", checked=True)
        self._btn_automation = self._mk_toggle("Automation", checked=False)
        self._btn_record = self._mk_toggle("Record", checked=False)
        self._btn_record.setToolTip(
            "MIDI Aufnahme: Aktiviere Record Arm (R) auf der Spur,\n"
            "dann drücke Record hier + Play.\n"
            "Eingehende MIDI-Noten werden in den aktiven Clip geschrieben.\n"
            "Tipp: Wähle MIDI-Input pro Spur im Mixer (All ins / Controller)."
        )

        from PySide6.QtWidgets import QCheckBox
        self._chk_loop = QCheckBox("Loop")
        self._chk_loop.setStyleSheet("QCheckBox { color: #FF8C00; font-weight: bold; }")
        self._chk_loop.setChecked(False)
        self._chk_loop.setFixedWidth(52)

        # Loop region controls (hidden until Loop on)
        self._lbl_loop_L = QLabel("L")
        self._lbl_loop_L.setStyleSheet("QLabel { color: #FF8C00; font-weight: bold; font-size: 10px; }")
        self._lbl_loop_L.setFixedWidth(10)
        self._spn_loop_start = QSpinBox()
        self._spn_loop_start.setRange(1, 999)
        self._spn_loop_start.setValue(1)
        self._spn_loop_start.setToolTip("Loop Start (Bar)")
        self._spn_loop_start.setFixedWidth(42)
        self._spn_loop_end = QSpinBox()
        self._spn_loop_end.setRange(1, 999)
        self._spn_loop_end.setValue(5)
        self._spn_loop_end.setToolTip("Loop End (Bar)")
        self._spn_loop_end.setFixedWidth(42)
        self._lbl_loop_dash = QLabel("–")
        self._lbl_loop_dash.setStyleSheet("QLabel { color: #FF8C00; }")
        self._lbl_loop_dash.setFixedWidth(8)
        for w in (self._lbl_loop_L, self._spn_loop_start, self._lbl_loop_dash, self._spn_loop_end):
            w.setVisible(False)

        self._btn_snap.clicked.connect(self._on_snap)
        try:
            self._btn_record.toggled.connect(self.record_toggled.emit)
        except Exception:
            pass
        self._chk_loop.toggled.connect(self._on_loop_toggled)
        self._spn_loop_start.valueChanged.connect(self._on_loop_start_bar_changed)
        self._spn_loop_end.valueChanged.connect(self._on_loop_end_bar_changed)

        for b in (self._btn_snap, self._btn_record, self._chk_loop):
            header_row.addWidget(b)
        header_row.addWidget(self._lbl_loop_L)
        header_row.addWidget(self._spn_loop_start)
        header_row.addWidget(self._lbl_loop_dash)
        header_row.addWidget(self._spn_loop_end)

        # ── Expression/Lane Tools → Dropdown Menu (v0.0.20.607) ──
        # These widgets exist but are HIDDEN — controlled via menu actions
        header_row.addSpacing(4)
        self._btn_expr = self._mk_toggle("Expr", checked=False)
        self._cmb_expr_param = QComboBox()
        self._cmb_expr_param.addItems(["velocity", "chance", "timbre", "pressure", "gain", "pan", "micropitch"])
        self._cmb_expr_param.setToolTip("Note Expressions Param")
        self._cmb_expr_param.setFixedWidth(72)
        self._btn_expr_mpe = self._mk_toggle("MPE", checked=False)
        self._btn_expr_mpe.setToolTip("Safe MPE-Mode")

        self._btn_lane_draw = self._mk_toggle("LaneDraw", checked=True)
        self._btn_lane_select = self._mk_toggle("LaneSelect", checked=False)
        self._btn_lane_erase = self._mk_toggle("LaneErase", checked=False)
        self._lane_tool_group = (self._btn_lane_draw, self._btn_lane_select, self._btn_lane_erase)

        self._btn_lane_vsnap = self._mk_toggle("V-Snap", checked=True)
        self._btn_lane_vsnap.setToolTip("Expression Lane: Value snapping (Alt=free)")

        self._btn_lane_draw.toggled.connect(lambda v: self._on_lane_tool_toggled('draw', v))
        self._btn_lane_select.toggled.connect(lambda v: self._on_lane_tool_toggled('select', v))
        self._btn_lane_erase.toggled.connect(lambda v: self._on_lane_tool_toggled('erase', v))
        self._btn_lane_vsnap.toggled.connect(self._on_lane_vsnap_toggled)

        self._btn_automation = self._mk_toggle("Automation", checked=False)

        # Hide all — they live only in the dropdown
        for w in (self._btn_expr, self._cmb_expr_param, self._btn_expr_mpe,
                  self._btn_lane_draw, self._btn_lane_select, self._btn_lane_erase,
                  self._btn_lane_vsnap, self._btn_automation):
            w.setVisible(False)

        # Dropdown button with checkable actions
        self._expr_menu_btn = QToolButton()
        self._expr_menu_btn.setText("Expr ▾")
        self._expr_menu_btn.setToolTip("Expression / Lane / MPE / Automation")
        self._expr_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        expr_menu = QMenu(self._expr_menu_btn)

        a_expr = expr_menu.addAction("Expressions")
        a_expr.setCheckable(True)
        a_expr.toggled.connect(self._btn_expr.setChecked)
        self._btn_expr.toggled.connect(a_expr.setChecked)

        a_mpe = expr_menu.addAction("MPE Mode")
        a_mpe.setCheckable(True)
        a_mpe.toggled.connect(self._btn_expr_mpe.setChecked)
        self._btn_expr_mpe.toggled.connect(a_mpe.setChecked)

        a_auto = expr_menu.addAction("Automation")
        a_auto.setCheckable(True)
        a_auto.toggled.connect(self._btn_automation.setChecked)
        self._btn_automation.toggled.connect(a_auto.setChecked)

        expr_menu.addSeparator()
        a_ldraw = expr_menu.addAction("Lane: Draw")
        a_ldraw.setCheckable(True); a_ldraw.setChecked(True)
        a_ldraw.toggled.connect(self._btn_lane_draw.setChecked)

        a_lsel = expr_menu.addAction("Lane: Select")
        a_lsel.setCheckable(True)
        a_lsel.toggled.connect(self._btn_lane_select.setChecked)

        a_lerase = expr_menu.addAction("Lane: Erase")
        a_lerase.setCheckable(True)
        a_lerase.toggled.connect(self._btn_lane_erase.setChecked)

        a_vsnap = expr_menu.addAction("V-Snap")
        a_vsnap.setCheckable(True); a_vsnap.setChecked(True)
        a_vsnap.toggled.connect(self._btn_lane_vsnap.setChecked)

        self._expr_menu_btn.setMenu(expr_menu)
        header_row.addWidget(self._expr_menu_btn)

        # ── Scale Lock ──
        header_row.addStretch(1)  # v0.0.20.607: absorb extra space BEFORE right tools
        self._scale_btn = ScaleMenuButton(self)
        self._scale_btn.changed.connect(self._on_scale_changed)
        self._scale_btn.setMinimumWidth(140)  # v0.0.20.607: show full scale name
        self._scale_btn.setMinimumHeight(38)  # v0.0.20.607: show dots clearly
        header_row.addWidget(self._scale_btn)

        # ── Undo/Redo + Zoom ──
        self._btn_undo = QToolButton()
        self._btn_undo.setText("Undo")
        self._btn_undo.setToolTip("Undo (Ctrl+Z)")
        self._btn_undo.clicked.connect(lambda: getattr(project, 'undo', lambda: None)())
        header_row.addWidget(self._btn_undo)

        self._btn_redo = QToolButton()
        self._btn_redo.setText("Redo")
        self._btn_redo.setToolTip("Redo (Ctrl+Shift+Z / Ctrl+Y)")
        self._btn_redo.clicked.connect(lambda: getattr(project, 'redo', lambda: None)())
        header_row.addWidget(self._btn_redo)

        self._btn_zoom_out = QToolButton()
        self._btn_zoom_out.setText("-")
        self._btn_zoom_out.setToolTip("Zoom out")
        self._btn_zoom_in = QToolButton()
        self._btn_zoom_in.setText("+")
        self._btn_zoom_in.setToolTip("Zoom in")
        self._btn_zoom_out.clicked.connect(lambda: self.canvas.zoom_out())
        self._btn_zoom_in.clicked.connect(lambda: self.canvas.zoom_in())
        header_row.addWidget(self._btn_zoom_out)
        header_row.addWidget(self._btn_zoom_in)

        # v0.0.20.607: Wrap toolbar in fixed-height widget so it never expands the dock
        toolbar_container = QWidget()
        toolbar_container.setLayout(header_row)
        toolbar_container.setFixedHeight(40)  # v0.0.20.619: Feste Höhe für Toolbar
        outer.addWidget(toolbar_container)

        # --- Main grid layout: corner + ruler + keyboard + scrollable canvas
        grid = QGridLayout()
        self._pianoroll_grid = grid
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        self.canvas = PianoRollCanvas(project, transport=self.transport)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.status_message.connect(lambda t, ms=1500: self.status_message.emit(str(t), int(ms)))

        # DAW-style shortcuts (work while focus is anywhere inside the PianoRoll)
        self._install_shortcuts()

        # Loop helpers from the right-click context menu
        if self.transport is not None:
            self.canvas.loop_start_requested.connect(self._set_loop_start)
            self.canvas.loop_end_requested.connect(self._set_loop_end)
            self.canvas.playhead_requested.connect(self._set_playhead)
            # v0.0.20.613: Dual-Clock Phase C — Adapter hat Vorrang
            # Bei Arranger-Fokus: Passthrough (identisch wie vorher)
            # Bei Launcher-Fokus: Lokaler Slot-Beat
            try:
                if self._editor_timeline is not None:
                    self._editor_timeline.playhead_changed.connect(
                        self.canvas.set_transport_playhead)
                else:
                    self.transport.playhead_changed.connect(
                        self.canvas.set_transport_playhead)
            except Exception:
                pass

        # v0.0.20.607: QScrollArea.sizeHint() returns the widget's size when
        # widgetResizable=False. This pushes the dock/window wider whenever
        # the canvas resizes (e.g. on Loop toggle). Fix: override sizeHint.
        class _StableScrollArea(QScrollArea):
            def sizeHint(self):
                from PySide6.QtCore import QSize
                return QSize(200, 200)
            def minimumSizeHint(self):
                from PySide6.QtCore import QSize
                return QSize(100, 80)

        self.scroll = _StableScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        corner = QWidget()
        corner.setFixedSize(_PianoRollUiConstants().keyboard_w, _PianoRollUiConstants().ruler_h)

        self.ruler = _PianoRollRuler(self.canvas, self.scroll)
        self.keyboard = _PianoRollKeyboard(self.canvas, self.scroll)

        grid.addWidget(corner, 0, 0)
        grid.addWidget(self.ruler, 0, 1)
        grid.addWidget(self.keyboard, 1, 0)
        grid.addWidget(self.scroll, 1, 1)

        # Expression Lane (below the piano roll, aligned to scroll)
        try:
            self.expr_lane = NoteExpressionLane(self.canvas, self.scroll)
        except Exception:
            self.expr_lane = None
        # Expression lane row: must NOT steal space when expressions are OFF
        lane_corner = QWidget()
        # Keep refs so toggles can truly collapse/expand the row.
        self._lane_corner = lane_corner
        lane_corner.setFixedWidth(_PianoRollUiConstants().keyboard_w)
        lane_corner.setMinimumHeight(0)
        # Default lane height (compact enough to not crush the editor)
        self._expr_lane_height = 90
        lane_corner.setMaximumHeight(self._expr_lane_height)
        grid.addWidget(lane_corner, 2, 0)
        if self.expr_lane is not None:
            # fixed lane height (Bitwig-style compact strip)
            self.expr_lane.setMinimumHeight(0)
            self.expr_lane.setMaximumHeight(self._expr_lane_height)
            grid.addWidget(self.expr_lane, 2, 1)
        # Default: lane row collapsed (0) until expressions enabled
        try:
            grid.setRowMinimumHeight(2, 0)
        except Exception:
            pass

        grid.setRowStretch(1, 1)
        grid.setColumnStretch(1, 1)

        outer.addLayout(grid)

        # v0.0.20.619: KORREKTUR — Grid (PianoRoll-Canvas) bekommt den Platz!
        # Index 0 = toolbar_container → 0 (fest)
        # Index 1 = grid (Canvas)     → 1 (expandiert)
        try:
            outer.setStretch(0, 0)  # Toolbar: fest
            outer.setStretch(1, 1)  # PianoRoll-Grid: expandiert
        except Exception:
            pass

        # Ghost Notes / Layered Editing: Layer Panel
        self.layer_panel = LayerPanel(self.canvas.layer_manager)
        self.layer_panel.setMaximumHeight(120)  # v0.0.20.594: reduced to prevent window overflow
        self.layer_panel.layer_added.connect(self._on_add_ghost_layer)  # Connect signal
        outer.addWidget(self.layer_panel)
        try:
            self.layer_panel.setSizePolicy(self.layer_panel.sizePolicy().horizontalPolicy(), self.layer_panel.sizePolicy().verticalPolicy())
            self.layer_panel.setMaximumHeight(120)
        except Exception:
            pass
        try:
            outer.setStretch(2, 0)  # Layer-Panel: fest
        except Exception:
            pass

        # defaults
        self._btn_pen.setChecked(True)
        self.canvas.set_tool_mode("pen")
        self._on_grid_div(self._cmb_grid_div.currentIndex())
        self._on_grid_mode(self._cmb_grid_mode.currentText())
        self._on_snap()

        # Note Expressions defaults from QSettings (OFF by default)
        self._init_note_expressions_ui()

        self.set_clip(None)

    def _init_note_expressions_ui(self) -> None:
        try:
            keys = SettingsKeys()
            enabled = bool(get_value(keys.ui_pianoroll_note_expressions_enabled, False))
            param = str(get_value(keys.ui_pianoroll_note_expressions_param, "velocity") or "velocity")
            vsnap = bool(get_value(keys.ui_pianoroll_expr_value_snap, True))
            self._btn_expr.setChecked(enabled)
            ix = self._cmb_expr_param.findText(param)
            if ix >= 0:
                self._cmb_expr_param.setCurrentIndex(ix)
            try:
                self._btn_lane_vsnap.setChecked(bool(vsnap))
            except Exception:
                pass
            try:
                mpe_mode = bool(get_value(keys.audio_note_expr_mpe_mode, False))
                self._btn_expr_mpe.setChecked(bool(mpe_mode))
            except Exception:
                pass
            self._cmb_expr_param.setEnabled(enabled)
            if getattr(self, 'expr_lane', None) is not None:
                self.expr_lane.setVisible(bool(enabled))
            try:
                grid = self._pianoroll_grid  # set in __init__
                h = int(getattr(self, '_expr_lane_height', 90) or 90)
                grid.setRowMinimumHeight(2, h if enabled else 0)
            except Exception:
                pass
            # Ensure the corner cell truly collapses as well.
            try:
                if getattr(self, '_lane_corner', None) is not None:
                    self._lane_corner.setMaximumHeight(int(getattr(self, '_expr_lane_height', 90) or 90) if enabled else 0)
            except Exception:
                pass
            # If we have a lane, clamp its height too.
            try:
                if getattr(self, 'expr_lane', None) is not None:
                    self.expr_lane.setMaximumHeight(int(getattr(self, '_expr_lane_height', 90) or 90) if enabled else 0)
            except Exception:
                pass
            # lane tool buttons
            try:
                for b in (self._btn_lane_draw, self._btn_lane_select, self._btn_lane_erase):
                    b.setEnabled(bool(enabled))
            except Exception:
                pass
            if bool(enabled) and getattr(self, 'expr_lane', None) is not None:
                try:
                    self.expr_lane.set_tool_mode('draw')
                except Exception:
                    pass

            self._btn_expr.toggled.connect(self._on_expr_toggled)
            self._cmb_expr_param.currentTextChanged.connect(self._on_expr_param_changed)
            self._btn_expr_mpe.toggled.connect(self._on_expr_mpe_toggled)

            # Apply to canvas engine
            eng = getattr(self.canvas, 'note_expression_engine', None)
            if eng is not None:
                try:
                    eng.set_active_param(param)
                    eng.set_enabled(enabled)
                except Exception:
                    pass

            # v0.0.20.205: Auto-compact the expression lane unless a note is selected/focused.
            try:
                self._expr_lane_compact_h = 26
                if not hasattr(self, '_expr_lane_height'):
                    self._expr_lane_height = 90
                if getattr(self, '_expr_lane_timer', None) is None:
                    self._expr_lane_timer = QTimer(self)
                    self._expr_lane_timer.setInterval(250)
                    self._expr_lane_timer.timeout.connect(self._refresh_expr_lane_height)
                    self._expr_lane_timer.start()
            except Exception:
                pass
        except Exception:
            pass

    def _on_expr_toggled(self, checked: bool) -> None:
        try:
            checked = bool(checked)
            keys = SettingsKeys()
            set_value(keys.ui_pianoroll_note_expressions_enabled, checked)
            self._cmb_expr_param.setEnabled(checked)
            if getattr(self, 'expr_lane', None) is not None:
                self.expr_lane.setVisible(bool(checked))
            # IMPORTANT: Collapse/expand the grid row. (Bugfix: row height stayed large)
            try:
                grid = self._pianoroll_grid
                h_full = int(getattr(self, '_expr_lane_height', 90) or 90)
                h_compact = int(getattr(self, '_expr_lane_compact_h', 26) or 26)
                grid.setRowMinimumHeight(2, (h_compact if checked else 0))
            except Exception:
                pass
            try:
                if getattr(self, '_lane_corner', None) is not None:
                    self._lane_corner.setMaximumHeight(int(getattr(self, '_expr_lane_height', 90) or 90) if checked else 0)
            except Exception:
                pass
            try:
                if getattr(self, 'expr_lane', None) is not None:
                    self.expr_lane.setMaximumHeight(int(getattr(self, '_expr_lane_height', 90) or 90) if checked else 0)
            except Exception:
                pass
            try:
                for b in (self._btn_lane_draw, self._btn_lane_select, self._btn_lane_erase):
                    b.setEnabled(bool(checked))
            except Exception:
                pass
            eng = getattr(self.canvas, 'note_expression_engine', None)
            if eng is not None:
                eng.set_enabled(checked)
            try:
                self.status_message.emit("Note Expressions: AN" if checked else "Note Expressions: AUS", 1200)
            except Exception:
                pass
        except Exception:
            pass

    def _on_expr_mpe_toggled(self, checked: bool) -> None:
        try:
            from pydaw.core.settings import SettingsKeys
            from pydaw.core.settings_store import set_value
            keys = SettingsKeys()
            set_value(keys.audio_note_expr_mpe_mode, bool(checked))
            try:
                self.status_message.emit("MPE-Mode: AN (hörbarer Start + SF2-Kurvenrender)" if checked else "MPE-Mode: AUS", 1800)
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_expr_lane_height(self) -> None:
        """Keep the expression lane compact unless a note is selected/focused.

        This is UI-only and safe. It avoids the "huge empty expression area" when
        no note is targeted, while still allowing discoverability.
        """
        try:
            eng = getattr(self.canvas, 'note_expression_engine', None)
            if not (eng is not None and bool(getattr(eng, 'enabled', False))):
                return
            grid = getattr(self, '_pianoroll_grid', None)
            if grid is None:
                return

            focus_idx = getattr(self.canvas, '_expr_focus_idx', None)
            sel = getattr(self.canvas, 'selected_indices', set()) or set()
            has_target = (focus_idx is not None) or (len(sel) >= 1)

            h_full = int(getattr(self, '_expr_lane_height', 90) or 90)
            h_compact = int(getattr(self, '_expr_lane_compact_h', 26) or 26)
            want = h_full if bool(has_target) else h_compact
            cur = int(grid.rowMinimumHeight(2))
            if cur != int(want):
                grid.setRowMinimumHeight(2, int(want))
                try:
                    if getattr(self, '_lane_corner', None) is not None:
                        self._lane_corner.setMaximumHeight(int(want))
                except Exception:
                    pass
                try:
                    if getattr(self, 'expr_lane', None) is not None:
                        self.expr_lane.setMaximumHeight(int(want))
                        self.expr_lane.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_expr_param_changed(self, key: str) -> None:
        try:
            key = str(key or 'velocity')
            keys = SettingsKeys()
            set_value(keys.ui_pianoroll_note_expressions_param, key)
            eng = getattr(self.canvas, 'note_expression_engine', None)
            if eng is not None:
                eng.set_active_param(key)
            self.canvas.update()
            if getattr(self, 'expr_lane', None) is not None:
                self.expr_lane.update()
        except Exception:
            pass


    def _on_lane_tool_toggled(self, mode: str, checked: bool) -> None:
        """Toggle expression-lane tool buttons (safe; does not affect canvas tools)."""
        if not bool(checked):
            return
        mode = str(mode or 'draw')
        try:
            mapping = {'draw': self._btn_lane_draw, 'select': self._btn_lane_select, 'erase': self._btn_lane_erase}
            for k, btn in mapping.items():
                if k != mode:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
        except Exception:
            pass
        try:
            if getattr(self, 'expr_lane', None) is not None:
                self.expr_lane.set_tool_mode(mode)
                self.expr_lane.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self.expr_lane.setFocus()
        except Exception:
            pass

    def _install_shortcuts(self) -> None:
        """Install core editing shortcuts for the PianoRoll.

        Paste behavior: anchored at last mouse position in the grid.
        """

        def add_act(seq, fn, text: str = ""):
            a = QAction(self)
            a.setShortcut(seq)
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if text:
                a.setText(text)
            a.triggered.connect(fn)
            self.addAction(a)
        # NOTE: Copy/Cut/Paste/SelectAll are handled by MainWindow global actions
        # to avoid shortcut ambiguity across panels.

        # Delete
        add_act(QKeySequence(Qt.Key.Key_Delete), self.canvas.delete_selected, "Delete")
        add_act(QKeySequence(Qt.Key.Key_Backspace), self.canvas.delete_selected, "Delete")

        # Duplicate (Ctrl+D)
        add_act(QKeySequence("Ctrl+D"), self.canvas.duplicate_selected, "Duplicate")

    # ---- UI helpers

    def _on_lane_vsnap_toggled(self, checked: bool) -> None:
        """Toggle value snapping in Expression Lane (Alt = free)."""
        try:
            keys = SettingsKeys()
            set_value(keys.ui_pianoroll_expr_value_snap, bool(checked))
        except Exception:
            pass
        try:
            if getattr(self, 'expr_lane', None) is not None:
                self.expr_lane.update()
        except Exception:
            pass


    def _mk_tool(self, label: str, mode: str, shortcut: str = "") -> QToolButton:
        b = QToolButton()
        b.setText(label)
        b.setCheckable(True)
        if shortcut:
            b.setToolTip(f"{label} [{shortcut}]")
        b.clicked.connect(lambda: self._set_tool(mode, b))
        return b

    def _mk_toggle(self, label: str, checked: bool = False) -> QToolButton:
        b = QToolButton()
        b.setText(label)
        b.setCheckable(True)
        b.setChecked(bool(checked))
        return b

    def _set_tool(self, mode: str, clicked: QToolButton) -> None:
        for b in (self._btn_select, self._btn_time, self._btn_pen, self._btn_erase, self._btn_knife):
            if b is not clicked:
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        clicked.setChecked(True)
        self.canvas.set_tool_mode(mode)
        try:
            self.status_message.emit(f"Tool: {mode}", 900)
        except Exception:
            pass

    # ---- hooks
    def _on_grid_mode(self, text: str) -> None:
        self.canvas.set_grid_mode(str(text or "fixed"))

    def _on_grid_div(self, idx: int) -> None:
        denom = int(self._cmb_grid_div.itemData(idx) or 16)
        self.canvas.set_grid_division(denom)

    def _on_snap(self) -> None:
        self.canvas.set_snap_enabled(bool(self._btn_snap.isChecked()))

    def _on_scale_changed(self) -> None:
        """Scale selector changed.

        The canvas reads the persistent settings when creating notes.
        We only refresh small UI hints / repaint.
        """
        try:
            self._scale_btn.refresh()
        except Exception:
            pass
        try:
            self.canvas.update()
            self.keyboard.update()
        except Exception:
            pass

    # ---- transport interactions
    def _set_loop_start(self, beat: float) -> None:
        if self.transport is None:
            return
        _start, end = self.transport.get_loop_region()
        self.transport.set_loop_region(float(beat), float(max(beat + 0.25, end)))
        self.transport.set_loop(True)

    def _set_loop_end(self, beat: float) -> None:
        if self.transport is None:
            return
        start, _end = self.transport.get_loop_region()
        self.transport.set_loop_region(float(min(start, beat - 0.25)), float(beat))
        self.transport.set_loop(True)

    def _set_playhead(self, beat: float) -> None:
        if self.transport is None:
            return
        try:
            self.transport.set_position_beats(float(beat))
        except Exception:
            # keep it non-fatal
            pass

    # ---- Ghost Notes / Layered Editing
    def _on_add_ghost_layer(self) -> None:
        """Handle add ghost layer request from Layer Panel."""
        from PySide6.QtWidgets import QDialog
        from pydaw.ui.clip_selection_dialog import ClipSelectionDialog
        from pydaw.model.ghost_notes import LayerState
        
        # Open clip selection dialog
        dialog = ClipSelectionDialog(
            self.project,
            current_clip_id=self.canvas.clip_id,
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            clip_id = dialog.get_selected_clip_id()
            if not clip_id:
                return
            
            # Get clip info for display name
            try:
                project = self.project.ctx.project
                clip = next((c for c in project.clips if c.id == clip_id), None)
                track = next((t for t in project.tracks if clip and t.id == clip.track_id), None)
                
                if clip and track:
                    track_name = str(track.name)
                    
                    # Add as ghost layer
                    self.canvas.layer_manager.add_layer(
                        clip_id=clip_id,
                        track_name=track_name,
                        state=LayerState.LOCKED,
                        opacity=0.3,
                    )
                    
                    # Show status message
                    try:
                        self.status_message.emit(f"Ghost Layer hinzugefügt: {track_name}", 2000)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error adding ghost layer: {e}")

    # ---- public API
    def set_clip(self, clip_id: str | None) -> None:
        self.canvas.set_clip(clip_id)
        if clip_id:
            short_id = str(clip_id)[:8] if len(str(clip_id)) > 8 else str(clip_id)
            self.header.setText(f"PR: {short_id}")
        else:
            self.header.setText("Piano Roll")
        self._refresh_loop_controls()
        self.ruler.update()
        self.keyboard.update()
        # v0.0.20.606: Scroll to beginning (Bar 1) when opening a new clip
        try:
            self.scroll.horizontalScrollBar().setValue(0)
        except Exception:
            pass

    # ---- v0.0.20.592: Clip Loop Region (Bitwig-style) ----

    def _get_current_clip(self):
        """Get the Clip object currently loaded in the Piano Roll."""
        cid = str(getattr(self.canvas, 'clip_id', '') or '')
        if not cid:
            return None
        try:
            return next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
        except Exception:
            return None

    def _beats_per_bar(self) -> float:
        try:
            ts = str(getattr(self.project.ctx.project, 'time_signature', '4/4') or '4/4')
            num, den = ts.split('/')
            return float(int(num)) * (4.0 / float(int(den)))
        except Exception:
            return 4.0

    def _refresh_loop_controls(self) -> None:
        """Sync loop toggle + spinboxes with current clip model."""
        clip = self._get_current_clip()
        if clip is None:
            self._chk_loop.setChecked(False)
            for w in (self._lbl_loop_L, self._spn_loop_start, self._lbl_loop_dash, self._spn_loop_end):
                w.setVisible(False)
            return

        loop_s = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
        loop_e = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
        has_loop = loop_e > loop_s + 0.01
        bpb = self._beats_per_bar()

        # Block signals while updating
        for w in (self._chk_loop, self._spn_loop_start, self._spn_loop_end):
            w.blockSignals(True)

        self._chk_loop.setChecked(has_loop)
        if has_loop:
            self._spn_loop_start.setValue(max(1, int(loop_s / bpb) + 1))
            self._spn_loop_end.setValue(max(1, int(loop_e / bpb) + 1))
        else:
            clip_len = float(getattr(clip, 'length_beats', 16.0) or 16.0)
            self._spn_loop_start.setValue(1)
            self._spn_loop_end.setValue(max(2, int(clip_len / bpb) + 1))

        for w in (self._chk_loop, self._spn_loop_start, self._spn_loop_end):
            w.blockSignals(False)

        visible = has_loop
        for w in (self._lbl_loop_L, self._spn_loop_start, self._lbl_loop_dash, self._spn_loop_end):
            w.setVisible(visible)

    def _on_loop_toggled(self, checked: bool) -> None:
        clip = self._get_current_clip()
        if clip is None:
            return
        if checked:
            bpb = self._beats_per_bar()
            clip_len = float(getattr(clip, 'length_beats', 16.0) or 16.0)
            clip.loop_start_beats = 0.0
            clip.loop_end_beats = max(bpb, clip_len)
        else:
            clip.loop_start_beats = 0.0
            clip.loop_end_beats = 0.0
        self._refresh_loop_controls()
        self.ruler.update()
        try:
            self.project.project_updated.emit()
        except Exception:
            pass

    def _on_loop_start_bar_changed(self, bar: int) -> None:
        clip = self._get_current_clip()
        if clip is None:
            return
        bpb = self._beats_per_bar()
        new_start = max(0.0, (float(bar) - 1.0) * bpb)
        clip.loop_start_beats = new_start
        # Keep end after start
        if clip.loop_end_beats <= new_start + 0.01:
            clip.loop_end_beats = new_start + bpb
            self._spn_loop_end.blockSignals(True)
            self._spn_loop_end.setValue(bar + 1)
            self._spn_loop_end.blockSignals(False)
        self.ruler.update()
        try:
            self.project.project_updated.emit()
        except Exception:
            pass

    def _on_loop_end_bar_changed(self, bar: int) -> None:
        clip = self._get_current_clip()
        if clip is None:
            return
        bpb = self._beats_per_bar()
        new_end = max(bpb, float(bar) * bpb)  # bar N means end of bar N-1
        clip.loop_end_beats = new_end
        # Keep start before end
        if clip.loop_start_beats >= new_end - 0.01:
            clip.loop_start_beats = max(0.0, new_end - bpb)
            self._spn_loop_start.blockSignals(True)
            self._spn_loop_start.setValue(max(1, bar - 1))
            self._spn_loop_start.blockSignals(False)
        self.ruler.update()
        try:
            self.project.project_updated.emit()
        except Exception:
            pass
