
# ChronoScaleStudio – Mouse Tools
# DAW-Style Edit: LMB-first, Multi-Select, Lasso, Group Move/Resize, Velocity-Edit.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, Dict, Tuple

from pydaw.notation.qt_compat import Qt, QPointF

from pydaw.notation.music.events import BaseEvent, NoteEvent, RestEvent


Role = Literal["head", "bar", "label", "vel", "rest", "unknown"]


@dataclass
class HitInfo:
    event_id: Optional[int]
    role: Role = "unknown"
    item: object | None = None
    near_resize_handle: bool = False


class BaseMouseTool:
    def __init__(self, view):
        self.view = view

    def on_press(self, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifiers):
        return

    def on_move(self, scene_pos: QPointF, buttons: Qt.MouseButtons, modifiers: Qt.KeyboardModifiers):
        return

    def on_release(self, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifiers):
        return

    def on_double_click(self, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifiers):
        return


class SelectTool(BaseMouseTool):
    """DAW-Style Select/Edit Tool.

    - Klick: Auswahl (Ctrl toggelt/addiert)
    - Drag auf Note: Move (Group, wenn Multi-Select)
    - Drag am rechten Ende: Resize (Group)
    - Drag im leeren Bereich: Lasso (Ctrl = addieren)
    - ALT+Drag (vertikal): Velocity Edit (Group)
    - Doppelklick: Properties
    """
    def __init__(self, view):
        super().__init__(view)
        self._dragging = False
        self._drag_kind: str = ""  # lasso | move_head | move_bar | resize | vel
        self._press_pos: Optional[QPointF] = None
        self._ctrl_at_press: bool = False

        self._active_id: Optional[int] = None
        self._targets: Tuple[int, ...] = tuple()
        self._origin: Dict[int, Tuple[float, float, int, int, int]] = {}  # id -> (start, dur, pitch, vel, track)

        self._did_mutate: bool = False
        self._lasso_started: bool = False

    def _snapshot_targets(self):
        self._origin.clear()
        for eid in self._targets:
            ev = self.view.sequence.get_event(eid)
            if not ev:
                continue
            pitch = int(ev.pitch) if isinstance(ev, NoteEvent) else 0
            vel = int(ev.velocity) if isinstance(ev, NoteEvent) else 0
            tid = int(getattr(ev, "track_id", 1))
            self._origin[eid] = (float(ev.start), float(ev.duration), pitch, vel, tid)

    def on_press(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return

        self._press_pos = QPointF(scene_pos)
        self._ctrl_at_press = bool(modifiers & Qt.ControlModifier)
        self._did_mutate = False
        self._lasso_started = False

        hit = self.view.hit_test(scene_pos)

        if hit.event_id is None:
            # Lasso starten
            self._drag_kind = "lasso"
            self._dragging = True
            self._lasso_started = True
            self.view.begin_lasso(scene_pos)
            return

        # Selection logic
        if self._ctrl_at_press:
            # Ctrl toggelt
            if self.view.is_selected(hit.event_id):
                self.view.remove_from_selection(hit.event_id)
            else:
                self.view.add_to_selection(hit.event_id)
        else:
            # ohne Ctrl: ersetzen, außer das Element ist bereits Teil der Multi-Selection
            if not self.view.is_selected(hit.event_id):
                self.view.set_selection({hit.event_id})
            else:
                self.view.set_primary(hit.event_id)

        self._active_id = hit.event_id

        # Determine drag targets: aktuelle Selection
        ids = tuple(sorted(self.view.selected_ids))
        if not ids:
            ids = (hit.event_id,)
            self.view.set_selection({hit.event_id})
        self._targets = ids
        self._snapshot_targets()

        ev = self.view.sequence.get_event(hit.event_id)
        if ev is None:
            return

        # ALT+Drag => Velocity (nur Notes in targets)
        if (modifiers & Qt.AltModifier) and any(isinstance(self.view.sequence.get_event(i), NoteEvent) for i in self._targets):
            self._drag_kind = "vel"
            self._dragging = True
            self.view.begin_undo_group()
            return

        # Resize handle
        if hit.role == "bar" and hit.near_resize_handle:
            self._drag_kind = "resize"
            self._dragging = True
            self.view.begin_undo_group()
            return

        if hit.role == "head":
            self._drag_kind = "move_head"
            self._dragging = True
            self.view.begin_undo_group()
            return

        self._drag_kind = "move_bar"
        self._dragging = True
        self.view.begin_undo_group()

    def on_move(self, scene_pos, buttons, modifiers):
        if not (buttons & Qt.LeftButton):
            return
        if not self._dragging or self._press_pos is None:
            return

        # Lasso update
        if self._drag_kind == "lasso":
            self.view.update_lasso(self._press_pos, scene_pos)
            return

        if not self._targets:
            return

        # Delta beats
        dx = scene_pos.x() - self._press_pos.x()
        dbeats = dx / float(self.view.beat_width)

        # quantize
        if self.view.snap_enabled:
            step = max(0.03125, float(self.view.quantize_step))
            dbeats = round(dbeats / step) * step

        # Vertical delta for move_head (pitch delta)
        dpitch = 0
        if self._drag_kind == "move_head" and self._active_id is not None:
            active_origin = self._origin.get(self._active_id)
            if active_origin:
                _, _, opitch, _, _ = active_origin
                # Pitch anhand absoluten Y → track ableiten → pitch
                pitch, _tid = self.view.y_to_pitch_and_track(scene_pos.y())
                dpitch = int(pitch) - int(opitch)

        if self._drag_kind in ("move_head", "move_bar"):
            for eid in self._targets:
                ev = self.view.sequence.get_event(eid)
                if not ev:
                    continue
                ostart, odur, op, ov, ot = self._origin.get(eid, (ev.start, ev.duration, 0, 0, int(getattr(ev,"track_id",1))))
                ev.start = max(0.0, float(ostart) + float(dbeats))
                # group pitch shift only for note events (move_head)
                if self._drag_kind == "move_head" and isinstance(ev, NoteEvent):
                    ev.pitch = max(0, min(127, int(op) + dpitch))
                    try:
                        ev.pitch = self.view._apply_scale_constraint(int(ev.pitch))
                    except Exception:
                        pass
                self._did_mutate = True

            self.view.update_event_geometry_batch(self._targets)
            return

        if self._drag_kind == "resize":
            step = max(0.03125, float(self.view.quantize_step))
            for eid in self._targets:
                ev = self.view.sequence.get_event(eid)
                if not ev:
                    continue
                ostart, odur, op, ov, ot = self._origin.get(eid, (ev.start, ev.duration, 0, 0, int(getattr(ev,"track_id",1))))
                ev.duration = max(step, float(odur) + float(dbeats))
                self._did_mutate = True
            self.view.update_event_geometry_batch(self._targets)
            return

        if self._drag_kind == "vel":
            # dy: up -> louder
            dy = self._press_pos.y() - scene_pos.y()
            delta = int(dy / 2.5)
            for eid in self._targets:
                ev = self.view.sequence.get_event(eid)
                if not isinstance(ev, NoteEvent):
                    continue
                ostart, odur, op, ov, ot = self._origin.get(eid, (ev.start, ev.duration, ev.pitch, ev.velocity, int(getattr(ev,"track_id",1))))
                ev.velocity = max(1, min(127, int(ov) + delta))
                self._did_mutate = True
            self.view.update_event_geometry_batch(self._targets)
            return

    def on_release(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return

        if self._drag_kind == "lasso" and self._lasso_started and self._press_pos is not None:
            rect_ids = self.view.finish_lasso(self._press_pos, scene_pos)
            if modifiers & Qt.ControlModifier:
                # Additive lasso
                self.view.add_many_to_selection(rect_ids)
            else:
                self.view.set_selection(set(rect_ids))
            self.view.redraw_events()
        else:
            self.view.end_undo_group(commit=self._did_mutate)
            if self._did_mutate:
                # einmaliger Full-Redraw am Ende (Ties/Background/Grid) – während Drag bleiben Scrollbars stabil
                self.view.redraw_events()

        # reset
        self._dragging = False
        self._drag_kind = ""
        self._press_pos = None
        self._active_id = None
        self._targets = tuple()
        self._origin.clear()
        self._did_mutate = False
        self._lasso_started = False

    def on_double_click(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return
        hit = self.view.hit_test(scene_pos)
        if hit.event_id is not None:
            self.view.set_selection({hit.event_id})
            self.view.open_event_properties_dialog(hit.event_id)


class NoteDrawTool(BaseMouseTool):
    def on_press(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return
        start = self.view.x_to_beat(scene_pos.x())
        duration = max(float(self.view.quantize_step), float(self.view.get_effective_duration()))
        midi, track_id = self.view.y_to_pitch_and_track(scene_pos.y())
        try:
            midi = int(midi) + int(self.view.get_accidental_offset())
        except Exception:
            midi = int(midi)
        try:
            midi = int(self.view._apply_scale_constraint(int(midi)))
        except Exception:
            midi = int(midi)
        ev = self.view.sequence.add_note(
            pitch=midi,
            start=start,
            duration=duration,
            velocity=self.view.current_velocity,
            track_id=track_id,
        )
        self.view.set_selection({ev.id})
        self.view.end_undo_group(commit=True)  # no-op if not begun
        self.view.commit_undo_checkpoint()
        self.view.redraw_events()
        self.view.preview_note(midi, self.view.current_velocity)


class RestDrawTool(BaseMouseTool):
    def on_press(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return
        start = self.view.x_to_beat(scene_pos.x())
        duration = max(float(self.view.quantize_step), float(self.view.get_effective_duration()))
        _midi, track_id = self.view.y_to_pitch_and_track(scene_pos.y())
        ev = self.view.sequence.add_rest(start=start, duration=duration, track_id=track_id)
        self.view.set_selection({ev.id})
        self.view.commit_undo_checkpoint()
        self.view.redraw_events()


class EraseTool(BaseMouseTool):
    def on_press(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return
        hit = self.view.hit_test(scene_pos)
        if hit.event_id is not None:
            self.view.sequence.remove_event(hit.event_id)
            self.view.remove_from_selection(hit.event_id)
            self.view.commit_undo_checkpoint()
            self.view.redraw_events()


class TieTool(BaseMouseTool):
    def on_press(self, scene_pos, button, modifiers):
        if button != Qt.LeftButton:
            return
        hit = self.view.hit_test(scene_pos)
        if hit.event_id is None:
            return
        ev = self.view.sequence.get_event(hit.event_id)
        if isinstance(ev, NoteEvent):
            ev.tie_to_next = not bool(ev.tie_to_next)
            self.view.commit_undo_checkpoint()
            self.view.redraw_events()
