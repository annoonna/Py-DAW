"""Notation editing tools (WIP).

Implements **Task 4 (Draw-Tool)** from ``PROJECT_DOCS/progress/TODO.md``.

Scope / Philosophy
------------------
This is intentionally minimal and pragmatic:

- We only implement the first editable action: **Draw a note** by click.
- Undo integration is supported via :meth:`pydaw.services.project_service.ProjectService.commit_midi_notes_edit`.
- The conversion from mouse position to musical data is kept simple:
  - X axis -> beat (snapped to project grid)
  - Y axis -> staff line/space -> diatonic pitch (natural notes for now)

Future tasks (TODO.md): Erase-Tool, Select-Tool, shortcuts, bidirectional sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QPointF, Qt

from pydaw.model.midi import MidiNote

from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value
from pydaw.music.scales import allowed_pitch_classes, apply_scale_constraint


def snap_beats_from_div(division: str) -> float:
    """Return beat grid size for a division string like "1/16"."""

    mapping = {
        "1/4": 1.0,
        "1/8": 0.5,
        "1/16": 0.25,
        "1/32": 0.125,
        "1/64": 0.0625,
    }
    return float(mapping.get(str(division), 0.25))


def snap_to_grid(value: float, step: float) -> float:
    """Snap a float value to a grid step."""

    s = float(step) if float(step) > 1e-9 else 0.25
    return round(float(value) / s) * s


@dataclass
class ToolResult:
    """Optional feedback from tool actions."""

    status: str = ""
    changed: bool = False


class NotationTool:
    """Base class for notation interaction tools."""

    name: str = "Tool"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        return ToolResult("", False)


class DrawTool(NotationTool):
    """Draw notes by clicking on the staff."""

    name = "Draw"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        # Only left click draws
        if button != Qt.MouseButton.LeftButton:
            return ToolResult("", False)

        clip_id = getattr(view, "clip_id", None)
        if not clip_id:
            return ToolResult("Kein MIDI-Clip ausgewählt.", False)

        ps = getattr(view, "project_service", None)
        if ps is None:
            return ToolResult("ProjectService fehlt.", False)

        # X -> beat
        beat = view.scene_x_to_beat(float(scene_pos.x()))
        snap_div = str(getattr(ps.ctx.project, "snap_division", "1/16") or "1/16")
        snap = snap_beats_from_div(snap_div)
        beat = max(0.0, snap_to_grid(beat, snap))

        # Y -> staff_line -> pitch
        staff_line = view.scene_y_to_staff_line(float(scene_pos.y()))

        # Read input state from the host view (NotationPalette).
        st = getattr(view, "input_state", None)
        try:
            accidental = int(getattr(st, "accidental", 0)) if st is not None else 0
        except Exception:
            accidental = 0

        # Keyboard modifier shortcuts for accidentals (v0.0.20.454):
        # Shift+Click = Sharp (+1), Alt+Click = Flat (-1)
        # These OVERRIDE the palette setting for this note.
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            accidental = 1  # Sharp / Kreuz
        elif modifiers & Qt.KeyboardModifier.AltModifier:
            accidental = -1  # Flat / Be

        pitch = view.staff_line_to_pitch(int(staff_line), accidental=accidental)

        # Scale constraint (optional): Snap vs Reject
        keys = SettingsKeys()
        if bool(get_value(keys.scale_enabled, False)):
            cat = str(get_value(keys.scale_category, ""))
            name = str(get_value(keys.scale_name, ""))
            root = int(get_value(keys.scale_root_pc, 0) or 0)
            mode = str(get_value(keys.scale_mode, "snap") or "snap")
            # FIX: Use keyword arguments (function requires them!)
            allowed = allowed_pitch_classes(category=cat, name=name, root_pc=root)
            new_pitch = apply_scale_constraint(int(pitch), allowed, mode)
            if new_pitch is None:
                return ToolResult("Scale: Note rejected (out of scale)", False)
            pitch = int(new_pitch)

        # Duration: from palette (1/1..1/64 + dotted). Fallback to grid-step (snap).
        try:
            duration = float(st.duration_beats()) if st is not None else float(snap)
        except Exception:
            duration = float(snap)
        duration = max(float(snap), float(duration))  # never shorter than one grid step

        # Rests are stored as notation marks (MVP). They do not affect MIDI playback.
        try:
            is_rest = bool(getattr(st, "is_rest", False)) if st is not None else False
        except Exception:
            is_rest = False

        # Undo snapshot (only for MIDI edits)
        before = ps.snapshot_midi_notes(str(clip_id))

        if is_rest and hasattr(ps, "add_notation_mark"):
            ps.add_notation_mark(str(clip_id), beat=float(beat), mark_type="rest", data={"duration_beats": float(duration)})
            return ToolResult(f"Pause gesetzt @ {beat:.3f} (Dauer {duration:.3f} beats)", True)

        ps.add_midi_note(str(clip_id), pitch=int(pitch), start_beats=float(beat), length_beats=float(duration), velocity=100)
        ps.commit_midi_notes_edit(str(clip_id), before, "Draw Note (Notation)")

        # Ornament marker (MVP): store as notation mark (e.g. trill)
        try:
            orn = str(getattr(st, "ornament", "") or "") if st is not None else ""
        except Exception:
            orn = ""
        if orn and hasattr(ps, "add_notation_mark"):
            ps.add_notation_mark(str(clip_id), beat=float(beat), mark_type="ornament", data={"ornament": orn, "pitch": int(pitch)})
        # Note name for status
        try:
            from pydaw.ui.notation.colors import note_name as _nn
            nn = _nn(int(pitch), german=True, with_octave=True)
        except Exception:
            nn = str(pitch)
        return ToolResult(f"Note hinzugefügt: {nn} (pitch={pitch}, beat={beat:.3f}, Grid {snap_div})", True)


def _nearest_note_index(
    view,
    notes: list[MidiNote],
    *,
    target_beat: float,
    target_staff_line: int,
    snap_step: float,
) -> Optional[int]:
    """Pick the most likely note under the cursor.

    We keep this deliberately simple for MVP:
    - Prefer notes whose *staff line* matches (±1).
    - Prefer notes whose start beat is close to the click (within ~0.75 grid).

    Returns:
        Index into ``notes`` or ``None`` if nothing is close enough.
    """

    if not notes:
        return None

    try:
        snap = float(snap_step) if float(snap_step) > 1e-9 else 0.25
    except Exception:
        snap = 0.25

    pitch_to_staff = getattr(view, "_pitch_to_staff_line", None)
    best_idx: Optional[int] = None
    best_score = 1e9

    for i, n in enumerate(list(notes)):
        try:
            sb = float(getattr(n, "start_beats", 0.0))
            p = int(getattr(n, "pitch", 60))
        except Exception:
            continue

        # Prefer view's internal mapping (keeps behavior identical to rendering).
        if callable(pitch_to_staff):
            try:
                sl = int(pitch_to_staff(p))
            except Exception:
                sl = 0
        else:
            # Fallback: use diatonic staff position.
            try:
                tmp = MidiNote(pitch=p, start_beats=0.0, length_beats=1.0, velocity=100)
                line, octv = tmp.to_staff_position()
                # Convert to the same half-step index that NotationView uses.
                diat = int(octv) * 7 + int(line)
                e4_ref = int(4) * 7 + int(2)  # E4 bottom line
                sl = int(diat - e4_ref)
            except Exception:
                continue

        d_beat = abs(sb - float(target_beat))
        d_line = abs(int(sl) - int(target_staff_line))

        # Hard gate so we don't delete the wrong note.
        if d_beat > snap * 0.75:
            continue
        if d_line > 1:
            continue

        # Weighted score: time distance dominates, line distance breaks ties.
        score = (d_beat / max(1e-9, snap)) + (d_line * 0.35)
        if score < best_score:
            best_score = score
            best_idx = int(i)

    return best_idx


class EraseTool(NotationTool):
    """Erase notes by clicking on them.

    MVP behavior:
    - Deletes the closest note at the clicked *beat* (within the current snap grid)
      and *staff line* (±1).
    - Uses the ProjectService undo stack via ``commit_midi_notes_edit``.
    """

    name = "Erase"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        # Erase expects either left click (if the tool is active) or right click (view routes it).
        if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return ToolResult("", False)

        clip_id = getattr(view, "clip_id", None)
        if not clip_id:
            return ToolResult("Kein MIDI-Clip ausgewählt.", False)

        ps = getattr(view, "project_service", None)
        if ps is None:
            return ToolResult("ProjectService fehlt.", False)

        try:
            notes = list(ps.get_midi_notes(str(clip_id)))
        except Exception:
            notes = []
        if not notes:
            return ToolResult("Keine Noten zum Löschen.", False)

        # Beat and grid
        beat = view.scene_x_to_beat(float(scene_pos.x()))
        snap_div = str(getattr(ps.ctx.project, "snap_division", "1/16") or "1/16")
        snap = snap_beats_from_div(snap_div)
        beat = max(0.0, snap_to_grid(float(beat), float(snap)))

        # Staff line
        staff_line = int(view.scene_y_to_staff_line(float(scene_pos.y())))

        idx = _nearest_note_index(view, notes, target_beat=float(beat), target_staff_line=int(staff_line), snap_step=float(snap))
        if idx is None:
            return ToolResult("Keine Note an dieser Position gefunden.", False)

        before = ps.snapshot_midi_notes(str(clip_id))
        ps.delete_midi_note_at(str(clip_id), int(idx))
        ps.commit_midi_notes_edit(str(clip_id), before, "Erase Note (Notation)")
        return ToolResult(f"Note gelöscht (Index {idx}, Grid {snap_div}).", True)


class SelectTool(NotationTool):
    """Select notes by clicking on them.

    Behavior:
    - **Left click** selects the closest note (clears previous selection)
    - **Ctrl+Click** toggles note in multi-selection
    - **Shift+Click** range select (from last selected to clicked note)
    - Clicking empty space clears the selection

    The view is responsible for rendering the selection state.
    """

    name = "Select"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        if button != Qt.MouseButton.LeftButton:
            return ToolResult("", False)

        clip_id = getattr(view, "clip_id", None)
        if not clip_id:
            return ToolResult("Kein MIDI-Clip ausgewählt.", False)

        ps = getattr(view, "project_service", None)
        if ps is None:
            return ToolResult("ProjectService fehlt.", False)

        try:
            notes = list(ps.get_midi_notes(str(clip_id)))
        except Exception:
            notes = []

        if not notes:
            # Clear selection if the clip is empty.
            try:
                view.clear_selection()
            except Exception:
                pass
            return ToolResult("Keine Noten im Clip.", False)

        # Beat and grid (reuse the same heuristic as EraseTool so selection feels consistent)
        beat = view.scene_x_to_beat(float(scene_pos.x()))
        snap_div = str(getattr(ps.ctx.project, "snap_division", "1/16") or "1/16")
        snap = snap_beats_from_div(snap_div)
        beat = max(0.0, snap_to_grid(float(beat), float(snap)))

        staff_line = int(view.scene_y_to_staff_line(float(scene_pos.y())))
        idx = _nearest_note_index(view, notes, target_beat=float(beat), target_staff_line=int(staff_line), snap_step=float(snap))

        # Check modifiers for multi-select
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if idx is None:
            # Clicked empty space
            if not ctrl and not shift:
                try:
                    view.clear_selection()
                except Exception:
                    pass
                return ToolResult("Auswahl gelöscht.", False)
            return ToolResult("", False)

        clicked_note = notes[idx]

        # Shift+Click: Range select
        if shift:
            try:
                # Get current selection
                selected = view.get_selected_notes()
                if selected:
                    # Find range between last selected and clicked note
                    last_note = selected[-1]
                    start_beat = min(last_note.start_beats, clicked_note.start_beats)
                    end_beat = max(last_note.start_beats + last_note.duration_beats,
                                   clicked_note.start_beats + clicked_note.duration_beats)
                    
                    # Select all notes in range
                    for n in notes:
                        if start_beat <= n.start_beats < end_beat:
                            view.select_note(n, multi=True, toggle=False)
                    
                    count = len(view.get_selected_notes())
                    return ToolResult(f"{count} Noten ausgewählt (Range)", False)
                else:
                    # No previous selection, just select clicked note
                    view.select_note(clicked_note, multi=False)
                    return ToolResult("Note ausgewählt.", False)
            except Exception:
                # Fallback to normal selection
                view.select_note(clicked_note, multi=False)
                return ToolResult("Note ausgewählt.", False)

        # Ctrl+Click: Toggle in multi-selection
        if ctrl:
            try:
                view.select_note(clicked_note, multi=True, toggle=True)
                count = len(view.get_selected_notes())
                if count > 1:
                    return ToolResult(f"{count} Noten ausgewählt", False)
                else:
                    return ToolResult("Note ausgewählt.", False)
            except Exception:
                return ToolResult("Note ausgewählt.", False)

        # Normal click: Single selection (clears previous)
        try:
            view.select_note(clicked_note, multi=False)
        except Exception:
            pass

        try:
            n = clicked_note
            return ToolResult(f"Note ausgewählt: pitch={int(getattr(n, 'pitch', 0))}, beat={float(getattr(n, 'start_beats', 0.0)):.3f}", False)
        except Exception:
            return ToolResult("Note ausgewählt.", False)


# ------------------------------------------------------------------
# Tie/Slur tools (Marker MVP)
# ------------------------------------------------------------------

class TieTool(NotationTool):
    """Create a tie between two notes (MVP marker).

    Behavior:
    - Click first note to set start.
    - Click second note (same pitch) to create a 'tie' marker.
    - Marker is stored via ProjectService.add_notation_mark and rendered by NotationView.

    This MVP does **not** change playback yet.
    """

    name = "Tie"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        if button != Qt.MouseButton.LeftButton:
            return ToolResult("", False)

        clip_id = getattr(view, "clip_id", None)
        if not clip_id:
            return ToolResult("Kein MIDI-Clip ausgewählt.", False)

        ps = getattr(view, "project_service", None)
        if ps is None:
            return ToolResult("ProjectService fehlt.", False)

        note = None
        try:
            note = view.pick_note_at(scene_pos)
        except Exception:
            note = None

        if note is None:
            # clicking empty space cancels pending tie
            try:
                if getattr(view, "_pending_connection", None):
                    view._pending_connection = None
                    view._set_temp_status("Tie abgebrochen.")
            except Exception:
                pass
            return ToolResult("", False)

        start = getattr(view, "_pending_connection", None)
        if not start or str(start.get("kind", "")) != "tie":
            # set start
            try:
                view._pending_connection = {
                    "kind": "tie",
                    "from": {
                        "beat": float(getattr(note, "start_beats", 0.0)),
                        "pitch": int(getattr(note, "pitch", 60)),
                    },
                }
                # select start note for feedback
                try:
                    view._selected_key = view._note_key(note)
                except Exception:
                    pass
                view.refresh()
            except Exception:
                pass
            return ToolResult("Tie: Startnote gewählt – Endnote anklicken.", True)

        # second click -> create tie
        try:
            a = start.get("from", {}) or {}
            p1 = int(a.get("pitch", 0))
            b1 = float(a.get("beat", 0.0))
            p2 = int(getattr(note, "pitch", 0))
            b2 = float(getattr(note, "start_beats", 0.0))
        except Exception:
            view._pending_connection = None
            return ToolResult("Tie: Fehler.", False)

        if p1 != p2:
            # ties require same pitch
            return ToolResult("Tie benötigt gleiche Tonhöhe – bitte Endnote mit gleichem Pitch wählen.", False)

        try:
            if hasattr(ps, "add_notation_mark"):
                ps.add_notation_mark(str(clip_id), beat=float(min(b1, b2)), mark_type="tie", data={"from": {"beat": b1, "pitch": p1}, "to": {"beat": b2, "pitch": p2}})
        except Exception:
            pass

        try:
            view._pending_connection = None
            view.refresh()
        except Exception:
            pass
        return ToolResult("Tie gesetzt.", True)


class SlurTool(NotationTool):
    """Create a slur between two notes (MVP marker).

    Behavior:
    - Click first note to set start.
    - Click second note to create a 'slur' marker.

    This MVP does **not** change playback yet.
    """

    name = "Slur"

    def handle_mouse_press(self, view, scene_pos: QPointF, button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> ToolResult:
        if button != Qt.MouseButton.LeftButton:
            return ToolResult("", False)

        clip_id = getattr(view, "clip_id", None)
        if not clip_id:
            return ToolResult("Kein MIDI-Clip ausgewählt.", False)

        ps = getattr(view, "project_service", None)
        if ps is None:
            return ToolResult("ProjectService fehlt.", False)

        note = None
        try:
            note = view.pick_note_at(scene_pos)
        except Exception:
            note = None

        if note is None:
            try:
                if getattr(view, "_pending_connection", None):
                    view._pending_connection = None
                    view._set_temp_status("Slur abgebrochen.")
            except Exception:
                pass
            return ToolResult("", False)

        start = getattr(view, "_pending_connection", None)
        if not start or str(start.get("kind", "")) != "slur":
            try:
                view._pending_connection = {
                    "kind": "slur",
                    "from": {
                        "beat": float(getattr(note, "start_beats", 0.0)),
                        "pitch": int(getattr(note, "pitch", 60)),
                    },
                }
                try:
                    view._selected_key = view._note_key(note)
                except Exception:
                    pass
                view.refresh()
            except Exception:
                pass
            return ToolResult("Slur: Startnote gewählt – Endnote anklicken.", True)

        try:
            a = start.get("from", {}) or {}
            b1 = float(a.get("beat", 0.0))
            p1 = int(a.get("pitch", 0))
            b2 = float(getattr(note, "start_beats", 0.0))
            p2 = int(getattr(note, "pitch", 0))
        except Exception:
            view._pending_connection = None
            return ToolResult("Slur: Fehler.", False)

        try:
            if hasattr(ps, "add_notation_mark"):
                ps.add_notation_mark(str(clip_id), beat=float(min(b1, b2)), mark_type="slur", data={"from": {"beat": b1, "pitch": p1}, "to": {"beat": b2, "pitch": p2}})
        except Exception:
            pass

        try:
            view._pending_connection = None
            view.refresh()
        except Exception:
            pass
        return ToolResult("Slur gesetzt.", True)
