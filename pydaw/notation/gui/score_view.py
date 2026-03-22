# ChronoScaleStudio – Notendarstellung (DAW-Style Editing)
# Multi-Track, Multi-Select + Lasso, Group Move/Resize, Undo/Redo, Cut/Copy/Paste.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Iterable, List, Tuple

from pydaw.notation.qt_compat import (
    QGraphicsView, QGraphicsScene, QMenu,
    QDialog, QFormLayout, QDoubleSpinBox, QSpinBox, QDialogButtonBox, QMessageBox, QApplication
)
from pydaw.notation.qt_compat import QPen, QBrush, QFont, QPainter, QKeySequence, QPixmap
from pydaw.notation.qt_compat import Qt, QPointF, QRectF, Signal

from pydaw.notation.music.notes import midi_to_name
from pydaw.notation.music.sequence import NoteSequence
from pydaw.notation.music.events import NoteEvent, RestEvent, BaseEvent

from pydaw.notation.audio.direct_synth import SYNTH
from pydaw.notation.gui.undo_stack import UndoStack
from pydaw.notation.gui.tools.mouse_tools import SelectTool, NoteDrawTool, RestDrawTool, EraseTool, TieTool, HitInfo
from pydaw.notation.gui.symbol_palette import SymbolPaletteWidget

import time


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


