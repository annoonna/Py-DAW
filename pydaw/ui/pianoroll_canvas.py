"""Piano roll canvas.

This module intentionally uses a QWidget paintEvent approach (instead of a
QGraphicsScene) to keep the architecture simple and avoid a heavy refactor.

Implemented:
- Tool modes: select, time, pen, erase, knife
- Selection rectangle
- Move notes (drag)
- Resize note length (drag right edge of selected note)
- Snap on/off
- Grid: fixed/adaptive (adaptive = coarser grid when zoomed out)
- Zoom +/- (changes pixels-per-beat / pixels-per-semitone)
- Note glow effect (BachOrgelForge-inspired)

Notes:
- "time" tool: emits playhead_requested(beat) on click
- "knife" tool: splits a note at the clicked beat (simple, no crossfade)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
import copy
from datetime import datetime
from typing import Optional, Set

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QWidget

from pydaw.model.midi import MidiNote
from pydaw.services.project_service import ProjectService

from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value, set_value, set_value
from pydaw.music.scales import allowed_pitch_classes, apply_scale_constraint

# Ghost Notes / Layered Editing Support
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.pianoroll_ghost_notes import GhostNotesRenderer

# Note Expressions (Bitwig/Cubase-style) — foundation (opt-in)
try:
    from pydaw.ui.note_expression_engine import NoteExpressionEngine, DEFAULT_PARAMS
except Exception:  # pragma: no cover
    NoteExpressionEngine = None  # type: ignore
    DEFAULT_PARAMS = ()  # type: ignore


@dataclass
class _DragMove:
    idx: int
    drag_dx_beats: float = 0.0


@dataclass
class _DragMoveGroup:
    """Drag state for moving a multi-selection as one block."""

    indices: list[int]
    origin: dict[int, tuple[float, int]]  # idx -> (start_beats, pitch)
    anchor_idx: int
    anchor_start: float
    anchor_pitch: int
    drag_dx_beats: float = 0.0


@dataclass
class _DragResize:
    idx: int
    origin_len: float
    origin_x: float


@dataclass
class _ExprMorphDrag:
    idx: int
    origin_x: float
    note_rect_w: float
    param: str
    origin_points: list[dict]
    before_snapshot: object
    last_scale: float = 1.0


class PianoRollCanvas(QWidget):
    # Context actions (handled by PianoRollEditor/MainWindow)
    loop_start_requested = pyqtSignal(float)
    loop_end_requested = pyqtSignal(float)
    playhead_requested = pyqtSignal(float)
    status_message = pyqtSignal(str, int)

    def __init__(self, project: ProjectService, transport=None, parent=None):
        super().__init__(parent)
        # v0.0.20.607: Canvas must NEVER influence parent dock/window size
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.project = project
        # Optional transport reference (for loop auto-extend convenience)
        self.transport = transport
        self.clip_id: str = ""

        # Clip meta (local coordinates): start/length in arrangement beats.
        # Notes in this project are stored relative to clip start, but we also
        # keep the arrangement placement to render a local playline.
        self._clip_start_beats: float = 0.0
        self._clip_length_beats: float = 4.0

        # Transport playhead (global beats). Rendered as local playline in PR.
        self._transport_playhead_beats: float | None = None

        # Paint cache: background/grid (performance)
        self._grid_cache_key = None
        self._grid_cache = None

        # Lasso selection state (notes)
        self._sel_initial_selection = set()

        # Zoom / layout
        self.pixels_per_beat = 90.0
        self.pixels_per_semitone = 14.0

        # Full range: C-1 .. C9 (MIDI 0..120). Scrolling handles the size.
        self.visible_pitches = (0, 120)  # inclusive

        # How far the editor extends on the X axis.
        self.total_beats = 64.0  # default: 16 bars @ 4/4

        # Grid / snap
        self.grid_mode: str = "fixed"  # fixed|adaptive
        self.base_grid_beats = 0.25  # 1/16
        self.snap_enabled = True

        self.default_note_len = 1.0

        # Tool mode used by the global toolbar (and the editor toolbar).
        # Supported: select, time, pen, erase, knife.
        self.tool_mode: str = "pen"

        self.selected_indices: Set[int] = set()

        self._move: Optional[object] = None  # _DragMove | _DragMoveGroup
        self._resize: Optional[_DragResize] = None

        # Undo snapshot for drag operations (Move/Resize)
        self._edit_before = None
        self._edit_label: str = ""

        self._selecting = False
        self._time_dragging = False
        self._time_range_origin_beat = None
        self._time_range = None
        self._time_range_origin_beat: float | None = None
        self._time_range: tuple[float, float] | None = None
        self._last_status_beat: float | None = None
        self._sel_origin: Optional[QPointF] = None
        self._sel_rect: Optional[QRectF] = None

        # Clipboard + mouse anchor (DAW-style copy/paste)
        # Clipboard stores a snapshot-like list[dict] (pitch/start/len/vel)
        self._clipboard: list[dict] = []
        self._clipboard_min_start: float = 0.0

        # Last mouse position in musical coordinates (used as paste anchor)
        self._last_mouse_beat: float | None = None
        self._last_mouse_pitch: int | None = None

        # Ghost Notes / Layered Editing Support
        self.layer_manager = LayerManager()
        self.ghost_renderer = GhostNotesRenderer(self)

        # Note Expressions (v0.0.20.196 foundation)
        self.note_expression_engine = None
        self._expr_hover_idx: int = -1
        self._expr_focus_idx: int | None = None
        self._expr_morph: _ExprMorphDrag | None = None
        try:
            if NoteExpressionEngine is not None:
                self.note_expression_engine = NoteExpressionEngine(self)
                # Persisted preferences (OFF by default)
                enabled = bool(get_value(SettingsKeys().ui_pianoroll_note_expressions_enabled, False))
                param = str(get_value(SettingsKeys().ui_pianoroll_note_expressions_param, "velocity") or "velocity")
                try:
                    self.note_expression_engine.set_active_param(param)
                    self.note_expression_engine.set_enabled(enabled)
                except Exception:
                    pass
                try:
                    self.note_expression_engine.changed.connect(self.update)
                except Exception:
                    pass
        except Exception:
            self.note_expression_engine = None

        # Hover tracking is required for the Expression Triangle interaction model.
        try:
            self.setMouseTracking(True)
        except Exception:
            pass

        # Restore persisted ghost layers (Project.ghost_layers)
        # IMPORTANT: ProjectService loads projects asynchronously (threadpool).
        # The canvas exists before `open_project()` finishes, so we must reload
        # ghost layers when the project context changes.
        self._load_ghost_layers_from_project(emit=False)
        try:
            self.project.project_changed.connect(self._on_project_changed)
        except Exception:
            pass

        # Persist changes back into project model
        self.layer_manager.layers_changed.connect(self._persist_ghost_layers_to_project)

        self._update_canvas_size()

        self.project.project_updated.connect(self._on_project_updated)


    def _load_ghost_layers_from_project(self, *, emit: bool = True) -> None:
        """Load ghost layer state from the current project (if present).

        Args:
            emit: If True, emit LayerManager change signals after loading.
                  For init, we use emit=False. For project-open/new, emit=True.
        """
        try:
            proj = getattr(self.project, "ctx", None)
            proj = getattr(proj, "project", None)
            state = getattr(proj, "ghost_layers", {}) or {}
            if isinstance(state, dict):
                self.layer_manager.load_state(state, emit=emit)
        except Exception:
            pass

    def _on_project_changed(self) -> None:
        """Reload persisted ghost layers after project open/new/load."""
        self._load_ghost_layers_from_project(emit=True)
        try:
            self.update()
        except Exception:
            pass

    def _persist_ghost_layers_to_project(self) -> None:
        """Persist current layer manager state into the project model."""
        try:
            proj = getattr(self.project, "ctx", None)
            proj = getattr(proj, "project", None)
            if proj is None:
                return
            setattr(proj, "ghost_layers", self.layer_manager.to_dict())
            try:
                proj.modified_utc = datetime.utcnow().isoformat(timespec="seconds")
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- public setters ----------------

    def _update_canvas_size(self) -> None:
        lo, hi = self.visible_pitches
        w = int(max(800.0, self.total_beats * self.pixels_per_beat))
        # Ensure canvas is tall enough for all pitches (C-1 to C9)
        # Add some extra padding at top/bottom for better visibility
        h = int(max(300.0, (hi - lo + 1) * self.pixels_per_semitone + 40))
        # v0.0.20.597: Only resize(), no setMinimumSize() — prevents forcing main window wider
        self.resize(w, h)
        # Geometry changes invalidate cached background/grid.
        try:
            self._invalidate_grid_cache()
        except Exception:
            pass

    def _on_project_updated(self) -> None:
        # Keep canvas geometry in sync with clip length and note extents.
        try:
            self._refresh_geometry()
        except Exception:
            pass
        self.update()

    def _refresh_geometry(self) -> None:
        """Update total_beats from clip meta + note extents.

        The PianoRoll works in clip-local coordinates; total_beats
        should at least cover the clip length, and also cover the farthest
        note end so users can edit beyond bar 1.
        """
        if not self.clip_id:
            return
        # Pull clip meta from project model (safe best-effort).
        clip_start = 0.0
        clip_len = 4.0
        try:
            proj = self.project.ctx.project
            for c in getattr(proj, "clips", []) or []:
                if getattr(c, "id", "") == str(self.clip_id):
                    clip_start = float(getattr(c, "start_beats", 0.0))
                    clip_len = float(getattr(c, "length_beats", 4.0))
                    break
        except Exception:
            pass
        self._clip_start_beats = float(clip_start)
        self._clip_length_beats = max(1.0, float(clip_len))

        max_end = 0.0
        try:
            for n in self.project.get_midi_notes(self.clip_id) or []:
                max_end = max(max_end, float(n.start_beats) + float(n.length_beats))
        except Exception:
            pass

        target = max(self._clip_length_beats, max_end)
        # Round up to full bars (4/4 assumed) + one extra bar for comfort.
        bars = int((target + 3.999) // 4.0) + 1
        target_beats = max(4.0, float(bars * 4))

        if abs(target_beats - float(self.total_beats)) > 0.01:
            self.total_beats = float(target_beats)
            self._update_canvas_size()

    def set_clip(self, clip_id: str | None) -> None:
        self.clip_id = clip_id or ""
        self.selected_indices.clear()
        self._move = None
        self._resize = None
        self._sel_rect = None
        try:
            self._refresh_geometry()
        except Exception:
            pass
        self.update()

    def set_transport_playhead(self, global_beat: float) -> None:
        """Update transport playhead (global beats).

        In PianoRoll we render a local playline relative to the selected clip.
        """
        try:
            self._transport_playhead_beats = float(global_beat)
        except Exception:
            pass
        self.update()

    def set_tool_mode(self, mode: str) -> None:
        mode = (mode or "").strip().lower()
        mapping = {
            "zeiger": "select",
            "pointer": "select",
            "select": "select",
            "time": "time",
            "zeit": "time",
            "stift": "pen",
            "pen": "pen",
            "pencil": "pen",
            "radiergummi": "erase",
            "erase": "erase",
            "eraser": "erase",
            "knife": "knife",
            "messer": "knife",
        }
        self.tool_mode = mapping.get(mode, mode) or "pen"
        # Cursor + hint
        cur = {
            "select": Qt.CursorShape.ArrowCursor,
            "time": Qt.CursorShape.IBeamCursor,
            "pen": Qt.CursorShape.CrossCursor,
            "erase": Qt.CursorShape.ForbiddenCursor,
            "knife": Qt.CursorShape.SplitVCursor,
        }.get(self.tool_mode, Qt.CursorShape.ArrowCursor)
        self.setCursor(cur)
        try:
            self.status_message.emit(
                f"PianoRoll Tool: {self.tool_mode}  |  ALT=Snap Override  |  SHIFT(Time)=Range/Loop",
                1800,
            )
        except Exception:
            pass
        self.update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = bool(enabled)
        self.update()

    def set_grid_mode(self, mode: str) -> None:
        mode = (mode or "").strip().lower()
        if mode not in ("fixed", "adaptive"):
            return
        self.grid_mode = mode
        try:
            self._invalidate_grid_cache()
        except Exception:
            pass
        self.update()

    def set_grid_division(self, division_label) -> None:  # noqa: ANN001
        """Accepts labels like '1/16', '1/4', '1/1' or a denominator int (e.g. 16)."""
        denom_i = None

        # int/float directly
        if isinstance(division_label, (int, float)):
            try:
                denom_i = int(division_label)
            except Exception:
                denom_i = None
        else:
            s = (division_label or "").strip()
            if "/" in s:
                try:
                    _num, denom = s.split("/", 1)
                    denom_i = int(denom)
                except Exception:
                    denom_i = None
            else:
                # allow "16" as shorthand
                try:
                    denom_i = int(s)
                except Exception:
                    denom_i = None

        if not denom_i:
            return
        self.set_grid_beats(4.0 / max(1, int(denom_i)))

    def set_grid_beats(self, grid_beats: float) -> None:
        try:
            g = float(grid_beats)
        except Exception:
            return
        self.base_grid_beats = max(1 / 128.0, min(16.0, g))
        try:
            self._invalidate_grid_cache()
        except Exception:
            pass
        self.update()

    def zoom_in(self) -> None:
        self._set_zoom(self.pixels_per_beat * 1.15, self.pixels_per_semitone * 1.08)

    def zoom_out(self) -> None:
        self._set_zoom(self.pixels_per_beat / 1.15, self.pixels_per_semitone / 1.08)

    def _set_zoom(self, ppb: float, pps: float) -> None:
        self.pixels_per_beat = float(max(20.0, min(360.0, ppb)))
        self.pixels_per_semitone = float(max(8.0, min(26.0, pps)))
        self._update_canvas_size()
        self.update()

    # ---------------- mapping ----------------

    def _effective_grid_beats(self) -> float:
        g = float(self.base_grid_beats)
        if self.grid_mode != "adaptive":
            return g

        # Adaptive: aim for ~12..60 px between grid lines.
        ppb = float(self.pixels_per_beat)
        min_px = 12.0
        max_px = 60.0

        # Coarsen when zoomed out (too dense)
        while g * ppb < min_px and g < 16.0:
            g *= 2.0

        # Refine when zoomed in (too sparse), but never below 1/64 by default.
        while g * ppb > max_px and g > (1.0 / 64.0):
            g /= 2.0

        return max(1.0 / 128.0, min(16.0, g))

    def _snap(self, beat: float, modifiers=None) -> float:  # noqa: ANN001
        # Alt overrides snap temporarily.
        try:
            if modifiers is not None and (modifiers & Qt.KeyboardModifier.AltModifier):
                return max(0.0, float(beat))
        except Exception:
            pass
        if not self.snap_enabled:
            return max(0.0, float(beat))
        g = self._effective_grid_beats()
        if g <= 0:
            return max(0.0, float(beat))
        return max(0.0, round(float(beat) / g) * g)

    def _snap_force(self, beat: float) -> float:
        """Snap to grid regardless of current snap toggle.

        Used for Ctrl+V paste anchoring so notes don't land between beats.
        """
        g = float(self._effective_grid_beats())
        if g <= 0:
            return max(0.0, float(beat))
        return max(0.0, round(float(beat) / g) * g)

    def _update_clip_length_for_notes(self) -> None:
        """Auto-extend the MIDI clip length so the editor isn't limited to 1 bar."""
        if not self.clip_id:
            return
        try:
            notes = self.project.get_midi_notes(self.clip_id)
            if not notes:
                return
            end_beats = max(float(n.start_beats) + float(n.length_beats) for n in notes)
            self.project.ensure_midi_clip_length(self.clip_id, float(end_beats))
            # If looping, extend loop-end so the new material is audible.
            try:
                if self.transport is not None:
                    self.transport.ensure_loop_covers(float(end_beats), snap_to_bar=True)
            except Exception:
                pass
        except Exception:
            return

    def _x_to_beat(self, x: float) -> float:
        return max(0.0, x / self.pixels_per_beat)

    def _beat_to_x(self, beat: float) -> float:
        return beat * self.pixels_per_beat

    def _y_to_pitch(self, y: float) -> int:
        lo, hi = self.visible_pitches
        pitch = int(round(hi - (y / self.pixels_per_semitone)))
        return max(lo, min(hi, pitch))

    def _pitch_to_y(self, pitch: int) -> float:
        _lo, hi = self.visible_pitches
        return (hi - pitch) * self.pixels_per_semitone

    def _note_rects(self):
        notes = self.project.get_midi_notes(self.clip_id) if self.clip_id else []
        rects = []
        for i, n in enumerate(notes):
            x = self._beat_to_x(n.start_beats)
            w = max(8.0, self._beat_to_x(n.length_beats))
            y = self._pitch_to_y(n.pitch)
            h = self.pixels_per_semitone
            rects.append((i, QRectF(x, y, w, h), n))
        return rects

    def _note_at(self, pos: QPointF) -> int:
        # Focus mode (Note Expressions): treat only the focused note as interactive.
        try:
            if self._expr_focus_idx is not None:
                f = int(self._expr_focus_idx)
                for idx, r, _n in self._note_rects():
                    if idx == f and r.contains(pos):
                        return idx
                return -1
        except Exception:
            pass
        for idx, r, _n in self._note_rects():
            if r.contains(pos):
                return idx
        return -1

    def _expr_hit_triangle(self, idx: int, pos: QPointF) -> bool:
        """Return True if pos hits the expression triangle of note idx.

        This works even when expressions are disabled (hover triangle still exists).
        """
        try:
            eng = getattr(self, 'note_expression_engine', None)
            if eng is None:
                return False
            for i, r, _n in self._note_rects():
                if i != idx:
                    continue
                return bool(getattr(eng, 'hit_triangle', lambda x, y, rr: False)(pos.x(), pos.y(), r))
        except Exception:
            return False

    def expression_target_index(self) -> int:
        """Best-effort target note for expression editing/lane display."""
        try:
            if self._expr_focus_idx is not None:
                return int(self._expr_focus_idx)
        except Exception:
            pass
        try:
            if len(self.selected_indices) == 1:
                return int(next(iter(self.selected_indices)))
        except Exception:
            pass
        return int(self._expr_hover_idx) if int(self._expr_hover_idx) >= 0 else -1

    def _show_context_menu(self, event, idx: int) -> None:  # noqa: ANN001
        pos = event.position()

        # Time tool: scrub playhead and optionally set a range (SHIFT)
        if self.tool_mode == "time" and getattr(self, "_time_dragging", False):
            beat = self._snap(self._x_to_beat(pos.x()), event.modifiers())
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self._time_range_origin_beat is not None:
                a = float(self._time_range_origin_beat)
                b = float(beat)
                self._time_range = (min(a, b), max(a, b))
                self.update()
            else:
                self.playhead_requested.emit(float(beat))
                if self._last_status_beat is None or abs(float(beat) - float(self._last_status_beat)) >= 0.10:
                    self._last_status_beat = float(beat)
                    try:
                        self.status_message.emit(f"Playhead: {beat:.2f} Beats", 350)
                    except Exception:
                        pass
            return

        beat = self._snap(self._x_to_beat(pos.x()), Qt.KeyboardModifier.NoModifier)

        menu = QMenu(self)

        # Note actions
        if idx >= 0:
            a_del = QAction("Note löschen", self)
            a_del.triggered.connect(lambda: self._delete_note_index(idx))
            menu.addAction(a_del)
        else:
            a_add = QAction("Note hinzufügen", self)
            a_add.triggered.connect(lambda: self._add_note_at(pos))
            menu.addAction(a_add)

        # Note length submenu (works for single + multi selection)
        if self.selected_indices:
            len_menu = menu.addMenu("Notenlänge")
            for div in ["1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]:
                act = QAction(div, self)
                act.triggered.connect(lambda _=False, d=div: self.set_selected_note_length(d))
                len_menu.addAction(act)

        menu.addSeparator()

        # Loop helpers (Project doesn't own loop; we emit and let the editor decide)
        a_ls = QAction(f"Loop Start hier (Beat {beat:.2f})", self)
        a_le = QAction(f"Loop End hier (Beat {beat:.2f})", self)
        a_ls.triggered.connect(lambda: self.loop_start_requested.emit(float(beat)))
        a_le.triggered.connect(lambda: self.loop_end_requested.emit(float(beat)))
        menu.addAction(a_ls)
        menu.addAction(a_le)

        menu.addSeparator()

        # Tool submenu
        tools = menu.addMenu("Werkzeug")
        for label, mode in (
            ("Zeiger", "select"),
            ("Time", "time"),
            ("Stift", "pen"),
            ("Radiergummi", "erase"),
            ("Messer", "knife"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.tool_mode == mode)
            act.triggered.connect(lambda _=False, m=mode: self.set_tool_mode(m))
            tools.addAction(act)

        gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else self.mapToGlobal(pos.toPoint())
        menu.exec(gp)

    def _delete_note_index(self, idx: int) -> None:
        if not self.clip_id:
            return
        notes = self.project.get_midi_notes(self.clip_id)
        if idx < 0 or idx >= len(notes):
            return
        before = self.project.snapshot_midi_notes(self.clip_id)
        self.project.delete_midi_note_at(self.clip_id, idx)
        self.project.commit_midi_notes_edit(self.clip_id, before, "Delete Note")
        self._update_clip_length_for_notes()

    def _add_note_at(self, pos: QPointF) -> None:
        if not self.clip_id:
            return
        beat = self._snap(self._x_to_beat(pos.x()), Qt.KeyboardModifier.NoModifier)
        pitch = self._y_to_pitch(pos.y())

        # Scale constraint (optional): Snap vs Reject
        keys = SettingsKeys()
        if bool(get_value(keys.scale_enabled, False)):
            cat = str(get_value(keys.scale_category, ""))
            name = str(get_value(keys.scale_name, ""))
            root = int(get_value(keys.scale_root_pc, 0) or 0)
            mode = str(get_value(keys.scale_mode, "snap") or "snap")
            allowed = allowed_pitch_classes(category=cat, name=name, root_pc=root)
            new_pitch = apply_scale_constraint(pitch, allowed, mode)
            if new_pitch is None:
                # Reject
                try:
                    self.status_message.emit("Scale: Note rejected (out of scale)", 900)
                except Exception:
                    pass
                return
            pitch = int(new_pitch)
        before = self.project.snapshot_midi_notes(self.clip_id)
        self.project.add_midi_note(
            self.clip_id,
            MidiNote(pitch=pitch, start_beats=beat, length_beats=self.default_note_len),
        )
        self.project.commit_midi_notes_edit(self.clip_id, before, "Add Note")
        try:
            self.project.preview_note(int(pitch), 100, 140)
        except Exception:
            pass
        self._update_clip_length_for_notes()

    def _scale_constrain_pitch(self, pitch: int, *, fallback: int) -> int:
        """Apply Scale Lock (Snap/Reject) to a pitch.

        - Snap: returns nearest allowed pitch.
        - Reject: returns `fallback` if out-of-scale.

        This is used for drag/move editing, so Reject should *not* delete notes;
        it simply prevents landing on disallowed pitches.
        """

        try:
            p = int(pitch)
            fb = int(fallback)
        except Exception:
            return int(fallback)

        keys = SettingsKeys()
        if not bool(get_value(keys.scale_enabled, False)):
            return p

        try:
            cat = str(get_value(keys.scale_category, ""))
            name = str(get_value(keys.scale_name, ""))
            root = int(get_value(keys.scale_root_pc, 0) or 0)
            mode = str(get_value(keys.scale_mode, "snap") or "snap")
            allowed = allowed_pitch_classes(category=cat, name=name, root_pc=root)
            new_pitch = apply_scale_constraint(int(p), allowed, mode)
            return fb if new_pitch is None else int(new_pitch)
        except Exception:
            return p

    def _hit_resize_handle(self, idx: int, pos: QPointF) -> bool:
        for i, r, _n in self._note_rects():
            if i != idx:
                continue
            handle = QRectF(r.right() - 6, r.top(), 12, r.height())
            return handle.contains(pos)
        return False

    def _split_note_at(self, idx: int, split_beat: float) -> None:
        if not self.clip_id:
            return
        notes = self.project.get_midi_notes(self.clip_id)
        if idx < 0 or idx >= len(notes):
            return
        n = notes[idx]
        start = float(n.start_beats)
        end = start + float(n.length_beats)
        sb = float(split_beat)
        if sb <= start + 1e-6 or sb >= end - 1e-6:
            return

        min_len = max(1.0 / 64.0, float(self._effective_grid_beats()))
        left_len = max(min_len, sb - start)
        right_len = max(min_len, end - sb)

        # Update left
        try:
            n.length_beats = left_len
        except Exception:
            pass

        # Create right note
        right = MidiNote(pitch=int(n.pitch), start_beats=sb, length_beats=right_len, velocity=int(getattr(n, "velocity", 100)))
        notes.append(right)
        # Keep deterministic order
        notes = sorted(notes, key=lambda x: (float(x.start_beats), -int(x.pitch)))
        self.project.set_midi_notes(self.clip_id, notes)

        # Select both resulting notes (best-effort)
        sel = set()
        for i2, n2 in enumerate(notes):
            try:
                if int(getattr(n2, 'pitch', -1)) == int(n.pitch) and (
                    abs(float(getattr(n2, 'start_beats', -999)) - start) < 1e-6
                    or abs(float(getattr(n2, 'start_beats', -999)) - sb) < 1e-6
                ):
                    sel.add(i2)
            except Exception:
                continue
        if sel:
            self.selected_indices = sel

    # ---------------- painting ----------------

    def _rounded_path(self, rect: QRectF, radius: float = 4.0) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _scale_hint_pcs(self) -> set[int] | None:
        """Return allowed pitch-classes for Pro-DAW-like visual hints.

        Hints are shown only when Scale Lock is enabled *and* visualization is enabled.
        """
        try:
            keys = SettingsKeys()
            if not bool(get_value(keys.scale_visualize, True)):
                return None
            if not bool(get_value(keys.scale_enabled, False)):
                return None
            cat = str(get_value(keys.scale_category, "Keine Einschränkung"))
            name = str(get_value(keys.scale_name, "Alle Noten"))
            if cat == "Keine Einschränkung":
                return None
            root = int(get_value(keys.scale_root_pc, 0) or 0)
            pcs = allowed_pitch_classes(category=cat, name=name, root_pc=root)
            return set(int(x) % 12 for x in pcs)
        except Exception:
            return None


    def _invalidate_grid_cache(self) -> None:
        """Invalidate cached background/grid pixmap (performance)."""
        self._grid_cache = None
        self._grid_cache_key = None


    def paintEvent(self, event):  # noqa: ANN001
        p = QPainter(self)
        fast = bool(self._move is not None or self._resize is not None or self._selecting or self._expr_morph is not None or self._time_dragging)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, not fast)

        # Classic (Bitwig-ish) theme: readable grid, nicer notes.
        bg = QColor(28, 30, 35)
        grid_sub = QColor(55, 60, 70)
        grid_beat = QColor(70, 80, 95)
        grid_bar = QColor(95, 110, 130)

        note_fill = QColor(105, 185, 255)
        note_sel = QColor(255, 175, 95)
        note_outline = QColor(255, 255, 255, 210)

        w = max(1, int(self.width()))
        h = max(1, int(self.height()))
        ppb = float(self.pixels_per_beat)

        def _draw_static_background(pp: QPainter, allowed_pcs: set[int] | None) -> None:
            """Draw background + scale visualization + pitch/beat grid."""
            pp.fillRect(0, 0, w, h, bg)

            # Scale visualization (Pro-DAW-like cyan dots)
            if allowed_pcs:
                pps = float(self.pixels_per_semitone)
                ppb_hint = float(self.pixels_per_beat)
                end_beat_hint = float(w) / ppb_hint if ppb_hint > 0 else 0.0

                # Spacing adapts with zoom so it doesn't get too dense
                if ppb_hint >= 160:
                    beat_step = 0.5
                elif ppb_hint >= 90:
                    beat_step = 1.0
                else:
                    beat_step = 2.0

                lo2, hi2 = self.visible_pitches
                allowed_pitches = [p_ for p_ in range(lo2, hi2 + 1) if (int(p_) % 12) in allowed_pcs]

                # Subtle row tint
                shade = QColor(0, 229, 255, 16)
                pp.setPen(Qt.PenStyle.NoPen)
                for pitch in allowed_pitches:
                    y = self._pitch_to_y(int(pitch))
                    pp.fillRect(QRectF(0, y, float(w), pps), shade)

                # Dots at beat positions
                dot = QColor(0, 229, 255, 120)
                pp.setBrush(QBrush(dot))
                r = 2.0
                x_off = (beat_step * ppb_hint) * 0.5
                beat = 0.0
                while beat <= end_beat_hint + beat_step:
                    x = beat * ppb_hint + x_off
                    for pitch in allowed_pitches:
                        y = self._pitch_to_y(int(pitch)) + pps * 0.5
                        pp.drawEllipse(QPointF(x, y), r, r)
                    beat += beat_step

            # pitch lines (horizontal)
            lo, hi = self.visible_pitches
            for pitch in range(lo, hi + 1):
                y = self._pitch_to_y(pitch)
                note_in_octave = pitch % 12
                is_black_key = note_in_octave in {1, 3, 6, 8, 10}

                if is_black_key:
                    pen_pitch = QPen(QColor(45, 50, 60))
                else:
                    pen_pitch = QPen(QColor(55, 60, 70))

                pen_pitch.setStyle(Qt.PenStyle.DotLine)
                pp.setPen(pen_pitch)
                pp.drawLine(0, int(y), w, int(y))

            # beat grid
            step = float(self._effective_grid_beats())
            end_beat = float(w) / ppb if ppb > 0 else 0.0

            def is_close(a: float, b: float, eps: float = 1e-6) -> bool:
                return abs(a - b) <= eps

            i = 0
            while True:
                beat = i * step
                if beat > end_beat + step:
                    break
                x = int(beat * ppb)

                # major lines
                if is_close((beat / 4.0) % 1.0, 0.0, 1e-4):
                    pp.setPen(QPen(grid_bar))
                elif is_close(beat % 1.0, 0.0, 1e-4):
                    pp.setPen(QPen(grid_beat))
                else:
                    pen = QPen(grid_sub)
                    pen.setStyle(Qt.PenStyle.DotLine)
                    pp.setPen(pen)

                pp.drawLine(x, 0, x, h)
                i += 1

        # Cached background/grid for smooth interaction (fix: never recurse)
        allowed_pcs = None
        try:
            allowed_pcs = self._scale_hint_pcs()
            scale_key = tuple(sorted(allowed_pcs)) if allowed_pcs else None
            key = (w, h, float(self.pixels_per_beat), float(self.pixels_per_semitone),
                   str(self.grid_mode), float(self._effective_grid_beats()), tuple(self.visible_pitches), scale_key)
            if self._grid_cache is None or self._grid_cache_key != key:
                pm = QPixmap(w, h)
                pm.fill(bg)
                pp = QPainter(pm)
                pp.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                _draw_static_background(pp, allowed_pcs)
                pp.end()
                self._grid_cache = pm
                self._grid_cache_key = key
            if self._grid_cache is not None:
                p.drawPixmap(0, 0, self._grid_cache)
            else:
                _draw_static_background(p, allowed_pcs)
        except Exception:
            # Fallback: draw directly (never lose the grid)
            try:
                _draw_static_background(p, allowed_pcs)
            except Exception:
                p.fillRect(self.rect(), bg)

        # PianoRoll playline (transport playhead rendered local to clip)
        # v0.0.20.593: Wrap playhead into clip loop region (Bitwig-style)
        try:
            if self._transport_playhead_beats is not None and self.clip_id:
                local = float(self._transport_playhead_beats) - float(self._clip_start_beats)
                # Wrap into loop region if clip has active loop
                try:
                    clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(self.clip_id)), None)
                    if clip_obj is not None:
                        ls = float(getattr(clip_obj, 'loop_start_beats', 0.0) or 0.0)
                        le = float(getattr(clip_obj, 'loop_end_beats', 0.0) or 0.0)
                        if le > ls + 0.01 and local > le:
                            span = le - ls
                            if span > 0.01:
                                local = ls + ((local - ls) % span)
                except Exception:
                    pass
                if local >= -0.01:
                    x = int(local * ppb)
                    if -2 <= x <= w + 2:
                        play_pen = QPen(QColor(220, 60, 60, 220))
                        play_pen.setWidth(2)
                        p.setPen(play_pen)
                        p.drawLine(x, 0, x, h)
        except Exception:
            pass

        # Ghost Notes / Layered Editing: Render ghost layers BEFORE main notes
        try:
            if hasattr(self, 'ghost_renderer') and hasattr(self, 'layer_manager'):
                self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
        except Exception:
            pass

        # notes
        note_rects = list(self._note_rects())
        focus_idx = self._expr_focus_idx
        hover_idx = int(self._expr_hover_idx) if int(self._expr_hover_idx) >= 0 else -1
        for idx, r, _n in note_rects:
            selected = idx in self.selected_indices
            color = note_sel if selected else note_fill

            # FAST paint during drag: keep interaction fluid (reduced effects)
            if fast:
                dim_other = (focus_idx is not None and int(idx) != int(focus_idx))
                body = QColor(color)
                # Keep notes solid while dragging (avoids "glassy" feeling).
                body.setAlpha(70 if dim_other else 235)
                pen = QPen(note_outline if selected else QColor(color).darker(150))
                pen.setWidth(1)
                p.setPen(pen)
                p.setBrush(QBrush(body))
                try:
                    p.drawRoundedRect(r, 4.5, 4.5)
                except Exception:
                    p.drawRect(r)
                if selected:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(255, 255, 255, 200)))
                    p.drawRoundedRect(QRectF(r.right() - 4, r.top() + 2, 3, max(3.0, r.height() - 4)), 2, 2)
                # Note name in fast mode (v0.0.20.456)
                try:
                    if r.width() >= 24 and r.height() >= 8:
                        from pydaw.ui.notation.colors import note_name as _nn
                        nn = _nn(int(_n.pitch), german=True, with_octave=True)
                        p.setFont(QFont("Sans", 7))
                        p.setPen(QPen(QColor(255, 255, 255, 180)))
                        p.drawText(QRectF(r.left() + 3, r.top(), r.width() - 6, r.height()),
                                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nn)
                except Exception:
                    pass
                continue

            # Focus mode: dim other notes (Micropitch drawing becomes precise).
            dim_other = (focus_idx is not None and int(idx) != int(focus_idx))

            # Glow: Bitwig-style "always present" subtle glow, stronger for hover/selection.
            # Kept lightweight by using fewer layers for non-selected notes.
            if not dim_other:
                is_hover = (int(idx) == hover_idx)
                glow_alpha = 88 if selected else (60 if is_hover else 42)
                glow_layers = (6.0, 4.0, 2.0) if (selected or is_hover) else (4.0, 2.0)
                p.setPen(Qt.PenStyle.NoPen)
                for j, expand in enumerate(glow_layers):
                    a = max(0, glow_alpha - j * (18 if (selected or is_hover) else 20))
                    glow = QColor(color)
                    glow.setAlpha(a)
                    rr = r.adjusted(-expand, -expand, expand, expand)
                    path = self._rounded_path(rr, radius=7.0)
                    p.fillPath(path, QBrush(glow))

            # Main body (subtle gradient for a nicer, less flat look)
            body = QColor(color)
            body.setAlpha(70 if dim_other else 235)
            inner = r.adjusted(0.5, 0.5, -0.5, -0.5)
            # Rounder notes (like v0.0.20.200 look)
            path = self._rounded_path(inner, radius=6.0)

            # gradient fill (cheap, and looks much better than flat fill)
            try:
                grad = QLinearGradient(inner.topLeft(), inner.bottomLeft())
                topc = QColor(body)
                topc.setAlpha(min(255, body.alpha() + 10))
                botc = QColor(body).darker(115)
                grad.setColorAt(0.0, topc)
                grad.setColorAt(1.0, botc)
                brush = QBrush(grad)
            except Exception:
                brush = QBrush(body)

            pen = QPen(note_outline if selected else QColor(color).darker(140))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(brush)
            p.drawPath(path)

            # Resize handle hint
            if selected:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 220)))
                p.drawRoundedRect(QRectF(r.right() - 4, r.top() + 2, 3, max(3.0, r.height() - 4)), 2, 2)

            # Note name inside the note rect (v0.0.20.456)
            # Only if note is wide enough and tall enough to be readable
            try:
                if r.width() >= 20 and r.height() >= 8 and not dim_other:
                    from pydaw.ui.notation.colors import note_name as _nn
                    nn = _nn(int(_n.pitch), german=True, with_octave=True)
                    name_font = QFont("Sans", 7)
                    name_font.setBold(True)
                    p.setFont(name_font)
                    # White text with slight transparency for readability on colored notes
                    p.setPen(QPen(QColor(255, 255, 255, 200)))
                    # Left-aligned inside the note, vertically centered
                    txt_rect = QRectF(r.left() + 3, r.top(), r.width() - 6, r.height())
                    p.drawText(txt_rect,
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               nn)
            except Exception:
                pass

        # Note Expressions overlay (opt-in)
        try:
            if not fast:
                eng = getattr(self, 'note_expression_engine', None)
                if eng is not None:
                    eng.draw_expressions(p, note_rects, hovered_idx=int(self._expr_hover_idx), focus_idx=self._expr_focus_idx)
        except Exception:
            pass

        # time range (SHIFT + Time tool)
        if self._time_range is not None:
            try:
                a, b = self._time_range
                x1 = self._beat_to_x(float(a))
                x2 = self._beat_to_x(float(b))
                if x2 > x1 + 2:
                    rr = QRectF(x1, 0, x2 - x1, float(h))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(180, 120, 255, 40)))
                    p.drawRect(rr)
            except Exception:
                pass

        # selection rectangle
        if self._sel_rect:
            pen = QPen(self.palette().highlight().color())
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self._sel_rect)

        # Focus mode banner (make it obvious; prevents confusion)
        try:
            if self._expr_focus_idx is not None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 185, 110, 60)))
                p.drawRect(QRectF(0, 0, 200, 18))
                p.setPen(QPen(QColor(255, 225, 190, 230)))
                p.drawText(QRectF(6, 0, 190, 18), Qt.AlignmentFlag.AlignVCenter, 'FOCUS MODE (ESC)')
        except Exception:
            pass

        if not self.clip_id:
            p.setPen(QPen(note_outline))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Kein MIDI-Clip ausgewählt.")

        p.end()
    # ---------------- clipboard helpers (DAW-style) ----------------

    def copy_selected(self) -> None:
        if not self.clip_id:
            return
        notes = self.project.get_midi_notes(self.clip_id)
        sel = sorted(int(i) for i in (self.selected_indices or set()) if 0 <= int(i) < len(notes))
        if not sel:
            return
        picked = [notes[i] for i in sel]
        self._clipboard_min_start = min(float(n.start_beats) for n in picked)
        self._clipboard = [
            {
                "pitch": int(n.pitch),
                "start_beats": float(n.start_beats),
                "length_beats": float(n.length_beats),
                "velocity": int(getattr(n, "velocity", 100)),
                "accidental": int(getattr(n, "accidental", 0) or 0),
                "tie_to_next": bool(getattr(n, "tie_to_next", False)),
                "expressions": dict(getattr(n, "expressions", {}) or {}) if isinstance(getattr(n, "expressions", {}), dict) else {},
            }
            for n in picked
        ]
        try:
            self.status_message.emit(f"{len(self._clipboard)} Note(n) kopiert", 900)
        except Exception:
            pass

    def cut_selected(self) -> None:
        if not self.clip_id:
            return
        self.copy_selected()
        if not self._clipboard:
            return
        before = self.project.snapshot_midi_notes(self.clip_id)
        # delete selected indices descending to keep indices stable
        for idx in sorted(self.selected_indices, reverse=True):
            try:
                self.project.delete_midi_note_at(self.clip_id, int(idx))
            except Exception:
                continue
        self.selected_indices.clear()
        self.project.commit_midi_notes_edit(self.clip_id, before, "Cut Notes")
        self._update_clip_length_for_notes()

    def delete_selected(self) -> None:
        if not self.clip_id:
            return
        if not self.selected_indices:
            return
        before = self.project.snapshot_midi_notes(self.clip_id)
        for idx in sorted(self.selected_indices, reverse=True):
            try:
                self.project.delete_midi_note_at(self.clip_id, int(idx))
            except Exception:
                continue
        self.selected_indices.clear()
        self.project.commit_midi_notes_edit(self.clip_id, before, "Delete Notes")
        self._update_clip_length_for_notes()

    def select_all(self) -> None:
        if not self.clip_id:
            return
        notes = self.project.get_midi_notes(self.clip_id)
        self.selected_indices = set(range(len(notes)))
        self.update()

    def paste_at_last_mouse(self) -> None:
        if not self.clip_id:
            return
        if not self._clipboard:
            return

        # Anchor = last mouse beat (snapped). Fallback: 0.0
        anchor = float(self._last_mouse_beat) if self._last_mouse_beat is not None else 0.0
        anchor = self._snap_force(anchor)

        delta = anchor - float(self._clipboard_min_start)

        before = self.project.snapshot_midi_notes(self.clip_id)
        try:
            pre_count = len(self.project.get_midi_notes(self.clip_id))
        except Exception:
            pre_count = 0

        added = 0
        for d in (self._clipboard or []):
            try:
                start = float(d.get("start_beats", 0.0)) + float(delta)
                start = self._snap_force(start)
                nd = dict(d)
                nd["start_beats"] = float(start)
                self.project.add_midi_note(self.clip_id, nd)
                added += 1
            except Exception:
                continue

        self.project.commit_midi_notes_edit(self.clip_id, before, "Paste Notes")
        self._update_clip_length_for_notes()

        # Select newly pasted notes so the user can immediately move them.
        if added > 0:
            self.selected_indices = set(range(int(pre_count), int(pre_count + added)))
        self.update()

    # ---------------- note length helpers ----------------

    @staticmethod
    def _len_beats_from_div(division: str) -> float:
        """Map note division label to length in beats (assumes 4/4).

        1/1 = whole note (4 beats)
        1/2 = half note (2 beats)
        1/4 = quarter note (1 beat)
        1/8 = 0.5 beats
        1/16 = 0.25 beats
        etc.
        """
        div = (division or "").strip()
        try:
            if "/" in div:
                _a, b = div.split("/", 1)
                denom = int(b)
                if denom <= 0:
                    return 1.0
                return 4.0 / float(denom)
        except Exception:
            pass
        return 1.0

    def set_selected_note_length(self, division: str) -> None:
        """Set length for all selected notes to a fixed musical division."""
        if not self.clip_id:
            return
        if not self.selected_indices:
            return
        length_beats = float(self._len_beats_from_div(division))
        length_beats = max(0.03125, float(length_beats))

        before = self.project.snapshot_midi_notes(self.clip_id)
        notes = list(self.project.get_midi_notes(self.clip_id) or [])
        changed = False
        for i in list(self.selected_indices):
            if 0 <= i < len(notes):
                n = notes[i]
                if abs(float(getattr(n, "length_beats", 0.0)) - length_beats) > 1e-9:
                    n.length_beats = float(length_beats)
                    changed = True
        if not changed:
            return
        self.project.set_midi_notes(self.clip_id, notes)
        self.project.commit_midi_notes_edit(self.clip_id, before, f"Set Note Length {division}")
        # Also update default length for new notes (DAW-style consistency)
        self.default_note_len = float(length_beats)
        self._update_clip_length_for_notes()
        self.update()

    def duplicate_selected(self) -> None:
        """Duplicate selection one grid step to the right (common DAW behavior)."""
        if not self.clip_id:
            return
        self.copy_selected()
        if not self._clipboard:
            return
        g = float(self._effective_grid_beats())
        # Anchor at (selection start + one grid), snapped.
        anchor = self._snap_force(float(self._clipboard_min_start) + g)
        self._last_mouse_beat = float(anchor)
        self.paste_at_last_mouse()

    # ---------------- interaction ----------------

    def mousePressEvent(self, event):  # noqa: ANN001
        if not self.clip_id:
            return

        pos = event.position()
        idx = self._note_at(pos)

        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event, idx)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Note Expressions: triangle interaction model (opt-in, zero regressions)
        # - Hover shows triangle (rendered by NoteExpressionEngine)
        # - Click triangle: quick param menu (enables expressions)
        # - Alt+Drag triangle: time-morph (scales normalized t values; single undo step)
        try:
            eng = getattr(self, 'note_expression_engine', None)
            if eng is not None and idx >= 0 and self._expr_hit_triangle(idx, pos):
                # Triangle consumes the click: do NOT start move/resize/selection.
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    # Alt+Drag = time-morph (scale normalized t values)
                    try:
                        self._set_expression_enabled(True)
                    except Exception:
                        pass
                    notes = self.project.get_midi_notes(self.clip_id)
                    if 0 <= idx < len(notes):
                        n = notes[idx]
                        param = str(getattr(eng, 'active_param', 'velocity') or 'velocity')
                        origin_points = copy.deepcopy(n.get_expression_points(param))
                        before = self.project.snapshot_midi_notes(self.clip_id)
                        # Determine note rect width for stable scaling
                        note_w = 1.0
                        for i2, r2, _n2 in self._note_rects():
                            if i2 == idx:
                                note_w = max(1.0, float(r2.width()))
                                break
                        self._expr_morph = _ExprMorphDrag(
                            idx=int(idx),
                            origin_x=float(pos.x()),
                            note_rect_w=float(note_w),
                            param=param,
                            origin_points=origin_points,
                            before_snapshot=before,
                            last_scale=1.0,
                        )
                        try:
                            self.setCursor(Qt.CursorShape.SizeHorCursor)
                        except Exception:
                            pass
                        try:
                            self.status_message.emit('Expression Morph: Alt+Drag (loslassen = commit)', 1500)
                        except Exception:
                            pass
                        return

                # Click = quick param menu (Mini-Popup)
                try:
                    from pydaw.ui.note_expression_engine import DEFAULT_PARAMS
                except Exception:
                    DEFAULT_PARAMS = []

                try:
                    menu = QMenu(self)
                    for spec in (DEFAULT_PARAMS or []):
                        key = str(getattr(spec, 'key', 'velocity') or 'velocity')
                        label = str(getattr(spec, 'label', key))
                        act = QAction(label, self)
                        act.setCheckable(True)
                        act.setChecked(key == str(getattr(eng, 'active_param', 'velocity') or 'velocity'))
                        act.triggered.connect(lambda _=False, k=key: self._on_expression_param_from_menu(k))
                        menu.addAction(act)
                    gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else self.mapToGlobal(pos.toPoint())
                    menu.exec(gp)
                    return
                except Exception:
                    pass
        except Exception:
            pass

        # Tool: time (set playhead)
        if self.tool_mode == "time":
            beat = self._snap(self._x_to_beat(pos.x()), Qt.KeyboardModifier.NoModifier)
            self.playhead_requested.emit(float(beat))
            self._time_dragging = True
            return

        # Tool: knife (split note)
        if self.tool_mode == "knife" and idx >= 0:
            split_beat = self._snap(self._x_to_beat(pos.x()), event.modifiers())
            before = self.project.snapshot_midi_notes(self.clip_id)
            self._split_note_at(idx, split_beat)
            self.project.commit_midi_notes_edit(self.clip_id, before, "Split Note")
            return

        # Tool: erase
        if self.tool_mode == "erase" and idx >= 0:
            self._delete_note_index(idx)
            return

        if idx >= 0:
            # Selection behavior (DAW style):
            # - Ctrl: toggle selection
            # - Shift: add to selection
            # - Plain click: keep current selection if the clicked note is already selected,
            #   otherwise select only this note.
            mods = event.modifiers()
            # Special-case: Ctrl+Drag duplication (Pro-DAW/DAW style).
            # If the clicked note is already selected and Ctrl is held, we start
            # a duplicate-move gesture instead of toggling selection.
            do_dup_drag = False
            if (mods & Qt.KeyboardModifier.ControlModifier) and idx in self.selected_indices:
                do_dup_drag = True
            elif mods & Qt.KeyboardModifier.ControlModifier:
                if idx in self.selected_indices:
                    self.selected_indices.discard(idx)
                else:
                    self.selected_indices.add(idx)
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                self.selected_indices.add(idx)
            else:
                if idx not in self.selected_indices:
                    self.selected_indices = {idx}

            # resize if on handle
            if self._hit_resize_handle(idx, pos):
                notes = self.project.get_midi_notes(self.clip_id)
                n = notes[idx]
                self._edit_before = self.project.snapshot_midi_notes(self.clip_id)
                self._edit_label = "Resize Note"
                self._resize = _DragResize(idx=idx, origin_len=float(n.length_beats), origin_x=pos.x())
                self._move = None
            else:
                # move (single or group)
                notes = self.project.get_midi_notes(self.clip_id)
                beat = self._x_to_beat(pos.x())

                # Ctrl+Drag duplication: create copies and move the copies.
                if do_dup_drag and self.selected_indices:
                    before = self.project.snapshot_midi_notes(self.clip_id)
                    base_notes = list(notes)
                    sel = sorted([i for i in self.selected_indices if 0 <= i < len(base_notes)])
                    copies = []
                    for i in sel:
                        n0 = base_notes[i]
                        try:
                            copies.append(
                                MidiNote(
                                    pitch=int(getattr(n0, "pitch", 60)),
                                    start_beats=float(getattr(n0, "start_beats", 0.0)),
                                    length_beats=float(getattr(n0, "length_beats", 1.0)),
                                    velocity=int(getattr(n0, "velocity", 100)),
                                )
                            )
                        except Exception:
                            continue

                    if copies:
                        new_notes = base_notes + copies
                        self.project.set_midi_notes(self.clip_id, new_notes)
                        # New selected indices correspond to appended copies
                        first_new = len(base_notes)
                        new_sel = list(range(first_new, first_new + len(copies)))
                        # Anchor maps to the clicked note's corresponding copy
                        try:
                            clicked_pos = sel.index(idx)
                        except ValueError:
                            clicked_pos = 0
                        anchor_idx = new_sel[min(clicked_pos, len(new_sel) - 1)]
                        n = new_notes[anchor_idx]
                        self.selected_indices = set(new_sel)
                        notes = new_notes
                        idx = anchor_idx
                        self._edit_before = before
                        self._edit_label = "Duplicate+Move Notes" if len(self.selected_indices) > 1 else "Duplicate+Move Note"
                    else:
                        self._edit_before = self.project.snapshot_midi_notes(self.clip_id)
                        self._edit_label = "Move Notes" if len(self.selected_indices) > 1 else "Move Note"
                        n = notes[idx]
                else:
                    self._edit_before = self.project.snapshot_midi_notes(self.clip_id)
                    self._edit_label = "Move Notes" if len(self.selected_indices) > 1 else "Move Note"
                    n = notes[idx]

                if len(self.selected_indices) > 1 and idx in self.selected_indices:
                    origin = {i: (float(notes[i].start_beats), int(notes[i].pitch)) for i in self.selected_indices if 0 <= i < len(notes)}
                    self._move = _DragMoveGroup(
                        indices=sorted(origin.keys()),
                        origin=origin,
                        anchor_idx=idx,
                        anchor_start=float(n.start_beats),
                        anchor_pitch=int(n.pitch),
                        drag_dx_beats=beat - float(n.start_beats),
                    )
                else:
                    self._move = _DragMove(idx=idx, drag_dx_beats=beat - float(n.start_beats))
                self._resize = None

            self._selecting = False
            self._sel_rect = None
            self.update()
            return

        # empty:
        # - Ctrl+Click stamping: paste selection at mouse pointer (snapped).
        # - otherwise: start selection rect
        mods = event.modifiers()
        if (mods & Qt.KeyboardModifier.ControlModifier) and self._clipboard:
            try:
                self._last_mouse_beat = float(self._x_to_beat(pos.x()))
                self._last_mouse_pitch = int(self._y_to_pitch(pos.y()))
            except Exception:
                self._last_mouse_beat = float(self._last_mouse_beat) if self._last_mouse_beat is not None else 0.0
            self.paste_at_last_mouse()
            return

        # empty: start lasso selection rect; in pen-mode we might add a note on release
        self._selecting = True
        try:
            self._sel_initial_selection = set(self.selected_indices or set())
        except Exception:
            self._sel_initial_selection = set()
        self._sel_origin = pos
        self._sel_rect = QRectF(pos, pos)
        self._edit_before = None
        self._edit_label = ""

        self._move = None
        self._resize = None
        self.update()

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if not self.clip_id:
            return

        pos = event.position()

        # Lasso selection rectangle update
        if self._selecting and self._sel_origin is not None:
            try:
                self._sel_rect = QRectF(self._sel_origin, pos).normalized()
                self.update()
            except Exception:
                pass

        # Hover tracking for expression triangle (only when enabled)
        try:
            eng = getattr(self, 'note_expression_engine', None)
            if eng is not None and bool(getattr(eng, 'enabled', False)):
                prev = int(self._expr_hover_idx)
                self._expr_hover_idx = int(self._note_at(pos))
                if prev != int(self._expr_hover_idx):
                    self.update()
        except Exception:
            pass

        # Expression time-morph drag (Alt+Drag on triangle)
        if self._expr_morph is not None:
            try:
                md = self._expr_morph
                dx = float(pos.x()) - float(md.origin_x)
                # 1 note-width right => scale ~2.0, left => ~0.5
                factor = 1.0 + (dx / max(1.0, float(md.note_rect_w)))
                factor = max(0.25, min(4.0, float(factor)))
                if abs(float(factor) - float(md.last_scale)) < 1e-3:
                    return
                md.last_scale = float(factor)

                notes = self.project.get_midi_notes(self.clip_id)
                if 0 <= int(md.idx) < len(notes):
                    n = notes[int(md.idx)]
                    scaled = []
                    for d in (md.origin_points or []):
                        try:
                            t = max(0.0, min(1.0, float(d.get('t', 0.0)) * float(factor)))
                            v = float(d.get('v', 0.0))
                        except Exception:
                            continue
                        scaled.append({'t': t, 'v': v})
                    try:
                        scaled.sort(key=lambda dd: float(dd.get('t', 0.0)))
                    except Exception:
                        pass
                    n.set_expression_points(str(md.param), scaled)
                    self.project.set_midi_notes(self.clip_id, notes)
                    self.update()
                    try:
                        self.status_message.emit(f"Morph {md.param}: x{factor:.2f}", 250)
                    except Exception:
                        pass
                return
            except Exception:
                return

        # Track last mouse position (used for Ctrl+V paste anchoring)
        try:
            self._last_mouse_beat = float(self._x_to_beat(pos.x()))
            self._last_mouse_pitch = int(self._y_to_pitch(pos.y()))
        except Exception:
            pass

        if self._resize is not None:
            dx = pos.x() - self._resize.origin_x
            dbeats = dx / self.pixels_per_beat
            min_len = max(1.0 / 64.0, float(self._effective_grid_beats()))
            new_len = max(min_len, self._resize.origin_len + dbeats)
            new_len = self._snap(new_len, event.modifiers())
            self.project.resize_midi_note_length(self.clip_id, self._resize.idx, new_len)
            self._update_clip_length_for_notes()
            return

        if self._move is not None:
            # Multi-selection move
            if isinstance(self._move, _DragMoveGroup):
                new_anchor_start = self._snap(self._x_to_beat(pos.x()) - self._move.drag_dx_beats, event.modifiers())
                new_anchor_pitch = int(self._y_to_pitch(pos.y()))
                dbeats = float(new_anchor_start) - float(self._move.anchor_start)
                dpitch = int(new_anchor_pitch) - int(self._move.anchor_pitch)

                updates = []
                for i in self._move.indices:
                    ostart, opitch = self._move.origin.get(i, (0.0, 60))
                    nstart = self._snap(float(ostart) + dbeats, event.modifiers())
                    npitch = int(max(0, min(127, int(opitch) + dpitch)))
                    # Scale Lock: also apply to drag/move (Snap or Reject).
                    npitch = self._scale_constrain_pitch(int(npitch), fallback=int(opitch))
                    updates.append((i, nstart, npitch))

                self.project.move_midi_notes_batch(self.clip_id, updates)
                self._update_clip_length_for_notes()
                return

            # Single note move
            beat = self._snap(self._x_to_beat(pos.x()) - self._move.drag_dx_beats, event.modifiers())
            pitch = self._y_to_pitch(pos.y())
            # Scale Lock: also apply to drag/move (Snap or Reject).
            try:
                notes = self.project.get_midi_notes(self.clip_id)
                op = int(getattr(notes[self._move.idx], 'pitch', pitch)) if 0 <= int(self._move.idx) < len(notes) else int(pitch)
            except Exception:
                op = int(pitch)
            pitch = self._scale_constrain_pitch(int(pitch), fallback=int(op))
            self.project.move_midi_note(self.clip_id, self._move.idx, beat, pitch)
            self._update_clip_length_for_notes()
            return

        if self._selecting and self._sel_origin is not None:
            self._sel_rect = QRectF(self._sel_origin, pos).normalized()
            sel = set()
            for idx, r, _n in self._note_rects():
                if self._sel_rect.intersects(r):
                    sel.add(idx)
            self.selected_indices = sel
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        try:
            if not self.clip_id:
                return

            # Commit expression morph (if active)
            if self._expr_morph is not None:
                try:
                    md = self._expr_morph
                    self.project.commit_midi_notes_edit(self.clip_id, md.before_snapshot, f"Morph Expression ({md.param})")
                except Exception:
                    pass
                self._expr_morph = None
                try:
                    self.unsetCursor()
                except Exception:
                    pass
                self.update()
                return

            # Time tool: commit optional range as loop (SHIFT)
            if self.tool_mode == "time" and self._time_range is not None and self._time_range_origin_beat is not None:
                try:
                    a, b = self._time_range
                    if float(b) - float(a) >= max(1.0 / 32.0, float(self._effective_grid_beats())):
                        self.loop_start_requested.emit(float(a))
                        self.loop_end_requested.emit(float(b))
                        try:
                            self.status_message.emit(f"Loop Range gesetzt: {a:.2f} .. {b:.2f}", 1800)
                        except Exception:
                            pass
                except Exception:
                    pass

            if self._selecting and self._sel_rect is not None and self._sel_origin is not None:
                # determine if it was a click (tiny rectangle)
                if self._sel_rect.width() < 4 and self._sel_rect.height() < 4:
                    if self.tool_mode == "pen":
                        # Use the shared helper so Scale-Lock Snap/Reject is applied
                        # consistently for all note input paths.
                        self._add_note_at(self._sel_origin)
                        self.selected_indices.clear()
                        self._update_clip_length_for_notes()


            # finalize lasso selection (Select tool)
            try:
                if self._selecting and self._sel_rect is not None and self._sel_origin is not None:
                    r = self._sel_rect
                    if r.width() >= 6 and r.height() >= 6:
                        mods = event.modifiers()
                        hit = set()
                        for idx, rr, _n in self._note_rects():
                            if rr.intersects(r):
                                hit.add(int(idx))
                        if mods & Qt.KeyboardModifier.ShiftModifier:
                            self.selected_indices = set(self._sel_initial_selection or set()) | hit
                        else:
                            self.selected_indices = hit
                        try:
                            if hit:
                                self.status_message.emit(f"{len(hit)} Note(n) ausgewählt (Lasso)", 900)
                        except Exception:
                            pass
            except Exception:
                pass
            if self._edit_before is not None and (self._move is not None or self._resize is not None):
                try:
                    self.project.commit_midi_notes_edit(self.clip_id, self._edit_before, self._edit_label or "Edit Note")
                except Exception:
                    pass
                self._update_clip_length_for_notes()
            self._edit_before = None
            self._edit_label = ""

            self._move = None
            self._resize = None
            self._selecting = False
            self._time_dragging = False
            self._time_range_origin_beat = None
            self._time_range = None
            self._time_range_origin_beat: float | None = None
            self._time_range: tuple[float, float] | None = None
            self._last_status_beat: float | None = None
            self._sel_origin = None
            self._sel_rect = None
            self.update()
        except Exception as e:
            # CRITICAL: Prevent PyQt6 SIGABRT on unhandled exceptions
            import logging
            logging.getLogger(__name__).error(f"mouseReleaseEvent exception: {e}", exc_info=True)
            # Clean up state even on error
            self._move = None
            self._resize = None
            self._selecting = False
            self._time_dragging = False
            self._sel_origin = None
            self._sel_rect = None
            self.update()

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        """Expression focus mode (Bitwig-like): double click note to isolate."""
        try:
            if not self.clip_id:
                return
            if event.button() != Qt.MouseButton.LeftButton:
                return
            pos = event.position()
            idx = self._note_at(pos)
            if idx < 0:
                return

            eng = getattr(self, 'note_expression_engine', None)
            if eng is None or not bool(getattr(eng, 'enabled', False)):
                return

            if self._expr_focus_idx is not None and int(self._expr_focus_idx) == int(idx):
                self._expr_focus_idx = None
                try:
                    self.status_message.emit("Expression Focus: AUS", 900)
                except Exception:
                    pass
            else:
                self._expr_focus_idx = int(idx)
                try:
                    self.status_message.emit("Expression Focus: AN (ESC zum Beenden)", 1200)
                except Exception:
                    pass
            self.update()
        except Exception:
            return

    def keyPressEvent(self, event):  # noqa: ANN001
        try:
            if event.key() == Qt.Key.Key_Escape and self._expr_focus_idx is not None:
                self._expr_focus_idx = None
                self.update()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def _set_expression_enabled(self, enabled: bool) -> None:
        """Enable/disable note expression overlays and persist to QSettings.

        Safe: additiv, affects only drawing + expression interactions.
        """
        try:
            eng = getattr(self, 'note_expression_engine', None)
            if eng is None:
                return
            eng.set_enabled(bool(enabled))
            try:
                set_value(SettingsKeys().ui_pianoroll_note_expressions_enabled, bool(enabled))
            except Exception:
                pass
            self.update()
        except Exception:
            return

    def _on_expression_param_from_menu(self, key: str) -> None:
        """Menu pick from triangle quick-menu: set param + enable expressions + repaint."""
        try:
            self._set_expression_param(str(key or 'velocity'))
            self._set_expression_enabled(True)
            try:
                self.status_message.emit(f'Expressions: {key}', 900)
            except Exception:
                pass
        except Exception:
            return

    def _set_expression_param(self, key: str) -> None:
        """Set active expression param and persist to QSettings."""
        try:
            eng = getattr(self, 'note_expression_engine', None)
            if eng is None:
                return
            eng.set_active_param(str(key or 'velocity'))
            try:
                set_value(SettingsKeys().ui_pianoroll_note_expressions_param, str(key or 'velocity'))
            except Exception:
                pass
            self.update()
        except Exception:
            return

    def wheelEvent(self, event):  # noqa: ANN001
        """Mousewheel zoom/scroll - DAW style.
        
        FIXED v0.0.19.7.20: Intuitiveres Mousewheel-Verhalten wie eine Pro-DAW/Ableton!
        
        - Plain Wheel: Scroll VERTIKAL (hoch/runter in Noten) ← HAUPTFUNKTION!
        - Shift + Wheel: Zoom HORIZONTAL (Zeit-Achse)
        - Ctrl + Wheel: Zoom VERTIKAL (Pitch-Achse)
        - Alt + Wheel: Pass through (parent)
        """
        try:
            mods = event.modifiers()
            dy = float(event.angleDelta().y())
            
            # Alt + Wheel = Let parent handle (pass through)
            if mods & Qt.KeyboardModifier.AltModifier:
                event.ignore()
                return
            
            # Ctrl + Wheel = Zoom VERTIKAL (Pitch-Achse)
            if mods & Qt.KeyboardModifier.ControlModifier:
                if dy > 0:
                    self.pixels_per_semitone = min(self.pixels_per_semitone * 1.15, 40.0)
                elif dy < 0:
                    self.pixels_per_semitone = max(self.pixels_per_semitone / 1.15, 4.0)
                self._update_canvas_size()
                self.update()
                event.accept()
                return
            
            # Shift + Wheel = Zoom HORIZONTAL (Zeit-Achse)
            if mods & Qt.KeyboardModifier.ShiftModifier:
                if dy > 0:
                    self.pixels_per_beat = min(self.pixels_per_beat * 1.15, 400.0)
                elif dy < 0:
                    self.pixels_per_beat = max(self.pixels_per_beat / 1.15, 20.0)
                self._update_canvas_size()
                self.update()
                event.accept()
                return
            
            # Plain Wheel = Scroll VERTIKAL (hoch/runter) ← HAUPTFUNKTION!
            # Let parent (QScrollArea) handle vertical scrolling
            event.ignore()  # Parent QScrollArea scrollt vertikal!
            
        except Exception:
            event.ignore()
