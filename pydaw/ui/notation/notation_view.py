"""NotationView (Task 3).

This module provides a lightweight, DAW-integrated notation view that can
display MIDI notes from :class:`pydaw.services.project_service.ProjectService`.

It intentionally stays *minimal*: the goal is to **show** notes reliably (MVP)
and keep the code easy to evolve into an editor (Draw/Erase/Select tools are
planned in TODO.md).

Key points
----------
- Uses :class:`pydaw.ui.notation.staff_renderer.StaffRenderer` for drawing.
- Uses a small QGraphicsScene so the UI remains responsive.
- Listens to ``project_updated`` and repaints when the active clip changes.

Run a visual demo:

.. code-block:: bash

    python3 -m pydaw.ui.notation.notation_view
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal

from PyQt6.QtGui import QBrush, QCursor, QFont, QPainter, QColor, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QRubberBand,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pydaw.model.midi import MidiNote
from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value
from pydaw.music.scales import allowed_pitch_classes
from pydaw.ui.notation.staff_renderer import StaffRenderer, StaffStyle
from pydaw.ui.notation.colors import (
    velocity_to_color, velocity_to_outline,
    pitch_class_color, pitch_class_outline, pitch_class_text_color, note_name,
)
from pydaw.ui.notation.tools import (
    DrawTool,
    EraseTool,
    NotationTool,
    SelectTool,
    TieTool,
    SlurTool,
    _nearest_note_index,
    snap_beats_from_div,
    snap_to_grid,
)

from pydaw.ui.notation.notation_palette import NotationPalette, NotationInputState

# Ghost Notes / Layered Editing Support
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.notation.notation_ghost_notes import NotationGhostRenderer


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


# --- duration formatting helpers (Notation UI) ---

_BEATS_TO_FRAC = {
    4.0: "1/1",
    2.0: "1/2",
    1.0: "1/4",
    0.5: "1/8",
    0.25: "1/16",
    0.125: "1/32",
    0.0625: "1/64",
}


def _format_duration_fraction(beats: float) -> str:
    """Return a stable fraction string (e.g. 1/16 or 1/8.) for a beat duration."""
    try:
        b = float(beats)
    except Exception:
        return "?"

    # dotted detection: beats ~= base * 1.5
    for base, frac in sorted(_BEATS_TO_FRAC.items(), key=lambda x: -x[0]):
        if abs(b - base) < 1e-6:
            return frac
        if abs(b - base * 1.5) < 1e-6:
            return f"{frac}."
    # fallback: show numeric
    return f"{b:g} beat"


def _format_rest_label(beats: float) -> str:
    frac = _format_duration_fraction(beats)
    # Keep it font-safe: use ASCII label, but include a subtle unicode rest if available
    # (If the system font lacks it, it will just render as a tofu box.)
    return f"Rest {frac}"



# Public helpers used in render code

def format_rest_label(beats: float) -> str:
    return _format_rest_label(beats)


def format_ornament_label(orn: str) -> str:
    o = str(orn or "").strip()
    if o == "trill":
        return "tr"
    return o if o else "orn"



@dataclass
class NotationLayout:
    """Layout constants for the view."""

    y_offset: int = 70
    left_margin: int = 40
    right_margin: int = 40
    top_margin: int = 30
    bottom_margin: int = 40
    pixels_per_beat: float = 120.0
    # Maximum width in beats we pre-allocate for a stable scene (prevents heavy resizes)
    max_beats: float = 64.0
    # Clef + Time Signature (v0.0.20.447)
    clef_type: str = "treble"
    time_sig_num: int = 4
    time_sig_denom: int = 4


@dataclass
class _LiveGhostState:
    """State for a currently held (live) MIDI note, shown as a ghost notehead."""

    pitch: int
    velocity: int
    channel: int
    start_beats: float  # clip-relative beat position
    accidental: int = 0



class _StaffBackgroundItem(QGraphicsItem):
    """Draws the staff, clef symbol, and time signature."""

    def __init__(self, width_px: float, style: StaffStyle, y_offset: int,
                 clef_type: str = "treble", time_sig_num: int = 4, time_sig_denom: int = 4):
        super().__init__()
        self._width_px = float(width_px)
        self._style = style
        self._y_offset = int(y_offset)
        self._clef_type = str(clef_type)
        self._ts_num = int(time_sig_num)
        self._ts_denom = int(time_sig_denom)
        self._clef_rect: QRectF = QRectF()  # for click detection

    @property
    def clef_rect(self) -> QRectF:
        return self._clef_rect

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        h = StaffRenderer.staff_height(self._style) + 120
        return QRectF(0, 0, self._width_px, float(h))

    def paint(self, painter: QPainter, _opt, _widget=None):  # noqa: N802 (Qt API)
        # IMPORTANT: Never let exceptions escape paint(); PyQt6 can abort the
        # whole process on unhandled exceptions during painting.
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            StaffRenderer.render_staff(painter, int(self._width_px), self._y_offset, self._style)

            # Clef symbol (v0.0.20.447)
            try:
                self._clef_rect = StaffRenderer.render_clef(
                    painter, 6.0, self._y_offset, self._clef_type, self._style
                )
            except Exception:
                pass

            # Time signature (v0.0.20.447)
            try:
                StaffRenderer.render_time_signature(
                    painter, 32.0, self._y_offset,
                    self._ts_num, self._ts_denom, self._style
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Staff background paint failed")


class _NoteItem(QGraphicsItem):
    """A single note rendered via StaffRenderer."""

    def __init__(
        self,
        note: MidiNote,
        *,
        x_center: float,
        staff_line: int,
        y_offset: int,
        style: StaffStyle,
        selected: bool = False,
    ):
        super().__init__()
        self.note = note
        self._x = float(x_center)
        self._line = int(staff_line)
        self._y_offset = int(y_offset)
        self._style = style
        self._selected = bool(selected)
        self._key = (
            int(getattr(note, "pitch", 0)),
            round(float(getattr(note, "start_beats", 0.0)), 6),
            round(float(getattr(note, "length_beats", 0.0)), 6),
        )
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    @property
    def key(self) -> tuple[int, float, float]:
        return self._key

    def set_selected(self, on: bool) -> None:
        on = bool(on)
        if on == self._selected:
            return
        self._selected = on
        # Slightly lift selected notes above others.
        try:
            self.setZValue(10.0 if on else 0.0)
        except Exception:
            pass
        self.update()
    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        """Conservative bounding rect around note head + stems/accidentals.

        Notes can be outside the staff (ledger lines). If the bounding rect is
        anchored incorrectly, Qt may clip items and they can appear to
        'disappear' when you scroll/zoom.
        """
        w = float(self._style.note_head_w * 4)
        h = float(self._style.stem_len + self._style.note_head_h * 6)

        bottom_line_y = StaffRenderer.line_y(self._y_offset, self._style.lines - 1, self._style)
        half_step = float(self._style.line_distance) / 2.0
        y = float(bottom_line_y) - (float(self._line) * half_step)

        return QRectF(float(self._x) - w, y - h, w * 2.0, h * 2.0)

    def paint(self, painter: QPainter, _opt, _widget=None):  # noqa: N802 (Qt API)
        # IMPORTANT: Never let exceptions escape paint(); PyQt6 can abort the
        # whole process on unhandled exceptions during painting.
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Determine accidental from note spelling
            # Ensure accidental is populated (MidiNote.to_staff_position updates it)
            try:
                _ = self.note.to_staff_position()
            except Exception:
                pass
            acc = int(getattr(self.note, "accidental", 0))

            # Stem direction: middle line (B4) is staff_line=4 when bottom line is E4.
            stem_up = self._line < 4

            # Pitch-class color (Klangfarbe, v0.0.20.451)
            vel = int(getattr(self.note, "velocity", 100))
            pitch = int(getattr(self.note, "pitch", 60))
            fill = pitch_class_color(pitch, selected=self._selected, velocity=vel)
            outline = pitch_class_outline(pitch, selected=self._selected, velocity=vel)

            StaffRenderer.render_accidental(painter, self._x, self._line, self._y_offset, acc, self._style)

            # Subtle glow effect (always, dezent — pitch-color based)
            try:
                from PyQt6.QtGui import QPainterPath

                note_head_w = self._style.note_head_w
                note_head_h = self._style.note_head_h
                bottom_line_y = StaffRenderer.line_y(self._y_offset, self._style.lines - 1, self._style)
                half_step = float(self._style.line_distance) / 2.0
                center_y = float(bottom_line_y) - (float(self._line) * half_step)

                glow_alpha = 50 if not self._selected else 80
                glow_layers = (5.0, 3.0) if not self._selected else (6.0, 4.0, 2.0)

                for j, expand in enumerate(glow_layers):
                    alpha = max(0, glow_alpha - j * 16)
                    glow_color = QColor(fill)
                    glow_color.setAlpha(alpha)

                    glow_rect = QRectF(
                        self._x - note_head_w / 2 - expand,
                        center_y - note_head_h / 2 - expand,
                        note_head_w + 2 * expand,
                        note_head_h + 2 * expand,
                    )
                    path = QPainterPath()
                    path.addEllipse(glow_rect)
                    painter.fillPath(path, QBrush(glow_color))
            except Exception:
                pass

            StaffRenderer.render_note_head(
                painter,
                self._x,
                self._line,
                self._y_offset,
                self._style,
                filled=True,
                fill_color=fill,
                outline_color=outline,
            )
            StaffRenderer.render_stem(painter, self._x, self._line, self._y_offset, stem_up, self._style)

            # Note name below the notehead (v0.0.20.452)
            # Shows full German name with octave: C4, Cis3, Dis2, Fis1, etc.
            try:
                nn = note_name(pitch, german=True, with_octave=True)
                txt_color = pitch_class_color(pitch, selected=False, velocity=vel)
                txt_color = txt_color.darker(130)  # slightly darker than fill for contrast

                bottom_line_y2 = StaffRenderer.line_y(self._y_offset, self._style.lines - 1, self._style)
                half_step2 = float(self._style.line_distance) / 2.0
                cy = float(bottom_line_y2) - (float(self._line) * half_step2)

                # Position: below the notehead + stem
                nhh = float(self._style.note_head_h)
                label_y = cy + nhh / 2 + 3  # just below notehead
                if not stem_up:
                    label_y = cy + nhh / 2 + float(self._style.stem_len) + 2

                name_font = QFont("Sans", 6)
                name_font.setBold(True)
                painter.setFont(name_font)
                painter.setPen(QPen(txt_color))
                painter.drawText(
                    QPointF(float(self._x) - 10, float(label_y) + 8),
                    nn
                )
            except Exception:
                pass

            # Selection outline (softer, matches glow effect)
            if self._selected:
                try:
                    # Subtle outline (not too harsh)
                    pen = QPen(QColor(100, 150, 255, 180))  # Soft blue with transparency
                    pen.setWidth(2)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    r = self.boundingRect()
                    painter.drawRoundedRect(r.adjusted(4, 4, -4, -4), 6, 6)
                except Exception:
                    pass

        except Exception:
            logger.exception("Note item paint failed")



class _LiveGhostNoteItem(QGraphicsItem):
    """Transient live notehead (ghost) for real-time input monitoring."""

    def __init__(
        self,
        *,
        x_center: float,
        line: int,
        accidental: int,
        velocity: int,
        y_offset: int,
        style: StaffStyle,
    ):
        super().__init__()
        self._x = float(x_center)
        self._line = int(line)
        self._acc = int(accidental)
        self._vel = int(velocity)
        self._y_offset = int(y_offset)
        self._style = style

        # Draw above normal notes
        try:
            self.setZValue(8.0)
        except Exception:
            pass

    def boundingRect(self) -> QRectF:  # noqa: N802
        # Similar to _NoteItem but tighter (notehead + accidental)
        w = float(self._style.note_head_w * 2.8)
        h = float(self._style.note_head_h * 2.8)

        bottom_line_y = StaffRenderer.line_y(self._y_offset, self._style.lines - 1, self._style)
        half_step = float(self._style.line_distance) / 2.0
        y = float(bottom_line_y) - (float(self._line) * half_step)

        # accidental sits left of notehead
        return QRectF(self._x - w - 16.0, y - h, (w * 2.0) + 28.0, h * 2.0)

    def paint(self, painter: QPainter, _opt, _widget=None):  # noqa: N802
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Pro-DAW-like cyan ghost noteheads
            color = QColor(0, 220, 200, 165)
            outline = QColor(0, 220, 200, 210)
            pen = QPen(outline)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            StaffRenderer.render_accidental(painter, self._x, self._line, self._y_offset, self._acc, self._style)

            # Hollow notehead (ghost)
            StaffRenderer.render_note_head(
                painter,
                self._x,
                self._line,
                self._y_offset,
                self._style,
                filled=False,
                fill_color=color,
                outline_color=outline,
            )
        except Exception:
            logger.exception("Live ghost note paint failed")


class _MarkItem(QGraphicsItem):
    """Small on-score marker for comments/rests/ornaments (MVP)."""

    def __init__(self, *, kind: str, x: float, y: float, text: str, mark_id: str = ""):
        super().__init__()
        self.kind = str(kind)
        self.text = str(text or "")
        self.mark_id = str(mark_id or "")
        self._rect = QRectF(float(x), float(y), 80.0 if self.kind == "comment" else 60.0, 18.0)

        # Make it easy to hover + selectable for editing (Delete / context menu).
        self.setAcceptHoverEvents(True)
        try:
            self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        except Exception:
            pass
        self.setToolTip(self.text if self.text else self.kind)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._rect

    def paint(self, painter: QPainter, option, widget=None):  # noqa: N802
        # IMPORTANT: never let exceptions escape paint() (Qt would abort).
        try:
            painter.save()
            pen = QPen(Qt.GlobalColor.black)
            try:
                if self.isSelected():
                    pen = QPen(QColor(90, 40, 200))
                    pen.setWidth(2)
            except Exception:
                pass
            painter.setPen(pen)

            if self.kind == "comment":
                painter.setBrush(QColor(255, 255, 160))
            elif self.kind == "rest":
                painter.setBrush(QColor(230, 230, 230))
            else:
                painter.setBrush(QColor(210, 240, 255))

            painter.drawRoundedRect(self._rect, 3.0, 3.0)

            # Text
            painter.drawText(self._rect.adjusted(4, 0, -4, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text[:32])
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass




class _ConnectionItem(QGraphicsItem):
    """Tie/Slur connection between two notes (MVP marker).

    Stored as a notation_mark with data: {"from": {"beat":..,"pitch":..}, "to": {...}}.
    """

    def __init__(self, *, kind: str, x1: float, y1: float, x2: float, y2: float, mark_id: str = ""):
        super().__init__()
        self.kind = str(kind or "slur")
        self.mark_id = str(mark_id or "")
        self._x1 = float(x1); self._y1 = float(y1)
        self._x2 = float(x2); self._y2 = float(y2)
        # Selectable for editing (Delete / context menu)
        try:
            self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        except Exception:
            pass
        self.setAcceptHoverEvents(True)
        self.setToolTip(self.kind)

    def boundingRect(self) -> QRectF:  # noqa: N802
        x1, x2 = sorted([self._x1, self._x2])
        y1, y2 = sorted([self._y1, self._y2])
        pad = 40.0
        return QRectF(x1 - pad, y1 - pad, (x2 - x1) + 2 * pad, (y2 - y1) + 2 * pad)

    def paint(self, painter: QPainter, option, widget=None):  # noqa: N802
        # IMPORTANT: never let exceptions escape paint() (Qt would abort).
        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Curve height: slur higher than tie
            dx = abs(self._x2 - self._x1)
            base = 10.0 if self.kind == "tie" else 18.0
            h = base + min(22.0, dx * 0.08)

            # Prefer drawing above the notes by default
            y_up = min(self._y1, self._y2) - h
            ctrl_x = (self._x1 + self._x2) * 0.5
            ctrl_y = y_up

            from PyQt6.QtGui import QPainterPath

            path = QPainterPath()
            path.moveTo(self._x1, self._y1)
            path.quadTo(ctrl_x, ctrl_y, self._x2, self._y2)

            pen = QPen(QColor(40, 40, 40, 160))
            try:
                if self.isSelected():
                    pen = QPen(QColor(90, 40, 200, 220))
                    pen.setWidth(3)
            except Exception:
                pass
            pen.setWidth(2 if self.kind == "slur" else 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass

class NotationView(QGraphicsView):
    """Notation view that renders notes from the current clip."""

    notes_changed = pyqtSignal()

    def __init__(self, project_service, *, parent: Optional[QWidget] = None):
        scene = QGraphicsScene()
        super().__init__(scene, parent)

        self._project_service = project_service
        self._clip_id: str | None = None
        self._layout = NotationLayout()
        self._style = StaffStyle()
        self._keys = SettingsKeys()

        # Live MIDI ghost notes (noteheads while key is held)
        self._live_ghost: dict[str, list[_LiveGhostState]] = {}
        self._live_ghost_items: list[_LiveGhostNoteItem] = []
        self._default_ppb = float(self._layout.pixels_per_beat)
        self._y_zoom = 1.0

        # --- Playhead + Ruler (v0.0.20.445) ---
        self._playhead_beat: float = 0.0
        self._last_playhead_px: int = 0
        self._ruler_height: int = 24  # pixel height for bar-label ruler strip
        # v0.0.20.535: Transport reference + Follow Playhead
        self._transport = None
        self._follow_playhead: bool = False

        # Notation input state (professionelle palette)
        self.input_state = NotationInputState()
        self._last_mouse_scene_pos = None  # updated by mouseMoveEvent

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._apply_view_transform()
        # Keep colors predictable across themes.
        try:
            from PyQt6.QtGui import QBrush

            self.setBackgroundBrush(QBrush(Qt.GlobalColor.white))
        except Exception:
            pass

        self._staff_item: _StaffBackgroundItem | None = None
        self._note_items: list[_NoteItem] = []

        # --- Task 7: Bidirektionale MIDI-Sync (MVP-Infra) ---
        # The project emits a global `project_updated` signal for many changes.
        # For the notation view we keep refreshes cheap and avoid feedback loops
        # when we ourselves update MIDI notes.
        self._suppress_project_updates: int = 0
        self._last_notes_sig: tuple | None = None

        # Selection (Task 6 - Select-Tool)
        self._selected_key: tuple[int, float, float] | None = None
        # Multi-Select Support (Phase 1 - SAFE)
        self._selected_keys: set[tuple[int, float, float]] = set()
        # Lasso Selection (Phase 2 - MEDIUM)
        self._lasso_start_pos: QPoint | None = None
        self._lasso_rubber_band: QRubberBand | None = None

        # Clipboard (Task 8 - Keyboard Shortcuts)
        # Stores notes for copy/paste (supports multi-note)
        self._clipboard_note: MidiNote | None = None  # Legacy single-note
        self._clipboard_notes: list[MidiNote] = []  # Multi-note support
        self._clipboard_last_paste_start: float | None = None

        # Editing tools
        self._draw_tool: NotationTool = DrawTool()
        self._select_tool: NotationTool = SelectTool()
        self._tie_tool: NotationTool = TieTool()
        self._slur_tool: NotationTool = SlurTool()
        # pending tie/slur multi-click state
        self._pending_connection: dict | None = None
        # Connection overlay mode (allows Tie/Slur while Draw tool stays active)
        self._connection_mode: str | None = None
        # Active tool defaults to Draw (MVP)
        self._tool: NotationTool = self._draw_tool
        # Task 5 (Erase-Tool): routed via right-click for now (keeps MVP UI simple)
        self._erase_tool: NotationTool = EraseTool()

        # Ghost Notes / Layered Editing Support
        self.layer_manager = LayerManager()
        self.ghost_renderer = NotationGhostRenderer(self)

        # Restore persisted ghost layers (Project.ghost_layers)
        # IMPORTANT: Project loading is async (threadpool). The view is created
        # before `open_project()` finishes, so we also reload when the project
        # context changes.
        self._load_ghost_layers_from_project(emit=False)

        try:
            self._project_service.project_changed.connect(self._on_project_changed)
        except Exception:
            pass

        # Connect layer changes to refresh + persist
        self.layer_manager.layers_changed.connect(self._refresh_ghost_notes)
        self.layer_manager.layers_changed.connect(self._persist_ghost_layers_to_project)

        # auto-refresh when project changes (throttled + recursion-safe)
        try:
            self._project_service.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

        self._rebuild_scene_base()


    # ------------------------------------------------------------------
    # Time signature helper
    # ------------------------------------------------------------------
    def _beats_per_bar(self) -> float:
        """v0.0.20.538: Return beats per bar from the project's time signature."""
        try:
            proj = getattr(self._project_service, "ctx", None)
            if proj is not None:
                proj_obj = getattr(proj, "project", None)
                if proj_obj is not None:
                    ts = str(getattr(proj_obj, "time_signature", "4/4") or "4/4")
                    parts = ts.split("/")
                    if len(parts) == 2:
                        num = int(parts[0])
                        den = int(parts[1])
                        return float(num) * (4.0 / float(den))
        except Exception:
            pass
        try:
            t = self._transport
            if t is not None and hasattr(t, "beats_per_bar"):
                return float(t.beats_per_bar())
        except Exception:
            pass
        return 4.0

    # ------------------------------------------------------------------
    # View transforms / scrolling / zooming
    # ------------------------------------------------------------------
    def _apply_view_transform(self) -> None:
        """Apply current Y zoom to the view transform (scene coords stay stable)."""
        try:
            t = QTransform()
            t.scale(1.0, float(self._y_zoom))
            self.setTransform(t)
        except Exception:
            pass

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        try:
            return max(float(lo), min(float(hi), float(v)))
        except Exception:
            return float(lo)

    def _set_x_zoom(self, factor: float) -> None:
        ppb = float(self._layout.pixels_per_beat)
        ppb = self._clamp(ppb * float(factor), 30.0, 600.0)
        self._layout.pixels_per_beat = ppb
        self.refresh()

    def _set_y_zoom(self, factor: float) -> None:
        self._y_zoom = self._clamp(float(self._y_zoom) * float(factor), 0.6, 3.5)
        self._apply_view_transform()
        try:
            self.viewport().update()
        except Exception:
            pass

    def _reset_zoom(self) -> None:
        self._layout.pixels_per_beat = float(self._default_ppb)
        self._y_zoom = 1.0
        self._apply_view_transform()
        self.refresh()

    # ------------------------------------------------------------------
    # Playhead (v0.0.20.445)
    # ------------------------------------------------------------------
    def set_playhead_beat(self, beat: float) -> None:
        """Update transport playhead position (in beats).

        Only invalidates the old/new playhead stripe to avoid full repaints.
        Same strategy as ArrangerCanvas.set_playhead().
        """
        try:
            ppb = float(self._layout.pixels_per_beat)
            left = float(self._layout.left_margin)
            old_x = int(left + self._playhead_beat * ppb)
            self._playhead_beat = max(0.0, float(beat))
            new_x = int(left + self._playhead_beat * ppb)
            self._last_playhead_px = new_x

            # Invalidate only the thin vertical stripes (old + new position)
            vp = self.viewport()
            if vp is not None:
                for sx in (old_x, new_x):
                    # Map scene x to viewport coords
                    vp_pt = self.mapFromScene(float(sx), 0.0)
                    vx = int(vp_pt.x())
                    vp.update(max(0, vx - 3), 0, 6, vp.height())

            # v0.0.20.535: Follow Playhead — auto-scroll when playhead exits visible area
            if self._follow_playhead and vp is not None:
                try:
                    vp_w = vp.width()
                    ph_vp = self.mapFromScene(float(new_x), 0.0).x()
                    # When playhead reaches 80% of visible width, jump so it's at 20%
                    if ph_vp > vp_w * 0.8 or ph_vp < 0:
                        target_scene_x = new_x - int(vp_w * 0.2)
                        self.horizontalScrollBar().setValue(max(0, target_scene_x))
                except Exception:
                    pass
        except Exception:
            pass

    def set_transport(self, transport) -> None:
        """v0.0.20.535: Set transport reference for click-to-seek."""
        self._transport = transport

    def _seek_to_beat(self, beat: float) -> None:
        """v0.0.20.535: Seek transport to the given beat position."""
        try:
            t = self._transport
            if t is not None and hasattr(t, "seek"):
                t.seek(float(beat))
        except Exception:
            pass

    def set_follow_playhead(self, enabled: bool) -> None:
        """v0.0.20.535: Enable/disable auto-scroll follow."""
        self._follow_playhead = bool(enabled)

    def drawForeground(self, painter: QPainter, rect: QRectF):  # noqa: N802 (Qt API)
        """Draw playhead (red line) and ruler bar labels on top of everything."""
        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            left = float(self._layout.left_margin)
            ppb = float(self._layout.pixels_per_beat)
            sr = self.sceneRect()

            # --- Ruler strip background (semi-transparent) ---
            ruler_h = float(self._ruler_height)
            ruler_top = float(sr.top())
            ruler_rect = QRectF(rect.left(), ruler_top, rect.width(), ruler_h)
            painter.fillRect(ruler_rect, QColor(38, 42, 52, 210))

            # --- Bar labels in ruler ---
            bar_beats = self._beats_per_bar()  # v0.0.20.538: from project time sig
            vis_beat0 = max(0.0, (rect.left() - left) / ppb)
            vis_beat1 = max(0.0, (rect.right() - left) / ppb)
            bar_start = int(max(0, math.floor(vis_beat0 / bar_beats)))
            bar_end = int(math.ceil(vis_beat1 / bar_beats)) + 1

            font = QFont("Sans", 9)
            font.setBold(False)
            painter.setFont(font)

            for k in range(bar_start, bar_end):
                beat = float(k) * bar_beats
                x = left + beat * ppb

                # Bar separator line in ruler
                pen_bar = QPen(QColor(100, 108, 120, 200))
                pen_bar.setWidth(1)
                painter.setPen(pen_bar)
                painter.drawLine(int(x), int(ruler_top), int(x), int(ruler_top + ruler_h))

                # Bar label
                painter.setPen(QPen(QColor(200, 206, 216)))
                painter.drawText(int(x + 4), int(ruler_top + ruler_h - 6), f"Bar {k + 1}")

            # Ruler bottom separator
            painter.setPen(QPen(QColor(80, 88, 100, 160)))
            painter.drawLine(int(rect.left()), int(ruler_top + ruler_h),
                             int(rect.right()), int(ruler_top + ruler_h))

            # --- Playhead (red line) ---
            ph_x = left + self._playhead_beat * ppb
            if rect.left() - 4 <= ph_x <= rect.right() + 4:
                pen_play = QPen(QColor(220, 40, 40))
                pen_play.setWidth(2)
                painter.setPen(pen_play)
                painter.drawLine(int(ph_x), int(sr.top()), int(ph_x), int(sr.bottom()))

                # Small triangle marker at top of ruler
                tri_h = 8.0
                tri_w = 6.0
                tri = QPolygonF([
                    QPointF(ph_x - tri_w, ruler_top),
                    QPointF(ph_x + tri_w, ruler_top),
                    QPointF(ph_x, ruler_top + tri_h),
                ])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(220, 40, 40)))
                painter.drawPolygon(tri)

            painter.restore()
        except Exception:
            try:
                painter.restore()
            except Exception:
                pass

    def wheelEvent(self, ev):  # noqa: N802 (Qt API)
        """DAW-style scroll/zoom.
        
        FIXED v0.0.19.7.20: Intuitiveres Mousewheel-Verhalten!
        
        - Plain Wheel: VERTIKAL scrollen (hoch/runter) ← HAUPTFUNKTION!
        - Shift + Wheel: HORIZONTAL scrollen (links/rechts)
        - Ctrl + Wheel: X zoom (pixels/beat, Zeit-Achse)
        - Ctrl + Shift + Wheel: Y zoom (staff spacing, Notenzeilen-Höhe)
        """
        try:
            delta = ev.angleDelta().y()
        except Exception:
            return super().wheelEvent(ev)

        mods = ev.modifiers()
        steps = float(delta) / 120.0  # typical wheel step
        if steps == 0.0:
            return

        # Ctrl + Shift + Wheel: Y zoom (staff spacing)
        if (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.ShiftModifier):
            self._set_y_zoom(1.12 if steps > 0 else 1.0 / 1.12)
            ev.accept()
            return

        # Ctrl + Wheel: X zoom (time axis)
        if mods & Qt.KeyboardModifier.ControlModifier:
            self._set_x_zoom(1.12 if steps > 0 else 1.0 / 1.12)
            ev.accept()
            return

        # Shift + Wheel: HORIZONTAL scroll (timeline)
        if mods & Qt.KeyboardModifier.ShiftModifier:
            sb = self.horizontalScrollBar()
            sb.setValue(int(sb.value() - steps * 80))
            ev.accept()
            return

        # Plain Wheel: VERTIKAL scroll (up/down) ← HAUPTFUNKTION!
        sb = self.verticalScrollBar()
        sb.setValue(int(sb.value() - steps * 60))
        ev.accept()

    def keyPressEvent(self, ev):  # noqa: N802 (Qt API)
        try:
            if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if ev.key() == Qt.Key.Key_0:
                    self._reset_zoom()
                    ev.accept()
                    return
                if ev.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                    self._set_x_zoom(1.12)
                    ev.accept()
                    return
                if ev.key() == Qt.Key.Key_Minus:
                    self._set_x_zoom(1.0 / 1.12)
                    ev.accept()
                    return
        except Exception:
            pass
        return super().keyPressEvent(ev)

    def drawBackground(self, painter: QPainter, rect: QRectF):  # noqa: N802 (Qt API)
        """Draw beat/bar grid + optional scale hints behind the staff."""
        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            # Base background (keep staff readable)
            painter.fillRect(rect, QColor("#ffffff"))

            left = float(self._layout.left_margin)
            ppb = float(self._layout.pixels_per_beat)

            # Visible beat range
            beat0 = max(0.0, (rect.left() - left) / ppb)
            beat1 = max(0.0, (rect.right() - left) / ppb)

            # v0.0.20.538: use project time signature
            bar = self._beats_per_bar()

            # Pens: subbeat (very light), beat, bar (strong)
            pen_sub = QPen(QColor(220, 224, 228), 1)
            pen_beat = QPen(QColor(190, 196, 202), 1)
            pen_bar = QPen(QColor(120, 128, 136), 2)

            # Subbeat grid: 1/4 beat (16th) – readable, not too dense
            sub = 0.25
            start = int(beat0 / sub) - 1
            end = int(beat1 / sub) + 2
            for i in range(start, end + 1):
                b = float(i) * sub
                x = left + b * ppb
                if x < rect.left() - 2 or x > rect.right() + 2:
                    continue
                is_beat = abs((b % 1.0)) < 1e-9
                is_bar = abs((b % bar)) < 1e-9
                painter.setPen(pen_bar if is_bar else (pen_beat if is_beat else pen_sub))
                painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))

            # Optional scale hints: subtle cyan row tint so in-scale notes are easier to spot
            try:
                if bool(get_value(self._keys.scale_visualize, True)) and bool(get_value(self._keys.scale_enabled, False)):
                    cat = str(get_value(self._keys.scale_category, "Keine Einschränkung"))
                    name = str(get_value(self._keys.scale_name, "Alle Noten"))
                    root = int(get_value(self._keys.scale_root_pc, 0) or 0) % 12
                    if cat != "Keine Einschränkung":
                        pcs = set(allowed_pitch_classes(category=cat, name=name, root_pc=root))
                        # Tint the staff band slightly; true per-pitch tint is hard in classical staff,
                        # but this gives a Pro-DAW-ish "scale mode is active" feel without clutter.
                        if pcs:
                            painter.fillRect(rect, QColor(0, 229, 255, 10))
            except Exception:
                pass

            painter.restore()
        except Exception:
            # Never crash paint pipeline
            try:
                painter.restore()
            except Exception:
                pass
            return super().drawBackground(painter, rect)

    # ------------------------------------------------------------------
    # Tool-facing helpers / properties
    # ------------------------------------------------------------------
    @property
    def project_service(self):
        return self._project_service

    @property
    def clip_id(self) -> str | None:
        return self._clip_id


    def set_input_state(self, state: object) -> None:
        """Update the current notation input state (from NotationPalette)."""
        try:
            if isinstance(state, NotationInputState):
                self.input_state = state
            else:
                self.input_state = getattr(self, "input_state", NotationInputState())
        except Exception:
            self.input_state = NotationInputState()
        try:
            self.viewport().update()
        except Exception:
            pass


    def _load_ghost_layers_from_project(self, *, emit: bool = True) -> None:
        """Load ghost layer state from the current project (if present).

        Args:
            emit: If True, emit LayerManager change signals after loading.
                  For init, use emit=False. For project open/new/load, emit=True.
        """
        try:
            proj = getattr(self._project_service, 'ctx', None)
            proj = getattr(proj, 'project', None)
            state = getattr(proj, 'ghost_layers', {}) or {}
            if isinstance(state, dict):
                self.layer_manager.load_state(state, emit=emit)
        except Exception:
            pass

    def _on_project_changed(self) -> None:
        """Reload persisted ghost layers after project open/new/load."""
        self._load_ghost_layers_from_project(emit=True)
        try:
            self.refresh()
        except Exception:
            pass

    def _persist_ghost_layers_to_project(self) -> None:
        """Persist current layer manager state into the project model."""
        try:
            proj = getattr(self._project_service, 'ctx', None)
            proj = getattr(proj, 'project', None)
            if proj is None:
                return
            setattr(proj, 'ghost_layers', self.layer_manager.to_dict())
            try:
                proj.modified_utc = datetime.utcnow().isoformat(timespec='seconds')
            except Exception:
                pass
        except Exception:
            pass



    def connection_mode(self) -> str | None:
        return self._connection_mode

    def set_connection_mode(self, mode: str | None) -> None:
        """Enable/disable Tie/Slur overlay mode.

        This is intentionally independent from the primary tool (Draw/Select),
        so users can keep the pencil active and still place ties/slurs,
        professionelles.
        """
        m = (str(mode).strip().lower() if mode is not None else "")
        if m in ("tie", "haltebogen"):
            self._connection_mode = "tie"
        elif m in ("slur", "bindebogen"):
            self._connection_mode = "slur"
        else:
            self._connection_mode = None
            # Cancel pending 2-click connection if any.
            try:
                self._pending_connection = None
            except Exception:
                pass

        try:
            lab = self._connection_mode or "off"
            self._project_service.status.emit(f"Notation Connection: {lab}")
        except Exception:
            pass

    def set_active_tool(self, name: str) -> None:
        """Switch the active left-click tool.

        Supported: "draw", "select", "tie", "slur".
        """

        n = str(name or "").strip().lower()
        if n in ("draw", "pencil"):
            self._tool = self._draw_tool
        elif n in ("select", "arrow"):
            self._tool = self._select_tool
        elif n in ("tie", "haltebogen"):
            # Overlay mode (can be used while Draw stays active)
            self.set_connection_mode("tie")
            return
        elif n in ("slur", "bindebogen"):
            self.set_connection_mode("slur")
            return
        else:
            self._tool = self._draw_tool


        # Provide UI feedback via status signal.
        try:
            self._project_service.status.emit(f"Notation Tool: {self._tool.name}")
        except Exception:
            pass

    # ---- selection helpers (used by SelectTool) ----

    def _open_clef_dialog(self) -> None:
        """Open the clef picker dialog (v0.0.20.447)."""
        try:
            from pydaw.ui.notation.clef_dialog import ClefDialog
            dlg = ClefDialog(current_clef=str(self._layout.clef_type), parent=self)
            if dlg.exec() != ClefDialog.DialogCode.Accepted:
                return
            new_clef = str(dlg.selected_clef())
            if new_clef == str(self._layout.clef_type):
                return  # no change
            self._layout.clef_type = new_clef
            self.refresh()
            try:
                self._project_service.status.emit(f"Schlüssel: {new_clef}")
            except Exception:
                pass
        except Exception:
            pass
    @staticmethod
    def _note_key(note: MidiNote) -> tuple[int, float, float]:
        return (
            int(getattr(note, "pitch", 0)),
            round(float(getattr(note, "start_beats", 0.0)), 6),
            round(float(getattr(note, "length_beats", 0.0)), 6),
        )

    def is_selected_note(self, note: MidiNote) -> bool:
        key = self._note_key(note)
        # Check both single and multi-select
        return (key == self._selected_key) or (key in self._selected_keys)

    def clear_selection(self) -> None:
        self._selected_key = None
        self._selected_keys.clear()
        self._apply_selection_to_items()

    def select_note(self, note: MidiNote, *, multi: bool = False, toggle: bool = False) -> None:
        """Select a note.
        
        Args:
            note: Note to select
            multi: If True, add to multi-selection. If False, clear previous selection.
            toggle: If True, toggle selection state (only with multi=True)
        """
        key = self._note_key(note)
        
        if multi:
            if toggle and key in self._selected_keys:
                # Toggle off
                self._selected_keys.discard(key)
                if self._selected_key == key:
                    self._selected_key = None
            else:
                # Add to multi-selection
                self._selected_keys.add(key)
                self._selected_key = key  # Keep for single-select compatibility
        else:
            # Single selection (clear previous)
            self._selected_keys.clear()
            self._selected_key = key
            self._selected_keys.add(key)
        
        self._apply_selection_to_items()
    
    def get_selected_notes(self) -> list[MidiNote]:
        """Get all currently selected notes."""
        if not self._clip_id:
            return []
        
        try:
            ps = self._project_service
            all_notes = list(ps.get_midi_notes(str(self._clip_id)))
        except Exception:
            return []
        
        # Combine single and multi-select
        selected_keys = self._selected_keys.copy()
        if self._selected_key is not None:
            selected_keys.add(self._selected_key)
        
        return [n for n in all_notes if self._note_key(n) in selected_keys]

    def _apply_selection_to_items(self) -> None:
        # Combine single and multi-select keys
        selected_keys = self._selected_keys.copy()
        if self._selected_key is not None:
            selected_keys.add(self._selected_key)
        
        for it in list(self._note_items):
            try:
                it.set_selected(it.key in selected_keys)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Lasso Selection (Phase 2 - MEDIUM)
    # ------------------------------------------------------------------
    def _start_lasso_selection(self, view_pos: QPoint, modifiers: Qt.KeyboardModifier) -> None:
        """Start lasso selection (rubber band rectangle)."""
        self._lasso_start_pos = view_pos
        
        # Create rubber band if not exists
        if self._lasso_rubber_band is None:
            self._lasso_rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        # Position rubber band at start point
        try:
            self._lasso_rubber_band.setGeometry(view_pos.x(), view_pos.y(), 1, 1)
            self._lasso_rubber_band.show()
        except Exception:
            pass
        
        # Clear selection if not Ctrl (additive mode)
        if not (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.clear_selection()

    def _update_lasso_rubber_band(self, current_pos: QPoint) -> None:
        """Update rubber band geometry during drag."""
        if self._lasso_start_pos is None or self._lasso_rubber_band is None:
            return
        
        try:
            # Calculate rectangle from start to current
            x1 = min(self._lasso_start_pos.x(), current_pos.x())
            y1 = min(self._lasso_start_pos.y(), current_pos.y())
            x2 = max(self._lasso_start_pos.x(), current_pos.x())
            y2 = max(self._lasso_start_pos.y(), current_pos.y())
            
            rect = QRect(x1, y1, x2 - x1, y2 - y1)
            self._lasso_rubber_band.setGeometry(rect)
        except Exception:
            pass

    def _finish_lasso_selection(self, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> None:
        """Complete lasso selection - select all notes in rectangle."""
        if self._lasso_start_pos is None or self._lasso_rubber_band is None:
            return
        
        try:
            # Get lasso rectangle in scene coordinates
            lasso_rect_view = self._lasso_rubber_band.geometry()
            lasso_rect_scene = QRectF(
                self.mapToScene(lasso_rect_view.topLeft()),
                self.mapToScene(lasso_rect_view.bottomRight())
            )
            
            # Find all notes that intersect with lasso rectangle
            if not self._clip_id:
                return
            
            ps = self._project_service
            try:
                all_notes = list(ps.get_midi_notes(str(self._clip_id)))
            except Exception:
                all_notes = []
            
            # Helper: staff_line to scene_y (inverse of scene_y_to_staff_line)
            def staff_line_to_scene_y(staff_line: int) -> float:
                bottom_line_y = float(self._layout.y_offset) + float((self._style.lines - 1) * self._style.line_distance)
                half_step = float(self._style.line_distance) / 2.0
                return bottom_line_y - (staff_line * half_step)
            
            # Check each note for intersection with lasso
            selected_count = 0
            for note in all_notes:
                try:
                    # Get note bounding box in scene coordinates
                    note_start_x = float(self._layout.left_margin) + float(note.start_beats) * float(self._layout.pixels_per_beat)
                    note_end_x = note_start_x + float(note.length_beats) * float(self._layout.pixels_per_beat)
                    
                    # Get note Y position from pitch
                    staff_line = self._pitch_to_staff_line(int(note.pitch))
                    note_y = staff_line_to_scene_y(staff_line)
                    
                    # Note bounding box (with some height for visibility)
                    note_height = 20.0  # Approximate note head height
                    note_rect = QRectF(note_start_x, note_y - note_height/2, note_end_x - note_start_x, note_height)
                    
                    # Check intersection
                    if lasso_rect_scene.intersects(note_rect):
                        self.select_note(note, multi=True, toggle=False)
                        selected_count += 1
                except Exception:
                    continue
            
            # Show status
            if selected_count > 0:
                try:
                    msg = f"{selected_count} Noten ausgewählt (Lasso)" if selected_count > 1 else "Note ausgewählt (Lasso)"
                    ps.status.emit(msg)
                except Exception:
                    pass
            else:
                # No notes selected - clear selection if not Ctrl
                if not (modifiers & Qt.KeyboardModifier.ControlModifier):
                    self.clear_selection()
            
        except Exception:
            pass
        finally:
            # Always cleanup
            self._cancel_lasso_selection()

    def _cancel_lasso_selection(self) -> None:
        """Cancel/cleanup lasso selection."""
        self._lasso_start_pos = None
        if self._lasso_rubber_band is not None:
            try:
                self._lasso_rubber_band.hide()
            except Exception:
                pass



    def pick_note_at(self, scene_pos) -> MidiNote | None:
        """Return the nearest note under the cursor (used by tie/slur tools).

        This is intentionally conservative to avoid picking the wrong note.
        """
        if not self._clip_id:
            return None
        try:
            ps = self._project_service
            notes = list(ps.get_midi_notes(str(self._clip_id)))
        except Exception:
            return None
        if not notes:
            return None

        try:
            beat = float(self.scene_x_to_beat(float(scene_pos.x())))
            staff_line = int(self.scene_y_to_staff_line(float(scene_pos.y())))
        except Exception:
            return None

        try:
            snap_div = str(getattr(self._project_service.ctx.project, "snap_division", "1/16") or "1/16")
            snap = float(snap_beats_from_div(snap_div))
        except Exception:
            snap = 0.25

        idx = None
        try:
            idx = _nearest_note_index(self, notes, target_beat=float(beat), target_staff_line=int(staff_line), snap_step=float(snap))
        except Exception:
            idx = None
        if idx is None:
            return None
        try:
            return notes[int(idx)]
        except Exception:
            return None

    def _get_selected_note(self) -> MidiNote | None:
        """Return the currently selected note (single selection MVP)."""
        if not self._clip_id or self._selected_key is None:
            return None
        ps = self._project_service
        try:
            notes = list(ps.get_midi_notes(str(self._clip_id)))
        except Exception:
            return None

        for n in notes:
            try:
                if self._note_key(n) == self._selected_key:
                    return n
            except Exception:
                continue
        return None

    def _delete_selected_note(self) -> bool:
        """Delete all currently selected notes, committed as a single Undo step."""
        if not self._clip_id:
            return False
        
        # Get all selected notes (supports multi-select)
        selected_notes = self.get_selected_notes()
        if not selected_notes:
            return False

        ps = self._project_service
        try:
            all_notes = list(ps.get_midi_notes(str(self._clip_id)))
        except Exception:
            all_notes = []

        # Create set of keys to delete for fast lookup
        keys_to_delete = {self._note_key(n) for n in selected_notes}
        
        # Filter out selected notes
        new_notes = [n for n in all_notes if self._note_key(n) not in keys_to_delete]
        
        if len(new_notes) == len(all_notes):
            # Nothing was deleted
            return False

        deleted_count = len(all_notes) - len(new_notes)
        self.commit_notes_to_project(new_notes, label=f"Delete {deleted_count} Note(s) (Notation)")
        self.clear_selection()
        self.refresh()
        try:
            msg = f"Notation: {deleted_count} Note(n) gelöscht." if deleted_count > 1 else "Notation: Note gelöscht."
            ps.status.emit(msg)
        except Exception:
            pass
        return True

    def _delete_selected_marks(self) -> bool:
        """Delete selected notation marks (ties/slurs/comments/rests/ornaments)."""
        try:
            items = list(self.scene().selectedItems())
        except Exception:
            items = []
        mark_ids: list[str] = []
        for it in items:
            try:
                mid = getattr(it, "mark_id", "") or ""
                if mid:
                    mark_ids.append(str(mid))
            except Exception:
                pass
        if not mark_ids:
            return False

        # Remove marks via ProjectService (persists in project json on save)
        try:
            for mid in mark_ids:
                self._project_service.remove_notation_mark(str(mid))
        except Exception:
            pass

        try:
            self.scene().clearSelection()
        except Exception:
            pass
        try:
            self._project_service.status.emit("Notation: Mark gelöscht.")
        except Exception:
            pass
        self.refresh()
        return True


    def _copy_selected_note(self) -> bool:
        """Copy all selected notes into internal clipboard."""
        selected_notes = self.get_selected_notes()
        if not selected_notes:
            return False
        
        try:
            # Sort by start time for predictable paste
            selected_notes.sort(key=lambda n: n.start_beats)
            
            # Find earliest start time for relative positioning
            min_start = min(n.start_beats for n in selected_notes)
            
            # Copy notes with relative positioning
            self._clipboard_notes = []
            for sel in selected_notes:
                copied = MidiNote(
                    pitch=int(getattr(sel, "pitch", 60)),
                    start_beats=float(getattr(sel, "start_beats", 0.0)) - min_start,  # Relative!
                    length_beats=float(getattr(sel, "length_beats", 1.0)),
                    velocity=int(getattr(sel, "velocity", 100)),
                    accidental=int(getattr(sel, "accidental", 0)),
                    tie_to_next=bool(getattr(sel, "tie_to_next", False)),
                ).clamp()
                self._clipboard_notes.append(copied)
            
            # Keep first note in legacy clipboard for compatibility
            if self._clipboard_notes:
                self._clipboard_note = self._clipboard_notes[0]
            
        except Exception:
            return False

        self._clipboard_last_paste_start = None
        try:
            count = len(self._clipboard_notes)
            msg = f"Notation: {count} Note(n) kopiert." if count > 1 else "Notation: Note kopiert."
            self._project_service.status.emit(msg)
        except Exception:
            pass
        return True

    def _cut_selected_note(self) -> bool:
        """Cut = copy + delete."""
        if not self._copy_selected_note():
            return False
        return self._delete_selected_note()

    def _paste_clipboard_note(self) -> bool:
        """Paste clipboard notes (supports multi-note).

        Placement logic:
        - If a note is selected: paste right after it (start = selected.end).
        - Else: paste at the last paste position + total length (stepwise).
        - Else: paste at beat 0.
        The start is snapped to the current project snap grid when available.
        """
        # Check if we have multi-note clipboard or single-note
        if not self._clip_id:
            return False
        
        clipboard = self._clipboard_notes if self._clipboard_notes else (
            [self._clipboard_note] if self._clipboard_note else []
        )
        
        if not clipboard:
            return False

        ps = self._project_service
        try:
            notes = list(ps.get_midi_notes(str(self._clip_id)))
        except Exception:
            notes = []

        # Determine paste position
        selected = self.get_selected_notes()
        if selected:
            # Paste after last selected note
            selected.sort(key=lambda n: n.start_beats)
            last = selected[-1]
            start = float(getattr(last, "start_beats", 0.0)) + float(getattr(last, "length_beats", 1.0))
        elif self._clipboard_last_paste_start is not None:
            # Paste after last paste (stepwise)
            # Calculate total length of clipboard notes
            total_length = max((n.start_beats + n.length_beats) for n in clipboard)
            start = float(self._clipboard_last_paste_start) + total_length
        else:
            start = 0.0

        # Snap to project grid
        try:
            snap_div = str(getattr(ps.ctx.project, "snap_division", "1/16") or "1/16")
            step = snap_beats_from_div(snap_div)
            start = snap_to_grid(float(start), float(step))
        except Exception:
            pass

        # Paste all notes with relative positioning
        pasted_notes = []
        for clip_note in clipboard:
            new_note = MidiNote(
                pitch=int(getattr(clip_note, "pitch", 60)),
                start_beats=float(start) + float(getattr(clip_note, "start_beats", 0.0)),
                length_beats=float(getattr(clip_note, "length_beats", 1.0)),
                velocity=int(getattr(clip_note, "velocity", 100)),
                accidental=int(getattr(clip_note, "accidental", 0)),
                tie_to_next=bool(getattr(clip_note, "tie_to_next", False)),
            ).clamp()
            pasted_notes.append(new_note)
            notes.append(new_note)

        # Keep stable ordering
        try:
            notes.sort(key=lambda n: (float(getattr(n, "start_beats", 0.0)), int(getattr(n, "pitch", 0))))
        except Exception:
            pass

        count = len(pasted_notes)
        label = f"Paste {count} Note(s) (Notation)" if count > 1 else "Paste Note (Notation)"
        self.commit_notes_to_project(notes, label=label)
        
        # Remember last paste position for stepwise pasting
        if pasted_notes:
            self._clipboard_last_paste_start = float(getattr(pasted_notes[0], "start_beats", 0.0))
        
        # Select pasted notes
        self.clear_selection()
        for n in pasted_notes:
            self.select_note(n, multi=True)
        
        self.refresh()
        try:
            msg = f"Notation: {count} Note(n) eingefügt." if count > 1 else "Notation: Note eingefügt."
            ps.status.emit(msg)
        except Exception:
            pass
        return True

    def scene_x_to_beat(self, scene_x: float) -> float:
        """Convert a scene X coordinate to beats (unsnapped)."""
        return (float(scene_x) - float(self._layout.left_margin)) / float(self._layout.pixels_per_beat)

    def scene_y_to_staff_line(self, scene_y: float) -> int:
        """Convert a scene Y coordinate to a staff line/space index.

        Our staff model (as used by StaffRenderer):
        - bottom staff line == 0
        - each step (1) == one *half step* in pixel space (line or space)
        """
        bottom_line_y = float(self._layout.y_offset) + float((self._style.lines - 1) * self._style.line_distance)
        half_step = float(self._style.line_distance) / 2.0
        return int(round((bottom_line_y - float(scene_y)) / max(1e-9, half_step)))

    def staff_line_to_pitch(self, staff_line: int, *, accidental: int = 0) -> int:
        """Convert a staff line/space index to a MIDI pitch (clef-aware, v0.0.20.454).

        Uses the clef's reference pitch and line to calculate correctly.
        Shift+Click = sharp, Alt+Click = flat (handled by DrawTool).
        """
        try:
            from pydaw.ui.notation.clef_dialog import get_clef
            info = get_clef(str(self._layout.clef_type))

            # Clef reference: info.ref_pitch at info.ref_line
            ref_halfsteps = int(info.ref_line) * 2
            diat_diff = int(staff_line) - ref_halfsteps

            # Convert ref_pitch to diatonic
            _pc_to_diat = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
            ref_p = int(info.ref_pitch)
            r_oct = (ref_p // 12) - 1
            r_pc = ref_p % 12
            r_diat = r_oct * 7 + _pc_to_diat[r_pc]

            target_diat = r_diat + diat_diff
            octave = target_diat // 7
            line = target_diat % 7

            return int(MidiNote.from_staff_position(int(line), int(octave), int(accidental)))
        except Exception:
            pass
        # Fallback: original treble-only
        e4_ref = self._diatonic_index(2, 4)
        diat = int(e4_ref) + int(staff_line)
        octave = diat // 7
        line = diat % 7
        return int(MidiNote.from_staff_position(int(line), int(octave), int(accidental)))

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event):  # noqa: N802 (Qt API)
        try:
            self._last_mouse_scene_pos = self.mapToScene(event.pos())
        except Exception:
            self._last_mouse_scene_pos = None
        
        # Phase 2: Update lasso rubber band during drag
        if self._lasso_start_pos is not None and self._lasso_rubber_band is not None:
            try:
                self._update_lasso_rubber_band(event.pos())
                return  # Don't propagate to super during lasso
            except Exception:
                pass
        
        try:
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt API)
        """Handle mouse release - complete lasso selection if active."""
        # Phase 2: Complete lasso selection on release
        if self._lasso_start_pos is not None:
            try:
                self._finish_lasso_selection(event.button(), event.modifiers())
                return
            except Exception:
                # Cleanup on error
                self._cancel_lasso_selection()
        
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: N802 (Qt API)
        try:
            scene_pos = self.mapToScene(event.pos())
            btn = event.button()
            mods = event.modifiers()

            # v0.0.20.535: Click-to-Seek in ruler area
            if btn == Qt.MouseButton.LeftButton:
                try:
                    ruler_h = float(self._ruler_height)
                    sr = self.mapToScene(self.viewport().rect()).boundingRect()
                    ruler_bottom = sr.top() + ruler_h
                    if scene_pos.y() < ruler_bottom:
                        # Click in ruler — seek transport to this beat
                        left = float(self._layout.left_margin)
                        ppb = float(self._layout.pixels_per_beat)
                        if ppb > 0:
                            beat = max(0.0, (scene_pos.x() - left) / ppb)
                            self._seek_to_beat(beat)
                            event.accept()
                            return
                except Exception:
                    pass

            # --- Clef click detection (v0.0.20.447) ---
            if btn == Qt.MouseButton.LeftButton and self._staff_item is not None:
                try:
                    cr = getattr(self._staff_item, 'clef_rect', QRectF())
                    if isinstance(cr, QRectF) and not cr.isNull() and cr.contains(scene_pos):
                        self._open_clef_dialog()
                        event.accept()
                        return
                except Exception:
                    pass

            # Hit-test items for editing (ties/slurs/marks)
            hit = None
            try:
                hit = self.scene().itemAt(scene_pos, self.transform())
            except Exception:
                hit = None

            # Right-click: prefer context actions on marks over erase.
            if btn == Qt.MouseButton.RightButton and hit is not None:
                if isinstance(hit, (_ConnectionItem, _MarkItem)):
                    try:
                        # Select the item so Delete works immediately.
                        self.scene().clearSelection()
                        hit.setSelected(True)
                    except Exception:
                        pass
                    # Show a tiny context menu (Delete)
                    try:
                        from PyQt6.QtWidgets import QMenu
                        menu = QMenu(self)
                        act_del = menu.addAction("Löschen")
                        act = menu.exec(event.globalPosition().toPoint())
                        if act == act_del:
                            self._delete_selected_marks()
                            return
                    except Exception:
                        # If menu fails, do not erase.
                        return

            # Left-click selection on marks (so Draw tool won't create notes by accident)
            if btn == Qt.MouseButton.LeftButton and hit is not None:
                if isinstance(hit, (_ConnectionItem, _MarkItem)):
                    try:
                        self.scene().clearSelection()
                        hit.setSelected(True)
                        return
                    except Exception:
                        pass

            # Phase 2: Lasso Selection (only for Select Tool)
            # Start lasso on left-click in empty space when Select Tool is active
            if btn == Qt.MouseButton.LeftButton and hit is None:
                # Check if Select Tool is active (not Draw/Erase/Tie/Slur)
                if self._tool is self._select_tool:
                    # No Shift/Alt modifiers (those are for range select)
                    if not (mods & Qt.KeyboardModifier.ShiftModifier) and not (mods & Qt.KeyboardModifier.AltModifier):
                        # Start lasso selection
                        try:
                            self._start_lasso_selection(event.pos(), mods)
                            return
                        except Exception:
                            pass

            # Route click to tools:
            # - Right-click defaults to erase tool
            # - Left-click supports a professionelle "armed" connection overlay
            #   (Tie/Slur can be active while Pencil stays active)
            tool = None
            if btn == Qt.MouseButton.RightButton:
                tool = self._erase_tool
            else:
                # Modifier shortcuts (v0.0.20.455):
                # Shift+Click = Sharp note (Cis, Dis, Fis...) → DrawTool handles it
                # Alt+Click = Flat note (Des, Es, Ges...) → DrawTool handles it
                # Ctrl+Shift+Click = Tie (Haltebogen)
                # Ctrl+Alt+Click = Slur (Bindebogen)
                if (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.ShiftModifier):
                    tool = self._tie_tool
                elif (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.AltModifier):
                    tool = self._slur_tool
                else:
                    # If a 2-click connection is already pending, keep routing
                    # clicks to the corresponding tool so users can complete
                    # or cancel the action without creating accidental notes.
                    pend = getattr(self, "_pending_connection", None)
                    if pend:
                        try:
                            kind = str(pend.get("kind", ""))
                        except Exception:
                            kind = ""
                        tool = self._tie_tool if kind == "tie" else self._slur_tool
                    else:
                        # Armed overlay mode: only engage on clicks near an
                        # existing note. This way Pencil can remain active and
                        # still draw notes in empty space.
                        # Ctrl+Click forces the primary tool even near notes.
                        force_primary = bool(mods & Qt.KeyboardModifier.ControlModifier)
                        if (not force_primary) and self._connection_mode in ("tie", "slur"):
                            near_note = False
                            try:
                                near_note = self.pick_note_at(scene_pos) is not None
                            except Exception:
                                near_note = False
                            if near_note:
                                tool = self._tie_tool if self._connection_mode == "tie" else self._slur_tool
                            else:
                                tool = self._tool
                        else:
                            tool = self._tool
            res = tool.handle_mouse_press(self, scene_pos, btn, mods)
            if getattr(res, "status", ""):
                try:
                    self._project_service.status.emit(str(res.status))
                except Exception:
                    pass
            if getattr(res, "changed", False):
                self.refresh()
                return
        except Exception:
            # Never break mouse input on errors.
            pass

        super().mousePressEvent(event)



    def keyPressEvent(self, event):  # noqa: N802 (Qt API)
        """Keyboard shortcuts.

        Implements DAW-friendly shortcuts for Notation:
        - D / S / E: Draw / Select / Erase tool
        - Ctrl+C / Ctrl+V / Ctrl+X: Copy / Paste / Cut (supports multi-note selection)
        - Ctrl+Z: Undo (ProjectService)
        - Del / Backspace: Delete selected note(s)
        
        Selection (with S tool or Select mode):
        - Click: Select single note (clears previous)
        - Ctrl+Click: Toggle note in multi-selection
        - Shift+Click: Range select (from last selected to clicked)
        """
        try:
            key = event.key()
            mods = event.modifiers()
        except Exception:
            return super().keyPressEvent(event)

        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # Tool switches (no Ctrl)
        if not ctrl:
            if key == Qt.Key.Key_D:
                self.set_active_tool("draw")
                return
            if key == Qt.Key.Key_S:
                self.set_active_tool("select")
                return
            if key == Qt.Key.Key_E:
                # Enable Erase as left-click tool (right-click erase stays available)
                self._tool = self._erase_tool
                try:
                    self._project_service.status.emit("Notation Tool: Erase")
                except Exception:
                    pass
                return

            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                if self._delete_selected_marks() or self._delete_selected_note():
                    return

        # Ctrl shortcuts
        if ctrl:
            if key == Qt.Key.Key_Z:
                try:
                    self._project_service.undo()
                    self.refresh()
                except Exception:
                    pass
                return

            if key == Qt.Key.Key_C:
                if self._copy_selected_note():
                    return

            if key == Qt.Key.Key_X:
                if self._cut_selected_note():
                    return

            if key == Qt.Key.Key_V:
                if self._paste_clipboard_note():
                    return

        return super().keyPressEvent(event)


    # ------------------------------------------------------------------
    # Context Menu (Task 11)
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event):  # noqa: N802 (Qt API)
        """professionelles context menu (v0.0.20.445).

        - **Right click on empty space** → full notation context menu
        - **Right click on a note** → erase (existing behavior, Task 5)
        - **Ctrl + Right click anywhere** → always open context menu
        """
        try:
            mods = event.modifiers()
        except Exception:
            mods = Qt.KeyboardModifier.NoModifier

        force_menu = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # Check if we clicked on a note item
        clicked_on_note = False
        if not force_menu:
            try:
                items = self.items(event.pos())
                for it in items:
                    try:
                        if it.data(1) == "note" or isinstance(it, _NoteItem):
                            clicked_on_note = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # Right-click on note without Ctrl → erase (existing behavior)
        if clicked_on_note and not force_menu:
            try:
                event.ignore()
            except Exception:
                pass
            return

        # Open the full context menu
        try:
            scene_pos = self.mapToScene(event.pos())
        except Exception:
            scene_pos = None

        try:
            global_pos = event.globalPos()
        except Exception:
            try:
                global_pos = event.globalPosition().toPoint()
            except Exception:
                global_pos = QCursor.pos()

        def _open() -> None:
            try:
                self._open_context_menu(scene_pos, global_pos)
            except Exception:
                pass

        try:
            QTimer.singleShot(0, _open)
            event.accept()
        except Exception:
            pass

    def _open_context_menu(self, scene_pos, global_pos) -> None:
        """professionelles comprehensive notation context menu (v0.0.20.445).

        Organized like professionellen Notations-Editor Paletten:
        - Notenwerte (note values)
        - Pausen (rests)
        - Vorzeichen (accidentals)
        - Tuplets (tuplets/irregular groups)
        - Artikulation (articulations)
        - Dynamik (dynamics)
        - Ornamente (ornaments)
        - Spielanweisungen (performance directions)
        - Struktur/Navigation (structural marks)
        - Bögen/Verbindungen (ties/slurs)
        - Werkzeuge (tools)
        - Sonstiges (misc)
        """
        try:
            menu = QMenu(self)

            def _emit_status(msg: str) -> None:
                try:
                    self._project_service.status.emit(str(msg))
                except Exception:
                    pass

            def _beat_from_scene() -> float:
                if scene_pos is None:
                    return 0.0
                try:
                    b = self.scene_x_to_beat(float(scene_pos.x()))
                except Exception:
                    b = 0.0
                try:
                    snap_div = str(getattr(self._project_service.ctx.project, "snap_division", "1/16") or "1/16")
                    snap = snap_beats_from_div(snap_div)
                    return max(0.0, snap_to_grid(float(b), float(snap)))
                except Exception:
                    return max(0.0, float(b))

            def _pitch_from_scene() -> int:
                if scene_pos is None:
                    return 60
                try:
                    # Use _pitch_to_staff_line inverse (approximate: staff bottom = E4 = 64)
                    spacing = float(self._style.line_distance)
                    half = spacing / 2.0
                    y_offset = float(self._layout.y_offset)
                    bottom_line_y = StaffRenderer.line_y(y_offset, self._style.lines - 1, self._style)
                    # staff_line = (bottom_line_y - y) / half  → approximate pitch
                    staff_line = (float(bottom_line_y) - float(scene_pos.y())) / half
                    # E4 = pitch 64 at staff_line 0
                    pitch = 64 + int(round(staff_line))
                    return max(0, min(127, pitch))
                except Exception:
                    return 60

            def _set_note_value(frac: str) -> None:
                try:
                    self.input_state.note_value = str(frac)
                    _emit_status(f"Notenwert: {frac}")
                except Exception:
                    pass

            def _set_accidental(acc: int) -> None:
                try:
                    self.input_state.accidental = int(acc)
                    _emit_status(f"Vorzeichen: {acc}")
                except Exception:
                    pass

            def _add_mark(mark_type: str, data: dict, label: str = "") -> None:
                if not self._clip_id:
                    _emit_status("Kein MIDI-Clip ausgewählt.")
                    return
                beat = _beat_from_scene()
                try:
                    if hasattr(self._project_service, "add_notation_mark"):
                        self._project_service.add_notation_mark(
                            str(self._clip_id), beat=float(beat),
                            mark_type=str(mark_type), data=dict(data),
                        )
                        self.refresh()
                        _emit_status(label or f"{mark_type} gesetzt bei Beat {beat:.2f}")
                except Exception:
                    pass

            # ============================================================
            # 🎵 NOTENWERTE (Note Values)
            # ============================================================
            sub_notes = menu.addMenu("🎵 Notenwerte")
            sub_notes.setToolTipsVisible(True)

            _note_defs = [
                ("𝅝  Ganze Note (1/1)", "1/1",
                 "Whole Note — dauert 4 Beats (ein ganzer 4/4-Takt). Shortcut: Alt+1"),
                ("𝅗𝅥  Halbe Note (1/2)", "1/2",
                 "Half Note — dauert 2 Beats (halber 4/4-Takt). Shortcut: Alt+2"),
                ("♩  Viertelnote (1/4)", "1/4",
                 "Quarter Note — dauert 1 Beat. Standard-Schlag in 4/4. Shortcut: Alt+3"),
                ("♪  Achtelnote (1/8)", "1/8",
                 "Eighth Note — dauert 1/2 Beat. Mit Fähnchen oder Balken. Shortcut: Alt+4"),
                ("𝅘𝅥𝅯  Sechzehntelnote (1/16)", "1/16",
                 "Sixteenth Note — dauert 1/4 Beat. Doppelbalken. Shortcut: Alt+5"),
                ("𝅘𝅥𝅰  Zweiunddreißigstelnote (1/32)", "1/32",
                 "32nd Note — dauert 1/8 Beat. Dreifachbalken."),
                ("𝅘𝅥𝅱  Vierundsechzigstelnote (1/64)", "1/64",
                 "64th Note — dauert 1/16 Beat. Vierfachbalken."),
            ]
            for label, frac, tip in _note_defs:
                a = sub_notes.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, f=frac: _set_note_value(f))

            sub_notes.addSeparator()

            a_dot = sub_notes.addAction("·  Punktiert (×1.5)")
            a_dot.setToolTip("Dotted — verlängert die Note um die Hälfte ihres Wertes.\n"
                             "Beispiel: Punktierte Viertel = 1.5 Beats.")
            a_dot.setCheckable(True)
            a_dot.setChecked(bool(getattr(self.input_state, "dotted", False)))
            a_dot.triggered.connect(lambda chk: setattr(self.input_state, "dotted", bool(chk)))

            a_ddot = sub_notes.addAction("··  Doppelt punktiert (×1.75)")
            a_ddot.setToolTip("Double Dotted — verlängert um 3/4 des Wertes.\n"
                              "Beispiel: Doppelt punktierte Viertel = 1.75 Beats.")
            a_ddot.triggered.connect(lambda: (
                setattr(self.input_state, "dotted", True),
                _emit_status("Doppelt punktiert (×1.75) — Hinweis: MVP nutzt einfach punktiert")
            ))

            # ============================================================
            # ⏸ PAUSEN (Rests)
            # ============================================================
            sub_rests = menu.addMenu("⏸ Pausen")
            sub_rests.setToolTipsVisible(True)

            _rest_defs = [
                ("𝄻  Ganze Pause", 4.0,
                 "Whole Rest — Stille für einen ganzen 4/4-Takt (4 Beats)."),
                ("𝄼  Halbe Pause", 2.0,
                 "Half Rest — Stille für 2 Beats."),
                ("𝄽  Viertelpause", 1.0,
                 "Quarter Rest — Stille für 1 Beat."),
                ("𝄾  Achtelpause", 0.5,
                 "Eighth Rest — Stille für 1/2 Beat."),
                ("𝄿  Sechzehntelpause", 0.25,
                 "Sixteenth Rest — Stille für 1/4 Beat."),
                ("   Zweiunddreißigstelpause", 0.125,
                 "32nd Rest — Stille für 1/8 Beat."),
            ]
            for label, dur, tip in _rest_defs:
                a = sub_rests.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, d=dur: _add_mark(
                    "rest", {"duration_beats": float(d)}, f"Pause ({d} Beats) gesetzt"
                ))

            sub_rests.addSeparator()
            a_rest_mode = sub_rests.addAction("🔀  Eingabemodus Pausen (Y)")
            a_rest_mode.setToolTip("Taste Y — schaltet zwischen Noten- und Pausen-Eingabe um.\n"
                                   "Wenn aktiv, erzeugt der Stift Pausen statt Noten.")
            a_rest_mode.setCheckable(True)
            a_rest_mode.setChecked(bool(getattr(self.input_state, "is_rest", False)))
            a_rest_mode.triggered.connect(lambda chk: (
                setattr(self.input_state, "is_rest", bool(chk)),
                _emit_status("Pausenmodus: " + ("AN" if chk else "AUS"))
            ))

            # ============================================================
            # ♯♭ VORZEICHEN (Accidentals)
            # ============================================================
            sub_acc = menu.addMenu("♯♭ Vorzeichen")
            sub_acc.setToolTipsVisible(True)

            _acc_defs = [
                ("♯  Kreuz (Sharp)", 1,
                 "Sharp — erhöht die Note um einen Halbton.\n"
                 "Wird links neben den Notenkopf geschrieben."),
                ("♭  Be (Flat)", -1,
                 "Flat — erniedrigt die Note um einen Halbton.\n"
                 "Wird links neben den Notenkopf geschrieben."),
                ("♮  Auflöser (Natural)", 0,
                 "Natural — hebt ein vorheriges Vorzeichen auf.\n"
                 "Stellt die Stammtonstufe wieder her."),
                ("𝄪  Doppelkreuz (Double Sharp)", 2,
                 "Double Sharp — erhöht die Note um zwei Halbtöne.\n"
                 "Seltener, in modulierender Harmonik (z.B. F𝄪 = G)."),
                ("𝄫  Doppel-Be (Double Flat)", -2,
                 "Double Flat — erniedrigt die Note um zwei Halbtöne.\n"
                 "Seltener, in modulierender Harmonik (z.B. B𝄫 = A)."),
            ]
            for label, acc, tip in _acc_defs:
                a = sub_acc.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, v=acc: _set_accidental(v))

            # ============================================================
            # 🎶 TUPLETS / SONDERRHYTHMEN (r3n, r2n)
            # ============================================================
            sub_tup = menu.addMenu("🎶 Tuplets / Sonderrhythmen")
            sub_tup.setToolTipsVisible(True)

            _tup_defs = [
                ("₃  Triole (3:2)", "triplet", 3, 2,
                 "Triplet — 3 Noten im Raum von 2.\n"
                 "Häufigste irreguläre Teilung. Shortcut: Ctrl+3."),
                ("₂  Duole (2:3)", "duplet", 2, 3,
                 "Duplet — 2 Noten im Raum von 3.\n"
                 "In zusammengesetzten Taktarten (6/8, 9/8)."),
                ("₅  Quintole (5:4)", "quintuplet", 5, 4,
                 "Quintuplet — 5 Noten im Raum von 4.\n"
                 "Chopins Nocturnes, Debussy."),
                ("₆  Sextole (6:4)", "sextuplet", 6, 4,
                 "Sextuplet — 6 Noten im Raum von 4.\n"
                 "Doppel-Triole. Häufig in virtuosen Passagen."),
                ("₇  Septole (7:4)", "septuplet", 7, 4,
                 "Septuplet — 7 Noten im Raum von 4.\n"
                 "Seltener, in moderner Musik."),
            ]
            for label, name, num, denom, tip in _tup_defs:
                a = sub_tup.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, n=name, nu=num, de=denom: _add_mark(
                    "tuplet", {"tuplet_type": n, "numerator": nu, "denominator": de},
                    f"{n.title()} ({nu}:{de}) gesetzt"
                ))

            # ============================================================
            # 🎻 ARTIKULATION (Articulations)
            # ============================================================
            sub_art = menu.addMenu("🎻 Artikulation")
            sub_art.setToolTipsVisible(True)

            _art_defs = [
                ("·   Staccato", "staccato",
                 "Staccato — Note kurz und abgesetzt spielen.\n"
                 "Punkt über/unter dem Notenkopf. Ungefähr halbe Dauer."),
                (">   Akzent (Accent)", "accent",
                 "Accent — Note betont anschlagen.\n"
                 "Keilförmiges Zeichen > über/unter dem Notenkopf."),
                ("—   Tenuto", "tenuto",
                 "Tenuto — Note in voller Länge aushalten.\n"
                 "Waagerechter Strich über/unter dem Notenkopf."),
                ("^   Marcato", "marcato",
                 "Marcato — stark betont, stärker als Accent.\n"
                 "Offenes Dreieck ^ über dem Notenkopf."),
                ("𝄐   Fermata", "fermata",
                 "Fermata — Note aushalten (Interpret entscheidet Dauer).\n"
                 "Halbkreis mit Punkt. Stoppt den metrischen Fluss."),
                ("▾   Staccatissimo", "staccatissimo",
                 "Staccatissimo — extrem kurz spielen.\n"
                 "Keilförmiger Punkt. Kürzer als Staccato."),
                ("—·  Portato (Tenuto+Staccato)", "portato",
                 "Portato / Louré — leicht getrennt aber gewichtet.\n"
                 "Kombination: Strich + Punkt. 'Zwischen Legato und Staccato'."),
                ("⌵   Downbow (Abstrich)", "downbow",
                 "Downbow — Streichinstrument: Bogen abwärts führen.\n"
                 "V-förmiges Zeichen. Ergibt natürlichen Akzent."),
                ("∨   Upbow (Aufstrich)", "upbow",
                 "Upbow — Streichinstrument: Bogen aufwärts führen.\n"
                 "V-förmiges Zeichen, umgekehrt."),
                ("+   Pizzicato (linke Hand)", "pizzicato_lh",
                 "Left-hand Pizzicato — Saite mit Greifhand zupfen.\n"
                 "Plus-Zeichen über der Note."),
                ("○   Flageolett (Harmonics)", "harmonics",
                 "Natural Harmonic — Oberton durch leichtes Berühren.\n"
                 "Kleiner Kreis über dem Notenkopf."),
            ]
            for label, art_type, tip in _art_defs:
                a = sub_art.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, t=art_type: _add_mark(
                    "articulation", {"articulation": t, "pitch": _pitch_from_scene()},
                    f"Artikulation: {t}"
                ))

            # ============================================================
            # 🎼 DYNAMIK (Dynamics)
            # ============================================================
            sub_dyn = menu.addMenu("🎼 Dynamik")
            sub_dyn.setToolTipsVisible(True)

            _dyn_defs = [
                ("𝆏𝆏𝆏  ppp (Pianississimo)", "ppp", 16,
                 "Pianississimo — so leise wie möglich.\n"
                 "MIDI Velocity ca. 16. Extremste Stille."),
                ("𝆏𝆏   pp (Pianissimo)", "pp", 33,
                 "Pianissimo — sehr leise.\n"
                 "MIDI Velocity ca. 33. Flüstern."),
                ("𝆏    p (Piano)", "p", 49,
                 "Piano — leise.\n"
                 "MIDI Velocity ca. 49. Sanft."),
                ("𝆐𝆏   mp (Mezzopiano)", "mp", 64,
                 "Mezzopiano — mittleres Leise.\n"
                 "MIDI Velocity ca. 64. Comfortable."),
                ("𝆐𝆑   mf (Mezzoforte)", "mf", 80,
                 "Mezzoforte — mittleres Laut.\n"
                 "MIDI Velocity ca. 80. Häufigste Dynamikstufe."),
                ("𝆑    f (Forte)", "f", 96,
                 "Forte — laut.\n"
                 "MIDI Velocity ca. 96. Kräftig."),
                ("𝆑𝆑   ff (Fortissimo)", "ff", 112,
                 "Fortissimo — sehr laut.\n"
                 "MIDI Velocity ca. 112. Kraftvoll."),
                ("𝆑𝆑𝆑  fff (Fortississimo)", "fff", 127,
                 "Fortississimo — so laut wie möglich.\n"
                 "MIDI Velocity ca. 127. Maximum."),
            ]
            for label, dyn_name, vel, tip in _dyn_defs:
                a = sub_dyn.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, d=dyn_name, v=vel: _add_mark(
                    "dynamics", {"dynamic": d, "velocity": v}, f"Dynamik: {d}"
                ))

            sub_dyn.addSeparator()

            _dyn_special = [
                ("sf   Sforzando", "sf", 112,
                 "Sforzando — plötzlicher einzelner Akzent.\n"
                 "Abrupte Betonung, danach normal weiter."),
                ("sfz  Sforzato", "sfz", 120,
                 "Sforzato — stärker als sf.\n"
                 "Noch heftigerer plötzlicher Akzent."),
                ("fp   Fortepiano", "fp", 96,
                 "Fortepiano — laut anfangen, sofort leise.\n"
                 "Beethoven-typisch."),
                ("fz   Forzando", "fz", 110,
                 "Forzando — einzelner starker Akzent.\n"
                 "Ähnlich sf, etwas weniger gebräuchlich."),
            ]
            for label, dyn_name, vel, tip in _dyn_special:
                a = sub_dyn.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, d=dyn_name, v=vel: _add_mark(
                    "dynamics", {"dynamic": d, "velocity": v}, f"Dynamik: {d}"
                ))

            sub_dyn.addSeparator()

            a_cresc = sub_dyn.addAction("< Crescendo (Hairpin)")
            a_cresc.setToolTip("Crescendo — langsam lauter werden.\n"
                               "Öffnende Gabel <. Dauer je nach Kontext (Takt/Phrase).")
            a_cresc.triggered.connect(lambda: _add_mark(
                "hairpin", {"direction": "crescendo"}, "Crescendo-Gabel gesetzt"
            ))

            a_decresc = sub_dyn.addAction("> Decrescendo (Hairpin)")
            a_decresc.setToolTip("Decrescendo/Diminuendo — langsam leiser werden.\n"
                                 "Schließende Gabel >. Dauer je nach Kontext.")
            a_decresc.triggered.connect(lambda: _add_mark(
                "hairpin", {"direction": "decrescendo"}, "Decrescendo-Gabel gesetzt"
            ))

            # ============================================================
            # 🎵 ORNAMENTE (Ornaments)
            # ============================================================
            sub_orn = menu.addMenu("🎵 Ornamente")
            sub_orn.setToolTipsVisible(True)

            _orn_defs = [
                ("tr   Triller", "trill",
                 "Trill — schneller Wechsel zwischen Hauptton und oberer Nebennote.\n"
                 "Häufigster Verzierung. 'tr' über der Note."),
                ("𝆖   Mordent", "mordent",
                 "Mordent (unterer) — schneller Wechsel: Hauptton → untere Nebennote → Hauptton.\n"
                 "Zickzack-Zeichen mit Strich."),
                ("𝆗   Pralltriller (Inv. Mordent)", "pralltriller",
                 "Pralltriller / Inverted Mordent — Hauptton → obere Nebennote → Hauptton.\n"
                 "Zickzack-Zeichen ohne Strich. Schneller als Triller."),
                ("∽   Doppelschlag (Turn)", "turn",
                 "Turn / Doppelschlag — obere Nebennote → Hauptton → untere Nebennote → Hauptton.\n"
                 "S-förmiges Zeichen. Barock/Klassik Standard."),
                ("∾   Gruppetto (Inv. Turn)", "inverted_turn",
                 "Inverted Turn — umgekehrter Doppelschlag.\n"
                 "Untere → Haupt → Obere → Haupt. S-Zeichen umgekehrt."),
                ("𝆔   Schleifer (Slide)", "slide",
                 "Slide / Schleifer — Auftakt aus 2-3 schnellen Noten zur Hauptnote.\n"
                 "Kleine Noten ohne Balken zum Hauptton hin."),
                ("♪̃   Vorschlag (Grace Note)", "grace_note",
                 "Appoggiatura / Vorschlag — kleine Note vor der Hauptnote.\n"
                 "Kurz (Acciaccatura, durchgestrichen) oder lang (Appoggiatura)."),
                ("≋   Tremolo", "tremolo",
                 "Tremolo — schnelle Wiederholung des gleichen Tons.\n"
                 "Schrägstriche durch den Notenhals. 1-3 Striche = 8tel bis 32tel."),
                ("∿   Vibrato", "vibrato",
                 "Vibrato — leichte Tonhöhenschwankung.\n"
                 "Wellenförmiges Zeichen. Geschwindigkeit + Weite variabel."),
                ("↗   Glissando", "glissando",
                 "Glissando — gleitendes Portamento zwischen zwei Noten.\n"
                 "Wellenförmige oder gerade Linie zwischen den Noten."),
            ]
            for label, orn_type, tip in _orn_defs:
                a = sub_orn.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, t=orn_type: _add_mark(
                    "ornament", {"ornament": t, "pitch": _pitch_from_scene()},
                    f"Ornament: {t}"
                ))

            # ============================================================
            # 🎹 SPIELANWEISUNGEN (Performance Directions)
            # ============================================================
            sub_perf = menu.addMenu("🎹 Spielanweisungen")
            sub_perf.setToolTipsVisible(True)

            _perf_defs = [
                ("8va   Ottava alta", "8va",
                 "8va — eine Oktave höher spielen als notiert.\n"
                 "Gestrichelte Linie über den Noten. Vermeidet extreme Hilfslinien."),
                ("8vb   Ottava bassa", "8vb",
                 "8vb — eine Oktave tiefer spielen als notiert.\n"
                 "Gestrichelte Linie unter den Noten."),
                ("15ma  Quindicesima alta", "15ma",
                 "15ma — zwei Oktaven höher spielen.\n"
                 "Selten, für extreme Register."),
                ("Ped.  Pedal (Haltepedal)", "pedal_down",
                 "Sustain Pedal drücken — Ped. Zeichen.\n"
                 "Hält alle klingenden Töne. Klavier-Standard."),
                ("*     Pedal Auf", "pedal_up",
                 "Sustain Pedal loslassen — * (Stern) Zeichen.\n"
                 "Beendet den Pedalklang. Muss immer auf Ped. folgen."),
                ("🅄   Una Corda", "una_corda",
                 "Una Corda (linkes Pedal) — weicherer, gedämpfter Klang.\n"
                 "Klavier: verschiebt die Hämmer. 'u.c.' Zeichen."),
                ("🅃   Tre Corde", "tre_corde",
                 "Tre Corde — Una Corda aufheben.\n"
                 "Zurück zum normalen Klang. 't.c.' Zeichen."),
                ("'    Atemzeichen (Breath)", "breath",
                 "Atemzeichen / Breath Mark — kurze Pause zum Atmen.\n"
                 "Komma oder Häkchen. Für Bläser/Sänger essentiell."),
                (",    Cäsur", "caesura",
                 "Cäsur — Unterbrechung im musikalischen Fluss.\n"
                 "Zwei Schrägstriche //. Stärker als Atemzeichen."),
                ("arco  Arco (mit Bogen)", "arco",
                 "Arco — mit dem Bogen spielen (Streicher).\n"
                 "Aufhebung von Pizzicato."),
                ("pizz. Pizzicato (gezupft)", "pizzicato",
                 "Pizzicato — Saiten zupfen statt streichen.\n"
                 "'pizz.' über der Note."),
                ("con sord.  Con Sordino", "con_sordino",
                 "Con Sordino — mit Dämpfer spielen.\n"
                 "Gedämpfter, weicherer Klang."),
                ("senza sord.  Senza Sordino", "senza_sordino",
                 "Senza Sordino — ohne Dämpfer.\n"
                 "Aufhebung von con sordino."),
            ]
            for label, perf_type, tip in _perf_defs:
                a = sub_perf.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, t=perf_type: _add_mark(
                    "performance", {"direction": t}, f"Spielanweisung: {t}"
                ))

            # ============================================================
            # 📐 STRUKTUR / NAVIGATION
            # ============================================================
            sub_struct = menu.addMenu("📐 Struktur / Navigation")
            sub_struct.setToolTipsVisible(True)

            _struct_defs = [
                ("𝄋   Segno", "segno",
                 "Segno — Markiert eine Stelle für 'Dal Segno' (D.S.).\n"
                 "S-förmiges Zeichen mit Schrägstrich."),
                ("𝄌   Coda", "coda",
                 "Coda — Markiert den Schluss-Abschnitt.\n"
                 "Kreuz im Kreis. Sprungziel für 'al Coda'."),
                ("D.C.  Da Capo", "da_capo",
                 "Da Capo — von vorn wiederholen.\n"
                 "Zurück zum Anfang des Stücks."),
                ("D.S.  Dal Segno", "dal_segno",
                 "Dal Segno — zum Segno-Zeichen zurück.\n"
                 "Wiederholung ab dem 𝄋 Zeichen."),
                ("D.S. al Coda", "ds_al_coda",
                 "Dal Segno al Coda — zum Segno, dann bei 'al Coda' zur Coda springen.\n"
                 "Häufigste Navigationsanweisung in Pop/Jazz."),
                ("D.C. al Fine", "dc_al_fine",
                 "Da Capo al Fine — von vorn bis 'Fine'.\n"
                 "Wiederholung des Anfangs bis zur Fine-Markierung."),
                ("Fine  Ende", "fine",
                 "Fine — Ende der Komposition (bei D.C./D.S.).\n"
                 "Markiert wo die Wiederholung enden soll."),
                ("𝄆   Wiederholungszeichen (Anfang)", "repeat_start",
                 "Repeat Start — Beginn eines Wiederholungsabschnitts.\n"
                 "Doppelstrich mit zwei Punkten links."),
                ("𝄇   Wiederholungszeichen (Ende)", "repeat_end",
                 "Repeat End — Ende eines Wiederholungsabschnitts.\n"
                 "Doppelstrich mit zwei Punkten rechts."),
                ("1.    Erste Klammer (Volta 1)", "volta_1",
                 "Prima Volta — 1. Durchgang der Wiederholung.\n"
                 "Klammer mit '1.' über den Noten."),
                ("2.    Zweite Klammer (Volta 2)", "volta_2",
                 "Seconda Volta — 2. Durchgang.\n"
                 "Klammer mit '2.' über den Noten."),
            ]
            for label, struct_type, tip in _struct_defs:
                a = sub_struct.addAction(label)
                a.setToolTip(tip)
                a.triggered.connect(lambda checked=False, t=struct_type: _add_mark(
                    "structure", {"structure": t}, f"Struktur: {t}"
                ))

            # ============================================================
            # ⌒∿ BÖGEN / VERBINDUNGEN (Ties, Slurs, Connections)
            # ============================================================
            sub_conn = menu.addMenu("⌒∿ Bögen / Verbindungen")
            sub_conn.setToolTipsVisible(True)

            a_tie = sub_conn.addAction("⌒  Haltebogen (Tie)")
            a_tie.setToolTip("Tie / Haltebogen — verbindet zwei Noten gleicher Tonhöhe.\n"
                             "Die zweite Note wird nicht neu angeschlagen, nur gehalten.\n"
                             "Klicke: 1. Startnote → 2. Endnote (gleiche Tonhöhe!).")
            a_tie.triggered.connect(lambda: (
                self.set_connection_mode("tie"),
                _emit_status("Tie/Haltebogen: Klicke Start- und Endnote")
            ))

            a_slur = sub_conn.addAction("∿  Bindebogen (Slur)")
            a_slur.setToolTip("Slur / Bindebogen — verbindet verschiedene Noten zu einer Phrase.\n"
                              "Legato: Alle Noten unter dem Bogen gebunden spielen.\n"
                              "Klicke: 1. Startnote → 2. Endnote.")
            a_slur.triggered.connect(lambda: (
                self.set_connection_mode("slur"),
                _emit_status("Slur/Bindebogen: Klicke Start- und Endnote")
            ))

            a_phrase = sub_conn.addAction("⏜  Phrasierungsbogen")
            a_phrase.setToolTip("Phrasing Slur — größerer Bogen über eine ganze Phrase.\n"
                                "Zeigt musikalische Phrasenstruktur an.\n"
                                "Größer/weiter als ein normaler Bindebogen.")
            a_phrase.triggered.connect(lambda: _add_mark(
                "phrasing", {}, "Phrasierungsbogen (MVP: als Marker gesetzt)"
            ))

            # ============================================================
            # 🔧 WERKZEUGE (Tools)
            # ============================================================
            menu.addSeparator()
            sub_tools = menu.addMenu("🔧 Werkzeuge")

            act_draw = sub_tools.addAction("✎  Stift (Draw)")
            act_draw.setToolTip("Zeichenwerkzeug — Noten per Klick setzen.")
            act_draw.triggered.connect(lambda: (self.set_active_tool("draw"), _emit_status("Tool: Draw")))

            act_select = sub_tools.addAction("⬚  Auswahl (Select)")
            act_select.setToolTip("Auswahlwerkzeug — Noten anklicken/auswählen.\nShift+Klick = Multi-Select.")
            act_select.triggered.connect(lambda: (self.set_active_tool("select"), _emit_status("Tool: Select")))

            act_erase = sub_tools.addAction("✖  Löschen (Erase)")
            act_erase.setToolTip("Einzelne Note unter dem Cursor löschen.\n"
                                 "Tipp: Rechtsklick direkt auf eine Note löscht auch.")
            def _do_erase() -> None:
                if scene_pos is None:
                    return
                res = self._erase_tool.handle_mouse_press(
                    self, scene_pos, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
                if getattr(res, "changed", False):
                    self.refresh()
            act_erase.triggered.connect(_do_erase)

            act_clear = sub_tools.addAction("⨯  Auswahl aufheben")
            act_clear.setEnabled(self._selected_key is not None or len(self._selected_keys) > 0)
            act_clear.triggered.connect(lambda: (self.clear_selection(), self.refresh()))

            act_refresh = sub_tools.addAction("⟳  Neu rendern")
            act_refresh.triggered.connect(self.refresh)

            # ============================================================
            # 🗒 SONSTIGES (Misc)
            # ============================================================
            menu.addSeparator()

            act_add_note = menu.addAction("🗒  Editor-Notiz hinzufügen")
            act_add_note.setToolTip("Kommentar/Notiz an dieser Stelle einfügen.\n"
                                    "Wird über dem Notensystem als Text angezeigt.")
            def _do_add_editor_note() -> None:
                if not self._clip_id:
                    _emit_status("Kein MIDI-Clip ausgewählt.")
                    return
                try:
                    from PyQt6.QtWidgets import QInputDialog
                    text, ok = QInputDialog.getMultiLineText(self, "Editor-Notiz", "Notiztext:", "")
                    if not ok:
                        return
                    txt = str(text or "").strip()
                    if not txt:
                        return
                except Exception:
                    return
                _add_mark("comment", {"text": txt}, "Editor-Notiz hinzugefügt")
            act_add_note.triggered.connect(_do_add_editor_note)

            act_remove = menu.addAction("🗑  Markierungen hier entfernen")
            act_remove.setToolTip("Alle Notations-Markierungen an dieser Beat-Position löschen.\n"
                                  "(Artikulation, Dynamik, Ornamente, Kommentare etc.)")
            def _do_remove_marks_here() -> None:
                if not self._clip_id:
                    return
                beat = _beat_from_scene()
                try:
                    proj = getattr(getattr(self._project_service, "ctx", None), "project", None)
                    marks = getattr(proj, "notation_marks", []) or []
                except Exception:
                    marks = []
                if not isinstance(marks, list):
                    return
                try:
                    snap_div = str(getattr(self._project_service.ctx.project, "snap_division", "1/16") or "1/16")
                    snap = float(snap_beats_from_div(snap_div))
                except Exception:
                    snap = 0.25
                keep = [m for m in marks if not (
                    str(m.get("clip_id","")) == str(self._clip_id) and
                    abs(float(m.get("beat",0.0)) - float(beat)) <= (0.5 * snap)
                )]
                try:
                    proj.notation_marks = keep
                    self.refresh()
                    _emit_status("Markierungen entfernt.")
                except Exception:
                    pass
            act_remove.triggered.connect(_do_remove_marks_here)

            menu.addSeparator()
            act_about = menu.addAction("ℹ  Über Notations-Symbole...")
            act_about.setToolTip("Zeigt eine Kurzreferenz der verfügbaren Notations-Symbole.")
            def _show_about() -> None:
                try:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.information(self, "Notations-Symbole (Professionelles)",
                        "🎵 Notenwerte: Ganze (1/1) bis 64tel (1/64), punktiert, doppelt punktiert\n"
                        "⏸ Pausen: Ganze Pause bis 32tel-Pause, Pausenmodus (Y)\n"
                        "♯♭ Vorzeichen: Kreuz, Be, Auflöser, Doppelkreuz, Doppel-Be\n"
                        "🎶 Tuplets: Triole, Duole, Quintole, Sextole, Septole\n"
                        "🎻 Artikulation: Staccato, Akzent, Tenuto, Marcato, Fermata, ...\n"
                        "🎼 Dynamik: ppp bis fff, sf, sfz, fp, Crescendo/Decrescendo\n"
                        "🎵 Ornamente: Triller, Mordent, Pralltriller, Doppelschlag, Tremolo, ...\n"
                        "🎹 Spielanweisungen: 8va/8vb, Pedal, Atemzeichen, Arco/Pizzicato, ...\n"
                        "📐 Struktur: Segno, Coda, D.C., D.S., Fine, Wiederholungen, Volten\n"
                        "⌒∿ Bögen: Haltebogen (Tie), Bindebogen (Slur), Phrasierungsbogen\n\n"
                        "Tipp: Rechtsklick auf leeren Bereich = dieses Menü\n"
                        "Tipp: Rechtsklick auf eine Note = Note löschen\n"
                        "Tipp: Ctrl+Rechtsklick = immer dieses Menü öffnen\n\n"
                        "Professioneller Notations-Editor für ChronoScaleStudio")
                except Exception:
                    pass
            act_about.triggered.connect(_show_about)

            # Show menu
            try:
                menu.exec(global_pos)
            except Exception:
                menu.exec(QCursor.pos())
        except Exception:
            # Context menus must never crash the editor.
            return


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_clip(self, clip_id: str | None):
        """Set the active clip id whose notes should be rendered."""
        self._clip_id = str(clip_id) if clip_id else None
        # Reset selection when switching clips (prevents confusing highlight).
        self._selected_key = None
        self.refresh()


    # --- Live MIDI Ghost Noteheads (Input Monitoring) ------------------------

    def handle_live_note_on(self, clip_id: str, track_id: str, pitch: int,
                            velocity: int, channel: int, start_beats: float) -> None:
        """Show a transient ghost notehead for a live key press.

        This does NOT commit anything to the clip (commit happens on note-off
        in MidiManager). Ghost notes are kept per clip and re-rendered on refresh.
        """
        cid = str(clip_id or "")
        if not cid:
            return
        # store state
        try:
            tmp = MidiNote(pitch=int(pitch), start_beats=0.0, length_beats=1.0, velocity=int(velocity))
            _ = tmp.to_staff_position()
            acc = int(getattr(tmp, "accidental", 0))
        except Exception:
            acc = 0
        st = _LiveGhostState(
            pitch=int(pitch),
            velocity=int(velocity),
            channel=int(channel),
            start_beats=float(start_beats),
            accidental=int(acc),
        )
        self._live_ghost.setdefault(cid, []).append(st)

        # If this is the currently visible clip, draw it immediately.
        if self._clip_id and str(self._clip_id) == cid:
            try:
                self._add_live_ghost_item(st)
            except Exception:
                # fallback: next refresh will draw
                pass

    def handle_live_note_off(self, clip_id: str, track_id: str, pitch: int, channel: int) -> None:
        """Remove the transient ghost notehead for a released key."""
        cid = str(clip_id or "")
        if not cid:
            return
        lst = self._live_ghost.get(cid, [])
        # remove one matching entry (supports repeated notes)
        removed = False
        for i, st in enumerate(list(lst)):
            if int(getattr(st, "pitch", -1)) == int(pitch) and int(getattr(st, "channel", -1)) == int(channel):
                try:
                    lst.pop(i)
                except Exception:
                    pass
                removed = True
                break
        if not lst and cid in self._live_ghost:
            self._live_ghost.pop(cid, None)

        if self._clip_id and str(self._clip_id) == cid:
            if removed:
                self._remove_live_ghost_item(int(pitch), int(channel))
            else:
                # if we couldn't match, just clear & re-render
                self._render_live_ghost_notes()

    def handle_midi_panic(self, _reason: str = "") -> None:
        """Clear all live ghost notes (e.g. on transport stop / panic)."""
        self._live_ghost.clear()
        self._render_live_ghost_notes()

    def _remove_live_ghost_item(self, pitch: int, channel: int) -> None:
        sc = self.scene()
        remaining: list[_LiveGhostNoteItem] = []
        for it in list(self._live_ghost_items):
            try:
                # We encode pitch/channel into tooltip to avoid storing extra fields on the item.
                tip = str(it.toolTip() or "")
                if tip == f"live:{pitch}:{channel}":
                    sc.removeItem(it)
                    continue
            except Exception:
                pass
            remaining.append(it)
        self._live_ghost_items = remaining

    def _add_live_ghost_item(self, st: _LiveGhostState) -> None:
        x = self._beat_to_x(float(st.start_beats))
        line = self._pitch_to_staff_line(int(st.pitch))
        item = _LiveGhostNoteItem(
            x_center=float(x),
            line=int(line),
            accidental=int(getattr(st, "accidental", 0)),
            velocity=int(getattr(st, "velocity", 100)),
            y_offset=int(self._layout.y_offset),
            style=self._style,
        )
        try:
            item.setToolTip(f"live:{int(st.pitch)}:{int(st.channel)}")
        except Exception:
            pass
        self.scene().addItem(item)
        self._live_ghost_items.append(item)

    def _render_live_ghost_notes(self) -> None:
        """Render (or re-render) all live ghost noteheads for the current clip."""
        # remove current live items
        sc = self.scene()
        try:
            for it in list(self._live_ghost_items):
                try:
                    sc.removeItem(it)
                except Exception:
                    pass
        except Exception:
            pass
        self._live_ghost_items = []

        if not self._clip_id:
            return
        cid = str(self._clip_id)
        for st in list(self._live_ghost.get(cid, []) or []):
            try:
                self._add_live_ghost_item(st)
            except Exception:
                continue

    def refresh(self):
        """Re-render staff + notes for the current clip."""
        notes: list[MidiNote] = []
        if self._clip_id:
            try:
                notes = list(self._project_service.get_midi_notes(self._clip_id))
            except Exception:
                notes = []

        # Cache a lightweight signature so we can skip redundant refreshes.
        self._last_notes_sig = self._notes_signature(notes)

        # Update the scene width based on clip content (keep it stable and only grow).
        if notes:
            max_end = 0.0
            for n in notes:
                try:
                    max_end = max(max_end, float(n.start_beats) + float(n.length_beats))
                except Exception:
                    continue
            max_end = max(8.0, min(256.0, max_end))
            self._layout.max_beats = max(self._layout.max_beats, float(max_end) + 4.0)

        self._rebuild_scene_base()
        self._render_notes(notes)
        self._render_live_ghost_notes()
        self._render_notation_marks()
        self._update_scene_rect_from_content()
        # re-apply selection after rebuild (if we could match it)
        self._apply_selection_to_items()
        self.notes_changed.emit()

    # ------------------------------------------------------------------
    # Task 7: Bidirektionale MIDI-Sync helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _notes_signature(notes: list[MidiNote]) -> tuple:
        """Create a stable signature for MIDI notes.

        We avoid hashing whole dataclasses; instead we use the most relevant
        numeric fields with rounding. Order is preserved as stored.
        """

        sig = []
        for n in list(notes or []):
            try:
                sig.append(
                    (
                        int(getattr(n, "pitch", 0)),
                        round(float(getattr(n, "start_beats", 0.0)), 6),
                        round(float(getattr(n, "length_beats", 0.0)), 6),
                        int(getattr(n, "velocity", 100)),
                    )
                )
            except Exception:
                continue
        return tuple(sig)

    def _on_project_updated(self) -> None:
        """React to global project updates.

        - Avoid infinite refresh loops by allowing callers to suppress the next
          few updates (e.g. when the notation view writes MIDI notes).
        - Skip redundant refreshes if the active clip's notes are unchanged.
        """

        if self._suppress_project_updates > 0:
            self._suppress_project_updates = max(0, int(self._suppress_project_updates) - 1)
            return

        if not self._clip_id:
            # No active clip -> nothing meaningful to refresh.
            return

        try:
            notes = list(self._project_service.get_midi_notes(self._clip_id))
        except Exception:
            notes = []

        sig = self._notes_signature(notes)
        if sig == self._last_notes_sig:
            return

        self.refresh()

    def commit_notes_to_project(self, notes: list[MidiNote], *, label: str = "Edit MIDI (Notation)") -> None:
        """Commit a full notes list back to the ProjectService.

        This is the preferred way for future notation edit actions (drag/resize)
        because it creates a single Undo step and keeps UI sync predictable.

        Notes:
        - For MVP tools (Draw/Erase) we may still call ProjectService helpers
          directly. This method mainly provides the bidirectional sync
          infrastructure and recursion prevention requested in Task 7.
        """

        if not self._clip_id:
            return
        ps = self._project_service
        try:
            before = ps.snapshot_midi_notes(str(self._clip_id))
        except Exception:
            before = []

        # set_midi_notes() emits project_updated, commit_midi_notes_edit() emits
        # again; allow a small suppression budget.
        self._suppress_project_updates += 3

        try:
            ps.set_midi_notes(str(self._clip_id), list(notes or []))
        except Exception:
            return

        try:
            ps.commit_midi_notes_edit(str(self._clip_id), before, str(label or "Edit MIDI (Notation)"))
        except Exception:
            # Even if undo commit fails, keep UI consistent.
            try:
                ps._emit_updated()  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @staticmethod
    def _diatonic_index(line: int, octave: int) -> int:
        # line: C=0..B=6
        return int(octave) * 7 + int(line)

    def _pitch_to_staff_line(self, pitch: int) -> int:
        """Map MIDI pitch to staff half-step index (clef-aware, v0.0.20.447).

        Uses the clef's reference note and line to calculate the correct
        staff position. Falls back to treble (E4) if anything fails.
        """
        try:
            from pydaw.ui.notation.clef_dialog import pitch_to_staff_line as _clef_p2sl
            return _clef_p2sl(int(pitch), str(self._layout.clef_type))
        except Exception:
            pass
        # Fallback: original treble-only mapping
        try:
            tmp = MidiNote(pitch=int(pitch), start_beats=0.0, length_beats=1.0, velocity=100)
            line, octv = tmp.to_staff_position()
            diat = self._diatonic_index(line, octv)
            e4_ref = self._diatonic_index(2, 4)  # E4 (bottom line treble)
            return int(diat - e4_ref)
        except Exception:
            return 0

    def _beat_to_x(self, beat: float) -> float:
        return float(self._layout.left_margin) + float(beat) * float(self._layout.pixels_per_beat)



    def _update_scene_rect_from_content(self) -> None:
        """Grow the scene rect to include all items (notes, marks, ghost layers)."""
        try:
            sc = self.scene()
            br = sc.itemsBoundingRect()
            # Add padding so selection/glow isn't clipped.
            pad_x = 80.0
            pad_y = 120.0
            x0 = max(0.0, float(br.left()) - pad_x)
            # CRITICAL FIX: Allow negative Y for high notes (C8, C9) above staff!
            # Don't clamp to 0 - let scene rect include notes with negative Y coords
            y0 = float(br.top()) - pad_y
            w = float(br.width()) + pad_x * 2.0
            h = float(br.height()) + pad_y * 2.0
            # Ensure a minimum height for comfortable Y scrolling
            h = max(h, float(StaffRenderer.staff_height(self._style) + 260))
            sc.setSceneRect(QRectF(x0, y0, w, h))
        except Exception:
            pass

    def _rebuild_scene_base(self) -> None:
        sc = self.scene()
        sc.clear()
        self._note_items.clear()

        width_px = (
            float(self._layout.left_margin)
            + float(self._layout.right_margin)
            + float(self._layout.max_beats) * float(self._layout.pixels_per_beat)
        )

        self._staff_item = _StaffBackgroundItem(
            width_px, self._style, self._layout.y_offset,
            clef_type=str(self._layout.clef_type),
            time_sig_num=int(self._layout.time_sig_num),
            time_sig_denom=int(self._layout.time_sig_denom),
        )
        sc.addItem(self._staff_item)

        # --- Clef hover tooltip overlay (v0.0.20.448) ---
        # Invisible rect over the clef area so hovering shows the full tooltip.
        try:
            from pydaw.ui.notation.clef_dialog import get_clef
            cinfo = get_clef(str(self._layout.clef_type))
            staff_h = float(StaffRenderer.staff_height(self._style))
            clef_overlay = sc.addRect(
                QRectF(0, float(self._layout.y_offset) - 12, 50.0, staff_h + 24),
                QPen(Qt.PenStyle.NoPen),
                QBrush(Qt.BrushStyle.NoBrush),
            )
            clef_overlay.setZValue(20.0)  # above everything
            clef_overlay.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            clef_overlay.setToolTip(
                cinfo.tooltip + "\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Klick = Schlüssel ändern"
            )
        except Exception:
            pass

        # stable scene rect; keeps scrolling consistent
        h = StaffRenderer.staff_height(self._style) + 180
        sc.setSceneRect(QRectF(0, 0, width_px, float(h)))

        # small hint if no clip selected
        if not self._clip_id:
            hint = sc.addText("Kein MIDI-Clip ausgewählt.\nWähle im Arranger einen MIDI-Clip.")
            hint.setDefaultTextColor(Qt.GlobalColor.black)
            hint.setPos(20, self._layout.y_offset + StaffRenderer.staff_height(self._style) + 40)

    def _render_notes(self, notes: list[MidiNote]) -> None:
        """Render notes to the scene.
        
        Note: Ghost layers are rendered even if main clip is empty!
        """
        if not self._clip_id:
            return

        # Ghost Notes / Layered Editing: Render ghost layers BEFORE main notes
        # IMPORTANT: Render ghost layers even if main clip is empty!
        try:
            if hasattr(self, 'ghost_renderer') and hasattr(self, 'layer_manager'):
                self.ghost_renderer.render_ghost_layers(
                    self.scene(),
                    self.layer_manager,
                    self._layout,
                    self._style,
                )
        except Exception:
            pass

        # Early return if no main notes (after ghost rendering!)
        if not notes:
            return

        # Add main notes
        for n in notes:
            try:
                x = self._beat_to_x(float(n.start_beats))
                staff_line = self._pitch_to_staff_line(int(n.pitch))
            except Exception:
                continue

            selected = False
            try:
                selected = self._selected_key == self._note_key(n)
            except Exception:
                selected = False

            item = _NoteItem(
                n,
                x_center=float(x),
                staff_line=int(staff_line),
                y_offset=int(self._layout.y_offset),
                style=self._style,
                selected=bool(selected),
            )
            self.scene().addItem(item)
            self._note_items.append(item)


    def _render_notation_marks(self) -> None:
        """Render notation marks (sticky notes, rests, ornaments) for the active clip."""
        if not self._clip_id:
            return

        try:
            proj = getattr(getattr(self._project_service, "ctx", None), "project", None)
            marks = getattr(proj, "notation_marks", []) or []
        except Exception:
            marks = []

        if not isinstance(marks, list):
            return

        # Render marks for this clip only.
        for m in list(marks):
            try:
                if str(m.get("clip_id", "")) != str(self._clip_id):
                    continue
                beat = float(m.get("beat", 0.0))
                mtype = str(m.get("type", ""))
                data = dict(m.get("data", {}) or {})
                x = self._beat_to_x(beat)

                if mtype == "comment":
                    txt = str(data.get("text", "") or "")
                    it = _MarkItem(kind="comment", x=float(x), y=float(self._layout.y_offset) - 46, text=txt, mark_id=str(m.get("id","")))
                    self.scene().addItem(it)
                elif mtype == "rest":
                    dur = float(data.get("duration_beats", 0.25))
                    lab = format_rest_label(dur)
                    it = _MarkItem(kind="rest", x=float(x), y=float(self._layout.y_offset) + 12, text=lab, mark_id=str(m.get("id","")))
                    self.scene().addItem(it)
                elif mtype == "ornament":
                    orn = str(data.get("ornament","") or "")
                    pitch = int(data.get("pitch", 0) or 0)
                    staff_line = self._pitch_to_staff_line(pitch) if pitch else 0
                    y = float(self._layout.y_offset) + StaffRenderer.staff_y_from_halfsteps(staff_line, self._style)
                    lab = format_ornament_label(orn)
                    it = _MarkItem(kind="ornament", x=float(x)+10, y=float(y)-22, text=lab, mark_id=str(m.get("id","")))
                    self.scene().addItem(it)
                elif mtype in ("tie", "slur"):
                    try:
                        a = dict(data.get("from", {}) or {})
                        b = dict(data.get("to", {}) or {})
                        b1 = float(a.get("beat", 0.0))
                        p1 = int(a.get("pitch", 0) or 0)
                        b2 = float(b.get("beat", 0.0))
                        p2 = int(b.get("pitch", 0) or 0)
                        x1 = self._beat_to_x(b1)
                        x2 = self._beat_to_x(b2)
                        sl1 = self._pitch_to_staff_line(p1) if p1 else 0
                        sl2 = self._pitch_to_staff_line(p2) if p2 else 0
                        y1 = float(self._layout.y_offset) + StaffRenderer.staff_y_from_halfsteps(sl1, self._style)
                        y2 = float(self._layout.y_offset) + StaffRenderer.staff_y_from_halfsteps(sl2, self._style)
                        conn = _ConnectionItem(kind=str(mtype), x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2), mark_id=str(m.get("id","")))
                        # Keep connections behind selected notes but above staff.
                        try:
                            conn.setZValue(2.0)
                        except Exception:
                            pass
                        self.scene().addItem(conn)
                    except Exception:
                        pass
            except Exception:
                continue


    def _refresh_ghost_notes(self) -> None:
        """Refresh ghost notes when layer configuration changes."""
        try:
            if hasattr(self, 'ghost_renderer') and hasattr(self, 'layer_manager'):
                self.ghost_renderer.render_ghost_layers(
                    self.scene(),
                    self.layer_manager,
                    self._layout,
                    self._style,
                )
        except Exception:
            pass