class ScoreView(QGraphicsView):
    zoomChanged = Signal(float)
    playheadChanged = Signal(float)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setMinimumHeight(360)
        self.setRenderHint(QPainter.Antialiasing)

        # Editor-like layout: no centering
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)

        # Scrollbars: DAW-Standard – Horizontal immer sichtbar, vertikal nach Bedarf.
        # Wichtig: AlwaysOn verhindert „sichtbar/unsichtbar“-Umschalten bei Zoom/Redraw (führt zu Sprüngen).
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Zoom
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._zoom = 1.0

        # Data
        self.sequence = NoteSequence()

        # UI/Editing state
        self.mode = "note"           # note | rest | erase | select | tie
        self.current_duration = 1.0  # Beats
        # Punktierung (0..2) und Vorzeichen-Offset für Neueingaben (♭=-1, none=0, ♯=+1, ♮=2)
        # (♮ bedeutet hier: "neutral" -> Offset=0, aber es ist UI-seitig sichtbar.)
        self.current_dots: int = 0
        self.current_accidental: int = 0
        self.quantize_step = 0.25    # Beats
        self.snap_enabled = True
        self.current_velocity = 90   # 1..127

        # Skalenrestriktion (DAW-Edit): Standard AUS (freie Eingabe), optional aktivierbar.
        self.scale_restriction_enabled: bool = False
        self.scale_system: str = "Keine Einschränkung"
        self.scale_name: str = "Alle Noten"
        self._allowed_pitch_classes: set[int] = set(range(12))  # 0..11
        self.custom_scale_pcs: set[int] = set(range(12))  # Custom-Scale (User) – initial frei

        # Tracks
        self.active_track_id = self.sequence.tracks[0].id if self.sequence.tracks else 1

        # Master Volume
        self._master_volume = 100
        SYNTH.set_channel_volume(self._master_volume)

        # View geometry
        self.left_margin = 90
        self.timeline_x0 = 140
        self.beat_width = 60
        self.total_beats = 16

        # Track layout
        self.track_top = 80
        self.track_spacing = 180   # px between staves
        self.staff_line_gap = 10

        # Items / mapping
        self.event_items: List[int] = []       # ids in playback order
        self._id_to_items = {}                 # id -> list[QGraphicsItem]
        self._id_to_bbox = {}                  # id -> QRectF (approx)

        # Selection
        self.selected_ids: set[int] = set()
        self.primary_selected_id: Optional[int] = None

        # Playback / Playhead (DAW-Style)
        self.playing_event_id: Optional[int] = None
        self.playhead_beat: float = 0.0
        self.loop_a_beat: Optional[float] = None
        self.loop_b_beat: Optional[float] = None

        # Auto-Follow/Scroll Stabilität
        # Problem: ensureVisible() kann bei Zoom + vielen Spuren vertikal/horizontal "springen".
        # Lösung: Follow-Logik nur horizontal, nur wenn nötig, und während User-Interaktion/Zoom kurz aussetzen.
        self.auto_follow_playhead: bool = True
        self._user_interacting: bool = False
        self._suppress_autofollow_until: float = 0.0
        self._last_follow_center_x: float | None = None

        # Background image (mitscrollend, weil Scene-Item)
        self._bg_path: Optional[str] = None
        self._bg_pixmap: Optional[QPixmap] = None
        self._bg_item = None
        self._bg_scaled_for: tuple[int, int] | None = None

        # Playhead item
        self._playhead_item = None

        # Cached staff bounds (for playhead line)
        self._grid_top_y = 0.0
        self._grid_bottom_y = 0.0

        # Clipboard (internal JSON)
        self._clipboard_cache: Optional[dict] = None
        self.paste_cursor_beat: float = 0.0

        # Lasso
        self._lasso_item = None

        # Undo
        self.undo = UndoStack(self.serialize_state, self.deserialize_state, max_depth=250)
        self._undo_group_active = False

        # Mouse Tools
        self._tools = {
            "select": SelectTool(self),
            "note": NoteDrawTool(self),
            "rest": RestDrawTool(self),
            "erase": EraseTool(self),
            "tie": TieTool(self),
        }
        self._active_tool = self._tools["note"]

        # Initial draw + Undo init
        self.redraw_events()
        self.undo.init()

    # ---------- Toolbox / external ----------
    def set_mode(self, mode: str):
        self.mode = mode
        self._active_tool = self._tools.get(mode, self._tools["note"])

    def set_duration(self, beats: float):
        self.current_duration = float(beats)

    def set_dots(self, dots: int):
        self.current_dots = max(0, min(2, int(dots)))

    def set_accidental(self, accidental: int):
        # -1 flat, 0 none, +1 sharp, 2 natural (special marker)
        self.current_accidental = int(accidental)

    def get_effective_duration(self) -> float:
        """Basisdauer + Punktierung (0..2)."""
        base = float(self.current_duration)
        dots = int(self.current_dots)
        if dots <= 0:
            return base
        if dots == 1:
            return base * 1.5
        return base * 1.75

    def get_accidental_offset(self) -> int:
        # Natural ist nur ein Marker -> kein Offset.
        if int(self.current_accidental) == 2:
            return 0
        return int(self.current_accidental)

    def set_quantize_step(self, beats: float):
        self.quantize_step = float(beats)

    def set_snap(self, enabled: bool):
        self.snap_enabled = bool(enabled)

    def set_master_volume(self, v: int):
        self._master_volume = _clamp_int(v, 0, 127)
        SYNTH.set_channel_volume(self._master_volume)

    def get_master_volume(self) -> int:
        return int(self._master_volume)

    def set_active_track(self, track_id: int):
        if self.sequence.get_track(track_id):
            self.active_track_id = int(track_id)

    # ---------- Zoom Methods (wichtig für Toolbox!) ----------
    def zoom_in(self):
        """Zoomt hinein (vergrößert die Ansicht)"""
        self.set_zoom(self._zoom * 1.15)

    def zoom_out(self):
        """Zoomt heraus (verkleinert die Ansicht)"""
        self.set_zoom(self._zoom / 1.15)

    def zoom_reset(self):
        """Setzt Zoom auf 100% zurück"""
        self.set_zoom(1.0)

    # ---------- Undo helpers ----------
    def begin_undo_group(self):
        self._undo_group_active = True

    def end_undo_group(self, commit: bool):
        if commit:
            self.commit_undo_checkpoint()
        self._undo_group_active = False

    def commit_undo_checkpoint(self):
        if self._undo_group_active:
            return
        self.undo.push_checkpoint()

    # ---------- Serialize / Deserialize ----------
    def serialize_state(self) -> dict:
        return {
            "sequence": self.sequence.to_dict(),
            "view": {
                "mode": self.mode,
                "current_duration": self.current_duration,
                "current_dots": int(self.current_dots),
                "current_accidental": int(self.current_accidental),
                "quantize_step": self.quantize_step,
                "snap_enabled": self.snap_enabled,
                "current_velocity": self.current_velocity,
                "master_volume": self._master_volume,
                "total_beats": self.total_beats,
                "zoom": self._zoom,
                "active_track_id": self.active_track_id,
                "paste_cursor_beat": self.paste_cursor_beat,
                "playhead_beat": self.playhead_beat,
                "loop_a_beat": self.loop_a_beat,
                "loop_b_beat": self.loop_b_beat,
                "bg_path": self._bg_path,
                "scale_restriction_enabled": self.scale_restriction_enabled,
                "scale_system": self.scale_system,
                "scale_name": self.scale_name,
                "custom_scale_pcs": sorted(int(x) for x in self.custom_scale_pcs),
            },
        }

    def deserialize_state(self, state: dict):
        try:
            self.sequence = NoteSequence.from_dict(state.get("sequence", {}))
        except Exception:
            pass

        view = state.get("view", {}) or {}
        self.mode = str(view.get("mode", self.mode))
        self.current_duration = float(view.get("current_duration", self.current_duration))
        self.current_dots = int(view.get("current_dots", self.current_dots))
        self.current_accidental = int(view.get("current_accidental", self.current_accidental))
        self.quantize_step = float(view.get("quantize_step", self.quantize_step))
        self.snap_enabled = bool(view.get("snap_enabled", self.snap_enabled))
        self.current_velocity = int(view.get("current_velocity", self.current_velocity))
        self._master_volume = _clamp_int(int(view.get("master_volume", self._master_volume)), 0, 127)
        SYNTH.set_channel_volume(self._master_volume)
        self.total_beats = int(view.get("total_beats", self.total_beats))
        self.active_track_id = int(view.get("active_track_id", self.active_track_id))
        self.paste_cursor_beat = float(view.get("paste_cursor_beat", self.paste_cursor_beat))

        self.playhead_beat = float(view.get("playhead_beat", self.playhead_beat))
        self.loop_a_beat = view.get("loop_a_beat", self.loop_a_beat)
        self.loop_b_beat = view.get("loop_b_beat", self.loop_b_beat)
        self._bg_path = view.get("bg_path", self._bg_path)
        # Scale / Restriction
        try:
            self.scale_restriction_enabled = bool(view.get("scale_restriction_enabled", self.scale_restriction_enabled))
        except Exception:
            self.scale_restriction_enabled = False
        self.scale_system = str(view.get("scale_system", self.scale_system) or self.scale_system)
        self.scale_name = str(view.get("scale_name", self.scale_name) or self.scale_name)
        try:
            pcs = view.get("custom_scale_pcs", None)
            if isinstance(pcs, list):
                self.custom_scale_pcs = set(int(x) % 12 for x in pcs)
        except Exception:
            pass
        self._recompute_allowed_pitch_classes()
        try:
            if self._bg_path:
                pm = QPixmap(str(self._bg_path))
                self._bg_pixmap = pm if not pm.isNull() else None
            else:
                self._bg_pixmap = None
        except Exception:
            self._bg_pixmap = None

        self._active_tool = self._tools.get(self.mode, self._tools["note"])

        self.selected_ids.clear()
        self.primary_selected_id = None

        self._zoom = float(view.get("zoom", self._zoom))
        self._apply_zoom()

        self.redraw_events()

    # ---------- Track layout helpers ----------
    def staff_y_for_track(self, track_id: int) -> float:
        for i, t in enumerate(self.sequence.tracks):
            if t.id == track_id:
                return self.track_top + i * self.track_spacing
        return self.track_top

    def clef_center_pitch(self, track_id: int) -> int:
        t = self.sequence.get_track(track_id)
        if t and t.clef == "bass":
            return 48  # C3
        return 60      # C4

    def midi_to_y(self, midi: int, track_id: int) -> float:
        staff_y = self.staff_y_for_track(track_id)
        center = self.clef_center_pitch(track_id)
        return staff_y + 20 - (int(midi) - center) * 3

    def y_to_pitch_and_track(self, y: float) -> tuple[int, int]:
        if not self.sequence.tracks:
            return 60, 1
        best_dist = float('inf')
        best = None
        for i, t in enumerate(self.sequence.tracks):
            staff_y = self.track_top + i * self.track_spacing
            mid_y = staff_y + 20
            dist = abs(y - mid_y)
            if dist < best_dist:
                best_dist = dist
                best = t
        track_id = best.id if best else self.active_track_id
        staff_y = self.staff_y_for_track(track_id)
        center = self.clef_center_pitch(track_id)
        midi = round(center - (y - (staff_y + 20)) / 3)
        midi = _clamp_int(midi, 0, 127)
        midi = self._apply_scale_constraint(midi)
        return midi, int(track_id)

    

    # ---------- Scale Restriction (optional, Standard AUS) ----------
    def set_scale_restriction_enabled(self, enabled: bool):
        self.scale_restriction_enabled = bool(enabled)

    def get_scale_restriction_enabled(self) -> bool:
        return bool(self.scale_restriction_enabled)

    def set_scale_selection(self, system: str, name: str):
        self.scale_system = str(system or "Keine Einschränkung")
        self.scale_name = str(name or "Alle Noten")
        self._recompute_allowed_pitch_classes()

    def set_custom_scale_pcs(self, pcs: Iterable[int]):
        try:
            self.custom_scale_pcs = set(int(x) % 12 for x in pcs)
        except Exception:
            self.custom_scale_pcs = set(range(12))
        self._recompute_allowed_pitch_classes()

    def _recompute_allowed_pitch_classes(self):
        # Free / no restriction
        sys_l = (self.scale_system or "").strip().lower()
        name_l = (self.scale_name or "").strip().lower()
        if sys_l in ("keine einschränkung", "free", "none") or name_l in ("alle noten", "keine einschränkung"):
            self._allowed_pitch_classes = set(range(12))
            return

        # Custom
        if sys_l.startswith("custom") or name_l.startswith("custom"):
            pcs = set(int(x) % 12 for x in (self.custom_scale_pcs or set()))
            self._allowed_pitch_classes = pcs if pcs else set(range(12))
            return

        # From DB
        try:
            from scales.database import SCALE_DB
            sc = SCALE_DB.get_scale(self.scale_system, self.scale_name)
            if sc and isinstance(sc, dict) and "intervals_cent" in sc:
                pcs = set(int(round(float(c) / 100.0)) % 12 for c in (sc.get("intervals_cent") or []))
                self._allowed_pitch_classes = pcs if pcs else set(range(12))
            else:
                self._allowed_pitch_classes = set(range(12))
        except Exception:
            self._allowed_pitch_classes = set(range(12))

    def _apply_scale_constraint(self, midi: int) -> int:
        midi = _clamp_int(int(midi), 0, 127)
        if not self.scale_restriction_enabled:
            return midi
        allowed = set(self._allowed_pitch_classes or set(range(12)))
        if len(allowed) >= 12:
            return midi
        pc = midi % 12
        if pc in allowed:
            return midi
        # Nearest semitone search (tie -> up)
        for d in range(1, 13):
            up = midi + d
            if up <= 127 and (up % 12) in allowed:
                return up
            down = midi - d
            if down >= 0 and (down % 12) in allowed:
                return down
        return midi

    def step_pitch_in_scale(self, midi: int, direction: int) -> int:
        midi = _clamp_int(int(midi), 0, 127)
        step = 1 if int(direction) >= 0 else -1
        if not self.scale_restriction_enabled:
            return _clamp_int(midi + step, 0, 127)

        allowed = set(self._allowed_pitch_classes or set(range(12)))
        if len(allowed) >= 12:
            return _clamp_int(midi + step, 0, 127)

        cur = midi
        for _ in range(1, 128):
            cur = _clamp_int(cur + step, 0, 127)
            if (cur % 12) in allowed:
                return cur
            if cur in (0, 127):
                break
        return midi


