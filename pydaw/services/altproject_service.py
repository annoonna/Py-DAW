"""ProjectService (v0.0.15.8 hotfix).

Ziel dieses Hotfix:
- Stabile, konsistente API für die UI (keine AttributeError-Crashes in Qt-Slots)
- Threaded File-IO (Open/Save/Import/Export) via ThreadPoolService.Worker
- Grundlegende Track/Clip-Operationen + PianoRoll/MIDI Notes Datenstruktur
- Clip Launcher Einstellungen + Slot Mapping

Hinweis: Audio-Playback/Recording ist weiterhin Placeholder.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import contextlib
import math
import wave
import re
from typing import Any, Callable, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import set_value as set_setting

from pydaw.core.threading import ThreadPoolService, Worker
from pydaw.model.project import Track, Clip
from pydaw.model.midi import MidiNote

from pydaw.fileio.file_manager import (
    ProjectContext,
    new_project as fm_new_project,
    open_project as fm_open_project,
    save_project_to as fm_save_project_to,
    import_audio_to_project as fm_import_audio,
    import_midi_to_project as fm_import_midi,
    export_audio_from_file as fm_export_audio,
)

from pydaw.fileio import project_io

from pydaw.fileio.midi_io import import_midi as midi_parse

from pydaw.commands import UndoStack
from pydaw.commands.midi_notes_edit import MidiNotesEditCommand, MidiSnapshot


class ProjectService(QObject):
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    project_updated = pyqtSignal()
    project_changed = pyqtSignal()
    clip_selected = pyqtSignal(str)
    active_clip_changed = pyqtSignal(str)  # backward compatible alias for pianoroll
    undo_changed = pyqtSignal()
    # Fired after a MIDI edit is committed (Undo step created). This allows
    # other services (e.g. audio) to react without the user needing to stop/play.
    midi_notes_committed = pyqtSignal(str)

    # Lifecycle hook for UI: emitted after new/open/snapshot-load.
    project_opened = pyqtSignal()

    # MIDI pre-render (performance): render MIDI->WAV in the background so
    # playback feels instant even with large SF2 instruments.
    prerender_started = pyqtSignal(int)    # total clips
    prerender_progress = pyqtSignal(int)   # percent 0..100
    prerender_label = pyqtSignal(str)      # short status text
    prerender_finished = pyqtSignal(bool)  # True if completed (not cancelled)

    def __init__(self, threadpool: ThreadPoolService, parent: QObject | None = None):
        super().__init__(parent)
        self.threadpool = threadpool
        self.ctx: ProjectContext = fm_new_project()
        self._selected_track_id: str = ""
        self._active_clip_id: str = ""
        self.undo_stack = UndoStack(max_depth=400)

        # Pre-render state (MIDI->WAV background rendering)
        self._prerender_running: bool = False
        self._prerender_cancel: bool = False


    @property
    def active_clip_id(self) -> str:
        """Aktuell ausgewählter Clip (für ClipLauncher/PianoRoll/UI)."""
        if self._active_clip_id:
            return self._active_clip_id
        return str(getattr(self.ctx.project, "selected_clip_id", ""))

    @property
    def selected_track_id(self) -> str:
        """Aktuell ausgewählte Spur (UI)."""
        return self._selected_track_id

    @property
    def active_track_id(self) -> str:
        """Backwards-compat Alias für ältere UI-Teile."""
        return self._selected_track_id


    # ---------- helpers ----------
    def display_name(self) -> str:
        p = self.ctx.path
        return p.name if p else self.ctx.project.name

    def set_track_soundfont(self, track_id: str, sf2_path: str, bank: int = 0, preset: int = 0) -> None:
        """Assign a SoundFont (SF2) to an instrument track (Phase 4)."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            self.status.emit("Kein Track ausgewählt")
            return
        if trk.kind not in ("instrument", "bus", "master", "audio"):
            pass
        # Store on track (dataclass fields)
        try:
            trk.sf2_path = str(sf2_path)
            trk.sf2_bank = int(bank)
            trk.sf2_preset = int(preset)
        except Exception:
            trk.sf2_path = str(sf2_path)
        self.status.emit(f"SF2 gesetzt für {trk.name}: {Path(sf2_path).name} (Bank {bank}, Preset {preset})")
        self._emit_updated()

    def _emit_updated(self) -> None:
        self.project_updated.emit()

    def _emit_changed(self) -> None:
        self.project_changed.emit()
        self.project_updated.emit()


    # ---------- notation marks / annotations ----------
    def add_notation_mark(self, clip_id: str, *, beat: float, mark_type: str, data: dict | None = None) -> str:
        """Add a notation mark (sticky note, rest, ornament, tie/slur marker).

        Marks are stored on the project model (Project.notation_marks) and are
        persisted in the project JSON when the user saves the project.

        Args:
            clip_id: Target clip id (usually the active MIDI clip).
            beat: Timeline position in beats.
            mark_type: 'comment' | 'rest' | 'ornament' | ...
            data: Additional JSON-safe payload (dict).

        Returns:
            mark_id (str)
        """
        import uuid
        from datetime import datetime
        m = {
            "id": uuid.uuid4().hex,
            "clip_id": str(clip_id),
            "beat": float(beat),
            "type": str(mark_type),
            "data": dict(data or {}),
            "created_utc": datetime.utcnow().isoformat(timespec="seconds"),
        }
        try:
            marks = getattr(self.ctx.project, "notation_marks", None)
            if marks is None:
                self.ctx.project.notation_marks = []
                marks = self.ctx.project.notation_marks
            if isinstance(marks, list):
                marks.append(m)
        except Exception:
            pass
        self._emit_updated()
        return str(m.get("id", ""))

    def remove_notation_mark(self, mark_id: str) -> None:
        """Remove a notation mark by id."""
        try:
            marks = getattr(self.ctx.project, "notation_marks", []) or []
            if not isinstance(marks, list):
                return
            mid = str(mark_id)
            self.ctx.project.notation_marks = [m for m in marks if str(m.get("id", "")) != mid]
        except Exception:
            pass
        self._emit_updated()
    def _submit(self, fn: Callable[[], Any], on_ok: Callable[[Any], None] | None = None, on_err: Callable[[str], None] | None = None) -> None:
        w = Worker(fn)
        if on_ok:
            w.signals.result.connect(on_ok)
        if on_err:
            w.signals.error.connect(on_err)
        self.threadpool.submit(w)

    # ---------- automation playback ----------
    def apply_automation_value(self, track_id: str, param: str, value: float) -> None:
        """Apply an automation value to the live project model.

        This is intentionally lightweight: it updates the in-memory model (Track.volume/Track.pan)
        and notifies the UI via project_updated.

        Audio rendering is still placeholder; when an audio engine exists, it can be hooked here.
        """
        t = next((x for x in self.ctx.project.tracks if x.id == track_id), None)
        if not t:
            return

        if param == "volume":
            t.volume = float(max(0.0, min(1.0, value)))
        elif param == "pan":
            t.pan = float(max(-1.0, min(1.0, value)))
        else:
            return

        # Avoid spamming status; keep it silent.
        self._emit_updated()

    # ---------- project ----------
    def new_project(self, name: str = "Neues Projekt") -> None:
        self.ctx = fm_new_project(name)
        self._selected_track_id = ""
        self.undo_stack.clear()
        self.undo_changed.emit()
        self.status.emit("Neues Projekt erstellt.")
        self._emit_changed()
        self.project_opened.emit()

    def open_project(self, path: Path) -> None:
        def fn():
            return fm_open_project(path)

        def ok(ctx: ProjectContext):
            self.ctx = ctx
            self.undo_stack.clear()
            self.undo_changed.emit()
            try:
                keys = SettingsKeys()
                set_setting(keys.last_project, str(path))
            except Exception:
                pass
            self._selected_track_id = ""
            try:
                keys = SettingsKeys()
                set_setting(keys.last_project, str(path))
            except Exception:
                pass
            self.status.emit(f"Projekt geöffnet: {path}")
            self._emit_changed()
            self.project_opened.emit()

        def err(msg: str):
            self.error.emit(msg)

        self._submit(fn, ok, err)

    def save_project_as(self, path: Path) -> None:
        try:
            from pydaw.audio.vst3_host import embed_project_state_blobs
            embed_project_state_blobs(self.ctx.project)
        except Exception:
            pass
        def fn():
            return fm_save_project_to(path, self.ctx)

        def ok(ctx: ProjectContext):
            self.ctx = ctx
            self.status.emit(f"Projekt gespeichert: {path}")
            self._emit_changed()

        def err(msg: str):
            self.error.emit(msg)

        self._submit(fn, ok, err)

    def save_project(self) -> None:
        """Speichert das Projekt in die aktuelle Projektdatei (falls vorhanden)."""
        if not getattr(self.ctx, "path", None):
            self.error.emit("Projekt ist noch nicht gespeichert. Bitte zuerst 'Speichern unter…' verwenden.")
            return
        self.save_project_as(self.ctx.path)

    def save_snapshot(self, label: str = "") -> None:
        """Erstellt einen Projektstand (Snapshot) in <Projektordner>/stamps/."""
        if not getattr(self.ctx, "path", None):
            self.error.emit("Projekt ist noch nicht gespeichert. Bitte zuerst speichern, dann Snapshot erstellen.")
            return
        try:
            from pydaw.audio.vst3_host import embed_project_state_blobs
            embed_project_state_blobs(self.ctx.project)
        except Exception:
            pass

        def fn():
            root = self.ctx.path.parent
            stamps = root / "stamps"
            stamps.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (label or "snapshot").strip())
            safe = safe.strip("_-") or "snapshot"
            snap_path = stamps / f"{ts}__{safe}.pydaw.json"
            project_io.save_project(snap_path, self.ctx.project)
            return snap_path

        def ok(path: Path):
            self.status.emit(f"Projektstand gespeichert: {path.name}")
            # kein _emit_changed nötig; nur Datei-Operation

        def err(msg: str):
            self.error.emit(msg)

        self._submit(fn, ok, err)

    def load_snapshot(self, snapshot_path: Path) -> None:
        """Lädt einen Snapshot in das aktuelle Projekt (Media-Pfade bleiben unverändert)."""
        if not snapshot_path:
            return

        def fn():
            return project_io.load_project(snapshot_path)

        def ok(project):
            self.ctx.project = project
            self.undo_stack.clear()
            self.undo_changed.emit()
            self.status.emit(f"Projektstand geladen: {snapshot_path.name}")
            self._emit_changed()
            self.project_opened.emit()

        def err(msg: str):
            self.error.emit(msg)

        self._submit(fn, ok, err)

    # ---------- settings ----------
    def set_time_signature(self, ts: str) -> None:
        self.ctx.project.time_signature = str(ts or "4/4")
        self.status.emit(f"Taktart: {self.ctx.project.time_signature}")
        self._emit_updated()

    def set_snap_division(self, div: str) -> None:
        self.ctx.project.snap_division = str(div)
        self._emit_updated()

    # ---------- tracks ----------
    def add_track(self, kind: str, name: str | None = None, **_kwargs) -> None:
        label = str(name or {"audio": "Audio Track", "instrument": "Instrument Track", "bus": "Bus", "master": "Master"}.get(kind, "Track"))
        trk = Track(kind=kind, name=label)

        # keep master at end
        tracks = [t for t in self.ctx.project.tracks if t.kind != "master"]
        master = next((t for t in self.ctx.project.tracks if t.kind == "master"), None)
        tracks.append(trk)
        if master:
            tracks.append(master)
        self.ctx.project.tracks = tracks

        self._selected_track_id = trk.id
        self.status.emit(f"Spur hinzugefügt: {trk.name}")
        self._emit_updated()

    def ensure_audio_track(self) -> str:
        trk = next((t for t in self.ctx.project.tracks if t.kind == "audio"), None)
        if trk:
            return trk.id
        self.add_track("audio")
        trk = next((t for t in self.ctx.project.tracks if t.kind == "audio"), None)
        return trk.id if trk else ""


    def ensure_instrument_track(self) -> str:
        trk = next((t for t in self.ctx.project.tracks if t.kind == "instrument"), None)
        if trk:
            return trk.id
        self.add_track("instrument")
        trk = next((t for t in self.ctx.project.tracks if t.kind == "instrument"), None)
        return trk.id if trk else ""


    def remove_track(self, track_id: str) -> None:
        if not track_id:
            return
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk or trk.kind == "master":
            return
        self.ctx.project.tracks = [t for t in self.ctx.project.tracks if t.id != track_id]
        # remove clips on that track
        removed = [c.id for c in self.ctx.project.clips if c.track_id == track_id]
        self.ctx.project.clips = [c for c in self.ctx.project.clips if c.track_id != track_id]
        for cid in removed:
            self.ctx.project.midi_notes.pop(cid, None)

        if self._selected_track_id == track_id:
            self._selected_track_id = ""
        self.status.emit(f"Spur entfernt: {trk.name}")
        self._emit_updated()

    def rename_track(self, track_id: str, new_name: str) -> None:
        """Rename a track."""
        if not track_id or not new_name:
            return
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        # Don't allow renaming master track
        if trk.kind == "master":
            return
        old_name = trk.name
        trk.name = str(new_name).strip()
        self.status.emit(f"Spur umbenannt: '{old_name}' → '{trk.name}'")
        self._emit_updated()


    def group_tracks(self, track_ids: list[str], group_name: str | None = None) -> str:
        """Create a real group-bus track and assign children (v0.0.20.357)."""
        ids = [str(x) for x in (track_ids or []) if str(x)]
        if len(ids) < 2:
            return ""
        from pydaw.model.project import Track
        import uuid
        name = str(group_name or "").strip() or f"Group {len(ids)}"
        group_track = Track(
            id=f"grp_{uuid.uuid4().hex[:10]}",
            kind="group",
            name=name,
        )
        tracks = self.ctx.project.tracks or []
        first_child_idx = len(tracks)
        for i, t in enumerate(tracks):
            if str(getattr(t, 'id', '')) in ids and str(getattr(t, 'kind', '')) != 'master':
                first_child_idx = min(first_child_idx, i)
        tracks.insert(first_child_idx, group_track)
        gid = str(group_track.id)
        changed = 0
        for t in tracks:
            if str(getattr(t, 'id', '')) in ids and str(getattr(t, 'kind', '')) != 'master':
                try:
                    t.track_group_id = str(gid)
                    t.track_group_name = str(name)
                    changed += 1
                except Exception:
                    pass
        if changed:
            self.status.emit(f"Gruppenbus erstellt: {name} ({changed} Spuren)")
            self._emit_updated()
            return str(gid)
        try:
            tracks.remove(group_track)
        except Exception:
            pass
        return ""

    def ungroup_tracks(self, track_ids: list[str]) -> None:
        """Remove children from group and delete group-bus track if empty (v0.0.20.357)."""
        ids = [str(x) for x in (track_ids or []) if str(x)]
        if not ids:
            return
        tracks = self.ctx.project.tracks or []
        group_ids_touched: set = set()
        changed = 0
        for t in tracks:
            if str(getattr(t, 'id', '')) in ids:
                gid = str(getattr(t, 'track_group_id', '') or '')
                if gid:
                    group_ids_touched.add(gid)
                if gid or str(getattr(t, 'track_group_name', '') or ''):
                    try:
                        t.track_group_id = ''
                        t.track_group_name = ''
                        changed += 1
                    except Exception:
                        pass
        for gid in group_ids_touched:
            still_has_children = any(
                str(getattr(t, 'track_group_id', '') or '') == gid
                for t in tracks if str(getattr(t, 'kind', '') or '') != 'group'
            )
            if not still_has_children:
                tracks[:] = [
                    t for t in tracks
                    if not (str(getattr(t, 'id', '')) == gid and str(getattr(t, 'kind', '')) == 'group')
                ]
        if changed:
            self.status.emit(f"Spurgruppe aufgehoben ({changed} Spuren)")
            self._emit_updated()

    def move_track(self, track_id: str, delta: int) -> None:
        tid = str(track_id or "")
        if not tid:
            return
        tracks = [t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') != 'master']
        master = next((t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') == 'master'), None)
        try:
            src = next(i for i, t in enumerate(tracks) if str(getattr(t, 'id', '') or '') == tid)
        except StopIteration:
            return
        target = max(0, min(len(tracks) - 1, int(src) + int(delta)))
        if target == src:
            return
        trk = tracks.pop(src)
        tracks.insert(target, trk)
        if master is not None:
            tracks.append(master)
        self.ctx.project.tracks = tracks
        self._selected_track_id = tid
        self.status.emit(f"Spur verschoben: {getattr(trk, 'name', 'Track')}")
        self._emit_updated()

    def move_group_block(self, group_id: str, delta: int) -> None:
        gid = str(group_id or "")
        if not gid:
            return
        step = -1 if int(delta) < 0 else (1 if int(delta) > 0 else 0)
        if step == 0:
            return
        tracks = [t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') != 'master']
        master = next((t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') == 'master'), None)
        members = [
            t for t in tracks
            if str(getattr(t, 'track_group_id', '') or '') == gid
            and str(getattr(t, 'kind', '') or '') != 'master'
        ]
        if len(members) < 2:
            return
        member_ids = {str(getattr(t, 'id', '') or '') for t in members}
        remaining = [t for t in tracks if str(getattr(t, 'id', '') or '') not in member_ids]
        if not remaining:
            return
        try:
            first_member_idx = next(i for i, t in enumerate(tracks) if str(getattr(t, 'id', '') or '') in member_ids)
        except StopIteration:
            return
        before_non_member = sum(1 for t in tracks[:first_member_idx] if str(getattr(t, 'id', '') or '') not in member_ids)
        target_non_member_idx = max(0, min(len(remaining), before_non_member + step))
        if target_non_member_idx == before_non_member:
            return
        ordered = list(remaining)
        ordered[target_non_member_idx:target_non_member_idx] = list(members)
        if master is not None:
            ordered.append(master)
        self.ctx.project.tracks = ordered
        self._selected_track_id = str(getattr(members[0], 'id', '') or '')
        group_name = str(getattr(members[0], 'track_group_name', '') or 'Gruppe')
        self.status.emit(f"Gruppe verschoben: {group_name}")
        self._emit_updated()

    def move_tracks_block(self, track_ids: list[str], before_track_id: str = "") -> None:
        ids = [str(tid) for tid in (track_ids or []) if str(tid)]
        if not ids:
            return
        tracks = [t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') != 'master']
        master = next((t for t in (self.ctx.project.tracks or []) if str(getattr(t, 'kind', '') or '') == 'master'), None)
        order_map = {str(getattr(t, 'id', '') or ''): idx for idx, t in enumerate(tracks)}
        ordered_ids = [tid for tid in ids if tid in order_map]
        ordered_ids.sort(key=lambda tid: order_map.get(tid, 10**9))
        if not ordered_ids:
            return
        moving_set = set(ordered_ids)
        moving = [t for t in tracks if str(getattr(t, 'id', '') or '') in moving_set]
        if not moving:
            return
        remaining = [t for t in tracks if str(getattr(t, 'id', '') or '') not in moving_set]
        anchor = str(before_track_id or "")
        if anchor and anchor in moving_set:
            return
        if anchor:
            try:
                idx = next(i for i, t in enumerate(remaining) if str(getattr(t, 'id', '') or '') == anchor)
            except StopIteration:
                idx = len(remaining)
        else:
            idx = len(remaining)
        ordered = list(remaining)
        ordered[idx:idx] = list(moving)
        old_ids = [str(getattr(t, 'id', '') or '') for t in tracks]
        new_ids = [str(getattr(t, 'id', '') or '') for t in ordered]
        if old_ids == new_ids:
            return
        if master is not None:
            ordered.append(master)
        self.ctx.project.tracks = ordered
        self._selected_track_id = str(getattr(moving[0], 'id', '') or '')
        if len(moving) == 1:
            self.status.emit(f"Spur per Maus verschoben: {getattr(moving[0], 'name', 'Track')}")
        else:
            self.status.emit(f"{len(moving)} Spuren per Maus verschoben")
        self._emit_updated()

    # ---------- track state (Mute / Solo / Record Arm) ----------
    def set_track_muted(self, track_id: str, muted: bool) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.muted = bool(muted)
        self._emit_updated()

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.solo = bool(solo)
        self._emit_updated()

    def set_track_record_arm(self, track_id: str, armed: bool) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.record_arm = bool(armed)
        self._emit_updated()

    def set_track_input_pair(self, track_id: str, pair: int) -> None:
        """Set stereo input pair (1..N) used for monitoring/recording."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk or getattr(trk, "kind", "") == "master":
            return
        try:
            trk.input_pair = max(1, int(pair))
        except Exception:
            trk.input_pair = 1
        self._emit_updated()

    def set_track_output_pair(self, track_id: str, pair: int) -> None:
        """Reserved: stereo output pair (1..N) for future bus/submix routing."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk or getattr(trk, "kind", "") == "master":
            return
        try:
            trk.output_pair = max(1, int(pair))
        except Exception:
            trk.output_pair = 1
        self._emit_updated()

    def set_track_monitor(self, track_id: str, enabled: bool) -> None:
        """Enable/disable input monitoring for this track."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk or getattr(trk, "kind", "") == "master":
            return
        trk.monitor = bool(enabled)
        self._emit_updated()

    # ---------- clip grouping ----------
    def group_clips(self, clip_ids: List[str]) -> str:
        """Assigns a shared group_id to the given clips.

        Grouping is used by the arranger UI to move multiple clips together.
        """
        ids = [cid for cid in clip_ids if cid]
        if len(ids) < 2:
            return ""
        gid = f"grp_{uuid4().hex[:8]}"
        for c in self.ctx.project.clips:
            if c.id in ids:
                c.group_id = gid
        self.status.emit(f"{len(ids)} Clips gruppiert")
        self._emit_updated()
        return gid

    def ungroup_clips(self, clip_ids: List[str]) -> None:
        ids = [cid for cid in clip_ids if cid]
        if not ids:
            return
        for c in self.ctx.project.clips:
            if c.id in ids:
                c.group_id = ""
        self.status.emit(f"Gruppierung aufgehoben")
        self._emit_updated()

    # ---------- clips ----------
    def select_clip(self, clip_id: str) -> None:
        self.ctx.project.selected_clip_id = str(clip_id)  # dynamic attr for UI
        self._active_clip_id = str(clip_id)
        self.clip_selected.emit(str(clip_id))
        self.active_clip_changed.emit(str(clip_id))
        self._emit_updated()

    def get_clip(self, clip_id: str):
        """Return a clip by id (compat wrapper used by UI).

        Some UI components (Audio Editor / Clip Launcher) expect a ProjectService.get_clip
        helper. Keeping this method preserves backwards compatibility.
        """
        try:
            cid = str(clip_id or '').strip()
        except Exception:
            cid = ''
        if not cid:
            return None
        try:
            return next((c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        except Exception:
            return None

    def add_placeholder_clip_to_track(self, track_id: str, kind: str = "audio") -> None:
        if not track_id:
            return
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        kind = "midi" if trk.kind == "instrument" else "audio"
        clip = Clip(kind='audio', track_id=track_id, label=f"{kind.upper()} Clip")

        # If this import is meant for the Clip-Launcher, keep it out of the Arranger timeline.
        try:
            clip.launcher_only = not bool(place_in_arranger)
        except Exception:
            pass
        self.ctx.project.clips.append(clip)
        if kind == "midi":
            self.ctx.project.midi_notes[clip.id] = []
        self.status.emit(f"Clip hinzugefügt: {clip.label}")
        if bool(place_in_arranger):
            self.select_clip(clip.id)
        self._emit_updated()

    def delete_clip(self, clip_id: str) -> None:
        self.ctx.project.clips = [c for c in self.ctx.project.clips if c.id != clip_id]
        self.ctx.project.midi_notes.pop(clip_id, None)
        # remove from launcher slots
        self.ctx.project.clip_launcher = {k: v for k, v in self.ctx.project.clip_launcher.items() if v != clip_id}
        if getattr(self.ctx.project, "selected_clip_id", "") == clip_id:
            self.select_clip("")
        self.status.emit("Clip gelöscht.")
        self._emit_updated()

    def rename_clip(self, clip_id: str, name: str) -> None:
        c = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not c:
            return
        c.label = str(name)
        self._emit_updated()

    def duplicate_clip(self, clip_id: str) -> None:
        """Duplicate a clip horizontally (same track), snapped to the end.

        Expected DAW behavior in Arranger:
        - Ctrl+D duplicates the selected clip(s) on the SAME track
        - The new clip starts exactly at the end of the source clip
        - MIDI content is deep-copied (notes preserved)

        Note:
        A previous implementation duplicated *vertically* by creating a new
        track. That broke the documented workflow. Vertical duplication can
        be reintroduced later under a different shortcut.
        """
        c = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not c:
            return

        # Same-track, snapped to end
        try:
            new_start = float(getattr(c, "start_beats", 0.0)) + float(getattr(c, "length_beats", 0.0))
        except Exception:
            new_start = 0.0
        # Reduce floating drift when duplicating many times
        new_start = round(float(new_start), 6)

        base_label = str(getattr(c, "label", ""))
        new_label = base_label if base_label.endswith(" Copy") else (base_label + " Copy")

        dup = Clip(
            kind=c.kind,
            track_id=c.track_id,  # SAME TRACK ✅
            start_beats=new_start,  # END-SNAP ✅
            length_beats=c.length_beats,
            label=new_label,
            media_id=c.media_id,
            source_path=c.source_path,
        )
        self.ctx.project.clips.append(dup)
        
        # Copy MIDI notes with deepcopy (notes preserved)
        if dup.kind == "midi":
            import copy
            original_notes = self.ctx.project.midi_notes.get(c.id, [])
            if original_notes:
                self.ctx.project.midi_notes[dup.id] = [
                    copy.deepcopy(note) 
                    for note in original_notes
                ]
            else:
                self.ctx.project.midi_notes[dup.id] = []
        
        self.select_clip(dup.id)
        self.status.emit("Clip dupliziert (Ctrl+D)")
        self._emit_updated()

    def join_clips(self, clip_ids: list[str]) -> str | None:
        """Join multiple clips into one (Pro-DAW-Style Ctrl+J).
        
        Rules:
        - All clips must be on the same track
        - All clips must be MIDI clips (for now)
        - Creates new clip spanning from first to last clip
        - Combines all MIDI notes with adjusted timing
        - Deletes original clips
        
        Returns:
            New clip ID if successful, None if failed
        """
        if not clip_ids or len(clip_ids) < 2:
            return None
        
        # Get all clips
        clips = [c for c in self.ctx.project.clips if c.id in clip_ids]
        if len(clips) < 2:
            return None
        
        # Check: All on same track
        track_ids = set(c.track_id for c in clips)
        if len(track_ids) > 1:
            return None  # Clips on different tracks
        
        # Check: All MIDI clips
        if not all(c.kind == "midi" for c in clips):
            return None  # Only MIDI clips supported for now
        
        # Sort by start_beats
        clips_sorted = sorted(clips, key=lambda c: float(c.start_beats))
        
        # Calculate new clip bounds
        first_clip = clips_sorted[0]
        last_clip = clips_sorted[-1]
        
        new_start = float(first_clip.start_beats)
        new_end = float(last_clip.start_beats) + float(last_clip.length_beats)
        new_length = new_end - new_start
        
        # Create new joined clip
        joined = Clip(
            kind="midi",
            track_id=first_clip.track_id,
            start_beats=new_start,
            length_beats=new_length,
            label="Joined Clip",
        )
        
        # Combine all MIDI notes
        all_notes = []
        for clip in clips_sorted:
            clip_notes = self.ctx.project.midi_notes.get(clip.id, [])
            clip_offset = float(clip.start_beats) - new_start
            
            for note in clip_notes:
                # Adjust note timing relative to new clip start
                adjusted_note = copy.deepcopy(note)
                try:
                    adjusted_note.start_beats = float(getattr(note, "start_beats", 0.0)) + clip_offset
                except Exception:
                    adjusted_note.start_beats = clip_offset
                try:
                    adjusted_note.length_beats = float(getattr(note, "length_beats", 0.0))
                except Exception:
                    pass
                all_notes.append(adjusted_note.clamp())
        
        # Add joined clip and notes
        self.ctx.project.clips.append(joined)
        self.ctx.project.midi_notes[joined.id] = all_notes
        
        # Delete original clips
        for clip in clips:
            self.ctx.project.clips.remove(clip)
            if clip.id in self.ctx.project.midi_notes:
                del self.ctx.project.midi_notes[clip.id]
        
        # Select new joined clip
        self.select_clip(joined.id)
        self._emit_updated()
        
        return joined.id

    def split_clip(self, clip_id: str, split_beat: float) -> tuple[str, str] | None:
        """Split a clip into two clips at given beat position (Pro-DAW-Style Knife tool).
        
        Args:
            clip_id: Clip to split
            split_beat: Beat position where to split (relative to project, not clip)
        
        Returns:
            Tuple of (left_clip_id, right_clip_id) if successful, None if failed
        """
        clip = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not clip:
            return None
        
        # Split position must be inside the clip
        clip_start = float(clip.start_beats)
        clip_end = clip_start + float(clip.length_beats)
        
        if split_beat <= clip_start or split_beat >= clip_end:
            return None  # Split position outside clip
        
        # Calculate lengths
        left_length = split_beat - clip_start
        right_length = clip_end - split_beat
        
        if left_length < 0.25 or right_length < 0.25:
            return None  # Clips would be too small
        
        # Create right clip
        right_clip = Clip(
            kind=clip.kind,
            track_id=clip.track_id,
            start_beats=split_beat,
            length_beats=right_length,
            label=clip.label,
            media_id=clip.media_id,
            source_path=clip.source_path,
        )
        
        # Adjust left clip length
        clip.length_beats = left_length
        
        # Handle MIDI notes
        if clip.kind == "midi":
            orig_notes = self.ctx.project.midi_notes.get(clip.id, [])
            left_notes = []
            right_notes = []
            
            for note in orig_notes:
                note_start = float(note.start_beats)
                note_end = note_start + float(note.length_beats)
                
                # Note completely in left clip
                if note_end <= left_length:
                    left_notes.append(copy.deepcopy(note).clamp())
                
                # Note completely in right clip
                elif note_start >= left_length:
                    # Adjust timing relative to right clip
                    adjusted_note = copy.deepcopy(note)
                    adjusted_note.start_beats = note_start - left_length
                    adjusted_note.length_beats = float(getattr(note, "length_beats", 0.0))
                    right_notes.append(adjusted_note.clamp())
                
                # Note spans split - keep in left, truncate
                else:
                    truncated_note = copy.deepcopy(note)
                    truncated_note.start_beats = note_start
                    truncated_note.length_beats = left_length - note_start
                    left_notes.append(truncated_note.clamp())
            
            self.ctx.project.midi_notes[clip.id] = left_notes
            self.ctx.project.midi_notes[right_clip.id] = right_notes
        
        # Add right clip to project
        self.ctx.project.clips.append(right_clip)
        
        # Select right clip
        self.select_clip(right_clip.id)
        self._emit_updated()
        
        return (clip.id, right_clip.id)

    def move_clip(self, clip_id: str, start_beats: float, snap_beats: float | None = None) -> None:
        c = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not c:
            return
        val = max(0.0, float(start_beats))
        if snap_beats and float(snap_beats) > 0:
            g = float(snap_beats)
            val = round(val / g) * g
        c.start_beats = max(0.0, val)
        self._emit_updated()

    def resize_clip(self, clip_id: str, length_beats: float, snap_beats: float | None = None) -> None:
        c = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not c:
            return
        val = max(0.25, float(length_beats))
        if snap_beats and float(snap_beats) > 0:
            g = float(snap_beats)
            val = max(g, round(val / g) * g)
        c.length_beats = max(0.25, val)
        self._emit_updated()


    def trim_clip_left(
        self,
        clip_id: str,
        start_beats: float,
        length_beats: float,
        offset_beats: float = 0.0,
        offset_seconds: float = 0.0,
        snap_beats: float | None = None,
    ) -> None:
        """Trim/extend the *left* edge of a clip."""
        c = next((c for c in self.ctx.project.clips if c.id == str(clip_id)), None)
        if not c:
            return

        st = max(0.0, float(start_beats))
        ln = max(0.25, float(length_beats))

        if snap_beats and float(snap_beats) > 0:
            g = float(snap_beats)
            st = max(0.0, round(st / g) * g)
            ln = max(g, round(ln / g) * g)

        c.start_beats = st
        c.length_beats = ln
        c.offset_beats = max(0.0, float(offset_beats))
        c.offset_seconds = max(0.0, float(offset_seconds))

        self._emit_updated()

    def move_clip_track(self, clip_id: str, track_id: str) -> None:
        c = next((c for c in self.ctx.project.clips if c.id == clip_id), None)
        if not c:
            return
        c.track_id = str(track_id)
        self._emit_updated()

    # ---------- track editing ----------
    def set_track_kind(self, track_id: str, kind: str) -> None:
        """Change track kind (e.g. audio -> instrument) in a project-safe way."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        k = str(kind or "audio")
        if getattr(trk, "kind", "audio") == k:
            return
        trk.kind = k
        self._emit_updated()


    # ---------- clip creation (non-placeholder) ----------
    def add_midi_clip_at(self, track_id: str, start_beats: float, length_beats: float = 4.0, label: str = "") -> str:
        """Create a real MIDI clip (notes editable in PianoRoll) on an instrument track.
        
        FIXED v0.0.19.7.4: Intelligente Label-Generierung wie eine Pro-DAW!
        """
        if not track_id:
            track_id = self.ensure_instrument_track()
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        # If the user draws a MIDI clip on a non-instrument track in the arranger,
        # we convert that track to an instrument track instead of silently creating
        # the clip elsewhere (which looks like "nothing happened" in the UI).
        if trk and getattr(trk, "kind", "audio") != "instrument":
            old_kind = str(getattr(trk, "kind", "audio"))
            trk.kind = "instrument"
            if old_kind == "audio":
                if str(getattr(trk, "name", "")).strip().lower().startswith("audio"):
                    trk.name = "Instrument Track"
        if not trk:
            track_id = self.ensure_instrument_track()
        
        # Generate intelligent label if not provided
        if not label or label == "MIDI Clip":
            label = self._generate_midi_clip_label(track_id)
        
        clip = Clip(kind="midi", track_id=track_id, start_beats=float(start_beats), length_beats=max(0.25, float(length_beats)), label=str(label))
        self.ctx.project.clips.append(clip)
        self.ctx.project.midi_notes.setdefault(clip.id, [])
        self.select_clip(clip.id)
        self.status.emit(f"MIDI-Clip erstellt: {clip.label}")
        self._emit_updated()
        return clip.id

    def _audio_duration_seconds(self, path: Path) -> float:
        """Best-effort duration for common formats. WAV is exact; others optional."""
        p = Path(path)
        try:
            if p.suffix.lower() in (".wav", ".wave"):
                with contextlib.closing(wave.open(str(p), "rb")) as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate() or 48000
                    return float(frames) / float(rate)
        except Exception:
            pass
        # Optional: pydub (requires ffmpeg for mp3/aac/ogg)
        try:
            from pydub import AudioSegment  # type: ignore
            seg = AudioSegment.from_file(str(p))
            return float(len(seg)) / 1000.0
        except Exception:
            return 0.0

    def _generate_midi_clip_label(self, track_id: str) -> str:
        """Generate intelligent MIDI clip label like 'Track1 MIDI 1'.
        
        FIXED v0.0.19.7.4: Clip Naming wie eine Pro-DAW!
        """
        try:
            # Get track name
            track = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
            track_name = "Track"
            if track:
                name = str(getattr(track, "name", "")).strip()
                if name:
                    track_name = name
            
            # Count existing MIDI clips on this track
            midi_clips_on_track = [
                c for c in self.ctx.project.clips 
                if c.track_id == track_id and c.kind == "midi"
            ]
            clip_number = len(midi_clips_on_track) + 1
            
            # Generate label like "Track1 MIDI 1"
            return f"{track_name} MIDI {clip_number}"
        
        except Exception as e:
            print(f"[ProjectService._generate_midi_clip_label] Error: {e}")
            return "MIDI Clip"



    def add_audio_clip_placeholder_at(self, track_id: str, start_beats: float = 0.0, length_beats: float = 4.0, label: str = "Audio Clip") -> str:
        """Create an empty/placeholder audio clip (no media yet).

        Useful for DAW workflow: Region first, content later (record/import).
        """
        tid = track_id or self.ensure_audio_track()
        clip = Clip(kind="audio", track_id=str(tid), start_beats=max(0.0, float(start_beats)), length_beats=max(0.25, float(length_beats)), label=str(label))
        # Keep source_path/media_id None -> waveform preview shows placeholder text.
        self.ctx.project.clips.append(clip)
        self.select_clip(clip.id)
        self.status.emit(f"Audio-Clip (Platzhalter) erstellt: {clip.label}")
        self._emit_updated()
        return clip.id

    def add_audio_clip_from_file_at(self, track_id: str, path: Path, start_beats: float = 0.0, launcher_slot_key: str | None = None, place_in_arranger: bool = True) -> Optional[str]:
        """Import audio into project media and create an audio clip at a specific position."""
        p = Path(path)
        if not p.exists():
            self.error.emit("Audio-Datei nicht gefunden.")
            return None

        def fn():
            return fm_import_audio(p, self.ctx)

        def ok(item):
            try:
                tid = track_id or self.ensure_audio_track()
                project_bpm = float(self.ctx.project.bpm or 120.0)
                secs = self._audio_duration_seconds(Path(item.path))

                # Phase 3: basic sync by detecting a source BPM from the file name.
                # Examples: "loop_150bpm.wav", "Kick (110 BPM).wav"
                source_bpm: Optional[float] = None
                m = re.search(r"(\d+(?:\.\d+)?)\s*bpm", (p.stem or ""), flags=re.IGNORECASE)
                if m:
                    try:
                        source_bpm = float(m.group(1))
                    except Exception:
                        source_bpm = None

                # If we know the source BPM, we compute the clip length in *beats of the source*,
                # so it will align to the grid after time-stretch.
                if secs > 0:
                    if source_bpm:
                        beats = secs * source_bpm / 60.0
                    else:
                        beats = secs * project_bpm / 60.0
                else:
                    beats = 4.0

                clip = Clip(kind="audio", track_id=tid, label=item.label or p.stem, media_id=item.id, source_path=str(Path(item.path)), source_bpm=source_bpm)
                clip.start_beats = max(0.0, float(start_beats))
                clip.length_beats = max(0.25, float(beats))

                # IMPORTANT: launcher-only clips must not appear in Arranger.
                # ArrangerCanvas filters clips via clip.launcher_only.
                clip.launcher_only = bool(not place_in_arranger)

                self.ctx.project.clips.append(clip)
                # Optional: assign to Clip-Launcher slot (Overlay drop)
                if launcher_slot_key:
                    try:
                        self.ctx.project.clip_launcher[str(launcher_slot_key)] = str(clip.id)
                    except Exception:
                        pass
                self.select_clip(clip.id)
                self.status.emit(f"Audio-Clip erstellt: {clip.label}")
                self._emit_updated()
            except Exception as e:
                self.error.emit(f"Audio-Clip Fehler: {e}")

        def err(msg: str):
            self.error.emit(f"Audio import fehlgeschlagen: {msg}")

        self._submit(fn, ok, err)
        return None

    def import_midi_to_track_at(self, path: Path, track_id: str, start_beats: float = 0.0, length_beats: float = 4.0) -> str:
        """Imports a MIDI file as a new MIDI clip at the given position.

        Phase 2: real parsing (note-on/note-off) into MidiNote events.
        We map MIDI tick-time into *beats* using ticks_per_beat. Tempo changes affect seconds,
        but the grid in the arranger is beat-based, so this mapping is stable.
        """
        p = Path(path)
        if not p.exists():
            self.error.emit("MIDI-Datei nicht gefunden.")
            return ""

        try:
            import mido  # type: ignore
        except Exception:
            self.error.emit("MIDI Import: Abhängigkeit 'mido' fehlt (pip install -r requirements.txt).")
            return ""

        mf = mido.MidiFile(str(p))
        tpb = float(mf.ticks_per_beat or 480)

        # Merge all tracks into one time-ordered stream.
        abs_tick = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}  # (channel,pitch) -> (start_tick, velocity)
        notes: list[MidiNote] = []

        for msg in mido.merge_tracks(mf.tracks):
            abs_tick += int(getattr(msg, "time", 0) or 0)
            if msg.type == "note_on" and int(getattr(msg, "velocity", 0) or 0) > 0:
                key = (int(getattr(msg, "channel", 0) or 0), int(getattr(msg, "note", 0) or 0))
                active[key] = (abs_tick, int(getattr(msg, "velocity", 0) or 0))
            elif msg.type in ("note_off", "note_on"):
                # note_on with velocity 0 is note_off
                vel = int(getattr(msg, "velocity", 0) or 0)
                if msg.type == "note_on" and vel != 0:
                    continue
                key = (int(getattr(msg, "channel", 0) or 0), int(getattr(msg, "note", 0) or 0))
                if key in active:
                    start_tick, start_vel = active.pop(key)
                    end_tick = abs_tick
                    if end_tick <= start_tick:
                        continue
                    start_b = float(start_tick) / tpb
                    len_b = float(end_tick - start_tick) / tpb
                    notes.append(MidiNote(pitch=key[1], start_beats=start_b + float(start_beats), length_beats=max(0.05, len_b), velocity=start_vel))

        # Compute clip length from notes if available.
        max_end = max((n.start_beats + n.length_beats for n in notes), default=float(start_beats) + float(length_beats))
        clip_len = max(float(length_beats), max_end - float(start_beats))
        clip_len = max(0.25, clip_len)

        clip_id = self.add_midi_clip_at(track_id, start_beats=start_beats, length_beats=clip_len, label=p.stem or "MIDI")
        self.ctx.project.midi_notes[clip_id] = notes
        self.status.emit(f"MIDI importiert: {p.name} ({len(notes)} Noten)")
        self._emit_updated()
        return clip_id

    def import_midi(self, path: Any, track_id: Optional[str] = None, start_beats: float = 0.0) -> str:
        """Import a MIDI file and place it into an instrument track.

        UI-friendly entry point.
        - If `track_id` is given and is an instrument track, it is used.
        - Otherwise the current active track is used if it is an instrument track.
        - Otherwise a new instrument track is created.
        """
        p = Path(str(path))

        # Prefer explicit target track
        tid = track_id or self.active_track_id
        if tid:
            trk = next((t for t in self.ctx.project.tracks if t.id == tid), None)
            if not trk or trk.kind != 'instrument':
                tid = ''

        if not tid:
            tid = self.add_track(kind='instrument', name='Instrument Track').id
            self.set_active_track(tid)

        return self.import_midi_to_track_at(p, track_id=tid, start_beats=float(start_beats), length_beats=16.0)

    # --- Track controls (Phase 2: UI toggles) ---
    def toggle_track_mute(self, track_id: str) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.muted = not bool(trk.muted)
        self.status.emit(f"Mute: {trk.name} = {trk.muted}")
        self._emit_updated()

    def toggle_track_solo(self, track_id: str) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.solo = not bool(trk.solo)
        self.status.emit(f"Solo: {trk.name} = {trk.solo}")
        self._emit_updated()

    def toggle_track_arm(self, track_id: str) -> None:
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.record_arm = not bool(getattr(trk, "record_arm", False))
        self.status.emit(f"Rec-Arm: {trk.name} = {trk.record_arm}")
        self._emit_updated()

    # --- Clip Launcher (Scenes) ---
    def set_launcher_settings(self, quantize: str, mode: str) -> None:
        """Persist launcher settings on the project model and notify UI.

        Quantize: Off | 1 Beat | 1 Bar
        Mode: Trigger | Toggle | Gate
        """
        q = str(quantize or '1 Bar')
        m = str(mode or 'Trigger')
        if q not in ['Off', '1 Beat', '1 Bar']:
            q = '1 Bar'
        if m not in ['Trigger', 'Toggle', 'Gate']:
            m = 'Trigger'
        try:
            self.ctx.project.launcher_quantize = q
            self.ctx.project.launcher_mode = m
        except Exception:
            pass
        self.status.emit(f'Launcher: Quantize={q}, Mode={m}')
        self._emit_updated()

    def cliplauncher_assign(self, slot_key: str, clip_id: str) -> None:
        """Assign an existing clip to a launcher slot (slot_key -> clip_id).

        Slot keys are stored on the project model (project.clip_launcher).
        """
        key = str(slot_key or '').strip()
        cid = str(clip_id or '').strip()
        if not key or not cid:
            return
        # only assign if clip exists
        if not any(c.id == cid for c in self.ctx.project.clips):
            self.error.emit('ClipLauncher: Clip nicht gefunden.')
            return
        try:
            self.ctx.project.clip_launcher[key] = cid
        except Exception:
            return
        self.status.emit('ClipLauncher: Slot belegt')
        self._emit_updated()

    def cliplauncher_clear(self, slot_key: str) -> None:
        """Clear a launcher slot."""
        key = str(slot_key or '').strip()
        if not key:
            return
        try:
            if key in self.ctx.project.clip_launcher:
                del self.ctx.project.clip_launcher[key]
        except Exception:
            pass
        self.status.emit('ClipLauncher: Slot geleert')
        self._emit_updated()

    # --- Clip grouping (Phase 2) ---
    def group_clips(self, clip_ids: List[str]) -> str:
        ids = [cid for cid in clip_ids if cid]
        if len(ids) < 2:
            return ""
        gid = f"grp_{uuid.uuid4().hex[:8]}"
        for c in self.ctx.project.clips:
            if c.id in ids:
                c.group_id = gid
        self.status.emit(f"Gruppe erstellt: {gid} ({len(ids)} Clips)")
        self._emit_updated()
        return gid

    def ungroup_clips(self, clip_ids: List[str]) -> None:
        ids = [cid for cid in clip_ids if cid]
        for c in self.ctx.project.clips:
            if c.id in ids:
                c.group_id = ""
        self.status.emit("Gruppe aufgelöst")
        self._emit_updated()

    # ---------- audio import/export (UI compatibility) ----------
    def import_audio(self, path: Path) -> str:
        """Imports audio into the active/first audio track (legacy UI entry point).

        Note: audio import is threaded; the created clip is committed asynchronously.
        This function returns an empty string for compatibility.
        """
        tid = self.active_track_id
        if not tid:
            tid = next((t.id for t in self.ctx.project.tracks if t.kind == 'audio'), '')
        if not tid:
            tid = self.ensure_audio_track()
        try:
            self.add_audio_clip_from_file_at(tid, Path(path), start_beats=0.0)
        except Exception as e:
            self.error.emit(f"Audio import fehlgeschlagen: {e}")
        return ''

    def import_audio_to_track_at(self, path: Path, track_id: str, start_beats: float = 0.0, length_beats: float = 4.0) -> str:
        """Legacy signature: import an audio file and place it at the given position.

        `length_beats` is ignored because the clip length is derived from the file duration.
        Import is threaded; this returns an empty string for compatibility.
        """
        try:
            self.add_audio_clip_from_file_at(str(track_id), Path(path), start_beats=float(start_beats))
        except Exception as e:
            self.error.emit(f"Audio import fehlgeschlagen: {e}")
        return ''

    
    # ---------- Undo / Redo (Command Pattern) ----------
    def snapshot_midi_notes(self, clip_id: str) -> MidiSnapshot:
        """Create a lightweight snapshot of a clip's MIDI notes."""
        snap: MidiSnapshot = []
        notes = self.ctx.project.midi_notes.get(str(clip_id), []) or []
        for n in notes:
            try:
                snap.append(
                    {
                        "pitch": int(getattr(n, "pitch", 60)),
                        "start_beats": float(getattr(n, "start_beats", 0.0)),
                        "length_beats": float(getattr(n, "length_beats", 1.0)),
                        "velocity": int(getattr(n, "velocity", 100)),
                        "accidental": int(getattr(n, "accidental", 0) or 0),
                        "tie_to_next": bool(getattr(n, "tie_to_next", False)),
                        "expressions": (getattr(n, "expressions", {}) or {}),
                        "expression_curve_types": (getattr(n, "expression_curve_types", {}) or {}),
                    }
                )
            except Exception:
                continue
        return snap

    def _apply_midi_snapshot(self, clip_id: str, snap: MidiSnapshot) -> None:
        from dataclasses import fields as _dc_fields
        from pydaw.model.midi import MidiNote
        note_keys = {f.name for f in _dc_fields(MidiNote)}
        notes = []
        for d in (snap or []):
            try:
                if not isinstance(d, dict):
                    continue
                d2 = {k: v for k, v in d.items() if k in note_keys}
                notes.append(
                    MidiNote(
                        pitch=int(d2.get("pitch", 60)),
                        start_beats=float(d2.get("start_beats", 0.0)),
                        length_beats=float(d2.get("length_beats", 1.0)),
                        velocity=int(d2.get("velocity", 100)),
                        accidental=int(d2.get("accidental", 0) or 0),
                        tie_to_next=bool(d2.get("tie_to_next", False)),
                        expressions=dict(d2.get("expressions", {}) or {}) if isinstance(d2.get("expressions", {}), dict) else {},
                        expression_curve_types=dict(d2.get("expression_curve_types", {}) or {}) if isinstance(d2.get("expression_curve_types", {}), dict) else {},
                    ).clamp()
                )
            except Exception:
                continue
        self.set_midi_notes(str(clip_id), notes)

    def set_note_expression_points(
        self,
        clip_id: str,
        note_index: int,
        param: str,
        points: list[dict] | None,
        *,
        label: str = "Edit Note Expression",
    ) -> None:
        """AltProjectService mirror of ProjectService note-expression API."""
        clip_id = str(clip_id)
        try:
            idx = int(note_index)
        except Exception:
            return

        before = self.snapshot_midi_notes(clip_id)
        notes = self.get_midi_notes(clip_id) or []
        if not (0 <= idx < len(notes)):
            return

        try:
            n = notes[idx]
            if hasattr(n, "set_expression_points"):
                n.set_expression_points(str(param), points)  # type: ignore[attr-defined]
            else:
                expr = getattr(n, "expressions", None)
                if not isinstance(expr, dict):
                    expr = {}
                if points:
                    expr[str(param)] = list(points)
                else:
                    expr.pop(str(param), None)
                setattr(n, "expressions", expr)
            try:
                n.clamp()
            except Exception:
                pass
        except Exception:
            return

        try:
            self.set_midi_notes(clip_id, notes)
        except Exception:
            pass
        self.commit_midi_notes_edit(clip_id, before, str(label))

    def commit_midi_notes_edit(self, clip_id: str, before: MidiSnapshot, label: str) -> None:
        """Register an undo step for edits already applied to the model."""
        after = self.snapshot_midi_notes(str(clip_id))
        if before == after:
            return
        cmd = MidiNotesEditCommand(
            clip_id=str(clip_id),
            before=list(before or []),
            after=list(after or []),
            label=str(label or "Edit MIDI"),
            apply_snapshot=self._apply_midi_snapshot,
        )
        self.undo_stack.push(cmd, already_done=True)
        self.undo_changed.emit()
        # Ensure UI/services observe the final state.
        try:
            self._emit_updated()
        except Exception:
            pass
        try:
            self.midi_notes_committed.emit(str(clip_id))
        except Exception:
            pass

    def can_undo(self) -> bool:
        return self.undo_stack.can_undo()

    def can_redo(self) -> bool:
        return self.undo_stack.can_redo()

    def undo_label(self) -> str:
        return self.undo_stack.undo_label()

    def redo_label(self) -> str:
        return self.undo_stack.redo_label()

    def undo(self) -> None:
        if not self.undo_stack.can_undo():
            return
        self.undo_stack.undo()
        self.undo_changed.emit()

    def redo(self) -> None:
        if not self.undo_stack.can_redo():
            return
        self.undo_stack.redo()
        self.undo_changed.emit()


    # ---------- MIDI notes backing store (Piano Roll) ----------
    def get_midi_notes(self, clip_id: str):
        return list(self.ctx.project.midi_notes.get(clip_id, []))

    def set_midi_notes(self, clip_id: str, notes):
        self.ctx.project.midi_notes[clip_id] = list(notes)
        # Auto-extend to cover farthest note end
        try:
            nl = self.ctx.project.midi_notes.get(str(clip_id), []) or []
            if nl:
                end_b = max(float(getattr(n, 'start_beats', 0.0)) + float(getattr(n, 'length_beats', 0.0)) for n in nl)
                if self.extend_clip_if_needed(str(clip_id), float(end_b), snap_to_bar=True):
                    return
        except Exception:
            pass
        self._emit_updated()

    def add_midi_note(
        self,
        clip_id: str,
        note=None,
        *,
        pitch: int | None = None,
        start_beats: float | None = None,
        length_beats: float | None = None,
        velocity: int = 100,
        accidental: int = 0,
        tie_to_next: bool = False,
        expressions: dict | None = None,
    ):
        """Add a MIDI note to a clip.

        The UI calls this in two variants:
        - add_midi_note(clip_id, MidiNote(...))
        - add_midi_note(clip_id, pitch=..., start_beats=..., length_beats=...)
        """
        from pydaw.model.midi import MidiNote

        if note is None:
            if pitch is None or start_beats is None or length_beats is None:
                return
            note = MidiNote(
                pitch=int(pitch),
                start_beats=float(start_beats),
                length_beats=float(length_beats),
                velocity=int(velocity),
                accidental=int(accidental or 0),
                tie_to_next=bool(tie_to_next),
                expressions=dict(expressions or {}) if isinstance(expressions, dict) else {},
            )
        elif isinstance(note, dict):
            # Convenience: accept dict-like notes
            note = MidiNote(
                pitch=int(note.get("pitch", 60)),
                start_beats=float(note.get("start_beats", 0.0)),
                length_beats=float(note.get("length_beats", 1.0)),
                velocity=int(note.get("velocity", 100)),
                accidental=int(note.get("accidental", 0) or 0),
                tie_to_next=bool(note.get("tie_to_next", False)),
                expressions=dict(note.get("expressions", {}) or {}) if isinstance(note.get("expressions", {}), dict) else {},
            )

        notes = self.ctx.project.midi_notes.setdefault(clip_id, [])
        notes.append(note)
        try:
            end_b = float(getattr(note, 'start_beats', 0.0)) + float(getattr(note, 'length_beats', 0.0))
            if self.extend_clip_if_needed(str(clip_id), float(end_b), snap_to_bar=True):
                return
        except Exception:
            pass
        self._emit_updated()

    # Backwards-compat alias used by some UI code paths
    def add_note(
        self,
        clip_id: str,
        note=None,
        *,
        pitch: int | None = None,
        start_beats: float | None = None,
        length_beats: float | None = None,
        velocity: int = 100,
    ):
        """Alias for add_midi_note.

        Some older UI paths (Arranger ctrl-drag duplicate) call `add_note()`.
        Keep this wrapper to avoid hard crashes.
        """
        return self.add_midi_note(
            clip_id,
            note,
            pitch=pitch,
            start_beats=start_beats,
            length_beats=length_beats,
            velocity=velocity,
        )

    def delete_midi_note_at(self, clip_id: str, idx_or_pitch: int, start_beats: float | None = None):
        """Delete a MIDI note.

        Supported call variants (for UI compatibility):
        - delete_midi_note_at(clip_id, idx)
        - delete_midi_note_at(clip_id, pitch, start_beats)
        """
        notes = self.ctx.project.midi_notes.get(clip_id, [])
        if start_beats is None:
            # Treat 2nd arg as index
            idx = int(idx_or_pitch)
            if 0 <= idx < len(notes):
                notes.pop(idx)
                self._emit_updated()
            return

        # Treat 2nd/3rd arg as (pitch, start_beats)
        pitch = int(idx_or_pitch)
        sb = float(start_beats)
        for i, n in enumerate(list(notes)):
            try:
                if int(getattr(n, "pitch", -1)) == pitch and abs(float(getattr(n, "start_beats", -999)) - sb) < 1e-6:
                    notes.pop(i)
                    self._emit_updated()
                    return
            except Exception:
                continue

    def move_midi_note(self, clip_id: str, idx: int, new_start: float, new_pitch: int):
        notes = self.ctx.project.midi_notes.get(clip_id, [])
        if 0 <= idx < len(notes):
            n = notes[idx]
            try:
                n.start_beats = max(0.0, float(new_start))
                n.pitch = int(new_pitch)
            except Exception:
                pass
            try:
                end_b = float(getattr(n, 'start_beats', 0.0)) + float(getattr(n, 'length_beats', 0.0))
                if self.extend_clip_if_needed(str(clip_id), float(end_b), snap_to_bar=True):
                    return
            except Exception:
                pass
            self._emit_updated()

    def move_midi_notes_batch(self, clip_id: str, updates: list[tuple[int, float, int]]) -> None:
        """Move multiple MIDI notes and emit a single project_updated.

        This is used for multi-selection dragging in the PianoRoll to avoid
        excessive signal emissions while the mouse is moving.

        Args:
            clip_id: MIDI clip id
            updates: list of (idx, new_start_beats, new_pitch)
        """
        notes = self.ctx.project.midi_notes.get(clip_id, [])
        changed = False
        for idx, new_start, new_pitch in updates:
            try:
                i = int(idx)
            except Exception:
                continue
            if not (0 <= i < len(notes)):
                continue
            n = notes[i]
            try:
                n.start_beats = max(0.0, float(new_start))
                n.pitch = int(new_pitch)
                changed = True
            except Exception:
                continue
        if changed:
            try:
                max_end = 0.0
                for n in notes:
                    try:
                        max_end = max(max_end, float(getattr(n, 'start_beats', 0.0)) + float(getattr(n, 'length_beats', 0.0)))
                    except Exception:
                        continue
                if max_end > 0 and self.extend_clip_if_needed(str(clip_id), float(max_end), snap_to_bar=True):
                    return
            except Exception:
                pass
            self._emit_updated()

    def resize_midi_note_length(self, clip_id: str, idx: int, new_length: float):
        notes = self.ctx.project.midi_notes.get(clip_id, [])
        if 0 <= idx < len(notes):
            n = notes[idx]
            try:
                n.length_beats = max(0.25, float(new_length))
            except Exception:
                pass
            try:
                end_b = float(getattr(n, 'start_beats', 0.0)) + float(getattr(n, 'length_beats', 0.0))
                if self.extend_clip_if_needed(str(clip_id), float(end_b), snap_to_bar=True):
                    return
            except Exception:
                pass
            self._emit_updated()


    # ---------- MIDI clip length helpers ----------
    def _beats_per_bar(self) -> float:
        """Return the current bar length in beats based on the project's time signature.

        Beats are quarter-note beats (i.e. 4/4 => 4.0 beats per bar).
        """
        ts = str(getattr(self.ctx.project, 'time_signature', '4/4') or '4/4')
        m = re.match(r'^\s*(\d+)\s*/\s*(\d+)\s*$', ts)
        if not m:
            return 4.0
        try:
            num = float(m.group(1))
            den = float(m.group(2))
            if den <= 0:
                return 4.0
            # Whole note = 4 beats (quarter-note beats)
            return max(0.25, float(num) * (4.0 / float(den)))
        except Exception:
            return 4.0

    def _snap_division_beats(self) -> float:
        """Convert project snap division to beats.

        Examples:
            '1/16' -> 0.25 beats
            '1/8'  -> 0.5 beats
            '1/4'  -> 1.0 beat
            '1 Bar' -> beats_per_bar
            '1 Beat' -> 1.0
        """
        div = str(getattr(self.ctx.project, 'snap_division', '1/16') or '1/16')
        d = div.strip().lower()
        if 'bar' in d:
            return float(self._beats_per_bar())
        if 'beat' in d:
            return 1.0
        m = re.match(r'^\s*1\s*/\s*(\d+)\s*$', div)
        if m:
            try:
                den = float(m.group(1))
                if den > 0:
                    return max(1.0 / 64.0, 4.0 / den)
            except Exception:
                pass
        # fallback: 1/16
        return 0.25

    def extend_clip_if_needed(self, clip_id: str, end_beats: float, *, snap_to_bar: bool = True) -> bool:
        """Auto-extend a MIDI clip if note content exceeds its current end.

        This is the canonical implementation for Task 9.

        Args:
            clip_id: target clip id
            end_beats: clip-local end position of content (start+length)
            snap_to_bar: if True, extend to the next full bar.

        Returns:
            True if the clip length changed.
        """
        try:
            cid = str(clip_id)
            end_b = max(0.0, float(end_beats))
        except Exception:
            return False

        clip = next((c for c in self.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
        if not clip:
            return False
        if str(getattr(clip, 'kind', '')) != 'midi':
            return False

        try:
            cur_len = float(getattr(clip, 'length_beats', 4.0) or 0.0)
        except Exception:
            cur_len = 4.0

        if end_b <= cur_len + 1e-9:
            return False

        if snap_to_bar:
            bar = float(self._beats_per_bar())
            bar = max(1.0 / 64.0, bar)
            new_len = math.ceil(end_b / bar) * bar
        else:
            g = float(self._snap_division_beats())
            g = max(1.0 / 64.0, g)
            new_len = math.ceil(end_b / g) * g

        try:
            clip.length_beats = float(max(cur_len, new_len))
        except Exception:
            return False

        self._emit_updated()
        return True

    def ensure_midi_clip_length(self, clip_id: str, end_beats: float) -> None:
        """Backward compatible alias for older UI code."""
        try:
            self.extend_clip_if_needed(str(clip_id), float(end_beats), snap_to_bar=True)
        except Exception:
            return

    # ---------------------------------------------------------------------
    # UI compatibility API (Undo/Redo) - required by main_window.py
    # ---------------------------------------------------------------------
    def can_undo(self) -> bool:
        """Prüfe ob Undo möglich ist."""
        try:
            return bool(self.undo_stack.can_undo())
        except Exception:
            return False

    def can_redo(self) -> bool:
        """Prüfe ob Redo möglich ist."""
        try:
            return bool(self.undo_stack.can_redo())
        except Exception:
            return False

    def undo_label(self) -> str:
        """Hole Undo-Label."""
        try:
            return self.undo_stack.undo_label() or "Undo"
        except Exception:
            return "Undo"

    def redo_label(self) -> str:
        """Hole Redo-Label."""
        try:
            return self.undo_stack.redo_label() or "Redo"
        except Exception:
            return "Redo"

    def undo(self):
        """Führe Undo aus."""
        try:
            self.undo_stack.undo()
            self._emit_updated()
        except Exception as e:
            print(f"Undo failed: {e}")

    def redo(self):
        """Führe Redo aus."""
        try:
            self.undo_stack.redo()
            self._emit_updated()
        except Exception as e:
            print(f"Redo failed: {e}")

    # ---------------------------------------------------------------------
    # Performance: MIDI pre-render (render MIDI->WAV caches in background)
    # ---------------------------------------------------------------------

    def cancel_prerender(self) -> None:
        """Request cancellation of a running pre-render job."""
        self._prerender_cancel = True

    def _collect_midi_prerender_jobs(self, clip_ids: list[str] | None = None, track_id: str | None = None):
        """Return a list of (clip, track) pairs for MIDI clips that can be rendered.

        Optional filters:
            clip_ids: only include these clip IDs
            track_id: only include clips belonging to this track
        """
        jobs = []
        try:
            proj = self.ctx.project
            tracks = list(getattr(proj, "tracks", []) or [])
            clips = list(getattr(proj, "clips", []) or [])
            track_by_id = {str(getattr(t, "id", "")): t for t in tracks}
            clip_id_set = set(str(x) for x in (clip_ids or []) if str(x)) if clip_ids else None
            track_filter = str(track_id) if track_id else None
            for c in clips:
                try:
                    if str(getattr(c, "kind", "")) != "midi":
                        continue
                    tid = str(getattr(c, "track_id", ""))
                    if track_filter and tid != track_filter:
                        continue
                    if clip_id_set is not None:
                        cid = str(getattr(c, "id", ""))
                        if not cid or cid not in clip_id_set:
                            continue
                    t = track_by_id.get(tid)
                    if t is None:
                        continue
                    sf2_path = getattr(t, "sf2_path", None)
                    if not sf2_path:
                        continue
                    jobs.append((c, t))
                except Exception:
                    continue
        except Exception:
            return []
        return jobs

    def midi_prerender_job_count(self, clip_ids: list[str] | None = None, track_id: str | None = None) -> int:
        try:
            return len(self._collect_midi_prerender_jobs(clip_ids=clip_ids, track_id=track_id))
        except Exception:
            return 0

    def prerender_midi_clips(self, *, reason: str = "manual", clip_ids: list[str] | None = None, track_id: str | None = None) -> None:
        """Render MIDI clips (via FluidSynth) in a worker thread.

        This warms the MIDI->WAV cache so starting playback does not stutter.
        """
        if self._prerender_running:
            return

        jobs = self._collect_midi_prerender_jobs(clip_ids=clip_ids, track_id=track_id)
        total = len(jobs)
        if total <= 0:
            # Nothing to do
            self.prerender_finished.emit(True)
            return

        # Snapshot the project so background rendering does not touch live model objects.
        try:
            proj_dict = self.ctx.project.to_dict()
        except Exception:
            proj_dict = None

        self._prerender_running = True
        self._prerender_cancel = False
        self.prerender_started.emit(int(total))
        self.prerender_progress.emit(0)
        self.prerender_label.emit(f"Pre-Render: {total} MIDI Clips…")

        def _work(progress_emit, label_emit, cancel_flag):
            # Local imports (keeps import time low for normal startup)
            from pydaw.model.project import Project
            from pydaw.core.settings import SettingsStore, SettingsKeys
            from pydaw.audio.midi_render import RenderKey, ensure_rendered_wav, midi_content_hash
            from pydaw.audio.arrangement_renderer import _apply_ties_to_notes, _midi_notes_content_hash

            # Rebuild a detached project instance from dict snapshot.
            project = Project.from_dict(proj_dict) if isinstance(proj_dict, dict) else self.ctx.project

            settings = SettingsStore()
            try:
                sr = int(settings.get_value(SettingsKeys.sample_rate, 48000) or 48000)
            except Exception:
                sr = 48000

            bpm = float(getattr(project, "bpm", 120.0) or 120.0)
            clips = list(getattr(project, "clips", []) or [])
            tracks = list(getattr(project, "tracks", []) or [])
            track_by_id = {str(getattr(t, "id", "")): t for t in tracks}
            midi_notes_map = getattr(project, "midi_notes", {}) or {}

            # Rebuild job list inside worker from detached project (apply same filters).
            worker_jobs = []
            clip_id_set = set(str(x) for x in (clip_ids or []) if str(x)) if clip_ids else None
            track_filter = str(track_id) if track_id else None
            for c in clips:
                if str(getattr(c, "kind", "")) != "midi":
                    continue
                tid = str(getattr(c, "track_id", ""))
                if track_filter and tid != track_filter:
                    continue
                if clip_id_set is not None:
                    cid = str(getattr(c, "id", ""))
                    if not cid or cid not in clip_id_set:
                        continue
                t = track_by_id.get(tid)
                if t is None:
                    continue
                if not getattr(t, "sf2_path", None):
                    continue
                worker_jobs.append((c, t))

            total_local = len(worker_jobs) or 0
            if total_local <= 0:
                return True

            for i, (clip, track) in enumerate(worker_jobs):
                if bool(cancel_flag.get("cancel", False)):
                    return False

                cid = str(getattr(clip, "id", ""))
                nm = getattr(clip, "name", "") or cid
                label_emit(f"{i+1}/{total_local}: {nm}")

                # Collect notes + apply ties
                notes_raw = list(midi_notes_map.get(cid, []) or [])
                try:
                    notes = list(_apply_ties_to_notes(project, cid, notes_raw) or [])
                except Exception:
                    notes = list(notes_raw or [])

                clip_len_beats = float(getattr(clip, "length_beats", 4.0) or 4.0)
                try:
                    if notes:
                        note_end = max(float(getattr(n, "start_beats", 0.0)) + float(getattr(n, "length_beats", 0.0)) for n in notes)
                        clip_len_beats = max(clip_len_beats, float(note_end))
                except Exception:
                    pass

                content_hash = midi_content_hash(
                    notes=notes,
                    bpm=float(bpm),
                    clip_length_beats=float(clip_len_beats),
                    sf2_bank=int(getattr(track, "sf2_bank", 0) or 0),
                    sf2_preset=int(getattr(track, "sf2_preset", 0) or 0),
                )
                key = RenderKey(
                    clip_id=cid,
                    sf2_path=str(getattr(track, "sf2_path", "")),
                    sf2_bank=int(getattr(track, "sf2_bank", 0) or 0),
                    sf2_preset=int(getattr(track, "sf2_preset", 0) or 0),
                    bpm=float(bpm),
                    samplerate=int(sr),
                    clip_length_beats=float(clip_len_beats),
                    content_hash=str(content_hash),
                )

                # FIXED v0.0.19.7.13: Progress VORHER emiten, damit User sieht dass etwas passiert!
                pct = int(round(((i) / float(total_local)) * 100.0))  # i statt i+1!
                progress_emit(max(0, min(100, pct)))
                label_emit(f"Rendering Clip {i+1}/{total_local}...")
                
                # Main work: create/refresh the cached WAV if needed.
                try:
                    ensure_rendered_wav(
                        key=key,
                        midi_notes=notes,
                        clip_start_beats=float(getattr(clip, "start_beats", 0.0)),
                        clip_length_beats=float(clip_len_beats),
                    )
                except Exception as e:
                    # FIXED: Falls ensure_rendered_wav hängt, wenigstens einen Fehler zeigen!
                    label_emit(f"Fehler bei Clip {i+1}: {str(e)[:50]}")
                    # Weitermachen mit nächstem Clip
                    continue

            return True

        # Thread-safe cancellation flag passed to worker
        cancel_flag = {"cancel": False}

        def _on_cancel():
            cancel_flag["cancel"] = True

        # allow UI to cancel
        self._prerender_cancel = False

        def _progress(p):
            try:
                self.prerender_progress.emit(int(p))
            except Exception:
                pass

        def _label(t):
            try:
                self.prerender_label.emit(str(t))
            except Exception:
                pass

        worker = Worker(_work, _progress, _label, cancel_flag)

        # Handle cancellation requests from outside
        def _sync_cancel():
            if self._prerender_cancel:
                cancel_flag["cancel"] = True

        # Error/finish handlers
        def _done():
            self._prerender_running = False
            _sync_cancel()
            ok = not bool(cancel_flag.get("cancel", False))
            self.prerender_progress.emit(100 if ok else 0)
            self.prerender_label.emit("Pre-Render fertig" if ok else "Pre-Render abgebrochen")
            self.prerender_finished.emit(bool(ok))

        def _err(msg: str):
            self._prerender_running = False
            try:
                self.error.emit(f"Pre-Render Fehler: {msg}")
            except Exception:
                pass
            self.prerender_finished.emit(False)

        worker.signals.finished.connect(_done)
        worker.signals.error.connect(_err)

        self.threadpool.run(worker)