class NotationWidget(QWidget):
    """A small tab-friendly wrapper around :class:`NotationView`."""

    status_message = pyqtSignal(str)
    record_toggled = pyqtSignal(bool)  # v0.0.20.449: MIDI live-record toggle

    def __init__(self, project_service, *, transport=None, editor_timeline=None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._project_service = project_service
        self._transport = transport
        self._editor_timeline = editor_timeline  # v0.0.20.613: Dual-Clock Phase E
        self._clip_id: str | None = None

        self._view = NotationView(project_service, parent=self)

        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 0)
        top.setSpacing(8)

        self._lbl = QLabel("Notation (MVP)")
        top.addWidget(self._lbl)
        top.addStretch(1)

        # Minimal tool switcher (keeps the MVP usable without shortcuts).
        btn_draw = QToolButton()
        btn_draw.setText("✎")
        btn_draw.setToolTip("Tool: Draw (Note zeichnen)")
        btn_draw.setCheckable(True)
        btn_draw.setChecked(True)
        top.addWidget(btn_draw)

        btn_select = QToolButton()
        btn_select.setText("⬚")
        btn_select.setToolTip("Tool: Select (Note auswählen)")
        btn_select.setCheckable(True)
        top.addWidget(btn_select)

        btn_tie = QToolButton()
        btn_tie.setText("⌒")
        btn_tie.setToolTip("Tool: Tie / Haltebogen (2 Klicks: Startnote → Endnote, gleiche Tonhöhe)")
        btn_tie.setCheckable(True)
        top.addWidget(btn_tie)

        btn_slur = QToolButton()
        btn_slur.setText("∿")
        btn_slur.setToolTip("Tool: Slur / Bindebogen (2 Klicks: Startnote → Endnote)")
        btn_slur.setCheckable(True)
        top.addWidget(btn_slur)

        # Clear visual indicator for the professionelle "armed" overlay.
        # This is important because connection mode does NOT replace the
        # primary tool (pencil can stay active).
        self._conn_indicator = QLabel("")
        try:
            self._conn_indicator.setMinimumWidth(120)
        except Exception:
            pass
        top.addWidget(self._conn_indicator)

        def _set_primary(name: str) -> None:
            # Primary tools are exclusive: Draw / Select.
            self._view.set_active_tool(name)
            btn_draw.setChecked(name == "draw")
            btn_select.setChecked(name == "select")

        def _set_connection(mode: str | None) -> None:
            # Connection mode is an overlay: can be enabled while Draw stays active.
            self._view.set_connection_mode(mode)
            btn_tie.setChecked(mode == "tie")
            btn_slur.setChecked(mode == "slur")
            # Update UI indicator text.
            try:
                if mode == "tie":
                    self._conn_indicator.setText("Tie armed")
                elif mode == "slur":
                    self._conn_indicator.setText("Slur armed")
                else:
                    self._conn_indicator.setText("")
            except Exception:
                pass

        btn_draw.clicked.connect(lambda: _set_primary("draw"))
        btn_select.clicked.connect(lambda: _set_primary("select"))

        def _toggle_tie() -> None:
            if btn_tie.isChecked():
                btn_slur.setChecked(False)
                _set_connection("tie")
            else:
                _set_connection(None)

        def _toggle_slur() -> None:
            if btn_slur.isChecked():
                btn_tie.setChecked(False)
                _set_connection("slur")
            else:
                _set_connection(None)

        # Extra guidance for the modifier workflow.
        try:
            btn_tie.setToolTip(
                "Tie / Haltebogen (2 Klicks: Startnote → Endnote, gleiche Tonhöhe)\n"
                "Overlay/Armed: bleibt aktiv, während der Stift aktiv bleibt.\n"
                "Momentary: Ctrl+Shift+Klick = Tie."
            )
            btn_slur.setToolTip(
                "Slur / Bindebogen (2 Klicks: Startnote → Endnote)\n"
                "Overlay/Armed: bleibt aktiv, während der Stift aktiv bleibt.\n"
                "Momentary: Ctrl+Alt+Klick = Slur."
            )
        except Exception:
            pass

        btn_tie.clicked.connect(_toggle_tie)
        btn_slur.clicked.connect(_toggle_slur)

        # --- Clef button (v0.0.20.447) ---
        top.addSpacing(8)
        self._btn_clef = QToolButton()
        self._btn_clef.setText("𝄞")
        self._btn_clef.setToolTip(
            "Schlüssel ändern (Klick zum Öffnen)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Verfügbare Schlüssel:\n"
            "𝄞 Violinschlüssel (G) — G4, Linie 2 von unten\n"
            "𝄢 Bassschlüssel (F) — F3, Linie 4 von unten\n"
            "𝄡 Altschlüssel (C3) — C4, Mittlere Linie\n"
            "𝄡 Tenorschlüssel (C4) — C4, Linie 4 von unten\n"
            "𝄡 Sopranschlüssel (C1) — C4, Linie 1 von unten\n"
            "𝄡 Mezzosopran (C2) — C4, Linie 2 von unten\n"
            "𝄡 Bariton (C5/F3) — variabel\n"
            "𝄞⁸ +8va / 𝄞₈ -8vb Varianten — oktaviert\n\n"
            "Tipp: Auch direkt auf den Schlüssel im Notensystem klicken!"
        )
        self._btn_clef.setFixedSize(32, 28)
        font_clef = self._btn_clef.font()
        font_clef.setPointSize(16)
        self._btn_clef.setFont(font_clef)
        self._btn_clef.clicked.connect(self._view._open_clef_dialog)
        top.addWidget(self._btn_clef)

        btn_refresh = QToolButton()
        btn_refresh.setText("⟳")
        btn_refresh.setToolTip("Neu rendern")
        btn_refresh.clicked.connect(self._view.refresh)
        top.addWidget(btn_refresh)

        # --- Zoom buttons (v0.0.20.445, Arranger-Style) ---
        top.addSpacing(12)

        btn_zoom_in = QToolButton()
        btn_zoom_in.setText("+")
        btn_zoom_in.setToolTip("Zoom In (Ctrl++ oder Ctrl+Mausrad)")
        btn_zoom_in.setFixedSize(28, 28)
        btn_zoom_in.clicked.connect(lambda: (self._view._set_x_zoom(1.25), self._refresh_zoom_label()))
        top.addWidget(btn_zoom_in)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setText("−")
        btn_zoom_out.setToolTip("Zoom Out (Ctrl+- oder Ctrl+Mausrad)")
        btn_zoom_out.setFixedSize(28, 28)
        btn_zoom_out.clicked.connect(lambda: (self._view._set_x_zoom(1.0 / 1.25), self._refresh_zoom_label()))
        top.addWidget(btn_zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(42)
        self._zoom_label.setToolTip("Zoom-Level (Ctrl+0 = Reset)")
        top.addWidget(self._zoom_label)

        btn_zoom_reset = QToolButton()
        btn_zoom_reset.setText("⊙")
        btn_zoom_reset.setToolTip("Zoom Reset (Ctrl+0)")
        btn_zoom_reset.clicked.connect(lambda: (self._view._reset_zoom(), self._refresh_zoom_label()))
        top.addWidget(btn_zoom_reset)

        # v0.0.20.535: Follow Playhead button (Bitwig-Style auto-scroll)
        top.addSpacing(8)
        self._btn_follow = QToolButton()
        self._btn_follow.setText("▶ Follow")
        self._btn_follow.setCheckable(True)
        self._btn_follow.setChecked(False)
        self._btn_follow.setFixedHeight(28)
        self._btn_follow.setToolTip(
            "Follow Playhead — automatischer Scroll\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Wenn aktiviert:\n"
            "• Notation scrollt automatisch mit dem Playhead\n"
            "• Wenn Playhead 80% erreicht → Sprung auf 20%\n"
            "• Klick ins Lineal = Playhead setzen (Seek)"
        )
        self._btn_follow.setStyleSheet(
            "QToolButton:checked { background: #1976d2; color: white; font-weight: bold; border-radius: 4px; padding: 2px 8px; }"
            "QToolButton { padding: 2px 8px; }"
        )
        self._btn_follow.toggled.connect(self._on_follow_toggled)
        top.addWidget(self._btn_follow)

        # --- Record button (v0.0.20.449, wie im Piano Roll) ---
        top.addSpacing(12)

        self._btn_record = QToolButton()
        self._btn_record.setText("Record")
        self._btn_record.setCheckable(True)
        self._btn_record.setChecked(False)
        self._btn_record.setToolTip(
            "MIDI Record — Live-Aufnahme in den aktiven Clip\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Wenn aktiviert:\n"
            "• MIDI-Keyboard-Eingaben werden als Noten\n"
            "  in den aktuellen Clip geschrieben\n"
            "• Transport muss laufen (Play drücken)\n"
            "• Noten werden in Echtzeit aufgezeichnet\n\n"
            "Gleiche Funktion wie Record im Piano Roll.\n"
            "Beide teilen den selben MIDI-Record-Pfad."
        )
        self._btn_record.setStyleSheet(
            "QToolButton:checked { background: #cc3333; color: white; font-weight: bold; }"
        )
        self._btn_record.toggled.connect(self._on_record_toggled)
        top.addWidget(self._btn_record)

        # --- ❓ Help button (v0.0.20.455) ---
        btn_help = QToolButton()
        btn_help.setText("?")
        btn_help.setFixedSize(24, 24)
        btn_help.setToolTip("Bedienungshilfe anzeigen")
        btn_help.clicked.connect(self._show_help)
        top.addWidget(btn_help)

        # --- Transport → Playhead wiring (v0.0.20.445) ---
        # v0.0.20.613: Dual-Clock Phase E — Adapter hat Vorrang
        if self._editor_timeline is not None:
            try:
                self._editor_timeline.playhead_changed.connect(self._on_playhead_changed)
            except Exception:
                pass
        elif self._transport is not None:
            try:
                self._transport.playhead_changed.connect(self._on_playhead_changed)
            except Exception:
                pass
        # v0.0.20.535: Pass transport to view for click-to-seek (immer, unabhängig vom Adapter)
        if self._transport is not None:
            try:
                self._view.set_transport(self._transport)
            except Exception:
                pass


        # professionelle notation input palette (note values, dotted, rests, accidentals, ornaments, editor-notes)
        self._palette = NotationPalette(self)
        self._palette.state_changed.connect(self._view.set_input_state)
        # push initial state
        try:
            self._view.set_input_state(self._palette.state())
        except Exception:
            pass

        # Optional: editor notes quick button -> anchors at last mouse position (or beat 0)
        self._palette.enable_editor_notes_button(True)

        def _add_editor_note_from_palette() -> None:
            try:
                from PyQt6.QtWidgets import QInputDialog
                txt, ok = QInputDialog.getMultiLineText(self, "Editor-Notiz", "Notiztext:", "")
                if not ok:
                    return
                msg = str(txt or "").strip()
                if not msg:
                    return
            except Exception:
                return
            # anchor at last hover position
            try:
                scene_pos = getattr(self._view, "_last_mouse_scene_pos", None)
                if scene_pos is None:
                    beat = 0.0
                else:
                    beat = float(self._view.scene_x_to_beat(float(scene_pos.x())))
                # snap to grid
                snap_div = str(getattr(self._project_service.ctx.project, "snap_division", "1/16") or "1/16")
                snap = float(snap_beats_from_div(snap_div))
                beat = max(0.0, snap_to_grid(float(beat), float(snap)))
            except Exception:
                beat = 0.0
            try:
                if getattr(self._view, "clip_id", None) and hasattr(self._project_service, "add_notation_mark"):
                    self._project_service.add_notation_mark(str(self._view.clip_id), beat=float(beat), mark_type="comment", data={"text": msg})
                    self._view.refresh()
            except Exception:
                pass

        try:
            self._palette.editor_notes_button().clicked.connect(_add_editor_note_from_palette)
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addLayout(top)
        root.addWidget(self._palette)
        root.addWidget(self._view, 1)

        # Permanent usage hint bar (v0.0.20.455)
        self._hint_label = QLabel(
            "💡 Klick = Note setzen  |  Shift+Klick = ♯ Kreuz (Cis, Dis, Fis...)  |  "
            "Alt+Klick = ♭ Be (Des, Es, Ges...)  |  Rechtsklick = Menü  |  "
            "F1 = alle Shortcuts"
        )
        self._hint_label.setStyleSheet(
            "color: #888; font-size: 8pt; padding: 2px 6px; "
            "border-top: 1px solid #444;"
        )
        root.addWidget(self._hint_label)

        # Ghost Notes / Layered Editing: Layer Panel
        from pydaw.ui.layer_panel import LayerPanel
        self.layer_panel = LayerPanel(self._view.layer_manager)
        self.layer_panel.setMaximumHeight(200)  # Collapsible panel height
        self.layer_panel.layer_added.connect(self._on_add_ghost_layer)  # Connect signal
        root.addWidget(self.layer_panel)

        # Keep label in sync
        self._view.notes_changed.connect(self._update_label)

        # --- Task 7: Bidirektionale MIDI-Sync (Clip-Selection) ---
        # If the host DAW selects a clip (Arranger/PianoRoll), follow it automatically.
        # Only MIDI clips are shown; selecting an audio clip clears the notation view.
        try:
            self._project_service.active_clip_changed.connect(self._on_active_clip_changed)
        except Exception:
            pass
        try:
            self._project_service.clip_selected.connect(self._on_active_clip_changed)
        except Exception:
            pass

        # Initial sync (if the project already has a selected clip)
        try:
            cid = str(getattr(self._project_service, "active_clip_id", "") or "")
            if cid:
                self._on_active_clip_changed(cid)
        except Exception:
            pass

    def _on_active_clip_changed(self, clip_id: str) -> None:
        cid = str(clip_id or "").strip()
        if not cid:
            self.set_clip(None)
            return

        # Only show MIDI clips.
        try:
            clip = next((c for c in self._project_service.ctx.project.clips if str(getattr(c, "id", "")) == cid), None)
        except Exception:
            clip = None

        if not clip or str(getattr(clip, "kind", "")) != "midi":
            self.set_clip(None)
            return

        self.set_clip(cid)

    def set_clip(self, clip_id: str | None) -> None:
        self._clip_id = str(clip_id) if clip_id else None
        self._view.set_clip(self._clip_id)
        self._update_label()


    # --- Live MIDI Ghost Noteheads (forward to view) -------------------------

    def handle_live_note_on(self, clip_id: str, track_id: str, pitch: int,
                            velocity: int, channel: int, start_beats: float) -> None:
        try:
            self._view.handle_live_note_on(str(clip_id), str(track_id), int(pitch),
                                           int(velocity), int(channel), float(start_beats))
        except Exception:
            pass

    def handle_live_note_off(self, clip_id: str, track_id: str, pitch: int, channel: int) -> None:
        try:
            self._view.handle_live_note_off(str(clip_id), str(track_id), int(pitch), int(channel))
        except Exception:
            pass

    def handle_midi_panic(self, reason: str = "") -> None:
        try:
            self._view.handle_midi_panic(str(reason))
        except Exception:
            pass

    def _update_label(self) -> None:
        if self._clip_id:
            self._lbl.setText(f"Notation (MVP) – Clip: {self._clip_id}")
        else:
            self._lbl.setText("Notation (MVP)")

    def _on_playhead_changed(self, beat: float) -> None:
        """Forward transport playhead to the notation view."""
        try:
            self._view.set_playhead_beat(float(beat))
        except Exception:
            pass
        self._refresh_zoom_label()

    def _on_follow_toggled(self, checked: bool) -> None:
        """v0.0.20.535: Toggle Follow Playhead auto-scroll."""
        try:
            self._view.set_follow_playhead(bool(checked))
        except Exception:
            pass

    def _refresh_zoom_label(self) -> None:
        """Update the zoom percentage label from current ppb."""
        try:
            pct = int(round(float(self._view._layout.pixels_per_beat) / float(self._view._default_ppb) * 100.0))
            self._zoom_label.setText(f"{pct}%")
        except Exception:
            pass

    def _on_record_toggled(self, checked: bool) -> None:
        """Forward record toggle to the signal (v0.0.20.449)."""
        try:
            self.record_toggled.emit(bool(checked))
        except Exception:
            pass
        try:
            state = "AN" if checked else "AUS"
            self.status_message.emit(f"Notation Record: {state}")
        except Exception:
            pass

    def _show_help(self) -> None:
        """Show notation editor help dialog (v0.0.20.455)."""
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Notation-Editor — Bedienung",
                "🎵 Noten setzen (Draw-Modus)\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Klick                  → Natürliche Note (C, D, E, F, G, A, H)\n"
                "Shift+Klick            → Kreuz ♯ (Cis, Dis, Fis, Gis, Ais)\n"
                "Alt+Klick              → Be ♭ (Des, Es, Ges, As, B)\n"
                "Palette ♯/♭ Button     → Vorzeichen dauerhaft an/aus\n\n"
                "🔍 Zoom & Navigation\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Mausrad                → Vertikal scrollen\n"
                "Shift+Mausrad          → Horizontal scrollen\n"
                "Ctrl+Mausrad           → Zoom (Zeit-Achse)\n"
                "Ctrl+Shift+Mausrad     → Zoom (Notenzeilen)\n"
                "+/− Buttons            → Zoom in/out\n"
                "Ctrl+0                 → Zoom Reset\n\n"
                "📋 Kontextmenü\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Rechtsklick (leerer Bereich) → Alle Notations-Symbole\n"
                "    (Artikulation, Dynamik, Ornamente, Spielanweisungen,\n"
                "     Struktur, Tuplets, Pausen, Vorzeichen...)\n"
                "Rechtsklick (auf Note)       → Note löschen\n"
                "Ctrl+Rechtsklick             → Menü erzwingen\n\n"
                "🎼 Schlüssel & Taktart\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Klick auf 𝄞 (im Notensystem) → Schlüssel wechseln\n"
                "𝄞 Button (Toolbar)           → Schlüssel-Dialog\n"
                "12 Schlüssel verfügbar (Violin, Bass, Alt, Tenor...)\n\n"
                "🎨 Farben\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Jede Note wird nach Tonhöhe eingefärbt:\n"
                "C=Rot, D=Orange, E=Gelb-Grün, F=Grün,\n"
                "G=Türkis, A=Indigo, H=Pink\n"
                "Notenname + Oktave steht unter dem Notenkopf.\n\n"
                "Mehr: Hilfe → Arbeitsmappe (F1)"
            )
        except Exception:
            pass

    def _on_add_ghost_layer(self) -> None:
        """Handle add ghost layer request from Layer Panel."""
        from PyQt6.QtWidgets import QDialog
        from pydaw.ui.clip_selection_dialog import ClipSelectionDialog
        from pydaw.model.ghost_notes import LayerState
        
        # Open clip selection dialog
        dialog = ClipSelectionDialog(
            self._project_service,
            current_clip_id=self._clip_id,
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            clip_id = dialog.get_selected_clip_id()
            if not clip_id:
                return
            
            # Get clip info for display name
            try:
                project = self._project_service.ctx.project
                clip = next((c for c in project.clips if c.id == clip_id), None)
                track = next((t for t in project.tracks if clip and t.id == clip.track_id), None)
                
                if clip and track:
                    track_name = str(track.name)
                    
                    # Add as ghost layer
                    self._view.layer_manager.add_layer(
                        clip_id=clip_id,
                        track_name=track_name,
                        state=LayerState.LOCKED,
                        opacity=0.3,
                    )
                    
                    # Show status message
                    try:
                        self.status_message.emit(f"Ghost Layer hinzugefügt: {track_name}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error adding ghost layer: {e}")


def _run_demo() -> None:
    """Standalone visual demo (does not require the full DAW)."""

    from PyQt6.QtCore import QObject

    class _Stub(QObject):
        project_updated = pyqtSignal()

        def __init__(self):
            super().__init__()
            self._notes = {
                "clip1": [
                    MidiNote(pitch=64, start_beats=0.0, length_beats=1.0, velocity=100),  # E4
                    MidiNote(pitch=66, start_beats=1.0, length_beats=1.0, velocity=100),  # F#4
                    MidiNote(pitch=67, start_beats=2.0, length_beats=2.0, velocity=100),  # G4
                    MidiNote(pitch=72, start_beats=4.0, length_beats=1.0, velocity=100),  # C5
                ]
            }

        def get_midi_notes(self, clip_id: str):
            return list(self._notes.get(clip_id, []))

    app = QApplication.instance() or QApplication([])
    stub = _Stub()
    w = NotationWidget(stub)
    w.resize(1000, 380)
    w.set_clip("clip1")
    w.show()
    app.exec()


if __name__ == "__main__":
    _run_demo()