# ---------- Beat mapping ----------
    def x_to_beat(self, x: float) -> float:
        beat = (x - self.timeline_x0) / max(1.0, self.beat_width)
        if self.snap_enabled:
            step = max(0.03125, float(self.quantize_step))
            beat = round(beat / step) * step
        return max(0.0, float(beat))

    def beat_to_x(self, beat: float) -> float:
        return self.timeline_x0 + float(beat) * self.beat_width

    # ---------- Selection API ----------
    def is_selected(self, event_id: int) -> bool:
        return int(event_id) in self.selected_ids

    def set_primary(self, event_id: int | None):
        self.primary_selected_id = int(event_id) if event_id is not None else None

    def set_selection(self, ids: set[int]):
        self.selected_ids = set(int(x) for x in ids if x is not None)
        self.primary_selected_id = next(iter(self.selected_ids), None)

    def add_to_selection(self, event_id: int):
        self.selected_ids.add(int(event_id))
        self.primary_selected_id = int(event_id)

    def add_many_to_selection(self, ids: Iterable[int]):
        for i in ids:
            self.selected_ids.add(int(i))
        if self.primary_selected_id is None and self.selected_ids:
            self.primary_selected_id = next(iter(self.selected_ids))

    def remove_from_selection(self, event_id: int):
        self.selected_ids.discard(int(event_id))
        if self.primary_selected_id == int(event_id):
            self.primary_selected_id = next(iter(self.selected_ids), None)

    # ---------- DAW Edit Ops (Split/Glue/Humanize/Quantize/Transpose) ----------
    def get_selected_events(self) -> list:
        out = []
        for eid in sorted(self.selected_ids):
            ev = self.sequence.get_event(int(eid))
            if ev is not None:
                out.append(ev)
        return out

    def quantize_selected(self, also_duration: bool = False):
        if not self.selected_ids:
            return
        step = max(0.03125, float(self.quantize_step))
        self.begin_undo_group()
        try:
            for ev in self.get_selected_events():
                ev.start = max(0.0, round(float(ev.start) / step) * step)
                if also_duration:
                    ev.duration = max(step, round(float(ev.duration) / step) * step)
        finally:
            self.end_undo_group(commit=True)
        self.redraw_events()

    def humanize_selected(self, timing_range_beats: float = 0.03, velocity_range: int = 6):
        # kleine DAW-typische Zufallsvariationen
        if not self.selected_ids:
            return
        import random

        self.begin_undo_group()
        try:
            for ev in self.get_selected_events():
                ev.start = max(0.0, float(ev.start) + random.uniform(-timing_range_beats, timing_range_beats))
                if isinstance(ev, NoteEvent):
                    ev.velocity = _clamp_int(int(ev.velocity) + random.randint(-abs(int(velocity_range)), abs(int(velocity_range))), 1, 127)
        finally:
            self.end_undo_group(commit=True)
        self.redraw_events()

    def transpose_selected(self, semitones: int):
        if not self.selected_ids:
            return
        st = int(semitones)
        if st == 0:
            return
        self.begin_undo_group()
        try:
            for ev in self.get_selected_events():
                if isinstance(ev, NoteEvent):
                    ev.pitch = _clamp_int(int(ev.pitch) + st, 0, 127)
                    ev.pitch = self._apply_scale_constraint(int(ev.pitch))
        finally:
            self.end_undo_group(commit=True)
        self.redraw_events()

    def split_selected_at_playhead(self):
        # split an Playhead-Position – nur wenn Playhead innerhalb liegt
        if not self.selected_ids:
            return
        beat = float(self.playhead_beat)
        step = max(0.03125, float(self.quantize_step))
        new_ids: set[int] = set()
        self.begin_undo_group()
        try:
            for ev in list(self.get_selected_events()):
                start = float(ev.start)
                end = start + float(ev.duration)
                if beat <= start + 1e-9 or beat >= end - 1e-9:
                    continue
                left_d = max(step, beat - start)
                right_d = max(step, end - beat)
                tid = int(getattr(ev, "track_id", self.active_track_id))
                if isinstance(ev, NoteEvent):
                    pitch = int(ev.pitch)
                    vel = int(ev.velocity)
                    tie = bool(getattr(ev, "tie_to_next", False))
                    self.sequence.remove_event(ev.id)
                    a = self.sequence.add_note(pitch=pitch, start=start, duration=left_d, velocity=vel, track_id=tid)
                    b = self.sequence.add_note(pitch=pitch, start=beat, duration=right_d, velocity=vel, track_id=tid)
                    # tie bleibt am rechten Segment (vereinfachtes Verhalten)
                    try:
                        b.tie_to_next = tie
                    except Exception:
                        pass
                    new_ids.update({a.id, b.id})
                elif isinstance(ev, RestEvent):
                    self.sequence.remove_event(ev.id)
                    a = self.sequence.add_rest(start=start, duration=left_d, track_id=tid)
                    b = self.sequence.add_rest(start=beat, duration=right_d, track_id=tid)
                    new_ids.update({a.id, b.id})
        finally:
            self.end_undo_group(commit=True)
        if new_ids:
            self.set_selection(new_ids)
        self.redraw_events()

    def glue_selected(self):
        # Merge (DAW-Style): gleiche Spur + gleicher Pitch (bei Noten) und überlappend/angrenzend.
        if len(self.selected_ids) < 2:
            return
        sels = self.get_selected_events()
        # gruppieren
        groups: dict[tuple, list] = {}
        for ev in sels:
            tid = int(getattr(ev, "track_id", self.active_track_id))
            if isinstance(ev, NoteEvent):
                key = ("note", tid, int(ev.pitch))
            else:
                key = ("rest", tid, None)
            groups.setdefault(key, []).append(ev)

        step = max(0.03125, float(self.quantize_step))
        new_ids: set[int] = set()
        self.begin_undo_group()
        try:
            for key, evs in groups.items():
                if len(evs) < 2:
                    continue
                evs = sorted(evs, key=lambda e: float(e.start))
                start = float(evs[0].start)
                end = max(float(e.start) + float(e.duration) for e in evs)
                tid = int(getattr(evs[0], "track_id", self.active_track_id))
                # entfernen
                for e in evs:
                    self.sequence.remove_event(e.id)
                dur = max(step, end - start)
                if key[0] == "note":
                    pitch = int(key[2])
                    vel = int(round(sum(int(getattr(e, "velocity", 90)) for e in evs) / float(len(evs))))
                    ev_new = self.sequence.add_note(pitch=pitch, start=start, duration=dur, velocity=vel, track_id=tid)
                    new_ids.add(ev_new.id)
                else:
                    ev_new = self.sequence.add_rest(start=start, duration=dur, track_id=tid)
                    new_ids.add(ev_new.id)
        finally:
            self.end_undo_group(commit=True)
        if new_ids:
            self.set_selection(new_ids)
        self.redraw_events()

    # ---------- Lasso helpers ----------
    def begin_lasso(self, start_scene: QPointF):
        if self._lasso_item is not None:
            try:
                self.scene.removeItem(self._lasso_item)
            except Exception:
                pass
        pen = QPen(Qt.darkGray)
        pen.setStyle(Qt.DashLine)
        self._lasso_item = self.scene.addRect(QRectF(start_scene, start_scene), pen, QBrush(Qt.transparent))
        self._lasso_item.setZValue(9999)

    def update_lasso(self, start_scene: QPointF, current_scene: QPointF):
        if self._lasso_item is None:
            return
        rect = QRectF(start_scene, current_scene).normalized()
        self._lasso_item.setRect(rect)

    def finish_lasso(self, start_scene: QPointF, end_scene: QPointF) -> list[int]:
        rect = QRectF(start_scene, end_scene).normalized()
        ids = self.event_ids_in_rect(rect)
        if self._lasso_item is not None:
            try:
                self.scene.removeItem(self._lasso_item)
            except Exception:
                pass
            self._lasso_item = None
        return ids

    def event_ids_in_rect(self, rect: QRectF) -> list[int]:
        ids = set()
        for eid, bbox in self._id_to_bbox.items():
            if bbox.intersects(rect):
                ids.add(int(eid))
        return sorted(ids)

    # ---------- Hit-Test ----------
    def hit_test(self, scene_pos: QPointF) -> HitInfo:
        items = self.scene.items(scene_pos)
        for it in items:
            try:
                v = it.data(0)
            except Exception:
                v = None
            if not v:
                continue
            try:
                role = it.data(1) or "unknown"
            except Exception:
                role = "unknown"

            near = False
            if str(role) == "bar":
                try:
                    r = it.sceneBoundingRect()
                    near = abs(scene_pos.x() - r.right()) < 6.0
                except Exception:
                    near = False

            return HitInfo(event_id=int(v), role=str(role), item=it, near_resize_handle=near)
        return HitInfo(event_id=None, role="unknown", item=None, near_resize_handle=False)

    def _event_id_at_pos(self, scene_pos: QPointF) -> Optional[int]:
        hit = self.hit_test(scene_pos)
        return hit.event_id

    # ---------- Drawing ----------
    def redraw_events(self):
        # Scroll position stabil halten (insbesondere beim Zoomen / vielen Spuren).
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        h_ratio = (hb.value() / max(1, hb.maximum())) if hb is not None else 0.0
        v_ratio = (vb.value() / max(1, vb.maximum())) if vb is not None else 0.0

        self.scene.clear()
        self._id_to_items.clear()
        self._id_to_bbox.clear()
        self.event_items.clear()

        self._draw_background()

        self._draw_staff_and_grid()

        for ev in self.sequence.sorted_events():
            if isinstance(ev, NoteEvent):
                self._draw_note_event(ev)
            elif isinstance(ev, RestEvent):
                self._draw_rest_event(ev)

        self._draw_playhead()
        self._update_scene_rect(preserve_scroll=False)

        # Restore scroll position (ratio-based to handle new ranges)
        try:
            hb = self.horizontalScrollBar()
            vb = self.verticalScrollBar()
            if hb is not None:
                hb.setValue(int(float(h_ratio) * max(0, hb.maximum())))
            if vb is not None:
                vb.setValue(int(float(v_ratio) * max(0, vb.maximum())))
        except Exception:
            pass

    def _draw_staff_and_grid(self):
        pen = QPen(Qt.darkGray)
        grid_pen = QPen(Qt.lightGray)
        grid_pen.setStyle(Qt.DashLine)

        # WICHTIG: keine viewport/zoom-abhängige Endlänge der Linien.
        # Sonst ändert sich beim Zoomen (oder Fenster-Resize) die Geometrie der Scene,
        # was Scrollbars „springen“ lassen kann. Wir zeichnen immer bis zur Timeline-Breite.
        end_x = self.timeline_x0 + (self.total_beats + 2) * self.beat_width + 240

        top_y = self.staff_y_for_track(self.sequence.tracks[0].id) - 60 if self.sequence.tracks else self.track_top - 60
        bottom_y = self.staff_y_for_track(self.sequence.tracks[-1].id) + 90 if self.sequence.tracks else self.track_top + 90

        self._grid_top_y = float(top_y)
        self._grid_bottom_y = float(bottom_y)

        for b in range(self.total_beats + 1):
            x = self.timeline_x0 + b * self.beat_width
            self.scene.addLine(x, top_y, x, bottom_y, grid_pen)
            if b % 4 == 0:
                lab = self.scene.addText(str(b), QFont("Sans", 9))
                lab.setDefaultTextColor(Qt.darkGray)
                lab.setPos(x + 2, top_y - 18)

        for i, tr in enumerate(self.sequence.tracks):
            staff_y = self.staff_y_for_track(tr.id)
            for li in range(5):
                y = staff_y + li * self.staff_line_gap
                self.scene.addLine(self.left_margin, y, end_x, y, pen)

            clef = self.scene.addText(tr.clef_symbol, QFont("DejaVu Sans", 34))
            clef.setDefaultTextColor(Qt.darkGray)
            clef.setPos(18, staff_y - 36)

            name = self.scene.addText(tr.name, QFont("Sans", 10))
            name.setDefaultTextColor(Qt.darkGray)
            name.setPos(60, staff_y - 22)

            if tr.id == self.active_track_id:
                hi_pen = QPen(Qt.darkGray)
                hi_pen.setWidth(2)
                self.scene.addLine(self.left_margin, staff_y - 8, end_x, staff_y - 8, hi_pen)

    def _draw_note_event(self, ev: NoteEvent):
        x = self.beat_to_x(ev.start)
        y = self.midi_to_y(ev.pitch, int(getattr(ev, "track_id", 1)))
        dur_w = max(8.0, float(ev.duration) * float(self.beat_width))
        # Style wird zentral über _apply_event_style gesetzt (Selection=Gelb, Playback=Cyan)
        pen = QPen(Qt.black)
        brush = QBrush(Qt.black)

        head = self.scene.addEllipse(x, y, 12, 8, pen, brush)
        head.setData(0, ev.id)
        head.setData(1, "head")

        bar = self.scene.addRect(x + 12, y + 3, dur_w, 2, pen, brush)
        bar.setData(0, ev.id)
        bar.setData(1, "bar")

        label = self.scene.addText(midi_to_name(ev.pitch), QFont("Sans", 9))
        label.setDefaultTextColor(Qt.black)
        label.setPos(x - 6, y - 22)
        label.setData(0, ev.id)
        label.setData(1, "label")

        vtxt = self.scene.addText(str(int(ev.velocity)), QFont("Sans", 8))
        vtxt.setDefaultTextColor(Qt.darkGray)
        vtxt.setPos(x + 10, y + 10)
        vtxt.setData(0, ev.id)
        vtxt.setData(1, "vel")

        items = [head, bar, label, vtxt]
        self._id_to_items[ev.id] = items
        bbox = head.sceneBoundingRect().united(bar.sceneBoundingRect()).united(label.sceneBoundingRect())
        self._id_to_bbox[ev.id] = bbox
        self.event_items.append(ev.id)

        self._apply_event_style(ev.id)

        if ev.tie_to_next:
            tie_pen = QPen(Qt.darkGray)
            tie_pen.setWidth(2)
            self.scene.addLine(x + 6, y + 16, x + dur_w + 18, y + 16, tie_pen)

    def _draw_rest_event(self, ev: RestEvent):
        x = self.beat_to_x(ev.start)
        tid = int(getattr(ev, "track_id", 1))
        staff_y = self.staff_y_for_track(tid)
        y = staff_y + 20
        dur_w = max(10.0, float(ev.duration) * float(self.beat_width))
        # Style wird zentral über _apply_event_style gesetzt (Selection=Gelb, Playback=Cyan)
        pen = QPen(Qt.black)
        brush = QBrush(Qt.black)

        rect = self.scene.addRect(x, y, dur_w, 6, pen, brush)
        rect.setData(0, ev.id)
        rect.setData(1, "rest")

        label = self.scene.addText("Pause", QFont("Sans", 9))
        label.setDefaultTextColor(Qt.black)
        label.setPos(x, y - 18)
        label.setData(0, ev.id)
        label.setData(1, "label")

        self._id_to_items[ev.id] = [rect, label]
        self._id_to_bbox[ev.id] = rect.sceneBoundingRect().united(label.sceneBoundingRect())
        self.event_items.append(ev.id)

        self._apply_event_style(ev.id)

    
    # ---------- Incremental geometry update (Drag ohne Full-Redraw) ----------
    def update_event_geometry(self, event_id: int):
        eid = int(event_id)
        ev = self.sequence.get_event(eid)
        items = self._id_to_items.get(eid)
        if ev is None or not items:
            return

        if isinstance(ev, NoteEvent):
            x = self.beat_to_x(ev.start)
            y = self.midi_to_y(ev.pitch, int(getattr(ev, "track_id", 1)))
            dur_w = max(8.0, float(ev.duration) * float(self.beat_width))

            head = bar = label = vel = None
            for it in items:
                try:
                    role = it.data(1) or ""
                except Exception:
                    role = ""
                if role == "head":
                    head = it
                elif role == "bar":
                    bar = it
                elif role == "label":
                    label = it
                elif role == "vel":
                    vel = it

            try:
                if head is not None:
                    head.setRect(x, y, 12, 8)
            except Exception:
                pass
            try:
                if bar is not None:
                    bar.setRect(x + 12, y + 3, dur_w, 2)
            except Exception:
                pass
            try:
                if label is not None:
                    label.setPlainText(midi_to_name(int(ev.pitch)))
                    label.setPos(x - 6, y - 22)
            except Exception:
                pass
            try:
                if vel is not None:
                    vel.setPlainText(str(int(ev.velocity)))
                    vel.setPos(x + 10, y + 10)
            except Exception:
                pass

            # bbox for lasso
            try:
                bbox = head.sceneBoundingRect()
                if bar is not None:
                    bbox = bbox.united(bar.sceneBoundingRect())
                if label is not None:
                    bbox = bbox.united(label.sceneBoundingRect())
                if vel is not None:
                    bbox = bbox.united(vel.sceneBoundingRect())
                self._id_to_bbox[eid] = bbox
            except Exception:
                pass

            self._apply_event_style(eid)
            return

        if isinstance(ev, RestEvent):
            x = self.beat_to_x(ev.start)
            tid = int(getattr(ev, "track_id", 1))
            staff_y = self.staff_y_for_track(tid)
            y = staff_y + 20
            dur_w = max(10.0, float(ev.duration) * float(self.beat_width))

            rect = label = None
            for it in items:
                try:
                    role = it.data(1) or ""
                except Exception:
                    role = ""
                if role == "rest":
                    rect = it
                elif role == "label":
                    label = it

            try:
                if rect is not None:
                    rect.setRect(x, y, dur_w, 6)
            except Exception:
                pass
            try:
                if label is not None:
                    label.setPos(x, y - 18)
            except Exception:
                pass

            try:
                bbox = rect.sceneBoundingRect()
                if label is not None:
                    bbox = bbox.united(label.sceneBoundingRect())
                self._id_to_bbox[eid] = bbox
            except Exception:
                pass

            self._apply_event_style(eid)

    def update_event_geometry_batch(self, ids: Iterable[int]):
        for eid in ids:
            self.update_event_geometry(int(eid))
        try:
            self.viewport().update()
        except Exception:
            pass


    def _calc_scene_size(self) -> tuple[float, float]:
        width = self.timeline_x0 + (self.total_beats + 2) * self.beat_width + 240
        height = self.track_top + max(1, len(self.sequence.tracks)) * self.track_spacing + 100
        return float(width), float(height)

    def _sync_background_to_scene(self, width_px: int, height_px: int):
        if self._bg_pixmap is None or self._bg_item is None:
            self._bg_scaled_for = None
            return
        w = max(1, int(width_px))
        h = max(1, int(height_px))
        if self._bg_scaled_for == (w, h):
            return
        try:
            pm = self._bg_pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._bg_item.setPixmap(pm)
            self._bg_item.setPos(0, 0)
            self._bg_scaled_for = (w, h)
        except Exception:
            pass

    def _update_scene_rect(self, preserve_scroll: bool = True):
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        # DAW-Style: Scrollbar-Position stabil halten (nicht als Ratio – das verursacht „Springen“ bei Zoom/Redraw)
        h_val = int(hb.value()) if (preserve_scroll and hb is not None) else 0
        v_val = int(vb.value()) if (preserve_scroll and vb is not None) else 0

        width, height = self._calc_scene_size()
        self.scene.setSceneRect(0, 0, float(width), float(height))

        # Background darf nie die Scene vergrößern → immer an SceneRect anpassen
        self._sync_background_to_scene(int(width), int(height))

        if preserve_scroll:
            try:
                if hb is not None:
                    hb.setValue(min(h_val, int(hb.maximum())))
                if vb is not None:
                    vb.setValue(min(v_val, int(vb.maximum())))
            except Exception:
                pass

    # ---------- Zoom ----------
    def _apply_zoom(self):
        # Absolute Zoom anwenden (z. B. nach Projekt laden)
        self.resetTransform()
        self.scale(self._zoom, self._zoom)
        self.zoomChanged.emit(self._zoom)

    def set_zoom(self, z: float):
        # Zoom soll die Scene nicht neu aufbauen (kein redraw_events), sonst springen Scrollbars.
        old = float(self._zoom)
        new = max(0.2, min(4.0, float(z)))
        if abs(new - old) < 1e-9:
            return
        self._zoom = new

        # Relative Skalierung nutzt AnchorUnderMouse korrekt (DAW-typisch)
        factor = new / old if old > 1e-9 else new
        self.scale(factor, factor)
        self.zoomChanged.emit(self._zoom)

        # Während/kurz nach Zoom Auto-Follow unterdrücken, um „Springen“ zu vermeiden
        self._suppress_autofollow_until = max(self._suppress_autofollow_until, time.monotonic() + 0.35)

    def get_zoom(self) -> float:
        return float(self._zoom)

    def set_total_beats(self, beats: int):
        self.total_beats = max(1, int(beats))
        self.commit_undo_checkpoint()
        self.redraw_events()

    def set_velocity(self, v: int):
        self.current_velocity = _clamp_int(int(v), 1, 127)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        factor = 1.15 if delta > 0 else 1/1.15
        self.set_zoom(self._zoom * factor)
        event.accept()

    # ---------- Context menu ----------
    def contextMenuEvent(self, event):
        """Rechtsklick-Menü.
        
        TEMPORÄR DEAKTIVIERT wegen QPaintDevice-Crash.
        """
        import os
        if os.environ.get("PYDAW_DISABLE_NOTATION_CONTEXT_MENU", "1") == "1":
            event.ignore()
            return
        
        # Original code (deaktiviert):
        """
        WICHTIG: redraw_events() darf nicht direkt aufgerufen werden,
        da das während eines Paint-Events zu "QPaintDevice being painted" führt.
        """
        scene_pos = self.mapToScene(event.pos())
        existing_id = self._event_id_at_pos(scene_pos)
        if existing_id is not None:
            self.set_selection({existing_id})
            # GEFIXT: Verzögere redraw mit QTimer
            from pydaw.notation.qt_compat import Qt
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.redraw_events)

        menu = QMenu(self)

        # --- Symbol-Palette (als ausklappbares Panel im Rechtsklick-Menü) ---
        # Wichtig: als QWidgetAction, damit man direkt klicken kann (wie DAW-Toolbox).
        try:
            from gui.symbol_palette import add_symbol_palette_to_menu
            m_palette = menu.addMenu("Symbol-Palette")
            add_symbol_palette_to_menu(m_palette, self, compact=True)

            # Dock Toggle (falls MainWindow es anbietet)
            mw = self.window()
            if hasattr(mw, "set_symbol_palette_visible") and hasattr(mw, "is_symbol_palette_visible"):
                act_dock = menu.addAction("Symbol-Palette (Panel) anzeigen")
                act_dock.setCheckable(True)
                act_dock.setChecked(bool(mw.is_symbol_palette_visible()))
                act_dock.triggered.connect(lambda checked=False, _mw=mw: _mw.set_symbol_palette_visible(bool(checked)))
            menu.addSeparator()
        except Exception:
            # Kontextmenü darf niemals crashen.
            pass

        # --- Werkzeuge ---
        m_tool = menu.addMenu("Werkzeug")
        modes = [
            ("Note zeichnen", "note"),
            ("Pause zeichnen", "rest"),
            ("Verschieben", "select"),
            ("Haltebogen (Toggle)", "tie"),
            ("Radierer (löschen)", "erase"),
        ]
        for label, mode in modes:
            act = m_tool.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mode == mode)
            act.triggered.connect(lambda _=False, m=mode: self.set_mode(m))

        # --- Quantisierung UI ---
        m_q = menu.addMenu("Quantisierung")
        act_snap = m_q.addAction("Snap/Grid aktiv")
        act_snap.setCheckable(True)
        act_snap.setChecked(self.snap_enabled)
        act_snap.toggled.connect(self.set_snap)

        m_qstep = m_q.addMenu("Step")
        steps = [
            ("Beat/1 (1.0)", 1.0),
            ("Beat/2 (0.5)", 0.5),
            ("Beat/4 (0.25)", 0.25),
            ("Beat/8 (0.125)", 0.125),
            ("Beat/16 (0.0625)", 0.0625),
        ]
        for label, val in steps:
            act = m_qstep.addAction(label)
            act.setCheckable(True)
            act.setChecked(abs(self.quantize_step - val) < 1e-9)
            act.triggered.connect(lambda _=False, s=val: self.set_quantize_step(s))

        # --- Bearbeiten (kontextsensitiv) ---
        m_edit = menu.addMenu("Bearbeiten")
        has_sel = bool(self.selected_ids)
        has_notes = any(isinstance(self.sequence.get_event(eid), NoteEvent) for eid in self.selected_ids)
        for label, func in [("← Links", self.nudge_left), ("→ Rechts", self.nudge_right), ("↑ Hoch", self.nudge_up), ("↓ Runter", self.nudge_down)]:
            act = m_edit.addAction(label)
            act.setEnabled(has_sel)
            act.triggered.connect(func)

        m_edit.addSeparator()

        # Split/Glue nur wenn sinnvoll
        act_split = m_edit.addAction("Split @ Playhead")
        act_split.setEnabled(has_sel)
        act_split.triggered.connect(self.split_selected_at_playhead)

        act_glue = m_edit.addAction("Glue/Merge")
        act_glue.setEnabled(len(self.selected_ids) >= 2)
        act_glue.triggered.connect(self.glue_selected)

        m_edit.addSeparator()

        m_qtz = m_edit.addMenu("Quantize")
        a_q1 = m_qtz.addAction("Start")
        a_q1.setEnabled(has_sel)
        a_q1.triggered.connect(lambda: self.quantize_selected(also_duration=False))
        a_q2 = m_qtz.addAction("Start + Länge")
        a_q2.setEnabled(has_sel)
        a_q2.triggered.connect(lambda: self.quantize_selected(also_duration=True))

        a_h = m_edit.addAction("Humanize")
        a_h.setEnabled(has_sel)
        a_h.triggered.connect(self.humanize_selected)

        m_tr = m_edit.addMenu("Transpose")
        for lab, st in [("-12", -12), ("-1", -1), ("+1", 1), ("+12", 12)]:
            a = m_tr.addAction(lab)
            a.setEnabled(has_notes)
            a.triggered.connect(lambda _=False, _st=st: self.transpose_selected(_st))

        # --- Zoom ---
        m_zoom = menu.addMenu("Zoom")
        m_zoom.addAction("Zoom +").triggered.connect(self.zoom_in)
        m_zoom.addAction("Zoom -").triggered.connect(self.zoom_out)
        m_zoom.addAction("Reset (100%)").triggered.connect(self.zoom_reset)

        menu.exec(event.globalPos())

    # ---------- Nudge helpers ----------
    def nudge_left(self):
        step = max(0.03125, self.quantize_step)
        if not self.selected_ids: return
        for eid in list(self.selected_ids):
            ev = self.sequence.get_event(eid)
            if ev: ev.start = max(0.0, ev.start - step)
        self.commit_undo_checkpoint()
        self.redraw_events()

    def nudge_right(self):
        step = max(0.03125, self.quantize_step)
        if not self.selected_ids: return
        for eid in list(self.selected_ids):
            ev = self.sequence.get_event(eid)
            if ev: ev.start += step
        self.commit_undo_checkpoint()
        self.redraw_events()

    def nudge_up(self):
        if not self.selected_ids: return
        for eid in list(self.selected_ids):
            ev = self.sequence.get_event(eid)
            if isinstance(ev, NoteEvent):
                ev.pitch = self.step_pitch_in_scale(int(ev.pitch), +1)
        self.commit_undo_checkpoint()
        self.redraw_events()

    def nudge_down(self):
        if not self.selected_ids: return
        for eid in list(self.selected_ids):
            ev = self.sequence.get_event(eid)
            if isinstance(ev, NoteEvent):
                ev.pitch = self.step_pitch_in_scale(int(ev.pitch), -1)
        self.commit_undo_checkpoint()
        self.redraw_events()

    # ---------- Mouse events ----------
    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if event.button() == Qt.LeftButton:
            self._user_interacting = True
            self._suppress_autofollow_until = max(self._suppress_autofollow_until, time.monotonic() + 0.25)
            self.paste_cursor_beat = self.x_to_beat(scene_pos.x())
            self.set_playhead_beat(self.paste_cursor_beat, ensure_visible=False)
        self._active_tool.on_press(scene_pos, event.button(), event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self._active_tool.on_move(scene_pos, event.buttons(), event.modifiers())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self._active_tool.on_release(scene_pos, event.button(), event.modifiers())
        if event.button() == Qt.LeftButton:
            self._user_interacting = False
            self._suppress_autofollow_until = max(self._suppress_autofollow_until, time.monotonic() + 0.15)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Mouse double click.

        IMPORTANT: Prevent uncaught exceptions from bubbling into Qt.
        Some PyQt6 builds/configs will treat them as fatal (SIGABRT).
        """
        try:
            scene_pos = self.mapToScene(event.pos())
            self._active_tool.on_double_click(scene_pos, event.button(), event.modifiers())
        except Exception:
            pass

        super().mouseDoubleClickEvent(event)

    # ---------- Cut/Copy/Paste ----------
    def copy_selection(self):
        if not self.selected_ids: return
        evs = [self.sequence.get_event(eid) for eid in sorted(self.selected_ids) if self.sequence.get_event(eid)]
        if not evs: return
        min_start = min(e.start for e in evs)
        payload = {"min_start": float(min_start), "events": []}
        for e in evs:
            d = {"type": "rest" if isinstance(e, RestEvent) else "note",
                 "start": float(e.start - min_start),
                 "duration": float(e.duration),
                 "track_id": int(getattr(e, "track_id", 1))}
            if isinstance(e, NoteEvent):
                d.update({"pitch": int(e.pitch), "velocity": int(e.velocity), "tie_to_next": bool(e.tie_to_next)})
            payload["events"].append(d)
        self._clipboard_cache = payload
        try:
            QApplication.clipboard().setText("ChronoScaleStudioClipboard")
        except Exception:
            pass

    def cut_selection(self):
        if not self.selected_ids: return
        self.copy_selection()
        self.sequence.remove_events(self.selected_ids)
        self.selected_ids.clear()
        self.primary_selected_id = None
        self.commit_undo_checkpoint()
        self.redraw_events()

    def paste(self):
        if not self._clipboard_cache: return
        base = float(self.paste_cursor_beat)
        new_ids = []
        for d in self._clipboard_cache.get("events", []):
            st = base + float(d.get("start", 0.0))
            dur = float(d.get("duration", self.quantize_step))
            tid = int(d.get("track_id", self.active_track_id))
            if d.get("type") == "rest":
                ev = self.sequence.add_rest(start=st, duration=dur, track_id=tid)
            else:
                ev = self.sequence.add_note(
                    pitch=int(d.get("pitch", 60)),
                    start=st,
                    duration=dur,
                    velocity=int(d.get("velocity", 90)),
                    track_id=tid,
                )
                ev.tie_to_next = bool(d.get("tie_to_next", False))
            new_ids.append(ev.id)
        self.set_selection(set(new_ids))
        self.commit_undo_checkpoint()
        self.redraw_events()

    # ---------- Key bindings ----------
    def keyPressEvent(self, event):
        # Tool-Shortcuts
        if event.key() == Qt.Key_D and not event.modifiers():
            self.set_mode("note"); return
        if event.key() == Qt.Key_E and not event.modifiers():
            self.set_mode("erase"); return
        if event.key() == Qt.Key_Escape:
            self.set_mode("select"); return
        if event.key() == Qt.Key_R and not event.modifiers():
            self.set_mode("rest"); return
        if event.key() == Qt.Key_T and not event.modifiers():
            self.set_mode("tie"); return
        
        # Undo/Redo
        if event.matches(QKeySequence.Undo):
            if self.undo.undo(): self.redraw_events()
            return
        if event.matches(QKeySequence.Redo) or (event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and event.key() == Qt.Key_Z):
            if self.undo.redo(): self.redraw_events()
            return

        if event.matches(QKeySequence.Copy):
            self.copy_selection(); return
        if event.matches(QKeySequence.Cut):
            self.cut_selection(); return
        if event.matches(QKeySequence.Paste):
            self.paste(); return

        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected_ids:
                self.sequence.remove_events(self.selected_ids)
                self.selected_ids.clear()
                self.primary_selected_id = None
                self.commit_undo_checkpoint()
                self.redraw_events()
            return

        if event.key() == Qt.Key_Left: self.nudge_left(); return
        if event.key() == Qt.Key_Right: self.nudge_right(); return
        if event.key() == Qt.Key_Up: self.nudge_up(); return
        if event.key() == Qt.Key_Down: self.nudge_down(); return

        step = max(0.03125, self.quantize_step)
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            if self.selected_ids:
                for eid in self.selected_ids:
                    ev = self.sequence.get_event(eid)
                    if ev: ev.duration += step
                self.commit_undo_checkpoint()
                self.redraw_events()
            return
        if event.key() == Qt.Key_Minus:
            if self.selected_ids:
                for eid in self.selected_ids:
                    ev = self.sequence.get_event(eid)
                    if ev: ev.duration = max(step, ev.duration - step)
                self.commit_undo_checkpoint()
                self.redraw_events()
            return

        super().keyPressEvent(event)

    # ---------- Properties dialog ----------
    def open_event_properties_dialog(self, event_id: int):
        ev = self.sequence.get_event(event_id)
        if ev is None: return

        dlg = QDialog(self)
        dlg.setWindowTitle("Event Eigenschaften")
        form = QFormLayout(dlg)

        sp_start = QDoubleSpinBox(); sp_start.setRange(0.0, 9999.0); sp_start.setDecimals(4); sp_start.setValue(float(ev.start))
        sp_dur = QDoubleSpinBox(); sp_dur.setRange(0.03125, 9999.0); sp_dur.setDecimals(4); sp_dur.setValue(float(ev.duration))
        form.addRow("Start (Beats)", sp_start)
        form.addRow("Dauer (Beats)", sp_dur)

        sp_pitch = sp_vel = None
        if isinstance(ev, NoteEvent):
            sp_pitch = QSpinBox(); sp_pitch.setRange(0, 127); sp_pitch.setValue(int(ev.pitch))
            sp_vel = QSpinBox(); sp_vel.setRange(1, 127); sp_vel.setValue(int(ev.velocity))
            form.addRow("Pitch", sp_pitch)
            form.addRow("Velocity", sp_vel)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)

        def apply():
            ev.start = float(sp_start.value())
            ev.duration = float(sp_dur.value())
            if isinstance(ev, NoteEvent) and sp_pitch and sp_vel:
                ev.pitch = int(sp_pitch.value())
                ev.velocity = int(sp_vel.value())
            self.commit_undo_checkpoint()
            self.redraw_events()

        buttons.accepted.connect(lambda: (apply(), dlg.accept()))
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    # ---------- Misc ----------
    def clear_all(self):
        self.sequence.clear()
        self.selected_ids.clear()
        self.primary_selected_id = None
        self.commit_undo_checkpoint()
        self.redraw_events()

    def preview_note(self, midi: int, velocity: int = 90):
        try:
            SYNTH.note_on(int(midi), int(velocity))
            SYNTH.note_off(int(midi))
        except Exception:
            pass

    def get_volume_automation_lane(self):
        return self.sequence.automation.get("volume")

    def get_playback_events(self):
        active = self.sequence.active_track_ids_for_playback()
        return [e for e in self.sequence.sorted_events() if int(getattr(e, "track_id", 1)) in active]

    # ---------- Playhead / Loop / Background API ----------
    def get_playhead_beat(self) -> float:
        return float(self.playhead_beat)

    def set_playhead_beat(self, beat: float, ensure_visible: bool = True):
        self.playhead_beat = max(0.0, float(beat))
        # Update playhead line if present
        if self._playhead_item is not None:
            try:
                x = self.beat_to_x(self.playhead_beat)
                self._playhead_item.setLine(x, self._grid_top_y, x, self._grid_bottom_y)
            except Exception:
                pass
        self.playheadChanged.emit(self.playhead_beat)
        if ensure_visible:
            self.ensure_playhead_visible()

    def move_playhead(self, delta_beats: float):
        self.set_playhead_beat(self.playhead_beat + float(delta_beats), ensure_visible=True)

    def ensure_playhead_visible(self):
        # Stabiler DAW-Scroll: nur horizontal nachführen, nur wenn nötig.
        # Wichtig: minimaler Shift (kein Re-Center), damit die untere Scrollbar nicht „hin und her“ springt.
        if not self.auto_follow_playhead:
            return
        now = time.monotonic()
        if now < float(self._suppress_autofollow_until):
            return
        if self._user_interacting:
            return

        try:
            if not self.viewport():
                return
            x = float(self.beat_to_x(self.playhead_beat))
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()

            margin = 140.0
            left_edge = float(view_rect.left()) + margin
            right_edge = float(view_rect.right()) - margin

            shift = 0.0
            if x > right_edge:
                shift = x - right_edge
            elif x < left_edge:
                shift = x - left_edge
            else:
                return

            target_center_x = float(view_rect.center().x()) + float(shift)

            # Hysterese gegen Oszillation
            if self._last_follow_center_x is not None and abs(target_center_x - float(self._last_follow_center_x)) < 1.5:
                return
            self._last_follow_center_x = target_center_x

            self.centerOn(QPointF(target_center_x, float(view_rect.center().y())))
        except Exception:
            return

    def set_loop_a(self):
        self.loop_a_beat = float(self.playhead_beat)

    def set_loop_b(self):
        self.loop_b_beat = float(self.playhead_beat)

    def get_loop_range(self):
        if self.loop_a_beat is None or self.loop_b_beat is None:
            return None
        a = float(self.loop_a_beat)
        b = float(self.loop_b_beat)
        if b <= a + 1e-6:
            return None
        return (a, b)

    def set_background_image(self, path: str):
        try:
            pm = QPixmap(str(path))
            if pm.isNull():
                return False
            self._bg_path = str(path)
            self._bg_pixmap = pm
            self._bg_scaled_for = None
            self.redraw_events()
            return True
        except Exception:
            return False

    def clear_background_image(self):
        self._bg_path = None
        self._bg_pixmap = None
        self._bg_scaled_for = None
        self.redraw_events()

    def _draw_background(self):
        if self._bg_pixmap is None:
            return
        try:
            # Background wird an die Scene-Größe angepasst, damit Scrollbars nicht „springen“.
            w, h = self._calc_scene_size()
            pm = self._bg_pixmap.scaled(int(w), int(h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._bg_item = self.scene.addPixmap(pm)
            self._bg_scaled_for = (int(w), int(h))
            self._bg_item.setOpacity(0.22)
            self._bg_item.setZValue(-10000)
            self._bg_item.setPos(0, 0)
        except Exception:
            self._bg_item = None

    def _draw_playhead(self):
        try:
            x = self.beat_to_x(self.playhead_beat)
            pen = QPen(Qt.darkCyan)
            pen.setWidth(2)
            self._playhead_item = self.scene.addLine(x, self._grid_top_y, x, self._grid_bottom_y, pen)
            self._playhead_item.setZValue(9000)
        except Exception:
            self._playhead_item = None

    # ---------- Style helpers (Original: Cyan Playback > Gelb Selection) ----------
    def _apply_event_style(self, event_id: int):
        eid = int(event_id)
        items = self._id_to_items.get(eid) or []
        playing = (self.playing_event_id == eid)
        selected = (eid in self.selected_ids)

        # Priority: Playback (Cyan) > Selection (Gelb)
        color = None
        if playing:
            color = Qt.cyan
        elif selected:
            color = Qt.yellow

        for it in items:
            try:
                role = it.data(1) or ""
            except Exception:
                role = ""

            # Shapes
            if role in ("head", "rest"):
                try:
                    it.setPen(QPen(Qt.black))
                    it.setBrush(QBrush(color if color is not None else Qt.black))
                except Exception:
                    pass
            elif role == "bar":
                # Bar bleibt immer schwarz (Original-Look)
                try:
                    it.setPen(QPen(Qt.black))
                    it.setBrush(QBrush(Qt.black))
                except Exception:
                    pass

            # Text
            if role == "label":
                try:
                    it.setDefaultTextColor(color if color is not None else Qt.black)
                except Exception:
                    pass
            elif role == "vel":
                try:
                    it.setDefaultTextColor(color if color is not None else Qt.darkGray)
                except Exception:
                    pass

    def highlight_note(self, index: int):
        """Playback Highlight (Original): Cyan für aktive Note, danach Selection (Gelb) wieder sichtbar."""
        prev = self.playing_event_id

        if index is None or int(index) < 0:
            self.playing_event_id = None
        else:
            idx = int(index)
            if 0 <= idx < len(self.event_items):
                self.playing_event_id = int(self.event_items[idx])
            else:
                self.playing_event_id = None

        # Update styles (prev + current)
        if prev is not None:
            self._apply_event_style(int(prev))
        if self.playing_event_id is not None:
            self._apply_event_style(int(self.playing_event_id))

            # Move playhead to active event start
            try:
                ev = self.sequence.get_event(int(self.playing_event_id))
                if ev is not None:
                    self.set_playhead_beat(float(ev.start), ensure_visible=True)
            except Exception:
                pass

