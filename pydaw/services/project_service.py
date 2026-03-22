"""ProjectService (v0.0.15.8 hotfix).

Ziel dieses Hotfix:
- Stabile, konsistente API für die UI (keine AttributeError-Crashes in Qt-Slots)
- Threaded File-IO (Open/Save/Import/Export) via ThreadPoolService.Worker
- Grundlegende Track/Clip-Operationen + PianoRoll/MIDI Notes Datenstruktur
- Clip Launcher Einstellungen + Slot Mapping

Hinweis: Audio-Playback/Recording ist weiterhin Placeholder.
"""

from __future__ import annotations

import logging
import copy
import json
import hashlib

log = logging.getLogger(__name__)

from ..model.project import AudioEvent, new_id
from pathlib import Path
from datetime import datetime
import contextlib
import math
import wave
import re
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, Signal, QTimer

from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import set_value as set_setting

from pydaw.core.threading import ThreadPoolService, Worker
from pydaw.model.project import Track, Clip, Project
from pydaw.model.midi import MidiNote

from pydaw.fileio.file_manager import (
    ProjectContext,
    new_project as fm_new_project,
    open_project as fm_open_project,
    save_project_to as fm_save_project_to,
    import_audio_to_project as fm_import_audio,
    import_midi_to_project as fm_import_midi,
    export_audio_from_file as fm_export_audio,
    resolve_loaded_media_paths,  # v0.0.20.75: Fix missing import
)

from pydaw.fileio import project_io

from pydaw.fileio.midi_io import import_midi as midi_parse

from pydaw.commands import UndoStack, ProjectSnapshotEditCommand
from pydaw.commands.midi_notes_edit import MidiNotesEditCommand, MidiSnapshot
from pydaw.services.smartdrop_morph_guard import (
    apply_audio_to_instrument_morph_plan,
    build_audio_to_instrument_morph_plan,
    validate_audio_to_instrument_morph_plan,
)


def _fusion_knob_to_engine_value(key: str, raw: float) -> float:
    """Convert a raw Fusion knob integer to an engine-ready float value.

    v0.0.20.585: Mirrors the scaling logic in FusionWidget._on_knob_changed
    so offline bounce can restore engine state without importing the widget.
    """
    if key == "flt.cutoff":
        return 20.0 + (raw / 100.0) ** 2.0 * 19980.0
    if key == "flt.resonance":
        return raw / 100.0
    if key == "flt.drive":
        return raw / 100.0
    if key == "flt.env_amount":
        return raw / 100.0
    if key.startswith("flt."):
        pname = key.split(".", 1)[1]
        if pname == "mode":
            return float(int(raw))
        if pname == "feedback":
            return raw / 100.0
        if pname == "damp_freq":
            return raw
        return raw / 100.0
    if key.startswith("aeg.") or key.startswith("feg."):
        pname = key.split(".", 1)[1]
        if pname in ("attack", "decay", "release"):
            return (raw / 100.0) ** 2.0 * 10.0
        if pname == "sustain":
            return raw / 100.0
        if pname in ("vel_amount", "brightness", "curve"):
            return raw / 100.0
        if pname in ("model", "loop"):
            return float(int(raw))
        return raw / 100.0
    if key.startswith("osc."):
        pname = key.split(".", 1)[1]
        if pname == "pitch_st":
            return raw
        if pname in ("detune_stereo",):
            return raw
        if pname in ("algorithm", "voices", "mode", "unison_mode", "unison_voices", "smooth"):
            return float(int(raw))
        return raw / 100.0
    if key == "sub_level":
        return raw / 100.0
    if key == "sub_width":
        return raw / 100.0
    if key == "noise_level":
        return raw / 100.0
    if key == "gain":
        return raw / 50.0
    if key == "pan":
        return raw / 100.0
    if key == "output":
        return raw / 50.0
    return raw / 100.0


class ProjectService(QObject):
    status = Signal(str)
    error = Signal(str)
    project_updated = Signal()
    project_changed = Signal()
    clip_selected = Signal(str)
    active_clip_changed = Signal(str)  # backward compatible alias for pianoroll
    undo_changed = Signal()
    # Fired after a MIDI edit is committed (Undo step created). This allows
    # other services (e.g. audio) to react without the user needing to stop/play.
    midi_notes_committed = Signal(str)

    note_preview = Signal(int, int, int)  # pitch, velocity, duration_ms

    # Lifecycle hook for UI: emitted after new/open/snapshot-load.
    project_opened = Signal()

    # ClipLauncher: UI play-state indicator (slot_key list)
    cliplauncher_active_slots_changed = Signal(list)

    # MIDI pre-render (performance): render MIDI->WAV in the background so
    # playback feels instant even with large SF2 instruments.
    prerender_started = Signal(int)    # total clips
    prerender_progress = Signal(int)   # percent 0..100
    prerender_label = Signal(str)      # short status text
    prerender_finished = Signal(bool)  # True if completed (not cancelled)

    def __init__(self, threadpool: ThreadPoolService, parent: QObject | None = None):
        super().__init__(parent)
        self.threadpool = threadpool
        self.ctx: ProjectContext = fm_new_project()
        self._selected_track_id: str = ""
        self._active_clip_id: str = ""
        self.undo_stack = UndoStack(max_depth=400)

        # v0.0.20.348: safety-first global project undo fallback.
        # Many UI paths already emit project_updated after model mutations, but
        # not all of them register an explicit command. We coalesce those model
        # changes into snapshot-based undo steps without touching the DSP core.
        self._auto_undo_suppress_depth: int = 0
        self._auto_undo_restore_in_progress: bool = False
        self._auto_undo_pending_label: str = "Projekt ändern"
        self._auto_undo_timer = QTimer(self)
        self._auto_undo_timer.setSingleShot(True)
        self._auto_undo_timer.setInterval(180)
        self._auto_undo_timer.timeout.connect(self._capture_auto_undo_snapshot)
        self._last_project_snapshot = self._project_snapshot_dict()
        self.project_updated.connect(self._schedule_auto_undo_capture)

        # Pre-render state (MIDI->WAV background rendering)
        self._prerender_running: bool = False
        self._prerender_cancel: bool = False

        # Optional service binding: ClipLauncher realtime playback.
        # This is injected by the ServiceContainer.
        self._cliplauncher_playback: Any = None

    # --- wiring

    def bind_cliplauncher_playback(self, playback_service: Any) -> None:
        """Bind a ClipLauncherPlaybackService instance (optional)."""
        self._cliplauncher_playback = playback_service

    # --- ClipLauncher Playback API (called by LauncherService)


    def cliplauncher_active_slots(self) -> list[str]:
        # Return slot_keys currently active in ClipLauncher playback (if bound)
        try:
            if self._cliplauncher_playback is None:
                return []
            fn = getattr(self._cliplauncher_playback, 'active_slots', None)
            if callable(fn):
                return [str(k) for k in (fn() or [])]
        except Exception:
            return []
        return []

    def _emit_cliplauncher_active_slots(self) -> None:
        try:
            self.cliplauncher_active_slots_changed.emit(self.cliplauncher_active_slots())
        except Exception:
            pass

    def cliplauncher_launch_immediate(self, slot_key: str, at_beat: float | None = None) -> None:
        """Launch a single launcher slot immediately.

        The slot mapping is stored in Project.clip_launcher (slot_key -> clip_id).
        """
        if self._cliplauncher_playback is None:
            self.status.emit("Launch: Playback-Service fehlt (cliplauncher).")
            return
        try:
            self._cliplauncher_playback.launch_slot(str(slot_key), at_beat=at_beat)
            self._emit_cliplauncher_active_slots()
        except Exception:
            self.status.emit("Launch: Playback-Service Fehler (cliplauncher).")

    def cliplauncher_launch_scene_immediate(self, scene_index: int, at_beat: float | None = None) -> None:
        if self._cliplauncher_playback is None:
            self.status.emit("Scene Launch: Playback-Service fehlt (cliplauncher).")
            return
        try:
            self._cliplauncher_playback.launch_scene(int(scene_index), at_beat=at_beat)
            self._emit_cliplauncher_active_slots()
        except Exception:
            self.status.emit("Scene Launch: Playback-Service Fehler (cliplauncher).")

    def cliplauncher_stop_all(self) -> None:
        """Stop only ClipLauncher clips (does NOT stop the global transport)."""
        if self._cliplauncher_playback is None:
            return
        try:
            self._cliplauncher_playback.stop_all()
            self._emit_cliplauncher_active_slots()
        except Exception:
            pass

    def preview_note(self, pitch: int, velocity: int = 100, duration_ms: int = 140) -> None:
        """Emit a lightweight note-preview event (for Sampler/MIDI preview sync)."""
        try:
            self.note_preview.emit(int(pitch), int(velocity), int(duration_ms))
        except Exception:
            # Keep UI calls safe; preview is best-effort.
            return

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

    # ---------- global auto-undo fallback ----------
    def _project_snapshot_dict(self) -> dict:
        try:
            return copy.deepcopy(self.ctx.project.to_dict())
        except Exception:
            try:
                return copy.deepcopy(Project.from_dict(self.ctx.project.to_dict()).to_dict())
            except Exception:
                return {}

    def _sync_auto_undo_baseline(self) -> None:
        try:
            self._last_project_snapshot = self._project_snapshot_dict()
        except Exception:
            self._last_project_snapshot = {}

    def _cancel_pending_auto_undo_capture(self, *, sync_to_current: bool = False) -> None:
        try:
            self._auto_undo_timer.stop()
        except Exception:
            pass
        if sync_to_current:
            self._sync_auto_undo_baseline()

    def _schedule_auto_undo_capture(self) -> None:
        if self._auto_undo_restore_in_progress:
            return
        if self._auto_undo_suppress_depth > 0:
            return
        try:
            self._auto_undo_timer.start()
        except Exception:
            pass

    def _restore_project_from_snapshot(self, snapshot: dict) -> None:
        snap = copy.deepcopy(snapshot or {})
        self._auto_undo_restore_in_progress = True
        try:
            self._cancel_pending_auto_undo_capture(sync_to_current=False)
            try:
                project_obj = Project.from_dict(snap)
            except Exception:
                project_obj = self.ctx.project
            self.ctx.project = project_obj

            track_ids = {str(getattr(t, 'id', '') or '') for t in (getattr(project_obj, 'tracks', []) or [])}
            if str(self._selected_track_id or '') not in track_ids:
                fallback = next((str(getattr(t, 'id', '') or '') for t in (getattr(project_obj, 'tracks', []) or []) if str(getattr(t, 'kind', '') or '') != 'master'), '')
                if not fallback:
                    fallback = next((str(getattr(t, 'id', '') or '') for t in (getattr(project_obj, 'tracks', []) or [])), '')
                self._selected_track_id = fallback

            clip_ids = {str(getattr(c, 'id', '') or '') for c in (getattr(project_obj, 'clips', []) or [])}
            if str(self._active_clip_id or '') not in clip_ids:
                self._active_clip_id = ''

            self._sync_auto_undo_baseline()
            self._emit_updated()
            self.project_changed.emit()
        finally:
            self._auto_undo_restore_in_progress = False

    def _capture_auto_undo_snapshot(self) -> None:
        if self._auto_undo_restore_in_progress or self._auto_undo_suppress_depth > 0:
            return
        before = copy.deepcopy(self._last_project_snapshot or {})
        after = self._project_snapshot_dict()
        if before == after:
            return
        label = str(getattr(self, '_auto_undo_pending_label', '') or 'Projekt ändern')
        try:
            cmd = ProjectSnapshotEditCommand(
                before=before,
                after=copy.deepcopy(after),
                label=label,
                apply_snapshot=self._restore_project_from_snapshot,
            )
            self.undo_stack.push(cmd, already_done=True)
        except Exception:
            return
        self._last_project_snapshot = copy.deepcopy(after)
        self.undo_changed.emit()


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

        v0.0.20.528: Also handles send automation — param format: "send:{fx_track_id}"
        """
        t = next((x for x in self.ctx.project.tracks if x.id == track_id), None)
        if not t:
            return

        if param == "volume":
            t.volume = float(max(0.0, min(1.0, value)))
        elif param == "pan":
            t.pan = float(max(-1.0, min(1.0, value)))
        elif param.startswith("send:"):
            # v0.0.20.528: Send-Automation — update send amount in-memory
            fx_tid = param[5:]  # strip "send:" prefix
            if not fx_tid:
                return
            sends = list(getattr(t, "sends", []) or [])
            found = False
            for s in sends:
                if isinstance(s, dict) and str(s.get("target_track_id", "")) == fx_tid:
                    s["amount"] = float(max(0.0, min(1.0, value)))
                    found = True
                    break
            if not found:
                # Auto-create send entry when automation drives a not-yet-existing send
                sends.append({"target_track_id": fx_tid, "amount": float(max(0.0, min(1.0, value))), "pre_fader": False})
            t.sends = sends
        else:
            return

        # Avoid spamming status; keep it silent.
        self._emit_updated()

    # ---------- project ----------
    def new_project(self, name: str = "Neues Projekt") -> None:
        self._auto_undo_suppress_depth += 1
        try:
            self.ctx = fm_new_project(name)
            self._selected_track_id = ""
            self._active_clip_id = ""
            self.undo_stack.clear()
            self._cancel_pending_auto_undo_capture(sync_to_current=True)
            self.undo_changed.emit()
            self.status.emit("Neues Projekt erstellt.")
            self._emit_changed()
            self.project_opened.emit()
        finally:
            self._auto_undo_suppress_depth = max(0, self._auto_undo_suppress_depth - 1)

    def open_project(self, path: Path) -> None:
        def fn():
            return fm_open_project(path)

        def ok(ctx: ProjectContext):
            self._auto_undo_suppress_depth += 1
            try:
                self.ctx = ctx
                self.undo_stack.clear()
                self._cancel_pending_auto_undo_capture(sync_to_current=True)
                self.undo_changed.emit()
                try:
                    keys = SettingsKeys()
                    set_setting(keys.last_project, str(path))
                except Exception:
                    pass
                self._selected_track_id = ""
                self._active_clip_id = ""
                try:
                    keys = SettingsKeys()
                    set_setting(keys.last_project, str(path))
                except Exception:
                    pass
                self.status.emit(f"Projekt geöffnet: {path}")
                self._emit_changed()
                self.project_opened.emit()
            finally:
                self._auto_undo_suppress_depth = max(0, self._auto_undo_suppress_depth - 1)

        def err(msg: str):
            self.error.emit(msg)

        self._submit(fn, ok, err)

    def save_project_as(self, path: Path) -> None:
        # v0.0.20.173: Persist enhanced AutomationManager lanes into the project
        # right before saving (non-destructive, forward-compatible).
        try:
            self._sync_automation_manager_to_project()
        except Exception:
            pass
        try:
            from pydaw.audio.vst3_host import embed_project_state_blobs
            embed_project_state_blobs(self.ctx.project)
        except Exception:
            pass
        # v0.0.20.533: Embed CLAP plugin state blobs
        try:
            from pydaw.audio.clap_host import embed_clap_project_state_blobs
            _ae = getattr(self, '_audio_engine_ref', None)
            if _ae is None:
                _ae = getattr(self.ctx.project, '_audio_engine_ref', None)
            embed_clap_project_state_blobs(self.ctx.project, _ae)
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

        # v0.0.20.173: Ensure automation data is serialized into the snapshot.
        try:
            self._sync_automation_manager_to_project()
        except Exception:
            pass
        try:
            from pydaw.audio.vst3_host import embed_project_state_blobs
            embed_project_state_blobs(self.ctx.project)
        except Exception:
            pass
        # v0.0.20.533: Embed CLAP plugin state blobs
        try:
            from pydaw.audio.clap_host import embed_clap_project_state_blobs
            _ae = getattr(self, '_audio_engine_ref', None)
            if _ae is None:
                _ae = getattr(self.ctx.project, '_audio_engine_ref', None)
            embed_clap_project_state_blobs(self.ctx.project, _ae)
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

    # --- AutomationManager persistence (v0.0.20.173) ---

    def _sync_automation_manager_to_project(self) -> None:
        """Write enhanced automation lanes into Project.automation_manager_lanes.

        Safe no-op if the automation manager is not wired.
        """
        mgr = getattr(self, 'automation_manager', None)
        if mgr is None:
            return
        try:
            data = mgr.export_lanes() if hasattr(mgr, 'export_lanes') else {}
        except Exception:
            data = {}
        try:
            if isinstance(data, dict):
                self.ctx.project.automation_manager_lanes = data
        except Exception:
            pass

    def load_automation_manager_from_project(self) -> None:
        """Import automation lanes from project into the AutomationManager.

        - Prefers Project.automation_manager_lanes (new format)
        - Falls back to legacy Project.automation_lanes
        """
        mgr = getattr(self, 'automation_manager', None)
        if mgr is None:
            return
        try:
            data = getattr(self.ctx.project, 'automation_manager_lanes', {})
            if isinstance(data, dict) and data:
                mgr.import_lanes(data)
                return
        except Exception:
            pass
        try:
            legacy = getattr(self.ctx.project, 'automation_lanes', {})
            if isinstance(legacy, dict) and legacy:
                mgr.import_legacy_lanes(legacy)
        except Exception:
            pass

    def load_snapshot(self, snapshot_path: Path) -> None:
        """Lädt einen Snapshot in das aktuelle Projekt (Media-Pfade bleiben unverändert)."""
        if not snapshot_path:
            return

        def fn():
            return project_io.load_project(snapshot_path)

        def ok(project):
            self._auto_undo_suppress_depth += 1
            try:
                self.ctx.project = project
                try:
                    root_dir = (self.ctx.path.parent if self.ctx.path else snapshot_path.parent.parent)
                    resolve_loaded_media_paths(self.ctx.project, root_dir)
                except Exception:
                    pass
                self.undo_stack.clear()
                self._cancel_pending_auto_undo_capture(sync_to_current=True)
                self.undo_changed.emit()
                self.status.emit(f"Projektstand geladen: {snapshot_path.name}")
                self._emit_changed()
                self.project_opened.emit()
            finally:
                self._auto_undo_suppress_depth = max(0, self._auto_undo_suppress_depth - 1)

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
    def _split_tracks_for_insert(self) -> tuple[list[Track], Track | None]:
        tracks = list(self.ctx.project.tracks or [])
        non_master = [t for t in tracks if str(getattr(t, "kind", "") or "") != "master"]
        master = next((t for t in tracks if str(getattr(t, "kind", "") or "") == "master"), None)
        return non_master, master

    def _rebuild_track_order(self, non_master: list[Track], master: Track | None) -> None:
        # v0.0.20.527: FX tracks always positioned directly before Master (Bitwig-style)
        regular = [t for t in (non_master or []) if str(getattr(t, "kind", "") or "") != "fx"]
        fx = [t for t in (non_master or []) if str(getattr(t, "kind", "") or "") == "fx"]
        ordered = regular + fx
        if master is not None:
            ordered.append(master)
        self.ctx.project.tracks = ordered

    def add_track(
        self,
        kind: str,
        name: str | None = None,
        *,
        insert_index: int | None = None,
        insert_after_track_id: str | None = None,
        group_id: str | None = None,
        group_name: str | None = None,
        **_kwargs,
    ) -> Track:
        default_name = {"audio": "Audio Track", "instrument": "Instrument Track", "bus": "Bus", "fx": "FX", "master": "Master"}.get(kind, "Track")
        trk = Track(kind=kind, name=str(name or default_name))
        if str(group_id or ""):
            trk.track_group_id = str(group_id or "")
            trk.track_group_name = str(group_name or "")

        tracks, master = self._split_tracks_for_insert()
        idx = None
        if insert_after_track_id:
            try:
                idx = next((i + 1 for i, t in enumerate(tracks) if str(getattr(t, "id", "") or "") == str(insert_after_track_id)), None)
            except Exception:
                idx = None
        if idx is None and insert_index is not None:
            try:
                idx = max(0, min(len(tracks), int(insert_index)))
            except Exception:
                idx = None
        if idx is None:
            idx = len(tracks)
        tracks.insert(int(idx), trk)
        self._rebuild_track_order(tracks, master)

        self._selected_track_id = trk.id
        self.status.emit(f"Spur hinzugefügt: {trk.name}")
        self._emit_updated()
        return trk

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

    def delete_track(self, track_id: str) -> None:
        """Backward-compatible alias used by some UI menus."""
        self.remove_track(track_id)

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
        """Create a real group-bus track and assign children to it.

        v0.0.20.357: The group track has its own audio_fx_chain that processes the
        summed output of all child tracks before it reaches the master bus.
        """
        ids = [str(x) for x in (track_ids or []) if str(x)]
        if len(ids) < 2:
            return ""

        from pydaw.model.project import Track

        name = str(group_name or "").strip() or f"Group {len(ids)}"

        # --- Create a real group-bus track ---
        import uuid
        group_track = Track(
            id=f"grp_{uuid.uuid4().hex[:10]}",
            kind="group",
            name=name,
        )

        tracks = self.ctx.project.tracks or []

        # Find position of first child to insert group track before it
        first_child_idx = len(tracks)
        for i, t in enumerate(tracks):
            if str(getattr(t, 'id', '')) in ids and str(getattr(t, 'kind', '')) != 'master':
                first_child_idx = min(first_child_idx, i)

        # Insert group track before its children
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
        # Rollback: remove group track if no children were assigned
        try:
            tracks.remove(group_track)
        except Exception:
            pass
        return ""

    def ungroup_tracks(self, track_ids: list[str]) -> None:
        """Remove children from their group and delete the group-bus track if empty.

        v0.0.20.357: Also removes the kind='group' track when no children remain.
        """
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
        # Remove group-bus tracks that have no children left
        for gid in group_ids_touched:
            still_has_children = any(
                str(getattr(t, 'track_group_id', '') or '') == gid
                for t in tracks
                if str(getattr(t, 'kind', '') or '') != 'group'
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
        tracks, master = self._split_tracks_for_insert()
        try:
            src = next(i for i, t in enumerate(tracks) if str(getattr(t, "id", "") or "") == tid)
        except StopIteration:
            return
        target = max(0, min(len(tracks) - 1, int(src) + int(delta)))
        if target == src:
            return
        trk = tracks.pop(src)
        tracks.insert(target, trk)
        self._rebuild_track_order(tracks, master)
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

        tracks, master = self._split_tracks_for_insert()
        members = [
            t for t in tracks
            if str(getattr(t, "track_group_id", "") or "") == gid
            and str(getattr(t, "kind", "") or "") != "master"
        ]
        if len(members) < 2:
            return

        member_ids = {str(getattr(t, "id", "") or "") for t in members}
        remaining = [t for t in tracks if str(getattr(t, "id", "") or "") not in member_ids]
        if not remaining:
            return

        try:
            first_member_idx = next(i for i, t in enumerate(tracks) if str(getattr(t, "id", "") or "") in member_ids)
        except StopIteration:
            return

        before_non_member = sum(1 for t in tracks[:first_member_idx] if str(getattr(t, "id", "") or "") not in member_ids)
        target_non_member_idx = before_non_member + step
        target_non_member_idx = max(0, min(len(remaining), target_non_member_idx))
        if target_non_member_idx == before_non_member:
            return

        ordered = list(remaining)
        ordered[target_non_member_idx:target_non_member_idx] = list(members)
        self._rebuild_track_order(ordered, master)
        self._selected_track_id = str(getattr(members[0], "id", "") or "")
        group_name = str(getattr(members[0], "track_group_name", "") or "Gruppe")
        self.status.emit(f"Gruppe verschoben: {group_name}")
        self._emit_updated()

    def move_tracks_block(self, track_ids: list[str], before_track_id: str = "") -> None:
        """Move one or multiple visible non-master tracks as a single block.

        Used by the arranger track list for safe same-project mouse drag reordering.
        Cross-project drag keeps using the existing MIME payload and is not touched.
        """
        ids = [str(tid) for tid in (track_ids or []) if str(tid)]
        if not ids:
            return

        tracks, master = self._split_tracks_for_insert()
        order_map = {str(getattr(t, "id", "") or ""): idx for idx, t in enumerate(tracks)}
        ordered_ids = [tid for tid in ids if tid in order_map]
        ordered_ids.sort(key=lambda tid: order_map.get(tid, 10**9))
        if not ordered_ids:
            return

        moving_set = set(ordered_ids)
        moving = [t for t in tracks if str(getattr(t, "id", "") or "") in moving_set]
        if not moving:
            return
        remaining = [t for t in tracks if str(getattr(t, "id", "") or "") not in moving_set]

        anchor = str(before_track_id or "")
        if anchor and anchor in moving_set:
            return
        if anchor:
            try:
                target_idx = next(i for i, t in enumerate(remaining) if str(getattr(t, "id", "") or "") == anchor)
            except StopIteration:
                target_idx = len(remaining)
        else:
            target_idx = len(remaining)

        new_tracks = list(remaining)
        new_tracks[target_idx:target_idx] = list(moving)
        old_ids = [str(getattr(t, "id", "") or "") for t in tracks]
        new_ids = [str(getattr(t, "id", "") or "") for t in new_tracks]
        if old_ids == new_ids:
            return

        self._rebuild_track_order(new_tracks, master)
        self._selected_track_id = str(getattr(moving[0], "id", "") or "")
        if len(moving) == 1:
            self.status.emit(f"Spur per Maus verschoben: {getattr(moving[0], 'name', 'Track')}")
        else:
            self.status.emit(f"{len(moving)} Spuren per Maus verschoben")
        self._emit_updated()

    def set_arranger_collapsed_group_ids(self, group_ids: list[str]) -> None:
        valid_groups = {
            str(getattr(t, 'track_group_id', '') or '')
            for t in (self.ctx.project.tracks or [])
            if str(getattr(t, 'track_group_id', '') or '')
        }
        cleaned: list[str] = []
        for gid in (group_ids or []):
            sgid = str(gid or "")
            if sgid and sgid in valid_groups and sgid not in cleaned:
                cleaned.append(sgid)
        if list(getattr(self.ctx.project, 'arranger_collapsed_group_ids', []) or []) == cleaned:
            return
        self.ctx.project.arranger_collapsed_group_ids = cleaned
        self.status.emit("Gruppenansicht aktualisiert")
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

    # v0.0.20.650: Multi-Output Plugin Routing (AP5 Phase 5C)

    def set_plugin_output_routing(self, track_id: str, output_index: int,
                                   target_track_id: str) -> None:
        """Route a plugin's extra output pair to another track.

        output_index: 1-based (output 0 = main track, implicit).
        target_track_id: "" to remove routing for this output.
        """
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        idx = int(output_index)
        if idx < 1:
            return
        routing = dict(getattr(trk, 'plugin_output_routing', {}) or {})
        tid = str(target_track_id or "").strip()
        if tid:
            routing[idx] = tid
        else:
            routing.pop(idx, None)
        trk.plugin_output_routing = routing
        self._emit_updated()

    def get_plugin_output_routing(self, track_id: str) -> dict:
        """Return current multi-output routing dict for a track's plugin."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return {}
        return dict(getattr(trk, 'plugin_output_routing', {}) or {})

    def set_plugin_output_count(self, track_id: str, count: int) -> None:
        """Set how many stereo output pairs a plugin provides (0 = auto)."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.plugin_output_count = max(0, int(count))
        self._emit_updated()

    def create_plugin_output_tracks(self, source_track_id: str, count: int) -> list:
        """Auto-create auxiliary tracks for multi-output plugin routing.

        Creates 'count' new audio tracks named 'Out 2', 'Out 3', etc.,
        and routes plugin outputs 1..count to them.
        Returns list of new track IDs.
        """
        trk = next((t for t in self.ctx.project.tracks if t.id == source_track_id), None)
        if not trk:
            return []
        new_ids = []
        base_name = str(getattr(trk, 'name', 'Track') or 'Track')
        for i in range(1, max(1, int(count)) + 1):
            try:
                new_tid = self.add_track(
                    name=f"{base_name} Out {i + 1}",
                    kind="audio",
                )
                if new_tid:
                    new_ids.append(new_tid)
                    self.set_plugin_output_routing(source_track_id, i, new_tid)
            except Exception:
                pass
        return new_ids

    def set_track_monitor(self, track_id: str, enabled: bool) -> None:
        """Enable/disable input monitoring for this track."""
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk or getattr(trk, "kind", "") == "master":
            return
        trk.monitor = bool(enabled)
        self._emit_updated()

    def set_track_midi_input(self, track_id: str, midi_input: str) -> None:
        """Set MIDI input routing for this track (Bitwig-Style v0.0.20.608).

        Values: "No input", "All ins", "Computer Keyboard", specific port name,
        or "track:<track_id>" for MIDI from another track.
        Empty string "" = auto-detect based on track kind.
        """
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.midi_input = str(midi_input or "")
        self._emit_updated()

    def get_track_effective_midi_input(self, track_id: str) -> str:
        """Return the effective MIDI input for a track (resolving '' → auto default).

        Instrument/drum tracks default to "All ins", all others to "No input".
        """
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return "No input"
        raw = str(getattr(trk, "midi_input", "") or "")
        if raw:
            return raw
        # Auto-detect: instrument-capable tracks get "All ins"
        kind = str(getattr(trk, "kind", "") or "")
        plugin = str(getattr(trk, "plugin_type", "") or "")
        sf2 = str(getattr(trk, "sf2_path", "") or "")
        if kind == "instrument" or plugin or sf2:
            return "All ins"
        return "No input"

    def set_track_midi_channel_filter(self, track_id: str, channel: int) -> None:
        """Set MIDI channel filter for this track (v0.0.20.609).

        -1 = Omni (all channels), 0-15 = specific MIDI channel.
        """
        trk = next((t for t in self.ctx.project.tracks if t.id == track_id), None)
        if not trk:
            return
        trk.midi_channel_filter = max(-1, min(15, int(channel)))
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

    # Backward compatibility: older UI expects set_active_clip()
    def set_active_clip(self, clip_id: str) -> None:
        """Alias for select_clip() (used by ClipContextService and legacy UI)."""
        self.select_clip(str(clip_id))


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

        # v0.0.20.442: Copy automation breakpoints from source range to new position
        try:
            am = getattr(self, 'automation_manager', None)
            if am is not None:
                src_start = float(getattr(c, "start_beats", 0.0))
                src_end = src_start + float(getattr(c, "length_beats", 0.0))
                am.copy_automation_range(str(c.track_id), src_start, src_end, new_start)
        except Exception:
            pass
        
        self.select_clip(dup.id)
        self.status.emit("Clip dupliziert (Ctrl+D)")
        self._emit_updated()

    def add_audio_clip_from_clip_events_at(self, source_clip_id: str, event_ids: List[str], target_track_id: str, *, start_beats: float = 0.0) -> Optional[str]:
        """Create a NEW audio clip from selected AudioEvent(s) of an existing audio clip.

        This is the basis for DAW-like workflow:
        - Split a clip in the Audio Editor (Knife)
        - Drag one or more segments (events) into the Arranger
        - A new clip is created on the target track (non-destructive)

        The new clip references the SAME source file and preserves clip-level edits
        (gain/pan/pitch/stretch/reverse/mute/fades, warp markers, clip automation).
        """
        src_id = str(source_clip_id or '').strip()
        if not src_id:
            return None
        try:
            wanted = [str(x) for x in (event_ids or []) if str(x).strip()]
        except Exception:
            wanted = []
        if not wanted:
            return None

        src = next((c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) == src_id), None)
        if not src or str(getattr(src, 'kind', '')) != 'audio':
            return None

        # Ensure events exist
        try:
            self._ensure_audio_events(src)
        except Exception:
            pass
        try:
            evs = list(getattr(src, 'audio_events', []) or [])
        except Exception:
            evs = []
        if not evs:
            return None

        want_set = set(wanted)
        sel = [e for e in evs if str(getattr(e, 'id', '')) in want_set]
        if not sel:
            return None

        # Selection bounds in clip timeline (UI/Editor timeline)
        def _st(e):
            return float(getattr(e, 'start_beats', 0.0) or 0.0)
        def _en(e):
            return float(getattr(e, 'start_beats', 0.0) or 0.0) + float(getattr(e, 'length_beats', 0.0) or 0.0)

        min_start = min(_st(e) for e in sel)
        max_end = max(_en(e) for e in sel)
        length = max(0.25, float(max_end - min_start))

        # IMPORTANT (v0.0.20.146): The arrangement renderer uses clip.offset_seconds
        # for trimming/offset (NOT offset_beats). If we don't set offset_seconds here,
        # exported slices will always start from the beginning of the file.
        #
        # We compute a stable seconds_per_beat mapping from the source file duration
        # and the *source clip* length_beats: seconds_per_beat = file_secs / src.length_beats.
        # This works for both:
        # - raw audio (length_beats derived from project BPM)
        # - tempo-synced loops (length_beats derived from source BPM)
        # because the renderer scales offset_seconds by effective_rate.
        try:
            src_path = Path(str(getattr(src, 'source_path', '') or ''))
            file_secs = float(self._audio_duration_seconds(src_path))
        except Exception:
            file_secs = 0.0
        try:
            src_len_beats = float(getattr(src, 'length_beats', 0.0) or 0.0)
        except Exception:
            src_len_beats = 0.0
        try:
            proj_bpm = float(getattr(self.ctx.project, 'bpm', 120.0) or 120.0)
        except Exception:
            proj_bpm = 120.0
        if file_secs > 0.0 and src_len_beats > 1e-9:
            seconds_per_beat = float(file_secs) / float(src_len_beats)
        else:
            seconds_per_beat = 60.0 / max(1e-9, float(proj_bpm))

        # Determine the source-start beat for the selection.
        # Prefer AudioEvent.source_offset_beats (actual source position) but fall back
        # to src.offset_beats + selection start if offsets look uninitialized.
        so_vals: list[float] = []
        se_vals: list[float] = []
        try:
            so_vals = [float(getattr(e, 'source_offset_beats', 0.0) or 0.0) for e in sel]
            se_vals = [float(getattr(e, 'source_offset_beats', 0.0) or 0.0) + float(getattr(e, 'length_beats', 0.0) or 0.0) for e in sel]
            src_start_beats = float(min(so_vals)) if so_vals else 0.0
            src_end_beats = float(max(se_vals)) if se_vals else float(src_start_beats + length)
        except Exception:
            src_start_beats = 0.0
            src_end_beats = float(src_start_beats + length)
            so_vals = []
            se_vals = []

        try:
            base_off_beats = float(getattr(src, 'offset_beats', 0.0) or 0.0)
        except Exception:
            base_off_beats = 0.0
        try:
            base_off_secs = float(getattr(src, 'offset_seconds', 0.0) or 0.0)
        except Exception:
            base_off_secs = 0.0

        # Heuristic: if offsets are all ~equal while selection start is not ~0,
        # assume source_offset_beats is missing and derive from clip timeline.
        try:
            if sel:
                if (abs(float(src_end_beats - src_start_beats)) < 1e-6 and float(length) > 1e-3) or (
                    max(so_vals) - min(so_vals) < 1e-6 and float(min_start) > 1e-3
                ):
                    src_start_beats = float(base_off_beats + float(min_start))
                    src_end_beats = float(base_off_beats + float(max_end))
        except Exception:
            pass

        # Final computed offset in *seconds* (source time).
        # Keep base_off_secs for future trim support.
        try:
            delta_beats_from_clip_off = float(src_start_beats - base_off_beats)
        except Exception:
            delta_beats_from_clip_off = float(src_start_beats)
        offset_seconds = float(base_off_secs + (delta_beats_from_clip_off * float(seconds_per_beat)))

        # Build new clip
        from pydaw.model.project import Clip, AudioEvent
        tid = str(target_track_id or src.track_id or self.ensure_audio_track())

        base_label = str(getattr(src, 'label', 'Audio') or 'Audio')
        # Avoid "Slice Slice" when exporting from an already-sliced clip.
        if base_label.strip().lower().endswith(' slice'):
            new_label = base_label
        else:
            new_label = base_label + ' Slice'

        newc = Clip(
            kind='audio',
            track_id=tid,
            start_beats=max(0.0, float(start_beats)),
            length_beats=float(length),
            label=str(new_label),
            media_id=getattr(src, 'media_id', None),
            source_path=getattr(src, 'source_path', None),
            source_bpm=getattr(src, 'source_bpm', None),
        )

        # Copy clip-level edits (safe, explicit)
        for attr in [
            'gain', 'pan', 'pitch', 'formant', 'stretch',
            'reversed', 'muted',
            'fade_in_beats', 'fade_out_beats',
            'group_id',
        ]:
            try:
                if hasattr(src, attr):
                    setattr(newc, attr, getattr(src, attr))
            except Exception:
                pass

        # Offset for playback/rendering (renderer uses offset_seconds today).
        # Keep offset_beats as a legacy/debug value.
        newc.offset_beats = float(src_start_beats)
        newc.offset_seconds = float(max(0.0, float(offset_seconds)))

        # IMPORTANT: Arrangement renderer currently ignores clip.audio_events.
        # To ensure exported slices play the correct segment, store this export as
        # ONE consolidated AudioEvent starting at 0 in the new clip.
        newc.audio_events = [AudioEvent(start_beats=0.0, length_beats=float(length), source_offset_beats=float(src_start_beats))]

        # Derived slices for legacy UI
        try:
            self._sync_slices_from_events(newc)
        except Exception:
            pass

        # Clip automation: crop + shift beats
        try:
            src_auto = dict(getattr(src, 'clip_automation', {}) or {})
        except Exception:
            src_auto = {}
        out_auto: dict = {}
        for pname, pts in (src_auto or {}).items():
            try:
                out_pts = []
                for pt in (pts or []):
                    if not isinstance(pt, dict):
                        continue
                    b = float(pt.get('beat', 0.0) or 0.0) - float(min_start)
                    if b < -1e-6 or b > (float(length) + 1e-6):
                        continue
                    out_pts.append({'beat': max(0.0, min(float(length), float(b))), 'value': float(pt.get('value', 0.0) or 0.0)})
                if out_pts:
                    out_pts.sort(key=lambda x: float(x.get('beat', 0.0) or 0.0))
                    out_auto[str(pname)] = out_pts
            except Exception:
                continue
        newc.clip_automation = out_auto

        # Warp markers: crop + shift (best-effort)
        try:
            raw_markers = list(getattr(src, 'stretch_markers', []) or [])
        except Exception:
            raw_markers = []
        out_markers: list = []
        for mm in raw_markers:
            if not isinstance(mm, dict):
                continue
            try:
                src_b = float(mm.get('src', mm.get('beat', 0.0)) or 0.0)
                dst_b = float(mm.get('dst', mm.get('beat', src_b)) or 0.0)
            except Exception:
                continue
            # keep markers that intersect selection window
            if src_b < (min_start - 1e-6) or src_b > (max_end + 1e-6):
                continue
            out_markers.append({'src': float(src_b - min_start), 'dst': float(dst_b - min_start)})
        out_markers.sort(key=lambda x: float(x.get('src', 0.0) or 0.0))
        newc.stretch_markers = out_markers

        # New clip always lives in Arranger
        newc.launcher_only = False

        self.ctx.project.clips.append(newc)
        try:
            self.select_clip(newc.id)
        except Exception:
            pass
        self.status.emit('Slice als neuer Clip erstellt')
        self._emit_updated()
        return str(newc.id)


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

    def scale_clip_content(self, clip_id: str, scale_factor: float, original_notes: list | None = None) -> None:
        """Bitwig-style Free Content Scaling: scale all MIDI note positions and durations."""
        notes = self.ctx.project.midi_notes.get(str(clip_id), [])
        if not notes:
            return
        sf = float(scale_factor)
        if sf <= 0.0 or abs(sf - 1.0) < 1e-9:
            return
        if original_notes and len(original_notes) == len(notes):
            for i, n in enumerate(notes):
                orig_start, orig_len = original_notes[i]
                n.start_beats = max(0.0, float(orig_start) * sf)
                n.length_beats = max(0.03125, float(orig_len) * sf)
        else:
            for n in notes:
                n.start_beats = max(0.0, float(n.start_beats) * sf)
                n.length_beats = max(0.03125, float(n.length_beats) * sf)
        for n in notes:
            try:
                n.clamp()
            except Exception:
                pass
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

    # ---------- send-FX routing (v0.0.20.518 Bitwig-style) ----------

    def add_send(self, source_track_id: str, target_track_id: str, amount: float = 0.5, pre_fader: bool = False) -> None:
        """Add a send from source track to an FX track."""
        src = next((t for t in self.ctx.project.tracks if t.id == str(source_track_id)), None)
        tgt = next((t for t in self.ctx.project.tracks if t.id == str(target_track_id)), None)
        if not src or not tgt:
            return
        if str(getattr(tgt, "kind", "")) != "fx":
            return
        sends = list(getattr(src, "sends", []) or [])
        # Don't duplicate
        for s in sends:
            if isinstance(s, dict) and str(s.get("target_track_id", "")) == str(target_track_id):
                s["amount"] = float(max(0.0, min(1.0, amount)))
                s["pre_fader"] = bool(pre_fader)
                src.sends = sends
                self._emit_updated()
                return
        sends.append({"target_track_id": str(target_track_id), "amount": float(max(0.0, min(1.0, amount))), "pre_fader": bool(pre_fader)})
        src.sends = sends
        self._emit_updated()

    def remove_send(self, source_track_id: str, target_track_id: str) -> None:
        """Remove a send from source track to target FX track."""
        src = next((t for t in self.ctx.project.tracks if t.id == str(source_track_id)), None)
        if not src:
            return
        sends = list(getattr(src, "sends", []) or [])
        src.sends = [s for s in sends if not (isinstance(s, dict) and str(s.get("target_track_id", "")) == str(target_track_id))]
        self._emit_updated()

    def set_send_amount(self, source_track_id: str, target_track_id: str, amount: float) -> None:
        """Update send amount (0.0-1.0)."""
        src = next((t for t in self.ctx.project.tracks if t.id == str(source_track_id)), None)
        if not src:
            return
        for s in list(getattr(src, "sends", []) or []):
            if isinstance(s, dict) and str(s.get("target_track_id", "")) == str(target_track_id):
                s["amount"] = float(max(0.0, min(1.0, amount)))
                self._emit_updated()
                return

    def toggle_send_pre_fader(self, source_track_id: str, target_track_id: str) -> bool | None:
        """Toggle pre/post-fader for an existing send. Returns new pre_fader state or None."""
        src = next((t for t in self.ctx.project.tracks if t.id == str(source_track_id)), None)
        if not src:
            return None
        for s in list(getattr(src, "sends", []) or []):
            if isinstance(s, dict) and str(s.get("target_track_id", "")) == str(target_track_id):
                new_pre = not bool(s.get("pre_fader", False))
                s["pre_fader"] = new_pre
                self._emit_updated()
                label = "Pre-Fader" if new_pre else "Post-Fader"
                self.status.emit(f"Send → {label}")
                return new_pre
        return None

    def get_fx_tracks(self) -> list:
        """Return all FX/Return tracks in the project."""
        return [t for t in self.ctx.project.tracks if str(getattr(t, "kind", "")) == "fx"]

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

    def preview_audio_to_instrument_morph(self, track_id: str, plugin_name: str = "") -> dict:
        """Return a non-mutating preview plan for future Audio→Instrument morphing."""
        trk = next((t for t in self.ctx.project.tracks if t.id == str(track_id or "")), None)
        return dict(build_audio_to_instrument_morph_plan(self.ctx.project, trk, plugin_name=str(plugin_name or ""), runtime_owner=self) or {})

    def validate_audio_to_instrument_morph(self, track_id: str, plugin_name: str = "") -> dict:
        """Validate a future Audio→Instrument morph target without changing the project."""
        trk = next((t for t in self.ctx.project.tracks if t.id == str(track_id or "")), None)
        return dict(validate_audio_to_instrument_morph_plan(self.ctx.project, trk, plugin_name=str(plugin_name or ""), runtime_owner=self) or {})

    def preview_audio_to_instrument_morph_mutation_gate(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later explicit mutation gate.

        This intentionally arms nothing. It only exposes which owner would later
        host the gate once the minimal-case morph path is truly unlocked.
        """
        return {
            "gate_key": f"audio_to_instrument_morph::mutation_gate::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "mutation_gate_state": "armed-preview-only",
            "project_mutation_enabled": False,
            "preview_only": True,
        }

    def preview_audio_to_instrument_morph_transaction_capsule(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later transaction capsule.

        The capsule stays purely descriptive in this phase and reuses the
        existing snapshot helpers instead of mutating project state.
        """
        return {
            "capsule_key": f"audio_to_instrument_morph::transaction_capsule::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "capture_method": "_project_snapshot_dict",
            "restore_method": "_restore_project_from_snapshot",
            "undo_method": "undo_stack.push",
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_capsule_commit(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later capsule commit path."""
        return {
            "capsule_commit_key": f"audio_to_instrument_morph::capsule_commit::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_capsule_rollback(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later capsule rollback path."""
        return {
            "capsule_rollback_key": f"audio_to_instrument_morph::capsule_rollback::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_project_snapshot_edit_command(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later ProjectSnapshotEditCommand shell."""
        return {
            "command_key": f"audio_to_instrument_morph::project_snapshot_edit_command::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "command_class": ProjectSnapshotEditCommand.__name__,
            "command_module": ProjectSnapshotEditCommand.__module__,
            "capture_method": "_project_snapshot_dict",
            "restore_method": "_restore_project_from_snapshot",
            "undo_method": "undo_stack.push",
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_command_undo_shell(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later atomic command/undo shell."""
        return {
            "shell_key": f"audio_to_instrument_morph::command_undo_shell::{str(track_id or '').strip() or 'track'}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "command_class": ProjectSnapshotEditCommand.__name__,
            "command_module": ProjectSnapshotEditCommand.__module__,
            "capture_method": "_project_snapshot_dict",
            "restore_method": "_restore_project_from_snapshot",
            "undo_method": "undo_stack.push",
            "already_done_supported": True,
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_before_after_snapshot_command_factory(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for a later before/after snapshot command factory.

        The method materializes current project snapshot payloads in memory so the
        guard can already inspect concrete before/after payload metadata without
        constructing or pushing a real command.
        """
        track_token = str(track_id or '').strip() or 'track'
        plugin_token = str(plugin_name or '').strip() or 'Instrument'

        def _payload_summary(payload: dict) -> dict:
            try:
                raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            except Exception:
                raw = repr(payload or {})
            digest = hashlib.sha1(str(raw).encode("utf-8", errors="ignore")).hexdigest()[:12]
            top_level_keys = sorted(str(key).strip() for key in dict(payload or {}).keys() if str(key).strip())
            return {
                "payload_entry_count": len(dict(payload or {})),
                "payload_digest": digest,
                "payload_size_bytes": len(str(raw).encode("utf-8", errors="ignore")),
                "top_level_key_count": len(top_level_keys),
                "top_level_keys": top_level_keys[:12],
                "track_count": len(list(dict(payload or {}).get("tracks") or [])) if isinstance(dict(payload or {}).get("tracks"), list) else 0,
                "clip_count": len(list(dict(payload or {}).get("clips") or [])) if isinstance(dict(payload or {}).get("clips"), list) else 0,
                "device_count": len(list(dict(payload or {}).get("devices") or [])) if isinstance(dict(payload or {}).get("devices"), list) else 0,
            }

        before_payload = copy.deepcopy(self._project_snapshot_dict() or {})
        after_payload = copy.deepcopy(before_payload)
        before_summary = _payload_summary(before_payload)
        after_summary = _payload_summary(after_payload)
        payload_delta_kind = "identical-preview-only" if before_summary.get("payload_digest") == after_summary.get("payload_digest") else "preview-diff-materialized"
        label_preview = f"Audio→Instrument Morph Preview ({track_token} → {plugin_token})"
        return {
            "factory_key": f"audio_to_instrument_morph::before_after_snapshot_command_factory::{track_token}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "command_class": ProjectSnapshotEditCommand.__name__,
            "command_module": ProjectSnapshotEditCommand.__module__,
            "label_preview": label_preview,
            "before_snapshot_method": "_project_snapshot_dict",
            "after_snapshot_method": "_project_snapshot_dict",
            "restore_method": "_restore_project_from_snapshot",
            "before_payload_summary": before_summary,
            "after_payload_summary": after_summary,
            "payload_delta_kind": payload_delta_kind,
            "materialized_payload_count": 2,
            "factory_stub": "build_audio_to_instrument_morph_before_after_snapshot_command_factory",
            "before_snapshot_stub": "materialize_audio_to_instrument_morph_before_snapshot_payload",
            "after_snapshot_stub": "materialize_audio_to_instrument_morph_after_snapshot_payload",
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def preview_audio_to_instrument_morph_preview_snapshot_command(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for the later explicit preview command construction.

        This instantiates ``ProjectSnapshotEditCommand`` only in memory so the
        guard can already inspect the real constructor shape without executing
        ``do()`` or pushing anything onto the undo stack.
        """
        track_token = str(track_id or '').strip() or 'track'
        plugin_token = str(plugin_name or '').strip() or 'Instrument'

        def _payload_summary(payload: dict) -> dict:
            try:
                raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            except Exception:
                raw = repr(payload or {})
            digest = hashlib.sha1(str(raw).encode("utf-8", errors="ignore")).hexdigest()[:12]
            top_level_keys = sorted(str(key).strip() for key in dict(payload or {}).keys() if str(key).strip())
            return {
                "payload_entry_count": len(dict(payload or {})),
                "payload_digest": digest,
                "payload_size_bytes": len(str(raw).encode("utf-8", errors="ignore")),
                "top_level_key_count": len(top_level_keys),
                "top_level_keys": top_level_keys[:12],
                "track_count": len(list(dict(payload or {}).get("tracks") or [])) if isinstance(dict(payload or {}).get("tracks"), list) else 0,
                "clip_count": len(list(dict(payload or {}).get("clips") or [])) if isinstance(dict(payload or {}).get("clips"), list) else 0,
                "device_count": len(list(dict(payload or {}).get("devices") or [])) if isinstance(dict(payload or {}).get("devices"), list) else 0,
            }

        before_payload = copy.deepcopy(self._project_snapshot_dict() or {})
        after_payload = copy.deepcopy(before_payload)
        before_summary = _payload_summary(before_payload)
        after_summary = _payload_summary(after_payload)
        payload_delta_kind = "identical-preview-only" if before_summary.get("payload_digest") == after_summary.get("payload_digest") else "preview-diff-materialized"
        label_preview = f"Audio→Instrument Morph Preview ({track_token} → {plugin_token})"
        preview_command = ProjectSnapshotEditCommand(
            before=before_payload,
            after=after_payload,
            label=label_preview,
            apply_snapshot=self._restore_project_from_snapshot,
        )
        command_field_names = [str(name).strip() for name in list(getattr(preview_command, "__dataclass_fields__", {}).keys()) if str(name).strip()]
        return {
            "preview_command_key": f"audio_to_instrument_morph::preview_snapshot_command::{track_token}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "command_class": preview_command.__class__.__name__,
            "command_module": preview_command.__class__.__module__,
            "command_constructor": "ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)",
            "command_field_names": command_field_names,
            "command_instance_state": "constructed-preview-only",
            "label_preview": label_preview,
            "apply_callback_name": "_restore_project_from_snapshot",
            "apply_callback_owner_class": self.__class__.__name__,
            "supports_do_preview": bool(callable(getattr(preview_command, "do", None))),
            "supports_undo_preview": bool(callable(getattr(preview_command, "undo", None))),
            "payload_delta_kind": payload_delta_kind,
            "materialized_payload_count": 2,
            "before_payload_summary": before_summary,
            "after_payload_summary": after_summary,
            "constructor_stub": "construct_audio_to_instrument_morph_preview_snapshot_command",
            "executor_stub": "simulate_audio_to_instrument_morph_preview_snapshot_command",
            "preview_only": True,
            "project_mutation_enabled": False,
        }


    def preview_audio_to_instrument_morph_dry_command_executor(self, track_id: str = "", plugin_name: str = "") -> dict:
        """Read-only descriptor for a later do()/undo() simulation harness.

        The command is instantiated against an in-memory recorder callback so the
        guard can already rehearse ``do()`` / ``undo()`` safely without touching
        the live project model or the undo stack.
        """
        track_token = str(track_id or '').strip() or 'track'
        plugin_token = str(plugin_name or '').strip() or 'Instrument'

        def _payload_summary(payload: dict) -> dict:
            try:
                raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            except Exception:
                raw = repr(payload or {})
            digest = hashlib.sha1(str(raw).encode("utf-8", errors="ignore")).hexdigest()[:12]
            top_level_keys = sorted(str(key).strip() for key in dict(payload or {}).keys() if str(key).strip())
            return {
                "payload_entry_count": len(dict(payload or {})),
                "payload_digest": digest,
                "payload_size_bytes": len(str(raw).encode("utf-8", errors="ignore")),
                "top_level_key_count": len(top_level_keys),
                "top_level_keys": top_level_keys[:12],
                "track_count": len(list(dict(payload or {}).get("tracks") or [])) if isinstance(dict(payload or {}).get("tracks"), list) else 0,
                "clip_count": len(list(dict(payload or {}).get("clips") or [])) if isinstance(dict(payload or {}).get("clips"), list) else 0,
                "device_count": len(list(dict(payload or {}).get("devices") or [])) if isinstance(dict(payload or {}).get("devices"), list) else 0,
            }

        before_payload = copy.deepcopy(self._project_snapshot_dict() or {})
        after_payload = copy.deepcopy(before_payload)
        before_summary = _payload_summary(before_payload)
        after_summary = _payload_summary(after_payload)
        payload_delta_kind = "identical-preview-only" if before_summary.get("payload_digest") == after_summary.get("payload_digest") else "preview-diff-materialized"
        label_preview = f"Audio→Instrument Morph Preview ({track_token} → {plugin_token})"

        callback_trace: list[str] = []
        callback_payload_digests: list[str] = []
        callback_payload_summaries: list[dict] = []

        def _shadow_apply_snapshot(snapshot: dict) -> None:
            summary = _payload_summary(dict(snapshot or {}))
            digest = str(summary.get("payload_digest") or "").strip()
            if digest == str(after_summary.get("payload_digest") or "").strip():
                phase = "do()"
            elif digest == str(before_summary.get("payload_digest") or "").strip():
                phase = "undo()"
            else:
                phase = "callback"
            callback_trace.append(phase)
            callback_payload_digests.append(digest)
            callback_payload_summaries.append(summary)

        preview_command = ProjectSnapshotEditCommand(
            before=before_payload,
            after=after_payload,
            label=label_preview,
            apply_snapshot=_shadow_apply_snapshot,
        )
        do_call_count = 0
        undo_call_count = 0
        if callable(getattr(preview_command, 'do', None)):
            preview_command.do()
            do_call_count += 1
        if callable(getattr(preview_command, 'undo', None)):
            preview_command.undo()
            undo_call_count += 1

        return {
            "dry_executor_key": f"audio_to_instrument_morph::dry_command_executor::{track_token}",
            "owner_class": self.__class__.__name__,
            "track_id": str(track_id or "").strip(),
            "plugin_name": str(plugin_name or "").strip(),
            "command_class": preview_command.__class__.__name__,
            "command_module": preview_command.__class__.__module__,
            "command_constructor": "ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)",
            "label_preview": label_preview,
            "apply_callback_name": "_shadow_apply_snapshot",
            "apply_callback_owner_class": f"{self.__class__.__name__}.preview_audio_to_instrument_morph_dry_command_executor",
            "command_instance_state": "constructed-preview-only",
            "simulation_state": "simulated-preview-only",
            "supports_do_preview": bool(callable(getattr(preview_command, "do", None))),
            "supports_undo_preview": bool(callable(getattr(preview_command, "undo", None))),
            "do_call_count": int(do_call_count),
            "undo_call_count": int(undo_call_count),
            "callback_call_count": int(len(callback_trace)),
            "simulation_sequence": ["do()", "undo()"],
            "callback_trace": list(callback_trace),
            "callback_payload_digests": list(callback_payload_digests),
            "callback_payload_summaries": [dict(item or {}) for item in callback_payload_summaries],
            "payload_delta_kind": payload_delta_kind,
            "materialized_payload_count": 2,
            "before_payload_summary": before_summary,
            "after_payload_summary": after_summary,
            "executor_stub": "simulate_audio_to_instrument_morph_preview_snapshot_command_dry_executor",
            "future_live_executor_stub": "execute_audio_to_instrument_morph_preview_snapshot_command_live",
            "preview_only": True,
            "project_mutation_enabled": False,
        }

    def apply_audio_to_instrument_morph(self, plan: dict | None) -> dict:
        """Future execution hook for Audio→Instrument morphing (currently blocked)."""
        return dict(apply_audio_to_instrument_morph_plan(self, dict(plan or {})) or {})



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

    def add_audio_clip_from_file_at(self, track_id: str, path: Path, start_beats: float = 0.0, launcher_slot_key: str | None = None, place_in_arranger: bool = True, source_bpm_override: Optional[float] = None) -> Optional[str]:
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
                # If caller provides a BPM (e.g. Browser BPM analysis), prefer it.
                if source_bpm_override is not None:
                    try:
                        source_bpm = float(source_bpm_override)
                    except Exception:
                        source_bpm = None

                if source_bpm is None:
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

    def clone_clip_for_launcher(
        self,
        source_clip_id: str,
        *,
        target_track_id: str | None = None,
        label_suffix: str = " Copy",
        select_new: bool = False,
    ) -> str | None:
        """Create a deep copy of a clip suitable for the Clip-Launcher.

        DAW semantics:
        - Ctrl+C / Ctrl+V on launcher slots should create an independent clip copy.
        - Ctrl+Drag between slots should duplicate-on-drop.

        Safety:
        - Does NOT delete or modify the source clip.
        - Only appends a new clip to the project model and returns its id.
        """
        src_id = str(source_clip_id or '').strip()
        if not src_id:
            return None
        c = next((c for c in self.ctx.project.clips if getattr(c, 'id', '') == src_id), None)
        if not c:
            return None

        tgt_track = str(target_track_id or getattr(c, 'track_id', '') or '').strip()
        if not tgt_track:
            tgt_track = str(getattr(c, 'track_id', '') or '')

        base_label = str(getattr(c, 'label', 'Clip') or 'Clip')
        suf = str(label_suffix or ' Copy')
        if base_label.endswith(suf):
            new_label = base_label
        else:
            new_label = base_label + suf

        # Create a fresh clip with a new id
        dup = Clip(
            kind=str(getattr(c, 'kind', 'audio') or 'audio'),
            track_id=tgt_track,
            start_beats=0.0,
            length_beats=float(getattr(c, 'length_beats', 4.0) or 4.0),
            label=new_label,
            media_id=getattr(c, 'media_id', None),
            source_path=getattr(c, 'source_path', None),
        )

        # Copy basic timing offsets (non-destructive)
        try:
            dup.offset_beats = float(getattr(c, 'offset_beats', 0.0) or 0.0)
        except Exception:
            pass
        try:
            dup.offset_seconds = float(getattr(c, 'offset_seconds', 0.0) or 0.0)
        except Exception:
            pass
        try:
            dup.source_bpm = getattr(c, 'source_bpm', None)
        except Exception:
            pass

        # Audio clip params
        for attr in (
            'gain', 'pan', 'pitch', 'formant', 'stretch', 'reversed', 'muted',
            'fade_in_beats', 'fade_out_beats',
            'loop_start_beats', 'loop_end_beats',
        ):
            try:
                setattr(dup, attr, getattr(c, attr))
            except Exception:
                pass

        # Launcher-only by default (keeps it out of the Arranger timeline)
        try:
            dup.launcher_only = True
        except Exception:
            pass

        # Copy launcher properties (Bitwig-style)
        for attr in (
            'launcher_start_quantize', 'launcher_alt_start_quantize',
            'launcher_playback_mode', 'launcher_alt_playback_mode',
            'launcher_release_action', 'launcher_alt_release_action',
            'launcher_q_on_loop', 'launcher_next_action', 'launcher_next_action_count',
            'launcher_shuffle', 'launcher_accent', 'launcher_seed', 'launcher_color',
        ):
            try:
                setattr(dup, attr, getattr(c, attr))
            except Exception:
                pass

        # Deep-copy non-destructive structures
        try:
            import copy
            dup.audio_slices = copy.deepcopy(getattr(c, 'audio_slices', []) or [])
            dup.onsets = copy.deepcopy(getattr(c, 'onsets', []) or [])
            dup.audio_events = copy.deepcopy(getattr(c, 'audio_events', []) or [])
            dup.clip_automation = copy.deepcopy(getattr(c, 'clip_automation', {}) or {})
            dup.stretch_markers = copy.deepcopy(getattr(c, 'stretch_markers', []) or [])
        except Exception:
            pass

        # Append + copy MIDI notes if needed
        self.ctx.project.clips.append(dup)
        if str(getattr(dup, 'kind', '')) == 'midi':
            try:
                import copy
                original_notes = self.ctx.project.midi_notes.get(src_id, [])
                self.ctx.project.midi_notes[dup.id] = [copy.deepcopy(n) for n in (original_notes or [])]
            except Exception:
                self.ctx.project.midi_notes[dup.id] = []

        if bool(select_new):
            try:
                self.select_clip(dup.id)
            except Exception:
                pass

        try:
            self.status.emit('ClipLauncher: Clip dupliziert')
        except Exception:
            pass
        self._emit_updated()
        return str(dup.id)


    # --- Audio Clip Editor integration (AudioEventEditor)
    def update_audio_clip_params(
        self,
        clip_id: str,
        *,
        gain: float | None = None,
        pan: float | None = None,
        pitch: float | None = None,
        formant: float | None = None,
        stretch: float | None = None,
        stretch_mode: str | None = None,
        stretch_markers: list | None = None,
        reversed: bool | None = None,
        muted: bool | None = None,
        fade_in_beats: float | None = None,
        fade_out_beats: float | None = None,
    ) -> None:
        """Update non-destructive audio parameters on a Clip.

        This updates the central Project model (single source of truth) so that:
        - AudioEventEditor reflects changes immediately
        - ClipLauncher slot preview stays in sync (via project.updated refresh)
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return

        changed = False
        if gain is not None:
            try:
                clip.gain = float(gain)
                changed = True
            except Exception:
                pass
        if pan is not None:
            try:
                clip.pan = float(pan)
                changed = True
            except Exception:
                pass
        if pitch is not None:
            try:
                clip.pitch = float(pitch)
                changed = True
            except Exception:
                pass
        if formant is not None:
            try:
                clip.formant = float(formant)
                changed = True
            except Exception:
                pass
        if stretch is not None:
            try:
                clip.stretch = max(0.01, float(stretch))
                changed = True
            except Exception:
                pass
        if reversed is not None:
            try:
                clip.reversed = bool(reversed)
                changed = True
            except Exception:
                pass
        if muted is not None:
            try:
                clip.muted = bool(muted)
                changed = True
            except Exception:
                pass
        if fade_in_beats is not None:
            try:
                clip.fade_in_beats = max(0.0, float(fade_in_beats))
                changed = True
            except Exception:
                pass
        if fade_out_beats is not None:
            try:
                clip.fade_out_beats = max(0.0, float(fade_out_beats))
                changed = True
            except Exception:
                pass
        # v0.0.20.650: Stretch mode + warp markers (AP3 Phase 3C Task 4)
        if stretch_mode is not None:
            try:
                sm = str(stretch_mode)
                if sm in ("tones", "beats", "texture", "repitch", "complex"):
                    clip.stretch_mode = sm
                    changed = True
            except Exception:
                pass
        if stretch_markers is not None:
            try:
                clip.stretch_markers = list(stretch_markers)
                changed = True
            except Exception:
                pass

        if changed:
            self._emit_updated()

    
    def set_audio_clip_loop(self, clip_id: str, start_beats: float, end_beats: float) -> None:
        """Set per-clip loop region (beats relative to clip content start)."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return
        try:
            s = max(0.0, float(start_beats))
            e = max(0.0, float(end_beats))
            clip.loop_start_beats = s
            clip.loop_end_beats = e
            self._emit_updated()
        except Exception:
            return

    # --- Pro Audio Clip methods (Bitwig/Ableton parity) ----------------------

    def normalize_audio_clip(self, clip_id: str) -> float | None:
        """Normalize clip by analysing peak level and setting gain to reach 0 dBFS.

        Returns the new gain value or None on failure.
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return None
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return None
        path = getattr(clip, "source_path", None)
        if not path:
            return None
        try:
            import os
            if not os.path.exists(str(path)):
                return None
            import soundfile as _sf
            import numpy as _np
            data, _sr = _sf.read(str(path), always_2d=True, dtype="float32")
            if data.size == 0:
                return None
            peak = float(_np.abs(data).max())
            if peak < 1e-10:
                return None
            new_gain = min(4.0, 1.0 / peak)
            clip.gain = new_gain
            self._emit_updated()
            return new_gain
        except Exception:
            return None

    def detect_onsets(self, clip_id: str, *, sensitivity: float = 2.0) -> list[float]:
        """Energy-based onset detection. Returns list of onset positions in beats.

        Uses spectral flux with adaptive threshold.
        sensitivity: threshold = mean + sensitivity*std (lower = more onsets)
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return []
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return []
        path = getattr(clip, "source_path", None)
        if not path:
            return []
        try:
            import os
            if not os.path.exists(str(path)):
                return []
            import soundfile as _sf
            import numpy as _np
            data, sr = _sf.read(str(path), always_2d=True, dtype="float32")
            if data.size == 0:
                return []

            mono = data.mean(axis=1)
            hop = max(1, int(sr * 0.01))  # 10ms hop
            n_frames = max(1, len(mono) // hop)

            # Energy per frame
            energy = _np.array([
                float(_np.sum(mono[i * hop:(i + 1) * hop] ** 2))
                for i in range(n_frames)
            ], dtype=_np.float64)

            # Spectral flux (half-wave rectified difference)
            flux = _np.zeros(n_frames, dtype=_np.float64)
            for i in range(1, n_frames):
                diff = energy[i] - energy[i - 1]
                flux[i] = max(0.0, diff)

            if flux.max() < 1e-12:
                return []

            # Adaptive threshold
            mean_f = float(flux.mean())
            std_f = float(flux.std())
            threshold = max(mean_f + sensitivity * std_f, 0.15 * float(flux.max()))

            # Minimum distance between onsets (50ms)
            min_dist_frames = max(1, int(0.05 * sr / hop))

            bpm = float(getattr(self.ctx.project, 'bpm', 120.0) or 120.0)
            samples_per_beat = sr * 60.0 / bpm

            onsets: list[float] = []
            last_onset = -min_dist_frames - 1
            for i in range(1, n_frames):
                if flux[i] > threshold and (i - last_onset) >= min_dist_frames:
                    sample_pos = i * hop
                    beat_pos = float(sample_pos / samples_per_beat)
                    onsets.append(round(beat_pos, 6))
                    last_onset = i

            clip.onsets = list(onsets)
            self._emit_updated()
            return list(onsets)
        except Exception:
            return []

    def add_onset_at(self, clip_id: str, at_beats: float) -> None:
        """Add a single onset marker at a given beat position."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip:
            return
        try:
            b = float(at_beats)
            if not hasattr(clip, 'onsets') or clip.onsets is None:
                clip.onsets = []
            clip.onsets.append(round(b, 6))
            clip.onsets = sorted(set(clip.onsets))
            self._emit_updated()
        except Exception:
            pass

    def clear_onsets(self, clip_id: str) -> None:
        """Remove all onset markers from a clip."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip:
            return
        try:
            clip.onsets = []
            self._emit_updated()
        except Exception:
            pass

    def find_zero_crossings(self, clip_id: str, near_beats: float, radius_beats: float = 0.05) -> float:
        """Find nearest zero-crossing to a given position for click-free edits.

        Returns the position in beats of the nearest zero crossing, or the
        original position if no crossing is found.
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return float(near_beats)
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return float(near_beats)
        path = getattr(clip, "source_path", None)
        if not path:
            return float(near_beats)
        try:
            import os
            if not os.path.exists(str(path)):
                return float(near_beats)
            import soundfile as _sf
            import numpy as _np
            data, sr = _sf.read(str(path), always_2d=True, dtype="float32")
            if data.size == 0:
                return float(near_beats)
            mono = data.mean(axis=1)

            bpm = float(getattr(self.ctx.project, 'bpm', 120.0) or 120.0)
            spb = sr * 60.0 / bpm  # samples per beat
            center = int(float(near_beats) * spb)
            radius = max(1, int(float(radius_beats) * spb))
            lo = max(0, center - radius)
            hi = min(len(mono) - 1, center + radius)

            seg = mono[lo:hi + 1]
            if len(seg) < 2:
                return float(near_beats)

            # Find sign changes
            signs = _np.sign(seg)
            crossings = _np.where(_np.diff(signs) != 0)[0]
            if len(crossings) == 0:
                return float(near_beats)

            # Find nearest to center
            center_in_seg = center - lo
            dists = _np.abs(crossings - center_in_seg)
            best_idx = int(crossings[_np.argmin(dists)])
            sample_pos = lo + best_idx
            return round(float(sample_pos / spb), 6)
        except Exception:
            return float(near_beats)

    def slice_at_onsets(self, clip_id: str) -> int:
        """Split audio events at all detected onset positions. Returns count of new splits."""
        cid = str(clip_id or "").strip()
        if not cid:
            return 0
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip:
            return 0
        try:
            onsets = sorted(set(getattr(clip, 'onsets', []) or []))
        except Exception:
            return 0
        if not onsets:
            return 0
        count = 0
        for ob in onsets:
            try:
                t = float(ob)
                if t <= 0.001:
                    continue
                # Find events that contain this onset
                evs = list(getattr(clip, "audio_events", []) or [])
                for e in evs:
                    s = float(getattr(e, "start_beats", 0.0) or 0.0)
                    l = float(getattr(e, "length_beats", 0.0) or 0.0)
                    eid = str(getattr(e, "id", ""))
                    if not eid or l < 0.01:
                        continue
                    if s + 0.001 < t < s + l - 0.001:
                        try:
                            self.split_audio_events_at(cid, t, event_ids=[eid])
                            count += 1
                        except Exception:
                            pass
                        break
            except Exception:
                continue
        return count

    # --- Clip-level automation (per-clip envelopes, Bitwig/Ableton-style) ---

    def add_clip_automation_point(self, clip_id: str, param: str, beat: float, value: float) -> None:
        """Add or update an automation breakpoint for a clip parameter.

        param: "gain", "pan", "pitch", "formant"
        beat: position in beats (relative to clip start)
        value: 0.0..1.0 normalized
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip:
            return
        if not hasattr(clip, 'clip_automation') or clip.clip_automation is None:
            clip.clip_automation = {}
        param = str(param or "").strip().lower()
        if param not in ("gain", "pan", "pitch", "formant"):
            return
        pts = clip.clip_automation.get(param, [])
        # Remove existing point at same beat (within epsilon)
        pts = [p for p in pts if abs(float(p.get("beat", 0)) - float(beat)) > 0.005]
        pts.append({"beat": round(float(beat), 4), "value": round(max(0.0, min(1.0, float(value))), 4)})
        pts.sort(key=lambda p: float(p.get("beat", 0)))
        clip.clip_automation[param] = pts
        self._emit_updated()

    def move_clip_automation_point(self, clip_id: str, param: str, old_beat: float, new_beat: float, value: float | None = None) -> None:
        """Move an existing automation breakpoint (tight tolerance) and optionally update its value.

        This is used by the *Zeiger/Pointer* tool in the AudioEventEditor so that dragging a point
        does not create duplicates.
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or not hasattr(clip, 'clip_automation') or clip.clip_automation is None:
            return
        param = str(param or "").strip().lower()
        if param not in ("gain", "pan", "pitch", "formant"):
            return
        pts = list(clip.clip_automation.get(param, []) or [])
        if not pts:
            return

        ob = float(old_beat)
        nb = float(new_beat)
        # Find nearest point to old_beat (tight tolerance)
        best_i = None
        best_d = 0.05  # beats
        for i, p in enumerate(pts):
            try:
                d = abs(float(p.get('beat', 0.0)) - ob)
            except Exception:
                continue
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            return

        # Use old value if none provided
        if value is None:
            try:
                value = float(pts[best_i].get('value', 0.5))
            except Exception:
                value = 0.5

        # Remove old + insert new
        try:
            pts.pop(best_i)
        except Exception:
            return

        # Prevent duplicates near new beat
        pts = [p for p in pts if abs(float(p.get('beat', 0.0)) - nb) > 0.01]
        pts.append({'beat': round(float(nb), 4), 'value': round(max(0.0, min(1.0, float(value))), 4)})
        pts.sort(key=lambda p: float(p.get('beat', 0.0)))
        clip.clip_automation[param] = pts
        self._emit_updated()

    def remove_clip_automation_point(self, clip_id: str, param: str, beat: float) -> None:
        """Remove an automation breakpoint near the given beat."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or not hasattr(clip, 'clip_automation') or not clip.clip_automation:
            return
        param = str(param or "").strip().lower()
        pts = clip.clip_automation.get(param, [])
        if not pts:
            return
        # Remove point nearest to beat (within tolerance)
        best_i = None
        best_d = 0.2  # tolerance in beats
        for i, p in enumerate(pts):
            d = abs(float(p.get("beat", 0)) - float(beat))
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is not None:
            pts.pop(best_i)
            clip.clip_automation[param] = pts
            self._emit_updated()

    def clear_clip_automation(self, clip_id: str, param: str | None = None) -> None:
        """Clear all automation points for a param (or all params if None)."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or not hasattr(clip, 'clip_automation') or not clip.clip_automation:
            return
        if param:
            clip.clip_automation[str(param).lower()] = []
        else:
            clip.clip_automation = {}
        self._emit_updated()

    # --- Stretch / Warp Markers ---

    def add_stretch_marker(self, clip_id: str, beat: float) -> None:
        """Add a warp marker at the given beat position.

        Storage format (JSON-safe): list of dicts:
            {"src": <beat in source space>, "dst": <beat in destination space>}

        For legacy projects where stretch_markers is a list of floats, we auto-upgrade to dicts.
        """
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == str(clip_id)), None)
        if not clip:
            return

        b = float(beat)
        raw = list(getattr(clip, "stretch_markers", None) or [])

        # Coerce legacy float markers into dict markers
        markers: list[dict] = []
        for m in raw:
            if isinstance(m, dict):
                try:
                    src = float(m.get('src', m.get('beat', 0.0)))
                    dst = float(m.get('dst', m.get('beat', src)))
                except Exception:
                    continue
                markers.append({'src': src, 'dst': dst})
            elif isinstance(m, (int, float)):
                fv = float(m)
                markers.append({'src': fv, 'dst': fv})

        # Don't add duplicates near dst
        if any(abs(float(mm.get('dst', 0.0)) - b) < 0.02 for mm in markers):
            return

        markers.append({'src': b, 'dst': b})
        markers.sort(key=lambda mm: float(mm.get('src', 0.0)))
        clip.stretch_markers = markers
        self._emit_updated()

    def remove_stretch_marker(self, clip_id: str, beat: float) -> None:
        """Remove the warp marker nearest to the given beat position (by dst)."""
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == str(clip_id)), None)
        if not clip:
            return

        raw = list(getattr(clip, "stretch_markers", None) or [])
        if not raw:
            return

        # Coerce legacy float markers into dict markers
        markers: list[dict] = []
        for m in raw:
            if isinstance(m, dict):
                try:
                    src = float(m.get('src', m.get('beat', 0.0)))
                    dst = float(m.get('dst', m.get('beat', src)))
                except Exception:
                    continue
                markers.append({'src': src, 'dst': dst})
            elif isinstance(m, (int, float)):
                fv = float(m)
                markers.append({'src': fv, 'dst': fv})

        if not markers:
            return

        b = float(beat)
        # Find nearest by dst
        nearest_idx = min(range(len(markers)), key=lambda i: abs(float(markers[i].get('dst', 0.0)) - b))
        if abs(float(markers[nearest_idx].get('dst', 0.0)) - b) < 0.5:
            markers.pop(nearest_idx)
            markers.sort(key=lambda mm: float(mm.get('src', 0.0)))
            clip.stretch_markers = markers
            self._emit_updated()

    def move_stretch_marker(self, clip_id: str, old_beat: float, new_beat: float) -> None:
        """Move a warp marker from old_beat to new_beat (updates dst).

        Markers are stored as dicts {src,dst}. We keep src fixed (anchor to source transient)
        and move dst (musical grid position). To prevent crossings, dst is clamped between
        neighbor dst positions in src-order.
        """
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == str(clip_id)), None)
        if not clip:
            return

        raw = list(getattr(clip, "stretch_markers", None) or [])
        if not raw:
            return

        # Coerce legacy float markers into dict markers
        markers: list[dict] = []
        for m in raw:
            if isinstance(m, dict):
                try:
                    src = float(m.get('src', m.get('beat', 0.0)))
                    dst = float(m.get('dst', m.get('beat', src)))
                except Exception:
                    continue
                markers.append({'src': src, 'dst': dst})
            elif isinstance(m, (int, float)):
                fv = float(m)
                markers.append({'src': fv, 'dst': fv})

        if not markers:
            return

        ob = float(old_beat)
        nb = float(new_beat)

        # Find nearest by dst to old_beat (before sorting)
        idx = min(range(len(markers)), key=lambda i: abs(float(markers[i].get('dst', 0.0)) - ob))
        if abs(float(markers[idx].get('dst', 0.0)) - ob) > 0.75:
            return
        src_key = float(markers[idx].get('src', 0.0))

        # Clamp dst between neighbor dst positions (in src order)
        markers.sort(key=lambda mm: float(mm.get('src', 0.0)))
        # Re-find index by src
        idx2 = None
        for i, mm in enumerate(markers):
            if abs(float(mm.get('src', 0.0)) - src_key) < 1e-6:
                idx2 = i
                break
        if idx2 is None:
            return

        lo = 0.0
        hi = float(getattr(clip, 'length_beats', 0.0) or 0.0)
        if hi <= 0.0:
            hi = max(0.0, float(max(float(mm.get('dst', 0.0)) for mm in markers) + 1.0))

        eps = 0.02
        if idx2 > 0:
            try:
                lo = max(lo, float(markers[idx2 - 1].get('dst', 0.0)) + eps)
            except Exception:
                pass
        if idx2 < len(markers) - 1:
            try:
                hi = min(hi, float(markers[idx2 + 1].get('dst', hi)) - eps)
            except Exception:
                pass

        nb = max(lo, min(hi, nb))
        markers[idx2]['dst'] = float(nb)
        clip.stretch_markers = markers
        self._emit_updated()

    def auto_detect_warp_markers(self, clip_id: str) -> int:
        """Detect beats in audio and auto-place warp markers at each beat.

        v0.0.20.641 (AP3 Phase 3A): Uses Essentia beat tracking (or autocorr fallback)
        to find beat positions in the audio, then creates WarpMarker entries.
        Returns the number of markers placed.
        """
        try:
            clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == str(clip_id)), None)
            if not clip:
                return 0
            if str(getattr(clip, "kind", "")) != "audio":
                return 0
            src = str(getattr(clip, "source_path", "") or "")
            if not src:
                return 0

            # Load audio
            import soundfile as sf
            try:
                data, sr = sf.read(src, dtype='float32', always_2d=True)
            except Exception:
                return 0

            if data is None or len(data) < sr // 4:
                return 0

            # Detect beat positions
            from pydaw.audio.bpm_detect import detect_beat_positions
            result = detect_beat_positions(data, int(sr))

            if not result.beats_seconds:
                return 0

            # Convert seconds → beats using project BPM
            project_bpm = float(getattr(self.ctx.project, "bpm", 120.0) or 120.0)
            if project_bpm < 20.0:
                project_bpm = 120.0
            secs_per_beat = 60.0 / project_bpm

            # Also store detected BPM on clip for tempo-sync
            if result.bpm and result.bpm > 20.0:
                clip.source_bpm = float(result.bpm)

            # Build warp markers: src_beat = position in source, dst_beat = same initially
            markers: list[dict] = []
            clip_len_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)
            if clip_len_beats <= 0.0:
                duration = float(len(data)) / float(sr)
                clip_len_beats = duration / secs_per_beat

            # Anchor at start
            markers.append({'src': 0.0, 'dst': 0.0})

            for sec in result.beats_seconds:
                beat_pos = float(sec) / secs_per_beat
                if beat_pos <= 0.01 or beat_pos >= clip_len_beats - 0.01:
                    continue
                # Avoid duplicates
                if any(abs(float(m.get('src', 0.0)) - beat_pos) < 0.02 for m in markers):
                    continue
                markers.append({'src': round(beat_pos, 6), 'dst': round(beat_pos, 6)})

            # Anchor at end
            markers.append({'src': round(clip_len_beats, 6), 'dst': round(clip_len_beats, 6)})

            markers.sort(key=lambda m: float(m.get('src', 0.0)))
            clip.stretch_markers = markers
            self._emit_updated()
            return len(markers)
        except Exception:
            return 0

    def clear_warp_markers(self, clip_id: str) -> None:
        """Remove all warp markers from a clip.

        v0.0.20.641 (AP3 Phase 3A).
        """
        try:
            clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == str(clip_id)), None)
            if clip:
                clip.stretch_markers = []
                self._emit_updated()
        except Exception:
            pass

    # --- Phase 2: Non-destructive AudioEvents (Knife/Merge) -----------------

    def _ensure_audio_events(self, clip) -> None:  # noqa: ANN001
        """Ensure clip.audio_events exists. If missing/empty, derive from slices or full length."""
        try:
            evs = list(getattr(clip, "audio_events", []) or [])
        except Exception:
            evs = []

        # If already has events, keep (but normalize types if dicts slipped in)
        if evs:
            from pydaw.model.project import AudioEvent
            conv = []
            for e in evs:
                if hasattr(e, "start_beats") and hasattr(e, "length_beats"):
                    conv.append(e)
                elif isinstance(e, dict):
                    try:
                        conv.append(AudioEvent(**e))
                    except Exception:
                        continue
            clip.audio_events = conv
            # keep slices in sync for legacy UI
            self._sync_slices_from_events(clip)
            return

        from pydaw.model.project import AudioEvent

        length = float(getattr(clip, "length_beats", 0.0) or 0.0)
        length = max(0.0, length)
        base_off = float(getattr(clip, "offset_beats", 0.0) or 0.0)

        # Build boundaries from slices (if any)
        try:
            slices = sorted(float(x) for x in (getattr(clip, "audio_slices", []) or []) if isinstance(x, (int, float)))
        except Exception:
            slices = []
        # keep only inside (0, length)
        eps = 1e-6
        slices = [s for s in slices if eps < s < (length - eps)]
        bounds = [0.0] + slices + [length]
        evs2 = []
        for i in range(len(bounds) - 1):
            a = float(bounds[i]); b = float(bounds[i+1])
            if b <= a + eps:
                continue
            evs2.append(AudioEvent(start_beats=a, length_beats=(b - a), source_offset_beats=base_off + a))
        if not evs2:
            evs2 = [AudioEvent(start_beats=0.0, length_beats=length, source_offset_beats=base_off)]
        clip.audio_events = evs2
        self._sync_slices_from_events(clip)

    def _sync_slices_from_events(self, clip) -> None:  # noqa: ANN001
        """Legacy compatibility: store event boundaries as clip.audio_slices."""
        try:
            evs = list(getattr(clip, "audio_events", []) or [])
        except Exception:
            evs = []
        cuts = []
        for e in evs:
            try:
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
            except Exception:
                continue
            if s > 1e-6:
                cuts.append(s)
        cuts = sorted(set(round(x, 6) for x in cuts))
        clip.audio_slices = cuts

    def split_audio_event(self, clip_id: str, at_beats: float) -> None:
        """Knife: split the AudioEvent that contains at_beats into two events (non-destructive)."""
        # Backward-compatible wrapper.
        # NOTE: Newer UI code can call split_audio_events_at(..., event_ids=[...])
        # to enforce selection rules.
        self.split_audio_events_at(clip_id, at_beats, event_ids=None)

    def split_audio_events_at(self, clip_id: str, at_beats: float, event_ids: List[str] | None = None) -> List[str]:
        """Knife: split one or multiple AudioEvents at the same clip-local time (non-destructive).

        Args:
            clip_id: target clip id
            at_beats: clip-local split time in beats
            event_ids: if provided, only these events are eligible and *all* that contain at_beats
                       will be split. If None, the first containing event is split (legacy behavior).

        Returns:
            List of event ids that should be selected after the operation.
            When a split happens, contains the two new ids (left/right). If multiple splits happen,
            the list contains all new ids.
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return []
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return []

        try:
            t = float(at_beats)
        except Exception:
            return []
        length = max(0.0, float(getattr(clip, "length_beats", 0.0) or 0.0))
        t = max(0.0, min(length, t))

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if not evs:
            return []

        wanted: set[str] | None = None
        if event_ids is not None:
            try:
                wanted = set(str(x) for x in event_ids if str(x).strip())
            except Exception:
                wanted = None

        from pydaw.model.project import AudioEvent

        eps = 1e-4
        out: List[AudioEvent] = []
        new_selected: List[str] = []
        did_any_split = False

        # In legacy mode (wanted is None), we split only the first containing event.
        legacy_done = False

        for e in evs:
            try:
                eid = str(getattr(e, "id", ""))
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
                base_off = float(getattr(e, "source_offset_beats", 0.0) or 0.0)
            except Exception:
                out.append(e)
                continue

            if l <= eps:
                out.append(e)
                continue

            eend = s + l
            contains = (s - eps) <= t <= (eend + eps)

            eligible = contains
            if wanted is not None:
                eligible = contains and (eid in wanted)

            if eligible and not legacy_done:
                # avoid splitting at boundaries
                if abs(t - s) < eps or abs(t - eend) < eps:
                    out.append(e)
                    if wanted is not None and eid in wanted:
                        new_selected.append(eid)
                    continue

                left_len = t - s
                right_len = eend - t
                if left_len <= eps or right_len <= eps:
                    out.append(e)
                    if wanted is not None and eid in wanted:
                        new_selected.append(eid)
                    continue

                left = AudioEvent(start_beats=s, length_beats=left_len, source_offset_beats=base_off)
                right = AudioEvent(start_beats=t, length_beats=right_len, source_offset_beats=base_off + left_len)
                out.extend([left, right])
                new_selected.extend([left.id, right.id])
                did_any_split = True

                if wanted is None:
                    legacy_done = True
                continue

            out.append(e)
            if wanted is not None and eid in wanted:
                new_selected.append(eid)

        if not did_any_split:
            return []

        out.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        clip.audio_events = out
        self._sync_slices_from_events(clip)
        self._emit_updated()
        return new_selected

    def merge_audio_events_near(self, clip_id: str, at_beats: float, *, tolerance_beats: float = 0.05) -> None:
        """Eraser: merge two neighboring events by clicking near their boundary."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return
        try:
            t = float(at_beats)
        except Exception:
            return
        tol = max(0.0, float(tolerance_beats))

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if len(evs) < 2:
            return

        # boundaries are start positions of events (excluding first at 0)
        best_i = None
        best_d = None
        for i in range(1, len(evs)):
            b = float(getattr(evs[i], "start_beats", 0.0) or 0.0)
            d = abs(b - t)
            if best_d is None or d < best_d:
                best_d = d
                best_i = i
        if best_i is None or best_d is None or best_d > tol:
            return

        prev = evs[best_i - 1]
        cur = evs[best_i]
        s0 = float(getattr(prev, "start_beats", 0.0) or 0.0)
        l0 = float(getattr(prev, "length_beats", 0.0) or 0.0)
        l1 = float(getattr(cur, "length_beats", 0.0) or 0.0)
        off0 = float(getattr(prev, "source_offset_beats", 0.0) or 0.0)

        from pydaw.model.project import AudioEvent
        merged = AudioEvent(start_beats=s0, length_beats=(l0 + l1), source_offset_beats=off0)

        new_list = evs[:best_i-1] + [merged] + evs[best_i+1:]
        new_list.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        clip.audio_events = new_list
        self._sync_slices_from_events(clip)
        self._emit_updated()


    # --- Phase 2.1: AudioEvent selection / move / quantize / consolidate -----

    def snap_quantum_beats(self, division: str | None = None) -> float:
        """Return grid snap quantum in beats (quarter-note beats).

        - For '1/16' -> 0.25 beats (because whole note = 4 beats).
        - For '1/4'  -> 1.0 beat.
        """
        div = (division or getattr(self.ctx.project, "snap_division", "1/16") or "1/16").strip()
        # Allow values like '1/16'
        try:
            if "/" in div:
                num_s, den_s = div.split("/", 1)
                num = float(num_s)
                den = float(den_s)
                if den <= 0:
                    return 0.25
                return max(1e-6, (4.0 * num) / den)
        except Exception:
            pass
        return 0.25

    def move_audio_events(self, clip_id: str, event_ids: List[str], delta_beats: float) -> None:
        """Move selected AudioEvents by delta_beats, clamped to clip bounds.

        Notes:
        - Non-destructive: source_offset_beats stays unchanged (slip editing is a separate feature).
        - Overlaps are currently allowed (Phase 2.2 can add collision handling).
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return
        try:
            d = float(delta_beats)
        except Exception:
            return
        if abs(d) < 1e-9:
            return

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if not evs:
            return

        wanted = {str(x) for x in (event_ids or []) if str(x)}
        if not wanted:
            return

        # collect items
        sel = []
        for e in evs:
            try:
                if str(getattr(e, "id", "")) in wanted:
                    sel.append(e)
            except Exception:
                continue
        if not sel:
            return

        length = max(0.0, float(getattr(clip, "length_beats", 0.0) or 0.0))

        min_start = None
        max_end = None
        for e in sel:
            s = float(getattr(e, "start_beats", 0.0) or 0.0)
            l = float(getattr(e, "length_beats", 0.0) or 0.0)
            if min_start is None or s < min_start:
                min_start = s
            if max_end is None or (s + l) > max_end:
                max_end = s + l
        if min_start is None or max_end is None:
            return

        # clamp delta to stay inside [0, length]
        d_min = -min_start
        d_max = length - max_end
        if d < d_min:
            d = d_min
        if d > d_max:
            d = d_max

        for e in sel:
            e.start_beats = float(getattr(e, "start_beats", 0.0) or 0.0) + d

        evs.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        clip.audio_events = evs
        self._sync_slices_from_events(clip)
        self._emit_updated()

    
    def duplicate_audio_events(self, clip_id: str, event_ids: List[str], delta_beats: float = 0.0, *, emit_updated: bool = True) -> dict[str, str]:
        """Duplicate selected AudioEvents and return a mapping old_id -> new_id.

        Used by AudioEventEditor for Pro-DAW-like Alt=Duplicate drag.
        Non-destructive: duplicates reference the same source file via source_offset_beats.
        """

        cid = str(clip_id or "").strip()
        if not cid:
            return {}
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return {}

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if not evs:
            return {}

        wanted = {str(x) for x in (event_ids or []) if str(x)}
        if not wanted:
            return {}

        try:
            d = float(delta_beats)
        except Exception:
            d = 0.0

        length = max(0.0, float(getattr(clip, "length_beats", 0.0) or 0.0))
        out_map: dict[str, str] = {}
        new_events: list[AudioEvent] = []

        for e in evs:
            try:
                oid = str(getattr(e, "id", ""))
                if oid not in wanted:
                    continue
                start = float(getattr(e, "start_beats", 0.0) or 0.0) + d
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
                # clamp within clip bounds
                start = max(0.0, min(start, max(0.0, length - max(0.0, l))))
                nid = new_id("aev")
                out_map[oid] = nid
                new_events.append(
                    AudioEvent(
                        id=nid,
                        start_beats=float(start),
                        length_beats=float(l),
                        source_offset_beats=float(getattr(e, "source_offset_beats", 0.0) or 0.0),
                    )
                )
            except Exception:
                continue

        if not new_events:
            return {}

        evs.extend(new_events)
        try:
            evs.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        except Exception:
            pass
        clip.audio_events = evs
        self._sync_slices_from_events(clip)

        if emit_updated:
            self._emit_updated()
        return out_map

    def delete_audio_events(self, clip_id: str, event_ids: List[str], *, emit_updated: bool = True) -> None:
        """Delete selected AudioEvents from an audio clip.

        Used by AudioEventEditor for standard DAW shortcuts:
        - Delete / Backspace
        - Ctrl+X (Cut)

        Safety:
        - No exceptions escape.
        - Clip slices are re-synced.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return
        clip = next((c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if not clip or str(getattr(clip, 'kind', '')) != 'audio':
            return

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, 'audio_events', []) or [])
        if not evs:
            return

        wanted = {str(x) for x in (event_ids or []) if str(x)}
        if not wanted:
            return

        evs2 = []
        removed = False
        for e in evs:
            try:
                if str(getattr(e, 'id', '')) in wanted:
                    removed = True
                    continue
            except Exception:
                pass
            evs2.append(e)

        if not removed:
            return

        try:
            evs2.sort(key=lambda x: float(getattr(x, 'start_beats', 0.0) or 0.0))
        except Exception:
            pass
        clip.audio_events = evs2
        try:
            self._sync_slices_from_events(clip)
        except Exception:
            pass
        if emit_updated:
            self._emit_updated()

    def add_audio_events_from_templates(
        self,
        clip_id: str,
        templates: List[dict],
        *,
        delta_beats: float = 0.0,
        emit_updated: bool = True,
    ) -> List[str]:
        """Create new AudioEvents from template dicts.

        Template format (best-effort):
            {
              'start_beats': float,
              'length_beats': float,
              'source_offset_beats': float
            }

        Returns:
            list of new AudioEvent ids.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return []
        clip = next((c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if not clip or str(getattr(clip, 'kind', '')) != 'audio':
            return []

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, 'audio_events', []) or [])
        length = max(0.0, float(getattr(clip, 'length_beats', 0.0) or 0.0))

        try:
            d = float(delta_beats)
        except Exception:
            d = 0.0

        new_ids: List[str] = []
        new_events: List[AudioEvent] = []
        for t in (templates or []):
            try:
                s = float(t.get('start_beats', 0.0) or 0.0) + d
                l = float(t.get('length_beats', 0.0) or 0.0)
                o = float(t.get('source_offset_beats', 0.0) or 0.0)
            except Exception:
                continue
            if l <= 1e-9:
                continue
            # clamp within clip bounds
            s = max(0.0, min(float(s), max(0.0, length - max(0.0, float(l)))))
            nid = new_id('aev')
            new_ids.append(str(nid))
            new_events.append(AudioEvent(id=str(nid), start_beats=float(s), length_beats=float(l), source_offset_beats=float(o)))

        if not new_events:
            return []

        evs.extend(new_events)
        try:
            evs.sort(key=lambda x: float(getattr(x, 'start_beats', 0.0) or 0.0))
        except Exception:
            pass
        clip.audio_events = evs
        try:
            self._sync_slices_from_events(clip)
        except Exception:
            pass
        if emit_updated:
            self._emit_updated()
        return new_ids

    def quantize_audio_events(self, clip_id: str, event_ids: List[str], division: str | None = None) -> None:
        """Quantize selected AudioEvents to the current snap grid (start_beats)."""
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if not evs:
            return

        wanted = {str(x) for x in (event_ids or []) if str(x)}
        if not wanted:
            return

        q = self.snap_quantum_beats(division)
        length = max(0.0, float(getattr(clip, "length_beats", 0.0) or 0.0))

        for e in evs:
            try:
                if str(getattr(e, "id", "")) not in wanted:
                    continue
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
                snapped = round(s / q) * q
                snapped = max(0.0, min(snapped, max(0.0, length - l)))
                e.start_beats = float(snapped)
            except Exception:
                continue

        evs.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        clip.audio_events = evs
        self._sync_slices_from_events(clip)
        self._emit_updated()

    def consolidate_audio_events(self, clip_id: str, event_ids: List[str]) -> None:
        """Consolidate selected AudioEvents into one, but only if they form a contiguous, source-aligned chain.

        Requirements for merge:
        - Events are contiguous in clip timeline (end == next.start)
        - And contiguous in source timeline (next.source_offset == prev.source_offset + prev.length)
        """
        cid = str(clip_id or "").strip()
        if not cid:
            return
        clip = next((c for c in self.ctx.project.clips if getattr(c, "id", "") == cid), None)
        if not clip or getattr(clip, "kind", "") != "audio":
            return

        self._ensure_audio_events(clip)
        evs = list(getattr(clip, "audio_events", []) or [])
        if len(evs) < 2:
            return

        wanted = {str(x) for x in (event_ids or []) if str(x)}
        if not wanted:
            return

        sel = [e for e in evs if str(getattr(e, "id", "")) in wanted]
        if len(sel) < 2:
            return
        sel.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))

        eps = 1e-4
        ok = True
        for a, b in zip(sel, sel[1:]):
            a_s = float(getattr(a, "start_beats", 0.0) or 0.0)
            a_l = float(getattr(a, "length_beats", 0.0) or 0.0)
            a_o = float(getattr(a, "source_offset_beats", 0.0) or 0.0)
            b_s = float(getattr(b, "start_beats", 0.0) or 0.0)
            b_o = float(getattr(b, "source_offset_beats", 0.0) or 0.0)
            if abs((a_s + a_l) - b_s) > eps:
                ok = False
                break
            if abs((a_o + a_l) - b_o) > eps:
                ok = False
                break
        if not ok:
            return

        from pydaw.model.project import AudioEvent
        first = sel[0]
        start = float(getattr(first, "start_beats", 0.0) or 0.0)
        off = float(getattr(first, "source_offset_beats", 0.0) or 0.0)
        total = sum(float(getattr(e, "length_beats", 0.0) or 0.0) for e in sel)
        merged = AudioEvent(start_beats=start, length_beats=total, source_offset_beats=off, id=str(getattr(first, "id", "")))

        # rebuild list: remove selected ids, insert merged
        new_list = [e for e in evs if str(getattr(e, "id", "")) not in wanted]
        new_list.append(merged)
        new_list.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        clip.audio_events = new_list
        self._sync_slices_from_events(clip)
        self._emit_updated()



    def bounce_consolidate_audio_events_to_new_clip(
        self,
        source_clip_id: str,
        event_ids: List[str],
        *,
        replace_in_launcher: bool = True,
        select_new_clip: bool = True,
        # mode:
        # - "bar"  : Consolidate Time (bar-anchored, keeps musical placement)
        # - "trim" : Trim to Selection (no leading silence; content starts at first selected event)
        mode: str = "bar",
        # Optional pro flags
        handles_beats: float = 0.0,   # pre/post handle audio kept in file but not played (offset_beats)
        tail_beats: float = 0.0,      # extra tail rendered and included in clip length
        normalize: bool = False,      # optional peak normalization after mixdown
        label_suffix: str = " Consolidated",
    ) -> str | None:
        """Bounce/Consolidate selected AudioEvents into ONE new rendered audio clip.

        Professional DAW behavior:
        - Ctrl+J (mode="bar"): Consolidate Time (bar-anchored). Keeps bar-relative timing.
        - Shift+Ctrl+J (mode="trim"): Trim to selection (no leading silence).
        - Optional: handles_beats creates edit handles in the rendered file WITHOUT changing playback
          timing (we keep them via clip.offset_beats).
        - Optional: tail_beats extends the clip length and renders extra audio at the end.

        Safety:
        - Does NOT destroy the source clip.
        - Can replace Clip-Launcher slot mappings that pointed to the source clip.
        """
        src_id = str(source_clip_id or '').strip()
        if not src_id:
            return None

        try:
            wanted = [str(x) for x in (event_ids or []) if str(x).strip()]
        except Exception:
            wanted = []
        if not wanted:
            return None

        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == src_id), None)
        if not clip or str(getattr(clip, 'kind', '')) != 'audio':
            return None

        # Ensure audio events exist
        try:
            self._ensure_audio_events(clip)
        except Exception:
            pass
        try:
            evs = list(getattr(clip, 'audio_events', []) or [])
        except Exception:
            evs = []
        if not evs:
            return None

        want_set = set(wanted)
        sel = [e for e in evs if str(getattr(e, 'id', '')) in want_set]
        if len(sel) < 1:
            return None
        sel.sort(key=lambda e: float(getattr(e, 'start_beats', 0.0) or 0.0))

        def _st(e: Any) -> float:
            return float(getattr(e, 'start_beats', 0.0) or 0.0)

        def _en(e: Any) -> float:
            return float(getattr(e, 'start_beats', 0.0) or 0.0) + float(getattr(e, 'length_beats', 0.0) or 0.0)

        sel_start = min(_st(e) for e in sel)
        sel_end = max(_en(e) for e in sel)
        if sel_end <= sel_start + 1e-6:
            return None

        # ---- determine base (playback) range ----
        mode_s = str(mode or 'bar').strip().lower()
        if mode_s not in ('bar', 'trim'):
            mode_s = 'bar'

        base_start = float(sel_start)
        base_end = float(sel_end)

        # Bar anchoring keeps musical placement inside the clip grid.
        if mode_s == 'bar':
            try:
                ts = str(getattr(proj, 'time_signature', '4/4') or '4/4')
                num_s = ts.split('/', 1)[0].strip()
                bar_beats = float(num_s) if num_s else 4.0
                if bar_beats <= 1e-9:
                    bar_beats = 4.0
            except Exception:
                bar_beats = 4.0
            try:
                base_start = float(math.floor(float(sel_start) / float(bar_beats)) * float(bar_beats))
                base_end = float(math.ceil(float(sel_end) / float(bar_beats)) * float(bar_beats))
            except Exception:
                base_start = float(sel_start)
                base_end = float(sel_end)

        # Tail is part of the clip length
        content_end = float(base_end) + max(0.0, float(tail_beats or 0.0))

        # ---- determine render range (includes handles) ----
        hb = max(0.0, float(handles_beats or 0.0))
        render_start = float(base_start) - float(hb)
        if render_start < 0.0:
            render_start = 0.0
        render_end = float(content_end) + float(hb)
        if render_end <= render_start + 1e-6:
            return None

        # Effective pre-handle kept in file but not played
        pre_handle = float(base_start) - float(render_start)

        clip_length_beats = float(max(0.25, float(content_end) - float(base_start)))
        render_length_beats = float(max(0.25, float(render_end) - float(render_start)))

        # --- render selection into a new WAV ---
        try:
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception:
            return None

        sr = int(getattr(proj, 'sample_rate', 48000) or 48000)
        bpm = float(getattr(proj, 'bpm', 120.0) or 120.0)
        beats_per_second = bpm / 60.0
        sppb = float(sr) / max(1e-9, beats_per_second)  # samples per beat

        src_path = str(getattr(clip, 'source_path', '') or '')
        if not src_path:
            return None

        # decode + resample to project SR
        try:
            data, file_sr = sf.read(str(src_path), dtype='float32', always_2d=True)
        except Exception:
            return None
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] >= 2:
            data = data[:, :2]

        try:
            file_sr_i = int(file_sr or sr)
        except Exception:
            file_sr_i = int(sr)
        if file_sr_i != int(sr) and int(data.shape[0]) > 1:
            ratio = float(sr) / float(file_sr_i)
            n_out = max(1, int(round(int(data.shape[0]) * ratio)))
            x_old = np.linspace(0.0, 1.0, num=int(data.shape[0]), endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
            data = np.vstack([
                np.interp(x_new, x_old, data[:, 0]),
                np.interp(x_new, x_old, data[:, 1]),
            ]).T.astype(np.float32, copy=False)

        # Clip params to bake
        clip_gain = float(getattr(clip, 'gain', 1.0) or 1.0)
        clip_pan = float(getattr(clip, 'pan', 0.0) or 0.0)
        clip_pitch = float(getattr(clip, 'pitch', 0.0) or 0.0)
        clip_stretch = float(getattr(clip, 'stretch', 1.0) or 1.0)
        if clip_stretch <= 1e-6:
            clip_stretch = 1.0
        rate = (2.0 ** (clip_pitch / 12.0)) / float(clip_stretch)

        # equal-power pan
        clip_pan = max(-1.0, min(1.0, clip_pan))
        angle = (clip_pan + 1.0) * (math.pi / 4.0)
        gl = float(clip_gain) * math.cos(angle)
        gr = float(clip_gain) * math.sin(angle)

        n_frames = int(round(float(render_length_beats) * float(sppb)))
        if n_frames <= 0:
            return None
        out = np.zeros((n_frames, 2), dtype=np.float32)

        base_off_beats = float(getattr(clip, 'offset_beats', 0.0) or 0.0)

        for e in sel:
            try:
                e_start = float(getattr(e, 'start_beats', 0.0) or 0.0)
                e_len = float(getattr(e, 'length_beats', 0.0) or 0.0)
                if e_len <= 1e-9:
                    continue
                e_end = e_start + e_len

                ov_start = max(float(render_start), e_start)
                ov_end = min(float(render_end), e_end)
                if ov_end <= ov_start + 1e-9:
                    continue

                dst_off = int(round((ov_start - float(render_start)) * float(sppb)))
                n = int(round((ov_end - ov_start) * float(sppb)))
                if n <= 0:
                    continue

                src_off_beats = float(getattr(e, 'source_offset_beats', 0.0) or 0.0)
                src_beat = float(base_off_beats + src_off_beats + (ov_start - e_start))
                src_off = int(round(src_beat * float(sppb)))

                if src_off >= int(data.shape[0]):
                    continue

                if abs(float(rate) - 1.0) < 1e-6:
                    src_end = min(int(data.shape[0]), int(src_off + n))
                    chunk = data[src_off:src_end]
                    if chunk.shape[0] < n:
                        pad = np.zeros((n, 2), dtype=np.float32)
                        pad[:chunk.shape[0]] = chunk
                        chunk = pad
                else:
                    idx = float(src_off) + (np.arange(int(n), dtype=np.float32) * float(rate))
                    i0 = np.floor(idx).astype(np.int64)
                    i1 = i0 + 1
                    max_i = int(data.shape[0]) - 1
                    i0 = np.clip(i0, 0, max_i)
                    i1 = np.clip(i1, 0, max_i)
                    frac = (idx - i0.astype(np.float32)).reshape((-1, 1))
                    s0 = data[i0]
                    s1 = data[i1]
                    chunk = (s0 * (1.0 - frac) + s1 * frac).astype(np.float32)

                # per-event reverse
                if bool(getattr(e, 'reversed', False)) and chunk.shape[0] > 1:
                    chunk = chunk[::-1].copy()

                # optional clip reverse
                if bool(getattr(clip, 'reversed', False)) and chunk.shape[0] > 1:
                    chunk = chunk[::-1].copy()

                end = min(n_frames, dst_off + int(n))
                take = int(end - dst_off)
                if take <= 0:
                    continue

                out[dst_off:dst_off + take, 0] += chunk[:take, 0] * float(gl)
                out[dst_off:dst_off + take, 1] += chunk[:take, 1] * float(gr)
            except Exception:
                continue

        # Optional normalize before final clip
        if bool(normalize):
            try:
                peak = float(np.max(np.abs(out))) if out.size else 0.0
                if peak > 1e-9:
                    out = out * (0.99 / peak)
            except Exception:
                pass

        out = np.clip(out, -1.0, 1.0)

        # Write into media dir
        media_dir = self.ctx.resolve_media_dir()
        try:
            media_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        safe_label = str(getattr(clip, 'label', 'Audio') or 'Audio').strip() or 'Audio'
        safe_label = re.sub(r"[^A-Za-z0-9_\- ]+", "", safe_label).strip().replace(" ", "_")
        fname = f"{safe_label}_consolidated_{new_id('wav')}.wav"
        out_path = media_dir / fname
        try:
            sf.write(str(out_path), out, int(sr))
        except Exception:
            return None

        # Register as media item
        try:
            load_path, media_id = self.import_audio_to_project(str(getattr(clip, 'track_id', '') or ''), Path(out_path), label=safe_label)
        except Exception:
            load_path, media_id = (str(out_path), '')

        # Create a NEW clip referencing the rendered file
        from pydaw.model.project import Clip, AudioEvent
        newc = Clip(kind='audio', track_id=str(getattr(clip, 'track_id', '') or ''), label=f"{getattr(clip, 'label', 'Audio')}{label_suffix}")
        newc.media_id = str(media_id) if media_id else None
        newc.source_path = str(load_path)
        newc.source_bpm = None

        # Keep musical playback timing: offset skips the pre-handle region.
        newc.offset_beats = float(pre_handle)
        newc.offset_seconds = 0.0
        newc.length_beats = float(clip_length_beats)
        newc.launcher_only = bool(getattr(clip, 'launcher_only', False))

        # Reset baked params to neutral
        newc.gain = 1.0
        newc.pan = 0.0
        newc.pitch = 0.0
        newc.formant = 0.0
        newc.stretch = 1.0
        newc.reversed = False
        newc.muted = False
        newc.fade_in_beats = 0.0
        newc.fade_out_beats = 0.0

        # One consolidated AudioEvent starting at 0 in the new clip.
        newc.audio_events = [AudioEvent(start_beats=0.0, length_beats=float(clip_length_beats), source_offset_beats=0.0, reversed=False)]

        # Full loop by default
        newc.loop_start_beats = 0.0
        newc.loop_end_beats = float(clip_length_beats)

        # --- Non-destructive render metadata (future-proof) ---
        try:
            badges = []
            badges.append('CONSOL') if mode_s == 'bar' else badges.append('TRIM')
            if hb > 1e-9:
                badges.append('+HANDLES')
            if float(tail_beats or 0.0) > 1e-9:
                badges.append('+TAIL')
            if bool(normalize):
                badges.append('NORM')
            newc.render_meta = {
                'badges': badges,
                'render': {
                    'kind': 'audio_events_bounce',
                    'mode': mode_s,
                    'base_start_beats': float(base_start),
                    'base_end_beats': float(base_end),
                    'tail_beats': float(max(0.0, float(tail_beats or 0.0))),
                    'handles_beats': float(hb),
                    'render_start_beats': float(render_start),
                    'render_end_beats': float(render_end),
                    'pre_handle_beats': float(pre_handle),
                    'clip_length_beats': float(clip_length_beats),
                    'render_length_beats': float(render_length_beats),
                    'normalize': bool(normalize),
                },
                'sources': {
                    'source_clip_id': str(src_id),
                    'source_path': str(src_path),
                    'source_clip_offset_beats': float(getattr(clip, 'offset_beats', 0.0) or 0.0),
                    # v0.0.20.173: capture original clip state (loop/automation/etc.)
                    # so Restore/Toggle can rebuild the exact original feel.
                    'source_clip_state': {
                        'loop_start_beats': float(getattr(clip, 'loop_start_beats', 0.0) or 0.0),
                        'loop_end_beats': float(getattr(clip, 'loop_end_beats', 0.0) or 0.0),
                        'fade_in_beats': float(getattr(clip, 'fade_in_beats', 0.0) or 0.0),
                        'fade_out_beats': float(getattr(clip, 'fade_out_beats', 0.0) or 0.0),
                        'clip_automation': dict(getattr(clip, 'clip_automation', {}) or {}) if isinstance(getattr(clip, 'clip_automation', {}), dict) else {},
                        'stretch_markers': list(getattr(clip, 'stretch_markers', []) or []) if isinstance(getattr(clip, 'stretch_markers', []), list) else [],
                    },
                    'event_ids': [str(x) for x in wanted],
                    'events': [
                        {
                            'id': str(getattr(e, 'id', '')),
                            'start_beats': float(getattr(e, 'start_beats', 0.0) or 0.0),
                            'length_beats': float(getattr(e, 'length_beats', 0.0) or 0.0),
                            'source_offset_beats': float(getattr(e, 'source_offset_beats', 0.0) or 0.0),
                            'reversed': bool(getattr(e, 'reversed', False)),
                        }
                        for e in sel
                    ],
                },
            }
        except Exception:
            pass

        self.ctx.project.clips.append(newc)

        # Replace launcher mapping(s) if requested
        if replace_in_launcher:
            try:
                for k, v in list((self.ctx.project.clip_launcher or {}).items()):
                    if str(v) == src_id:
                        self.ctx.project.clip_launcher[str(k)] = str(newc.id)
            except Exception:
                pass
        if bool(select_new_clip):
            try:
                self.select_clip(str(newc.id))
            except Exception:
                pass

        self._emit_updated()
        return str(newc.id)

    def _find_media_path_by_id(self, media_id: str) -> str:
        mid = str(media_id or '').strip()
        if not mid:
            return ''
        try:
            for m in (getattr(self.ctx.project, 'media', []) or []):
                if str(getattr(m, 'id', '') or '') == mid:
                    return str(getattr(m, 'path', '') or '')
        except Exception:
            pass
        return ''

    def _create_bounce_audio_track(self, name: str) -> Any:
        trk = Track(kind='audio', name=str(name or 'Bounce Track'))
        try:
            trk.instrument_state = {}
        except Exception:
            pass
        tracks = [t for t in self.ctx.project.tracks if str(getattr(t, 'kind', '')) != 'master']
        master = next((t for t in self.ctx.project.tracks if str(getattr(t, 'kind', '')) == 'master'), None)
        tracks.append(trk)
        if master is not None:
            tracks.append(master)
        self.ctx.project.tracks = tracks
        return trk

    def _track_display_name(self, track_id: str) -> str:
        trk = next((t for t in self.ctx.project.tracks if str(getattr(t, 'id', '')) == str(track_id)), None)
        if trk is None:
            return 'Track'
        return str(getattr(trk, 'name', '') or 'Track')

    def _render_engine_notes_offline(self, engine: Any, midi_notes: list[Any], bpm: float, clip_length_beats: float, samplerate: int, _progress_dlg: Any = None) -> Any:
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None
        if engine is None:
            return None
        beats_per_second = float(bpm) / 60.0
        if beats_per_second <= 1e-9:
            return None
        total_frames = int(round(max(0.25, float(clip_length_beats)) / beats_per_second * int(samplerate)))
        if total_frames <= 0:
            return None
        out = np.zeros((int(total_frames), 2), dtype=np.float32)
        events: list[tuple[int, int, int, int]] = []
        for n in (midi_notes or []):
            try:
                pitch = int(getattr(n, 'pitch', 60))
                start_beats = float(getattr(n, 'start_beats', 0.0) or 0.0)
                length_beats = float(getattr(n, 'length_beats', 0.25) or 0.25)
                velocity = int(getattr(n, 'velocity', 100) or 100)
                start_frame = max(0, int(round(start_beats / beats_per_second * int(samplerate))))
                dur_ms = max(10, int(round(max(0.01, length_beats / beats_per_second) * 1000.0)))
                events.append((start_frame, pitch, velocity, dur_ms))
            except Exception:
                continue
        events.sort(key=lambda x: x[0])
        cursor = 0
        evt_idx = 0
        block = 1024
        # v0.0.20.586: Keep GUI alive during long offline renders
        _qapp2 = None
        _blk_count = 0
        try:
            from PySide6.QtWidgets import QApplication
            _qapp2 = QApplication.instance()
        except Exception:
            pass
        while cursor < total_frames:
            while evt_idx < len(events) and events[evt_idx][0] <= cursor:
                _, pitch, velocity, dur_ms = events[evt_idx]
                try:
                    engine.trigger_note(int(pitch), int(velocity), int(dur_ms))
                except Exception:
                    try:
                        engine.note_on(int(pitch), int(velocity))
                    except Exception:
                        pass
                evt_idx += 1
            next_event = events[evt_idx][0] if evt_idx < len(events) else total_frames
            seg_end = min(total_frames, max(cursor + 1, next_event))
            while cursor < seg_end:
                take = min(block, seg_end - cursor)
                try:
                    chunk = engine.pull(int(take), int(samplerate))
                except Exception:
                    chunk = None
                if chunk is None:
                    chunk = np.zeros((int(take), 2), dtype=np.float32)
                try:
                    frames = int(min(int(take), int(getattr(chunk, 'shape', [0])[0] or 0)))
                except Exception:
                    frames = 0
                if frames > 0:
                    try:
                        out[cursor:cursor + frames, :] += chunk[:frames, :2]
                    except Exception:
                        pass
                cursor += int(take)
                _blk_count += 1
                if _qapp2 is not None and (_blk_count & 7) == 0:
                    try:
                        if _progress_dlg is not None:
                            _progress_dlg.set_progress(
                                float(cursor) / max(1, total_frames),
                                f"Rendering … {cursor * 100 // max(1, total_frames)}%"
                            )
                        else:
                            _qapp2.processEvents()
                    except Exception:
                        pass
        return out

    def _apply_track_fx_offline(self, track: Any, audio: Any, samplerate: int) -> Any:
        try:
            import numpy as np  # type: ignore
        except Exception:
            return audio
        if audio is None:
            return None
        chain = getattr(track, 'audio_fx_chain', None)
        if not isinstance(chain, dict) or not (chain.get('devices') or []):
            return audio
        try:
            from pydaw.audio.rt_params import RTParamStore
            from pydaw.audio.fx_chain import ChainFx
        except Exception:
            return audio
        try:
            rt = RTParamStore(default_smooth_ms=0.0)
        except Exception:
            class _RT:
                def __init__(self):
                    self._vals = {}
                def ensure(self, k, v):
                    self._vals.setdefault(str(k), float(v))
                def get_smooth(self, k, d=0.0):
                    return float(self._vals.get(str(k), d))
            rt = _RT()
        try:
            fx = ChainFx(track_id=str(getattr(track, 'id', '') or 'offline'), chain_spec=chain, rt_params=rt, max_frames=8192, sr=int(samplerate))
        except Exception:
            return audio
        if fx is None:
            return audio
        try:
            buf = np.array(audio, dtype=np.float32, copy=True)
        except Exception:
            return audio
        pos = 0
        total = int(buf.shape[0]) if getattr(buf, 'ndim', 0) >= 2 else 0
        while pos < total:
            n = min(8192, total - pos)
            try:
                fx.process_inplace(buf[pos:pos+n, :], int(n), int(samplerate))
            except Exception:
                break
            pos += int(n)
        return buf

    def _render_arrangement_subset_offline(self, track: Any, clips: list[Any], midi_notes_map: dict[str, list[Any]], render_start_beats: float, render_length_beats: float, samplerate: int) -> Any:
        try:
            from pydaw.model.project import Project, Track as _Track, Clip as _Clip
            from pydaw.audio.arrangement_renderer import prepare_clips, ArrangementState
            import numpy as np  # type: ignore
        except Exception:
            return None
        bpm = float(getattr(self.ctx.project, 'bpm', 120.0) or 120.0)
        tmp = Project(
            version=str(getattr(self.ctx.project, 'version', '') or ''),
            name=str(getattr(self.ctx.project, 'name', '') or ''),
            sample_rate=int(samplerate),
            bpm=float(bpm),
            time_signature=str(getattr(self.ctx.project, 'time_signature', '4/4') or '4/4'),
            snap_division=str(getattr(self.ctx.project, 'snap_division', '1/16') or '1/16'),
        )
        t = _Track(id=str(getattr(track, 'id', '') or ''), kind=str(getattr(track, 'kind', 'audio') or 'audio'), name=str(getattr(track, 'name', 'Track') or 'Track'))
        for attr in ('plugin_type','instrument_enabled','instrument_state','sf2_path','sf2_bank','sf2_preset','midi_channel','note_fx_chain'):
            try:
                setattr(t, attr, getattr(track, attr))
            except Exception:
                pass
        tmp.tracks = [t]
        tmp.midi_notes = {}
        for c in (clips or []):
            cc = _Clip(kind=str(getattr(c, 'kind', 'audio') or 'audio'), track_id=str(getattr(c, 'track_id', '') or ''))
            for attr in (
                'id','length_beats','offset_beats','offset_seconds','label','media_id','source_path','source_bpm',
                'gain','pan','pitch','formant','stretch','reversed','muted','fade_in_beats','fade_out_beats',
                'clip_automation','stretch_markers'
            ):
                try:
                    setattr(cc, attr, getattr(c, attr))
                except Exception:
                    pass
            try:
                cc.start_beats = float(getattr(c, 'start_beats', 0.0) or 0.0) - float(render_start_beats)
            except Exception:
                cc.start_beats = 0.0
            tmp.clips.append(cc)
            if str(getattr(cc, 'kind', '')) == 'midi':
                tmp.midi_notes[str(getattr(cc, 'id', ''))] = list(midi_notes_map.get(str(getattr(c, 'id', '')), []) or [])
        beats_per_second = float(bpm) / 60.0
        frames = int(round(max(0.25, float(render_length_beats)) / max(1e-9, beats_per_second) * int(samplerate)))
        if frames <= 0:
            return None
        try:
            prepared, midi_events, _ = prepare_clips(tmp, int(samplerate))
            st = ArrangementState(prepared, int(samplerate), 0.0, float(bpm), False, 0.0, 0.0, midi_events=midi_events)
            audio = st.render(int(frames))
        except Exception:
            return None
        if audio is None:
            return None
        try:
            return np.array(audio, dtype=np.float32, copy=False)
        except Exception:
            return audio

    def _track_has_vst_device(self, track: Any) -> bool:
        """Check if a track has any ext.vst2 or ext.vst3 device in its fx chain."""
        chain = getattr(track, 'audio_fx_chain', None)
        if not isinstance(chain, dict):
            return False
        for dev in (chain.get('devices') or []):
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get('plugin_id') or dev.get('type') or '')
            if pid.startswith('ext.vst2:') or pid.startswith('ext.vst3:'):
                return True
        # Also check if audio engine has a running VST engine for this track
        try:
            ae = getattr(self, '_audio_engine_ref', None)
            if ae is not None:
                tid = str(getattr(track, 'id', '') or '')
                if tid and tid in getattr(ae, '_vst_instrument_engines', {}):
                    return True
        except Exception:
            pass
        return False

    def _create_vst_instrument_engine_offline(self, track: Any, sr: int) -> Any:
        """v0.0.20.428: Get a VST instrument engine for offline bounce.

        BEST PRACTICE (how Bitwig/Ableton/Cubase do it):
        ─────────────────────────────────────────────────
        Real DAWs do NOT create a new plugin instance for bounce-in-place.
        They reuse the ALREADY RUNNING engine instance from the audio engine.
        The plugin is already loaded, initialized, has the correct state,
        and is guaranteed to produce audio.

        During bounce, transport is stopped → audio callback is idle →
        safe to borrow the running engine for offline render.

        Approach:
        1. FIRST: Try to borrow the running engine from audio_engine._vst_instrument_engines
        2. FALLBACK: Create a new offline instance (v426/v427 approach)

        The returned engine has a `_borrowed` flag. If True, caller must NOT shutdown().
        """
        import sys
        tid = str(getattr(track, 'id', '') or '')

        # ════════════════════════════════════════════════════════════════════
        # APPROACH 1: Borrow the RUNNING engine (best practice — always works)
        # ════════════════════════════════════════════════════════════════════
        try:
            ae = getattr(self, '_audio_engine_ref', None)
            if ae is not None:
                vst_engines = getattr(ae, '_vst_instrument_engines', {})
                running = vst_engines.get(tid)
                if running is not None and getattr(running, '_ok', False):
                    # Mark as borrowed — caller must NOT shutdown
                    running._borrowed = True
                    print(f"[BOUNCE] ★ Borrowed RUNNING VST engine for track={tid} "
                          f"(plugin={getattr(running, 'path', '?')})",
                          file=sys.stderr, flush=True)
                    # Warmup: process a few empty blocks to flush any stale state
                    try:
                        for _ in range(10):
                            running.pull(1024, int(sr))
                    except Exception:
                        pass
                    return running
                else:
                    print(f"[BOUNCE] No running VST engine for track={tid} in audio_engine "
                          f"(available: {list(vst_engines.keys())})",
                          file=sys.stderr, flush=True)
            else:
                print(f"[BOUNCE] No audio_engine_ref on ProjectService", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[BOUNCE] Borrow attempt failed: {e}", file=sys.stderr, flush=True)

        # ════════════════════════════════════════════════════════════════════
        # APPROACH 2: Create new offline instance (fallback)
        # ════════════════════════════════════════════════════════════════════
        print(f"[BOUNCE] Falling back to offline VST engine creation for track={tid}",
              file=sys.stderr, flush=True)
        chain = getattr(track, 'audio_fx_chain', None)
        if not isinstance(chain, dict):
            print(f"[BOUNCE] Track has no audio_fx_chain", file=sys.stderr, flush=True)
            return None
        devices = chain.get('devices') or []
        if not isinstance(devices, list):
            return None
        for dev_idx, dev in enumerate(devices):
            if not isinstance(dev, dict):
                continue
            if dev.get('enabled', True) is False:
                continue
            pid = str(dev.get('plugin_id') or dev.get('type') or '')
            is_vst2 = pid.startswith('ext.vst2:')
            is_vst3 = pid.startswith('ext.vst3:')
            if not (is_vst2 or is_vst3):
                continue
            params = dev.get('params', {}) if isinstance(dev.get('params', {}), dict) else {}
            vst_ref = pid.split(':', 1)[1] if ':' in pid else ''
            vst_ref = str(params.get('__ext_ref') or vst_ref)
            vst_plugin_name = str(params.get('__ext_plugin_name') or '')
            did = str(dev.get('id') or dev.get('device_id') or '')
            print(f"[BOUNCE] Offline fallback: creating engine for {vst_ref}",
                  file=sys.stderr, flush=True)
            try:
                try:
                    from pydaw.audio.rt_params import RTParamStore
                    rt = RTParamStore(default_smooth_ms=0.0)
                except Exception:
                    class _OfflineRT:
                        def __init__(self):
                            self._vals: dict = {}
                        def ensure(self, k, v):
                            self._vals.setdefault(str(k), float(v))
                        def get_smooth(self, k, d=0.0):
                            return float(self._vals.get(str(k), d))
                        def get_param(self, k, d=0.0):
                            return float(self._vals.get(str(k), d))
                        def set_smooth(self, k, v):
                            self._vals[str(k)] = float(v)
                        def set_param(self, k, v):
                            self._vals[str(k)] = float(v)
                    rt = _OfflineRT()
                engine = None
                if is_vst2:
                    from pydaw.audio.vst2_host import Vst2InstrumentEngine
                    engine = Vst2InstrumentEngine(
                        path=vst_ref, plugin_name=vst_plugin_name,
                        track_id=tid, device_id=did,
                        rt_params=rt, params=params,
                        sr=int(sr), max_frames=8192,
                    )
                else:
                    from pydaw.audio.vst3_host import Vst3InstrumentEngine
                    engine = Vst3InstrumentEngine(
                        path=vst_ref, plugin_name=vst_plugin_name,
                        track_id=tid, device_id=did,
                        rt_params=rt, params=params,
                        sr=int(sr), max_frames=8192,
                    )
                if not getattr(engine, '_ok', False):
                    print(f"[BOUNCE] Offline engine NOT OK: {getattr(engine, '_err', '?')}",
                          file=sys.stderr, flush=True)
                    try:
                        engine.shutdown()
                    except Exception:
                        pass
                    continue
                engine._borrowed = False
                # VST2: Suspend/Resume after state restore
                if is_vst2:
                    try:
                        plugin = getattr(engine, '_plugin', None)
                        if plugin is not None:
                            from pydaw.audio.vst2_host import effMainsChanged, effStartProcess
                            plugin._disp(effMainsChanged, 0, 0, None, 0.0)
                            plugin._disp(effMainsChanged, 0, 1, None, 0.0)
                            plugin._disp(effStartProcess, 0, 0, None, 0.0)
                    except Exception:
                        pass
                # Warmup
                try:
                    for _ in range(int(sr * 0.2 / 1024) + 1):
                        engine.pull(1024, int(sr))
                except Exception:
                    pass
                print(f"[BOUNCE] Offline engine created OK: {vst_ref}", file=sys.stderr, flush=True)
                return engine
            except Exception as e:
                import traceback
                print(f"[BOUNCE] Offline engine FAILED: {e}", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
        return None

    def _render_vst_notes_offline(self, engine: Any, midi_notes: list[Any], bpm: float, clip_length_beats: float, samplerate: int, _progress_dlg: Any = None) -> Any:
        """v0.0.20.427: Offline render MIDI notes through a VST engine with proper note_on/note_off.

        Fixes over v426:
        - Diagnostic logging (peak levels, event counts)
        - Proper block processing with events at exact frame positions
        """
        import sys
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None
        if engine is None:
            return None
        beats_per_second = float(bpm) / 60.0
        if beats_per_second <= 1e-9:
            return None
        total_frames = int(round(max(0.25, float(clip_length_beats)) / beats_per_second * int(samplerate)))
        if total_frames <= 0:
            return None
        # Build event list: (frame, type, pitch, velocity)  type: 0=note_on, 1=note_off
        events: list[tuple[int, int, int, int]] = []
        for n in (midi_notes or []):
            try:
                pitch = int(getattr(n, 'pitch', 60))
                start_beats = float(getattr(n, 'start_beats', 0.0) or 0.0)
                length_beats = float(getattr(n, 'length_beats', 0.25) or 0.25)
                velocity = int(getattr(n, 'velocity', 100) or 100)
                start_frame = max(0, int(round(start_beats / beats_per_second * int(samplerate))))
                end_frame = max(start_frame + 1, int(round((start_beats + length_beats) / beats_per_second * int(samplerate))))
                events.append((start_frame, 0, pitch, velocity))  # note_on
                events.append((end_frame, 1, pitch, 0))            # note_off
            except Exception:
                continue
        # Sort: by frame, then note_off before note_on at same frame
        events.sort(key=lambda x: (x[0], x[1]))
        note_on_count = sum(1 for e in events if e[1] == 0)
        print(f"[BOUNCE-RENDER] {note_on_count} note_on events, total_frames={total_frames}, "
              f"bpm={bpm}, clip_len={clip_length_beats} beats, sr={samplerate}",
              file=sys.stderr, flush=True)
        if note_on_count > 0:
            first_on = next(e for e in events if e[1] == 0)
            print(f"[BOUNCE-RENDER] First note_on: frame={first_on[0]} pitch={first_on[2]} vel={first_on[3]}",
                  file=sys.stderr, flush=True)
        # Render with 1 second tail for release
        tail_frames = int(samplerate)  # 1 second
        render_total = total_frames + tail_frames
        out = np.zeros((render_total, 2), dtype=np.float32)
        cursor = 0
        evt_idx = 0
        block = 1024
        peak_max = 0.0
        blocks_processed = 0
        # v0.0.20.586: Keep GUI alive during long offline renders.
        # Without this, Qt shows "main.py antwortet nicht" for clips > ~2 seconds.
        _qapp = None
        try:
            from PySide6.QtWidgets import QApplication
            _qapp = QApplication.instance()
        except Exception:
            pass

        while cursor < render_total:
            # Dispatch all events at or before current cursor (only within note region)
            while evt_idx < len(events) and events[evt_idx][0] <= cursor:
                _, etype, pitch, vel = events[evt_idx]
                try:
                    if etype == 0:
                        engine.note_on(int(pitch), int(vel))
                    else:
                        engine.note_off(int(pitch))
                except Exception as e:
                    print(f"[BOUNCE-RENDER] MIDI send error: {e}", file=sys.stderr, flush=True)
                evt_idx += 1
            # All notes off at end of note region
            if cursor >= total_frames and evt_idx >= len(events):
                try:
                    if hasattr(engine, 'all_notes_off'):
                        engine.all_notes_off()
                except Exception:
                    pass
                evt_idx = len(events) + 999  # prevent re-trigger
            take = min(block, render_total - cursor)
            try:
                chunk = engine.pull(int(take), int(samplerate))
            except Exception as e:
                if blocks_processed < 5:
                    print(f"[BOUNCE-RENDER] pull error: {e}", file=sys.stderr, flush=True)
                chunk = None
            if chunk is not None:
                try:
                    frames = int(min(int(take), int(chunk.shape[0])))
                    if frames > 0:
                        out[cursor:cursor + frames, :] += chunk[:frames, :2]
                        block_peak = float(np.max(np.abs(chunk[:frames, :])))
                        if block_peak > peak_max:
                            peak_max = block_peak
                except Exception:
                    pass
            blocks_processed += 1
            cursor += int(take)
            # v0.0.20.586: Pump Qt event loop every ~8 blocks to keep GUI alive.
            if _qapp is not None and (blocks_processed & 7) == 0:
                try:
                    if _progress_dlg is not None:
                        _progress_dlg.set_progress(
                            float(cursor) / max(1, render_total),
                            f"Rendering … {cursor * 100 // max(1, render_total)}%"
                        )
                    else:
                        _qapp.processEvents()
                except Exception:
                    pass
        print(f"[BOUNCE-RENDER] Done: {blocks_processed} blocks, peak={peak_max:.6f}, "
              f"{'AUDIO OK' if peak_max > 0.0001 else 'SILENT!'}",
              file=sys.stderr, flush=True)
        return out

    def _render_track_subset_offline(self, track: Any, clips: list[Any], *, render_start_beats: float, render_length_beats: float, include_fx: bool = True, _progress_dlg: Any = None) -> Any:
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None
        bpm = float(getattr(self.ctx.project, 'bpm', 120.0) or 120.0)
        sr = int(getattr(self.ctx.project, 'sample_rate', 48000) or 48000)
        total_frames = int(round(max(0.25, float(render_length_beats)) / max(1e-9, (bpm / 60.0)) * sr))
        if total_frames <= 0:
            return None
        out = np.zeros((int(total_frames), 2), dtype=np.float32)
        if track is None:
            return out
        plugin_type = str(getattr(track, 'plugin_type', '') or '')
        kind = str(getattr(track, 'kind', '') or '')
        if not plugin_type and kind == 'instrument' and getattr(track, 'sf2_path', None):
            plugin_type = 'sf2'
        # v0.0.20.585: Auto-detect plugin_type from instrument_state when empty.
        # Older projects or tracks created before consistent plugin_type assignment
        # may have instrument_state but no plugin_type set.
        if not plugin_type and kind == 'instrument':
            try:
                _ist = getattr(track, 'instrument_state', None) or {}
                if isinstance(_ist, dict):
                    _detect_map = {
                        'fusion': 'chrono.fusion',
                        'aeterna': 'chrono.aeterna',
                        'bach_orgel': 'chrono.bach_orgel',
                        'drum_machine': 'chrono.pro_drum_machine',
                        'sampler': 'chrono.pro_audio_sampler',
                    }
                    for _key, _ptype in _detect_map.items():
                        if _key in _ist:
                            plugin_type = _ptype
                            import sys as _sys
                            print(f"[BOUNCE] Auto-detected plugin_type={plugin_type!r} "
                                  f"from instrument_state key {_key!r}",
                                  file=_sys.stderr, flush=True)
                            break
            except Exception:
                pass
        audio_or_sf2 = []
        audio_or_sf2_notes: dict[str, list[Any]] = {}
        internal_midi = []
        try:
            from pydaw.audio.note_fx_chain import apply_note_fx_chain_to_notes
        except Exception:
            apply_note_fx_chain_to_notes = None
        for c in (clips or []):
            ck = str(getattr(c, 'kind', '') or '')
            if ck == 'audio':
                audio_or_sf2.append(c)
                continue
            if ck != 'midi':
                continue
            notes = list((getattr(self.ctx.project, 'midi_notes', {}) or {}).get(str(getattr(c, 'id', '')), []) or [])
            if apply_note_fx_chain_to_notes is not None:
                try:
                    notes = list(apply_note_fx_chain_to_notes(notes, getattr(track, 'note_fx_chain', None)) or notes)
                except Exception:
                    pass
            if plugin_type == 'sf2':
                audio_or_sf2.append(c)
                audio_or_sf2_notes[str(getattr(c, 'id', ''))] = notes
            else:
                internal_midi.append((c, notes))
        if audio_or_sf2:
            arr = self._render_arrangement_subset_offline(track, audio_or_sf2, audio_or_sf2_notes, float(render_start_beats), float(render_length_beats), int(sr))
            if arr is not None:
                try:
                    n = min(out.shape[0], arr.shape[0])
                    out[:n, :] += arr[:n, :2]
                except Exception:
                    pass
        if internal_midi and (kind == 'instrument' or self._track_has_vst_device(track)):
            import sys as _sys
            _ist_keys = []
            try:
                _ist = getattr(track, 'instrument_state', None) or {}
                if isinstance(_ist, dict):
                    _ist_keys = list(_ist.keys())
            except Exception:
                pass
            print(f"[BOUNCE] Track has {len(internal_midi)} MIDI clips to render "
                  f"(kind={kind!r}, plugin_type={plugin_type!r}, "
                  f"instrument_state_keys={_ist_keys})",
                  file=_sys.stderr, flush=True)
            engine = None
            try:
                if plugin_type in ('sampler', 'chrono.pro_audio_sampler'):
                    from pydaw.plugins.sampler.sampler_engine import ProSamplerEngine
                    engine = ProSamplerEngine(target_sr=int(sr))
                    ist = getattr(track, 'instrument_state', None) or {}
                    st = ist.get('sampler') if isinstance(ist, dict) else None
                    if isinstance(st, dict):
                        eng_st = st.get('engine') if isinstance(st.get('engine'), dict) else None
                        if isinstance(eng_st, dict):
                            try:
                                engine.import_state(eng_st)
                            except Exception:
                                pass
                        sample_path = ''
                        mid = str(st.get('sample_media_id') or '')
                        if mid:
                            sample_path = self._find_media_path_by_id(mid)
                        if not sample_path:
                            sample_path = str(st.get('sample_path') or '')
                        if not sample_path and isinstance(eng_st, dict):
                            sample_path = str(eng_st.get('sample_name') or '')
                        if sample_path and Path(sample_path).exists():
                            try:
                                engine.load_wav(str(sample_path))
                            except Exception:
                                pass
                elif plugin_type in ('drum_machine', 'chrono.pro_drum_machine'):
                    from pydaw.plugins.drum_machine.drum_engine import DrumMachineEngine
                    engine = DrumMachineEngine(target_sr=int(sr))
                    ist = getattr(track, 'instrument_state', None) or {}
                    st = ist.get('drum_machine') if isinstance(ist, dict) else None
                    if isinstance(st, dict):
                        try:
                            engine.import_state(st)
                        except Exception:
                            pass
                elif plugin_type in ('aeterna', 'chrono.aeterna'):
                    from pydaw.plugins.aeterna.aeterna_engine import AeternaEngine
                    engine = AeternaEngine(target_sr=int(sr))
                    ist = getattr(track, 'instrument_state', None) or {}
                    st = ist.get('aeterna') if isinstance(ist, dict) else None
                    if isinstance(st, dict):
                        try:
                            engine.import_state(st)
                        except Exception:
                            pass
                elif plugin_type in ('bach_orgel', 'chrono.bach_orgel'):
                    # Bach Orgel — uses aeterna engine with orgel preset
                    try:
                        from pydaw.plugins.aeterna.aeterna_engine import AeternaEngine
                        engine = AeternaEngine(target_sr=int(sr))
                        ist = getattr(track, 'instrument_state', None) or {}
                        st = ist.get('bach_orgel') or ist.get('aeterna')
                        if isinstance(st, dict):
                            engine.import_state(st)
                    except Exception:
                        engine = None
                # v0.0.20.585: Fusion semi-modular synthesizer offline render
                elif plugin_type in ('fusion', 'chrono.fusion'):
                    try:
                        from pydaw.plugins.fusion.fusion_engine import FusionEngine
                        engine = FusionEngine(target_sr=int(sr))
                        ist = getattr(track, 'instrument_state', None) or {}
                        st = ist.get('fusion') if isinstance(ist, dict) else None
                        if isinstance(st, dict):
                            # Restore module types
                            engine.set_oscillator(str(st.get('osc_type', 'sine')))
                            engine.set_filter(str(st.get('flt_type', 'svf')))
                            engine.set_envelope(str(st.get('env_type', 'adsr')))
                            # Restore knob values with same scaling as FusionWidget._on_knob_changed
                            for key, raw_val in (st.get('knobs', {}) or {}).items():
                                try:
                                    raw = float(raw_val)
                                    val = _fusion_knob_to_engine_value(str(key), raw)
                                    engine.set_param(str(key), float(val))
                                except Exception:
                                    pass
                            # Restore Scrawl/Wavetable state
                            try:
                                sp = st.get('scrawl_points', [])
                                if sp and isinstance(sp, list):
                                    engine._scrawl_points = [tuple(p) for p in sp]
                                    engine._scrawl_smooth = bool(st.get('scrawl_smooth', True))
                                    if str(st.get('osc_type', '')) == 'scrawl':
                                        for v in engine._voices:
                                            if hasattr(v.osc, 'set_points'):
                                                v.osc.set_points(engine._scrawl_points)
                                                v.osc.set_param('smooth', 1.0 if engine._scrawl_smooth else 0.0)
                            except Exception:
                                pass
                            try:
                                import os as _os
                                wt = str(st.get('wt_file_path', '') or '')
                                if wt and _os.path.isfile(wt):
                                    engine._wt_file_path = wt
                                    if str(st.get('osc_type', '')) == 'wavetable':
                                        for v in engine._voices:
                                            if hasattr(v.osc, 'load_file'):
                                                v.osc.load_file(wt)
                            except Exception:
                                pass
                        import sys as _sys
                        print(f"[BOUNCE] Fusion engine created (osc={st.get('osc_type', '?') if isinstance(st, dict) else '?'}, "
                              f"flt={st.get('flt_type', '?') if isinstance(st, dict) else '?'}, "
                              f"knobs={len(st.get('knobs', {})) if isinstance(st, dict) else 0})",
                              file=_sys.stderr, flush=True)
                    except Exception:
                        engine = None
            except Exception:
                engine = None
            # v0.0.20.585: Fallback — detect instrument from instrument_state
            # when plugin_type is empty/None (happens with older projects or
            # when the track was created before plugin_type was consistently set).
            if engine is None:
                try:
                    ist = getattr(track, 'instrument_state', None) or {}
                    if isinstance(ist, dict):
                        _detected = None
                        if 'fusion' in ist:
                            _detected = 'chrono.fusion'
                        elif 'aeterna' in ist:
                            _detected = 'chrono.aeterna'
                        elif 'bach_orgel' in ist:
                            _detected = 'chrono.bach_orgel'
                        elif 'drum_machine' in ist:
                            _detected = 'chrono.pro_drum_machine'
                        elif 'sampler' in ist:
                            _detected = 'chrono.pro_audio_sampler'
                        if _detected and _detected != plugin_type:
                            import sys as _sys
                            print(f"[BOUNCE] Fallback: detected {_detected!r} from instrument_state "
                                  f"(plugin_type was {plugin_type!r})",
                                  file=_sys.stderr, flush=True)
                            # Recurse into the same logic with corrected plugin_type
                            if _detected in ('chrono.fusion', 'fusion'):
                                from pydaw.plugins.fusion.fusion_engine import FusionEngine
                                engine = FusionEngine(target_sr=int(sr))
                                st = ist.get('fusion')
                                if isinstance(st, dict):
                                    engine.set_oscillator(str(st.get('osc_type', 'sine')))
                                    engine.set_filter(str(st.get('flt_type', 'svf')))
                                    engine.set_envelope(str(st.get('env_type', 'adsr')))
                                    for fkey, raw_val in (st.get('knobs', {}) or {}).items():
                                        try:
                                            engine.set_param(str(fkey), float(_fusion_knob_to_engine_value(str(fkey), float(raw_val))))
                                        except Exception:
                                            pass
                                    # Scrawl/Wavetable state
                                    try:
                                        sp = st.get('scrawl_points', [])
                                        if sp and isinstance(sp, list):
                                            engine._scrawl_points = [tuple(p) for p in sp]
                                            engine._scrawl_smooth = bool(st.get('scrawl_smooth', True))
                                            if str(st.get('osc_type', '')) == 'scrawl':
                                                for v in engine._voices:
                                                    if hasattr(v.osc, 'set_points'):
                                                        v.osc.set_points(engine._scrawl_points)
                                                        v.osc.set_param('smooth', 1.0 if engine._scrawl_smooth else 0.0)
                                    except Exception:
                                        pass
                                    try:
                                        import os as _os
                                        wt = str(st.get('wt_file_path', '') or '')
                                        if wt and _os.path.isfile(wt):
                                            engine._wt_file_path = wt
                                            if str(st.get('osc_type', '')) == 'wavetable':
                                                for v in engine._voices:
                                                    if hasattr(v.osc, 'load_file'):
                                                        v.osc.load_file(wt)
                                    except Exception:
                                        pass
                                    print(f"[BOUNCE] Fusion engine created via fallback "
                                          f"(osc={st.get('osc_type', '?')}, knobs={len(st.get('knobs', {}))})",
                                          file=_sys.stderr, flush=True)
                            elif _detected in ('chrono.aeterna', 'aeterna'):
                                from pydaw.plugins.aeterna.aeterna_engine import AeternaEngine
                                engine = AeternaEngine(target_sr=int(sr))
                                st = ist.get('aeterna')
                                if isinstance(st, dict):
                                    try:
                                        engine.import_state(st)
                                    except Exception:
                                        pass
                            elif _detected in ('chrono.bach_orgel', 'bach_orgel'):
                                from pydaw.plugins.aeterna.aeterna_engine import AeternaEngine
                                engine = AeternaEngine(target_sr=int(sr))
                                st = ist.get('bach_orgel') or ist.get('aeterna')
                                if isinstance(st, dict):
                                    try:
                                        engine.import_state(st)
                                    except Exception:
                                        pass
                except Exception:
                    pass
            # v0.0.20.428: VST2/VST3 instrument offline rendering
            if engine is None:
                import sys as _sys
                print(f"[BOUNCE] No internal engine (plugin_type={plugin_type!r}, kind={kind!r}), trying VST...",
                      file=_sys.stderr, flush=True)
                try:
                    engine = self._create_vst_instrument_engine_offline(track, int(sr))
                except Exception as _e:
                    import traceback
                    print(f"[BOUNCE] VST engine exception: {_e}", file=_sys.stderr, flush=True)
                    traceback.print_exc(file=_sys.stderr)
                    engine = None
                if engine is None:
                    print(f"[BOUNCE] No engine available — MIDI render will be SILENT",
                          file=_sys.stderr, flush=True)
            # v0.0.20.428: Use _render_vst_notes_offline for VST engines (note_on/note_off)
            # vs _render_engine_notes_offline for internal engines (trigger_note)
            is_vst_engine = engine is not None and hasattr(engine, 'note_on') and hasattr(engine, 'pull') and not hasattr(engine, 'trigger_note')
            if engine is not None:
                import sys as _sys
                _borrowed = getattr(engine, '_borrowed', False)
                print(f"[BOUNCE] Rendering {len(internal_midi)} MIDI clips, is_vst={is_vst_engine}, borrowed={_borrowed}",
                      file=_sys.stderr, flush=True)
                for c, notes in internal_midi:
                    try:
                        clip_start = float(getattr(c, 'start_beats', 0.0) or 0.0)
                        rel_start = max(0.0, clip_start - float(render_start_beats))
                        start_frame = int(round(rel_start / max(1e-9, (bpm / 60.0)) * sr))
                        clip_len = float(getattr(c, 'length_beats', 0.0) or 0.0)
                        if clip_len <= 0.0 and notes:
                            clip_len = max(float(getattr(n, 'start_beats', 0.0) or 0.0) + float(getattr(n, 'length_beats', 0.0) or 0.0) for n in notes)
                        clip_len = max(0.25, float(clip_len))
                        print(f"[BOUNCE] Clip: start={clip_start:.1f} rel={rel_start:.1f} len={clip_len:.1f} notes={len(notes)}",
                              file=_sys.stderr, flush=True)
                        if is_vst_engine:
                            buf = self._render_vst_notes_offline(engine, notes, float(bpm), float(clip_len), int(sr), _progress_dlg=_progress_dlg)
                        else:
                            buf = self._render_engine_notes_offline(engine, notes, float(bpm), float(clip_len), int(sr), _progress_dlg=_progress_dlg)
                        if buf is None:
                            print(f"[BOUNCE] Render returned None!", file=_sys.stderr, flush=True)
                            continue
                        end = min(out.shape[0], start_frame + int(buf.shape[0]))
                        if end > start_frame:
                            out[start_frame:end, :] += buf[:end-start_frame, :2]
                    except Exception as _ce:
                        print(f"[BOUNCE] Clip render error: {_ce}", file=_sys.stderr, flush=True)
                        import traceback
                        traceback.print_exc(file=_sys.stderr)
                        continue
                # Cleanup: all_notes_off + only shutdown if NOT borrowed
                try:
                    if hasattr(engine, 'all_notes_off'):
                        engine.all_notes_off()
                        # Flush the all_notes_off through a few blocks
                        for _ in range(5):
                            try:
                                engine.pull(1024, int(sr))
                            except Exception:
                                break
                except Exception:
                    pass
                if not getattr(engine, '_borrowed', False):
                    try:
                        engine.shutdown()
                    except Exception:
                        pass
        if include_fx:
            out = self._apply_track_fx_offline(track, out, int(sr))
        return out

    def _create_audio_clip_from_generated_file(self, track_id: str, path: str, start_beats: float, length_beats: float, label: str) -> str | None:
        p = Path(str(path))
        if not p.exists():
            return None
        load_path, media_id = self.import_audio_to_project(str(track_id), p, label=str(label))
        clip = Clip(kind='audio', track_id=str(track_id), label=str(label))
        clip.start_beats = max(0.0, float(start_beats))
        clip.length_beats = max(0.25, float(length_beats))
        clip.media_id = str(media_id) if media_id else None
        clip.source_path = str(load_path)
        clip.source_bpm = None
        self.ctx.project.clips.append(clip)
        try:
            self.select_clip(str(clip.id))
        except Exception:
            pass
        return str(clip.id)

    def _render_tracks_selection_to_wav(self, track_ids: list[str], *, clip_ids: list[str] | None = None, include_fx: bool = True, label: str = 'Bounce') -> tuple[str | None, float | None, float | None]:
        try:
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception:
            return (None, None, None)
        ids = [str(x) for x in (track_ids or []) if str(x).strip()]
        if not ids:
            return (None, None, None)
        proj = self.ctx.project
        clip_want = {str(x) for x in (clip_ids or []) if str(x).strip()} if clip_ids else None
        selected = []
        for c in (getattr(proj, 'clips', []) or []):
            tid = str(getattr(c, 'track_id', '') or '')
            if tid not in ids:
                continue
            if clip_want is not None and str(getattr(c, 'id', '') or '') not in clip_want:
                continue
            selected.append(c)
        if not selected:
            return (None, None, None)
        def _st(c):
            return float(getattr(c, 'start_beats', 0.0) or 0.0)
        def _en(c):
            return float(getattr(c, 'start_beats', 0.0) or 0.0) + float(getattr(c, 'length_beats', 0.0) or 0.0)
        render_start = min(_st(c) for c in selected)
        render_end = max(_en(c) for c in selected)
        if render_end <= render_start + 1e-9:
            return (None, None, None)
        render_length = float(render_end - render_start)
        sr = int(getattr(proj, 'sample_rate', 48000) or 48000)
        bpm = float(getattr(proj, 'bpm', 120.0) or 120.0)
        total_frames = int(round(render_length / max(1e-9, (bpm / 60.0)) * sr))
        if total_frames <= 0:
            return (None, None, None)
        # v0.0.20.690: Bounce Progress Dialog
        _bounce_dlg = None
        try:
            from pydaw.ui.bounce_progress import create_bounce_progress
            _bounce_dlg = create_bounce_progress(title=str(label or 'Bounce'))
        except Exception:
            pass
        mix = np.zeros((int(total_frames), 2), dtype=np.float32)
        for t_idx, tid in enumerate(ids):
            trk = next((t for t in (proj.tracks or []) if str(getattr(t, 'id', '')) == tid), None)
            if trk is None:
                continue
            tclips = [c for c in selected if str(getattr(c, 'track_id', '') or '') == tid]
            if not tclips:
                continue
            trk_name = str(getattr(trk, 'name', '') or f'Track {t_idx+1}')
            if _bounce_dlg is not None:
                _bounce_dlg.set_progress(
                    float(t_idx) / max(1, len(ids)),
                    f"Rendering: {trk_name}"
                )
            buf = self._render_track_subset_offline(trk, tclips, render_start_beats=float(render_start), render_length_beats=float(render_length), include_fx=bool(include_fx), _progress_dlg=_bounce_dlg)
            if buf is None:
                continue
            try:
                n = min(mix.shape[0], buf.shape[0])
                mix[:n, :] += buf[:n, :2]
            except Exception:
                pass
        try:
            mix = np.clip(mix, -1.0, 1.0).astype(np.float32, copy=False)
        except Exception:
            pass
        # v0.0.20.427: Diagnostic — peak level of final mix
        import sys as _sys
        try:
            _peak = float(np.max(np.abs(mix)))
            print(f"[BOUNCE-WAV] Final mix: frames={mix.shape[0]}, peak={_peak:.6f}, "
                  f"{'AUDIO OK' if _peak > 0.0001 else 'SILENT!'}",
                  file=_sys.stderr, flush=True)
        except Exception:
            pass
        if _bounce_dlg is not None:
            _bounce_dlg.set_progress(0.95, "Schreibe WAV …")
        media_dir = self.ctx.resolve_media_dir()
        try:
            media_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        # v0.0.20.586: Keep GUI alive before heavy WAV write
        try:
            from PySide6.QtWidgets import QApplication
            _qa = QApplication.instance()
            if _qa is not None:
                _qa.processEvents()
        except Exception:
            pass
        from pydaw.model.project import new_id
        safe = str(label or 'Bounce').strip().replace(' ', '_')
        out_path = media_dir / f"{safe}_{new_id('wav')}.wav"
        try:
            sf.write(str(out_path), mix, int(sr))
        except Exception:
            if _bounce_dlg is not None:
                try:
                    _bounce_dlg.close()
                except Exception:
                    pass
            return (None, None, None)
        if _bounce_dlg is not None:
            try:
                _bounce_dlg.finish("✓ Bounce fertig!")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(600, _bounce_dlg.close)
            except Exception:
                try:
                    _bounce_dlg.close()
                except Exception:
                    pass
        return (str(out_path), float(render_start), float(render_length))

    def bounce_tracks_to_new_audio_track(
        self,
        track_ids: list[str],
        *,
        include_fx: bool = True,
        disable_sources: bool = True,
        label: str = 'Freeze',
    ) -> str | None:
        ids = [str(x) for x in (track_ids or []) if str(x).strip()]
        if not ids:
            return None
        out_path, start_beats, length_beats = self._render_tracks_selection_to_wav(ids, include_fx=bool(include_fx), label=str(label))
        if not out_path or start_beats is None or length_beats is None:
            self.error.emit('Bounce/Freeze fehlgeschlagen.')
            return None
        bounce_name = str(label or 'Freeze').strip() or 'Freeze'
        trk = self._create_bounce_audio_track(f'{bounce_name} Audio')
        try:
            if getattr(trk, 'instrument_state', None) is None:
                trk.instrument_state = {}
            trk.instrument_state['freeze_proxy'] = {
                'source_track_ids': list(ids),
                'include_fx': bool(include_fx),
                'label': str(label or 'Freeze'),
            }
        except Exception:
            pass
        new_id_clip = self._create_audio_clip_from_generated_file(str(getattr(trk, 'id', '') or ''), str(out_path), float(start_beats), float(length_beats), f'{bounce_name} Audio')
        if not new_id_clip:
            return None
        clip = next((c for c in self.ctx.project.clips if str(getattr(c, 'id', '')) == str(new_id_clip)), None)
        if clip is not None:
            try:
                clip.length_beats = max(0.25, float(length_beats))
                clip.render_meta = {
                    'badges': ['FREEZE' if disable_sources else 'BOUNCE', '+FX' if include_fx else 'DRY'],
                    'sources': {'track_ids': list(ids)},
                    'render': {'kind': 'track_bounce', 'include_fx': bool(include_fx), 'start_beats': float(start_beats), 'length_beats': float(length_beats)},
                }
            except Exception:
                pass
        if disable_sources:
            for tid in ids:
                t = next((x for x in self.ctx.project.tracks if str(getattr(x, 'id', '')) == tid), None)
                if t is None:
                    continue
                try:
                    t.muted = True
                except Exception:
                    pass
                try:
                    if str(getattr(t, 'kind', '')) == 'instrument':
                        t.instrument_enabled = False
                except Exception:
                    pass
        self.status.emit(f"{label}: neue Audiospur erstellt")
        self._emit_updated()
        return str(new_id_clip)

    def restore_frozen_source_tracks(self, proxy_track_id: str, *, mute_proxy: bool = True) -> bool:
        tid = str(proxy_track_id or '').strip()
        if not tid:
            return False
        proxy = next((t for t in self.ctx.project.tracks if str(getattr(t, 'id', '')) == tid), None)
        if proxy is None:
            return False
        meta = getattr(proxy, 'instrument_state', None) or {}
        info = meta.get('freeze_proxy') if isinstance(meta, dict) else None
        if not isinstance(info, dict):
            return False
        ok = False
        for src_id in (info.get('source_track_ids') or []):
            t = next((x for x in self.ctx.project.tracks if str(getattr(x, 'id', '')) == str(src_id)), None)
            if t is None:
                continue
            try:
                t.muted = False
            except Exception:
                pass
            try:
                if str(getattr(t, 'kind', '')) == 'instrument':
                    t.instrument_enabled = True
            except Exception:
                pass
            ok = True
        if mute_proxy:
            try:
                proxy.muted = True
            except Exception:
                pass
        if ok:
            self.status.emit('Freeze-Quellspuren wieder aktiviert')
            self._emit_updated()
        return bool(ok)

    def bounce_selected_clips_to_new_audio_track(
        self,
        clip_ids: list[str],
        *,
        include_fx: bool = True,
        mute_sources: bool = False,
        label: str = 'Bounce in Place',
    ) -> str | None:
        ids = [str(x) for x in (clip_ids or []) if str(x).strip()]
        if not ids:
            return None
        clips = [c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) in set(ids)]
        if not clips:
            return None
        track_ids = {str(getattr(c, 'track_id', '') or '') for c in clips}
        if len(track_ids) != 1:
            self.error.emit('Bounce in Place braucht Clips von genau einer Spur.')
            return None
        src_track_id = next(iter(track_ids))
        out_path, start_beats, length_beats = self._render_tracks_selection_to_wav([src_track_id], clip_ids=ids, include_fx=bool(include_fx), label=str(label))
        if not out_path or start_beats is None or length_beats is None:
            self.error.emit('Bounce in Place fehlgeschlagen.')
            return None
        src_name = self._track_display_name(src_track_id)
        bounce_name = str(label or src_name or 'Bounce in Place').strip() or 'Bounce in Place'
        trk = self._create_bounce_audio_track(f'{src_name} Bounce')
        new_id_clip = self._create_audio_clip_from_generated_file(str(getattr(trk, 'id', '') or ''), str(out_path), float(start_beats), float(length_beats), f'{bounce_name} Audio')
        if not new_id_clip:
            return None
        clip = next((c for c in self.ctx.project.clips if str(getattr(c, 'id', '')) == str(new_id_clip)), None)
        if clip is not None:
            try:
                clip.length_beats = max(0.25, float(length_beats))
                clip.render_meta = {
                    'badges': ['BIP', '+FX' if include_fx else 'DRY'],
                    'sources': {'clip_ids': list(ids), 'track_id': str(src_track_id)},
                    'render': {'kind': 'clip_bounce', 'include_fx': bool(include_fx), 'start_beats': float(start_beats), 'length_beats': float(length_beats)},
                }
            except Exception:
                pass
        if mute_sources:
            for c in clips:
                try:
                    c.muted = True
                except Exception:
                    pass
        self.status.emit('Bounce in Place: neue Audiospur erstellt')
        self._emit_updated()
        return str(new_id_clip)

    def rerender_clip_from_meta(
        self,
        clip_id: str,
        *,
        replace_usages: bool = True,
        label_suffix: str = " ReRendered",
    ) -> str | None:
        """Ultra-Pro: Re-render a consolidated/bounced clip using its render_meta.

        Safety:
        - Creates a NEW clip.
        - Optionally replaces Clip-Launcher slot mappings that pointed to the *current* clip.
        - Does NOT delete the original clip.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return None
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return None
        try:
            rm = getattr(clip, 'render_meta', {})
        except Exception:
            rm = {}
        if not isinstance(rm, dict):
            return None
        render = rm.get('render', {}) if isinstance(rm.get('render', {}), dict) else {}
        sources = rm.get('sources', {}) if isinstance(rm.get('sources', {}), dict) else {}

        src_id = str(sources.get('source_clip_id', '') or '').strip()
        ev_ids = sources.get('event_ids', [])
        if not src_id or not isinstance(ev_ids, list) or not ev_ids:
            return None

        mode = str(render.get('mode', 'bar') or 'bar')
        handles = float(render.get('handles_beats', render.get('handles_beats', 0.0)) or 0.0)
        tail = float(render.get('tail_beats', 0.0) or 0.0)
        norm = bool(render.get('normalize', False))

        # IMPORTANT: do NOT replace launcher mappings for the *source* clip here.
        new_id = self.bounce_consolidate_audio_events_to_new_clip(
            src_id,
            [str(x) for x in ev_ids if str(x).strip()],
            replace_in_launcher=False,
            mode=str(mode),
            handles_beats=float(max(0.0, handles)),
            tail_beats=float(max(0.0, tail)),
            normalize=bool(norm),
            label_suffix=str(label_suffix),
        )
        if not new_id:
            return None

        # Align placement/usage with the current clip (track/start/launcher-only)
        try:
            newc = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == str(new_id)), None)
        except Exception:
            newc = None
        if newc is not None:
            try:
                newc.track_id = str(getattr(clip, 'track_id', '') or '')
                newc.start_beats = float(getattr(clip, 'start_beats', 0.0) or 0.0)
                newc.launcher_only = bool(getattr(clip, 'launcher_only', False))
                newc.group_id = str(getattr(clip, 'group_id', '') or '')
                # Keep label close to what user sees
                try:
                    newc.label = str(getattr(clip, 'label', 'Audio') or 'Audio') + str(label_suffix)
                except Exception:
                    pass
                # Add an extra badge so it's visible
                try:
                    if isinstance(getattr(newc, 'render_meta', None), dict):
                        bs = newc.render_meta.get('badges', [])
                        if isinstance(bs, list) and 'RERENDER' not in bs:
                            bs.append('RERENDER')
                            newc.render_meta['badges'] = bs
                except Exception:
                    pass
            except Exception:
                pass

        # Replace usages of CURRENT clip id in launcher mappings
        if bool(replace_usages):
            try:
                for k, v in list((proj.clip_launcher or {}).items()):
                    if str(v) == cid:
                        proj.clip_launcher[str(k)] = str(new_id)
            except Exception:
                pass

        try:
            self.select_clip(str(new_id))
        except Exception:
            pass

        self.status.emit('Re-rendered from sources')
        self._emit_updated()
        return str(new_id)


    def back_to_sources_from_meta(self, clip_id: str) -> str | None:
        """Ultra-Pro: Jump back to the source clip + select the original events.

        This sets a one-shot selection payload that the AudioEventEditor consumes
        on next refresh.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return None
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return None
        try:
            rm = getattr(clip, 'render_meta', {})
        except Exception:
            rm = {}
        if not isinstance(rm, dict):
            return None
        sources = rm.get('sources', {}) if isinstance(rm.get('sources', {}), dict) else {}
        src_id = str(sources.get('source_clip_id', '') or '').strip()
        ev_ids = sources.get('event_ids', [])
        if not src_id:
            return None
        if not isinstance(ev_ids, list):
            ev_ids = []

        try:
            setattr(proj, 'pending_event_select', {'clip_id': str(src_id), 'event_ids': [str(x) for x in ev_ids]})
        except Exception:
            pass

        try:
            self.select_clip(str(src_id))
        except Exception:
            return None

        self.status.emit('Back to sources')
        return str(src_id)

    def rerender_clip_in_place_from_meta(self, clip_id: str) -> bool:
        """Ultra-Ultra-Pro: Re-render a consolidated/bounced clip IN PLACE.

        - Keeps the SAME clip id (arranger placement + launcher mappings stay intact).
        - Does NOT delete anything (non-destructive).
        - Uses render_meta.sources + render_meta.render flags.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return False
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return False

        try:
            rm = getattr(clip, 'render_meta', {}) or {}
        except Exception:
            rm = {}
        if not isinstance(rm, dict):
            return False

        render = rm.get('render', {}) if isinstance(rm.get('render', {}), dict) else {}
        sources = rm.get('sources', {}) if isinstance(rm.get('sources', {}), dict) else {}

        src_id = str(sources.get('source_clip_id', '') or '').strip()
        ev_ids = sources.get('event_ids', [])

        # v0.0.20.174:
        # Allow "Re-render (in place)" even for normal audio clips that do NOT yet have render_meta.
        # In that case we treat the current clip as the source, derive a full-length event list,
        # and perform an initial render. This keeps the workflow discoverable and non-destructive.
        is_initial = False
        if (not src_id) or (not isinstance(ev_ids, list)) or (not ev_ids):
            is_initial = True
            src_id = cid
            try:
                self._ensure_audio_events(clip)
            except Exception:
                pass
            try:
                evs0 = list(getattr(clip, 'audio_events', []) or [])
                ev_ids = [str(getattr(e, 'id', '') or '').strip() for e in evs0]
                ev_ids = [x for x in ev_ids if x]
            except Exception:
                ev_ids = []
            if not ev_ids:
                return False

            # Defaults for first render (exact selection, no handles/tail)
            try:
                if not isinstance(render, dict):
                    render = {}
                render.setdefault('mode', 'trim')
                render.setdefault('handles_beats', 0.0)
                render.setdefault('tail_beats', 0.0)
                render.setdefault('normalize', False)
            except Exception:
                pass


        mode = str(render.get('mode', 'bar') or 'bar')
        handles = float(render.get('handles_beats', 0.0) or 0.0)
        tail = float(render.get('tail_beats', 0.0) or 0.0)
        norm = bool(render.get('normalize', False))

        # Keep what the user sees/edits on this clip (do NOT reset user params)
        keep_label = str(getattr(clip, 'label', 'Clip') or 'Clip')
        keep_track = str(getattr(clip, 'track_id', '') or '')
        keep_start = float(getattr(clip, 'start_beats', 0.0) or 0.0)
        keep_group = str(getattr(clip, 'group_id', '') or '')
        keep_launcher_only = bool(getattr(clip, 'launcher_only', False))

        # Snapshot current rendered state (so "Restore Sources" can be non-destructive and reversible)
        try:
            cur_state = {
                'source_path': str(getattr(clip, 'source_path', '') or ''),
                'media_id': str(getattr(clip, 'media_id', '') or ''),
                'offset_beats': float(getattr(clip, 'offset_beats', 0.0) or 0.0),
                'length_beats': float(getattr(clip, 'length_beats', 0.0) or 0.0),
            }
        except Exception:
            cur_state = {}

        # Render into a TEMP new clip, then swap its content into the current clip.
        tmp_id = self.bounce_consolidate_audio_events_to_new_clip(
            str(src_id),
            [str(x) for x in ev_ids if str(x).strip()],
            replace_in_launcher=False,
            select_new_clip=False,
            mode=str(mode),
            handles_beats=float(max(0.0, handles)),
            tail_beats=float(max(0.0, tail)),
            normalize=bool(norm),
            label_suffix=" ReRenderTmp",
        )
        if not tmp_id:
            try:
                self.status.emit('Re-render in place fehlgeschlagen')
            except Exception:
                pass
            return False

        tmp = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == str(tmp_id)), None)
        if tmp is None:
            return False

        # Swap "content" fields only (keep user params on the current clip)
        try:
            clip.media_id = getattr(tmp, 'media_id', None)
            clip.source_path = getattr(tmp, 'source_path', None)
            clip.source_bpm = getattr(tmp, 'source_bpm', None)
            clip.offset_beats = float(getattr(tmp, 'offset_beats', 0.0) or 0.0)
            clip.offset_seconds = float(getattr(tmp, 'offset_seconds', 0.0) or 0.0)
            clip.length_beats = float(getattr(tmp, 'length_beats', 0.0) or 0.0)

            clip.audio_events = list(getattr(tmp, 'audio_events', []) or [])
            clip.audio_slices = list(getattr(tmp, 'audio_slices', []) or [])
            clip.onsets = list(getattr(tmp, 'onsets', []) or [])
        except Exception:
            pass

        # Preserve placement/identity
        try:
            clip.label = keep_label
            clip.track_id = keep_track
            clip.start_beats = keep_start
            clip.group_id = keep_group
            clip.launcher_only = keep_launcher_only
        except Exception:
            pass

        # Clamp loop region to new length (keep user's loop if set; otherwise full)
        try:
            lb = float(getattr(clip, 'length_beats', 0.0) or 0.0)
        except Exception:
            lb = 0.0
        try:
            ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
            le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
        except Exception:
            ls, le = (0.0, 0.0)
        if lb <= 1e-6:
            lb = 4.0
        if le <= ls + 1e-9:
            ls, le = (0.0, float(lb))
        ls = max(0.0, min(float(ls), float(lb)))
        le = max(ls, min(float(le), float(lb)))
        try:
            clip.loop_start_beats = float(ls)
            clip.loop_end_beats = float(le)
        except Exception:
            pass

        # Adopt fresh render_meta from tmp, but keep reversible state snapshot
        try:
            new_rm = getattr(tmp, 'render_meta', {}) or {}
        except Exception:
            new_rm = {}
        if not isinstance(new_rm, dict):
            new_rm = {}

        try:
            # For normal re-render: snapshot previous rendered state so Restore Sources can be reversible.
            # For the *first* render of a normal clip (no meta yet), do NOT set rendered_state here,
            # because cur_state still represents the original sources. In that initial case,
            # restore_sources_in_place_from_meta() will snapshot the true rendered_state later.
            if (not bool(is_initial)) and (not isinstance(new_rm.get('rendered_state', None), dict)) and isinstance(cur_state, dict) and cur_state:
                new_rm['rendered_state'] = cur_state
            bs = new_rm.get('badges', [])
            if not isinstance(bs, list):
                bs = []
            if 'RERENDER_INPLACE' not in bs:
                bs.append('RERENDER_INPLACE')
            new_rm['badges'] = bs
            new_rm['active_state'] = 'rendered'
        except Exception:
            pass

        try:
            clip.render_meta = new_rm
        except Exception:
            pass

        # Remove temp clip object (keep audio media on disk; non-destructive)
        try:
            proj.clips = [c for c in (proj.clips or []) if str(getattr(c, 'id', '')) != str(tmp_id)]
        except Exception:
            try:
                (proj.clips or []).remove(tmp)
            except Exception:
                pass

        try:
            self.select_clip(str(cid))
        except Exception:
            pass

        try:
            self.status.emit('Re-rendered in place')
        except Exception:
            pass
        self._emit_updated()
        return True

    def restore_sources_in_place_from_meta(self, clip_id: str) -> bool:
        """Ultra-Ultra-Pro: Restore the original source events INTO the current clip (non-destructive).

        Behavior:
        - Keeps SAME clip id (arranger placement + launcher slot stay intact).
        - Restores clip.source_path + audio_events from render_meta.sources snapshot.
        - Keeps the previously rendered state inside render_meta['rendered_state'] (so you can re-render again).
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return False
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return False

        try:
            rm = getattr(clip, 'render_meta', {}) or {}
        except Exception:
            rm = {}
        if not isinstance(rm, dict):
            return False

        render = rm.get('render', {}) if isinstance(rm.get('render', {}), dict) else {}
        sources = rm.get('sources', {}) if isinstance(rm.get('sources', {}), dict) else {}
        src_id = str(sources.get('source_clip_id', '') or '').strip()

        # Determine source path and event snapshot
        src_path = str(sources.get('source_path', '') or '').strip()
        events_snap = sources.get('events', [])
        ev_ids = sources.get('event_ids', [])
        if not isinstance(ev_ids, list):
            ev_ids = []

        src_clip = None
        if src_id:
            src_clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == src_id), None)

        if not src_path and src_clip is not None:
            src_path = str(getattr(src_clip, 'source_path', '') or '').strip()

        if not src_path:
            return False

        # Snapshot current rendered state if missing
        try:
            if not isinstance(rm.get('rendered_state', None), dict):
                rm['rendered_state'] = {
                    'source_path': str(getattr(clip, 'source_path', '') or ''),
                    'media_id': str(getattr(clip, 'media_id', '') or ''),
                    'offset_beats': float(getattr(clip, 'offset_beats', 0.0) or 0.0),
                    'length_beats': float(getattr(clip, 'length_beats', 0.0) or 0.0),
                }
        except Exception:
            pass

        # Determine base start and clip length (from render_meta)
        try:
            base_start = float(render.get('base_start_beats', 0.0) or 0.0)
            base_end = float(render.get('base_end_beats', 0.0) or 0.0)
            tail = float(render.get('tail_beats', 0.0) or 0.0)
        except Exception:
            base_start, base_end, tail = (0.0, 0.0, 0.0)
        if base_end <= base_start + 1e-6:
            # fallback: derive from snapshot
            try:
                if isinstance(events_snap, list) and events_snap:
                    ss = [float((e or {}).get('start_beats', 0.0) or 0.0) for e in events_snap if isinstance(e, dict)]
                    ee = [float((e or {}).get('start_beats', 0.0) or 0.0) + float((e or {}).get('length_beats', 0.0) or 0.0) for e in events_snap if isinstance(e, dict)]
                    if ss and ee:
                        base_start = float(min(ss))
                        base_end = float(max(ee))
            except Exception:
                pass
        clip_len = float(max(0.25, (base_end - base_start) + max(0.0, float(tail or 0.0))))

        # Determine clip offset (prefer snapshot if present, else source clip current offset)
        try:
            src_off = float(sources.get('source_clip_offset_beats', None))
        except Exception:
            src_off = None
        if src_off is None:
            try:
                src_off = float(getattr(src_clip, 'offset_beats', 0.0) or 0.0) if src_clip is not None else 0.0
            except Exception:
                src_off = 0.0

        # Restore clip content
        try:
            clip.source_path = str(src_path)
        except Exception:
            pass
        try:
            # Try to keep media_id consistent with the source clip, if any
            if src_clip is not None and str(getattr(src_clip, 'source_path', '') or '').strip() == str(src_path):
                clip.media_id = getattr(src_clip, 'media_id', None)
                clip.source_bpm = getattr(src_clip, 'source_bpm', None)
        except Exception:
            pass

        try:
            clip.offset_beats = float(src_off or 0.0)
            clip.offset_seconds = 0.0
            clip.length_beats = float(clip_len)
        except Exception:
            pass

        # Build restored events in THIS clip timeline (relative to base_start)
        from pydaw.model.project import AudioEvent

        restored: List[AudioEvent] = []
        if isinstance(events_snap, list) and events_snap:
            for d in events_snap:
                if not isinstance(d, dict):
                    continue
                try:
                    sid = str(d.get('id', '') or '').strip()
                    st = float(d.get('start_beats', 0.0) or 0.0)
                    ln = float(d.get('length_beats', 0.0) or 0.0)
                    so = float(d.get('source_offset_beats', 0.0) or 0.0)
                    rv = bool(d.get('reversed', False))
                except Exception:
                    continue
                if ln <= 1e-9:
                    continue
                rel_start = float(st - float(base_start))
                if rel_start < 0.0:
                    rel_start = 0.0
                # Clamp inside clip length
                if rel_start > float(clip_len) - 1e-6:
                    continue
                if rel_start + ln > float(clip_len):
                    ln = max(0.0, float(clip_len) - rel_start)
                if ln <= 1e-9:
                    continue
                if sid:
                    restored.append(AudioEvent(id=sid, start_beats=rel_start, length_beats=ln, source_offset_beats=so, reversed=rv))
                else:
                    restored.append(AudioEvent(start_beats=rel_start, length_beats=ln, source_offset_beats=so, reversed=rv))
        else:
            # fallback: try fetch events by id from source clip
            try:
                if src_clip is not None:
                    self._ensure_audio_events(src_clip)
                    src_evs = list(getattr(src_clip, 'audio_events', []) or [])
                    want = set(str(x) for x in ev_ids if str(x).strip())
                    for e in src_evs:
                        if want and str(getattr(e, 'id', '')) not in want:
                            continue
                        st = float(getattr(e, 'start_beats', 0.0) or 0.0)
                        ln = float(getattr(e, 'length_beats', 0.0) or 0.0)
                        so = float(getattr(e, 'source_offset_beats', 0.0) or 0.0)
                        rv = bool(getattr(e, 'reversed', False))
                        rel_start = float(st - float(base_start))
                        if rel_start < 0.0:
                            rel_start = 0.0
                        if ln <= 1e-9:
                            continue
                        restored.append(AudioEvent(start_beats=rel_start, length_beats=ln, source_offset_beats=so, reversed=rv))
            except Exception:
                restored = []

        if not restored:
            return False
        restored.sort(key=lambda e: float(getattr(e, 'start_beats', 0.0) or 0.0))
        try:
            clip.audio_events = restored
        except Exception:
            pass

        try:
            self._sync_slices_from_events(clip)
        except Exception:
            pass

        # Loop defaults to full length after restore
        try:
            clip.loop_start_beats = 0.0
            clip.loop_end_beats = float(clip_len)
        except Exception:
            pass

        # Update badges/state
        try:
            bs = rm.get('badges', [])
            if not isinstance(bs, list):
                bs = []
            if 'RESTORED' not in bs:
                bs.append('RESTORED')
            rm['badges'] = bs
            rm['active_state'] = 'sources'
            clip.render_meta = rm
        except Exception:
            pass

        try:
            self.status.emit('Sources restored (non-destructive)')
        except Exception:
            pass
        self._emit_updated()
        return True

    def toggle_rendered_sources_in_place_from_meta(self, clip_id: str) -> bool:
        """Ultra-Ultra-Ultra: One-click toggle Rendered ↔ Sources.

        Safety rules:
        - Keeps same clip id.
        - Uses existing in-place functions, so it cannot break placement or launcher slots.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return False
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return False
        try:
            rm = getattr(clip, 'render_meta', {}) or {}
        except Exception:
            rm = {}
        state = str(rm.get('active_state', 'rendered') or 'rendered')
        if state == 'rendered':
            return bool(self.restore_sources_in_place_from_meta(cid))
        # From sources → rendered
        return bool(self.rerender_clip_in_place_from_meta(cid))

    def rebuild_original_clip_state_from_meta(self, clip_id: str) -> bool:
        """Restore original clip state (loop/automation/params) from render_meta.

        This is non-destructive: it only restores *metadata/state* (loop, automation, fades,
        etc.) and does not delete any audio files.
        """
        cid = str(clip_id or '').strip()
        if not cid:
            return False
        proj = self.ctx.project
        clip = next((c for c in (proj.clips or []) if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return False

        try:
            rm = getattr(clip, 'render_meta', {}) or {}
        except Exception:
            rm = {}
        if not isinstance(rm, dict):
            return False
        sources = rm.get('sources', {}) if isinstance(rm.get('sources', {}), dict) else {}
        st = sources.get('source_clip_state', {}) if isinstance(sources.get('source_clip_state', {}), dict) else {}
        if not isinstance(st, dict) or not st:
            return False

        # Apply only safe state fields.
        try:
            for k in ('loop_start_beats', 'loop_end_beats', 'fade_in_beats', 'fade_out_beats'):
                if k in st:
                    setattr(clip, k, float(st.get(k, 0.0) or 0.0))
        except Exception:
            pass
        try:
            if isinstance(st.get('clip_automation', None), dict):
                clip.clip_automation = dict(st.get('clip_automation', {}) or {})
        except Exception:
            pass
        try:
            if isinstance(st.get('stretch_markers', None), list):
                clip.stretch_markers = list(st.get('stretch_markers', []) or [])
        except Exception:
            pass

        # Badges
        try:
            bs = rm.get('badges', [])
            if not isinstance(bs, list):
                bs = []
            if 'REBUILT' not in bs:
                bs.append('REBUILT')
            rm['badges'] = bs
            clip.render_meta = rm
        except Exception:
            pass

        try:
            self.status.emit('Original clip state rebuilt')
        except Exception:
            pass
        self._emit_updated()
        return True

    def consolidate_audio_clips_bounce(
        self,
        clip_ids: List[str],
        *,
        snap_beats: float | None = None,
        snap_to_grid: bool = True,
        handles_beats: float = 0.0,
        tail_beats: float = 0.0,
        normalize: bool = False,
        delete_originals: bool = True,
        label: str = "Consolidated",
    ) -> str | None:
        """Bounce/Consolidate multiple *Arranger* audio clips into ONE new audio clip.

        Professional behavior + future-proofing:
        - Default (Ctrl+J): snap_to_grid=True (uses current grid) and bounces the time range.
        - Trim mode can call this with snap_to_grid=False (exact selection bounds).
        - handles_beats keeps edit handles in the rendered file without shifting playback
          (we preserve timing via new_clip.offset_beats).
        - tail_beats extends the resulting clip length and renders extra tail.

        Safety:
        - Originals can be deleted (MIDI-Join style) or kept (non-destructive).
        - Internal boundary fades are ignored so they won't be baked accidentally.
        """
        try:
            ids = [str(x) for x in (clip_ids or []) if str(x).strip()]
        except Exception:
            ids = []
        if len(ids) < 2:
            return None

        proj = self.ctx.project
        clips = [c for c in (proj.clips or []) if str(getattr(c, 'id', '')) in set(ids)]
        if len(clips) < 2:
            return None
        clips = [c for c in clips if str(getattr(c, 'kind', '')) == 'audio']
        if len(clips) < 2:
            return None

        # Same track
        track_ids = {str(getattr(c, 'track_id', '') or '') for c in clips}
        if len(track_ids) != 1:
            return None
        track_id = next(iter(track_ids))

        clips.sort(key=lambda c: float(getattr(c, 'start_beats', 0.0) or 0.0))

        def _st(c):
            return float(getattr(c, 'start_beats', 0.0) or 0.0)

        def _en(c):
            return float(getattr(c, 'start_beats', 0.0) or 0.0) + float(getattr(c, 'length_beats', 0.0) or 0.0)

        raw_start = min(_st(c) for c in clips)
        raw_end = max(_en(c) for c in clips)
        if raw_end <= raw_start + 1e-9:
            return None

        # Determine grid quantum
        q = None
        if snap_beats is not None:
            try:
                q = float(snap_beats)
            except Exception:
                q = None
        if q is None:
            try:
                q = float(self.snap_quantum_beats())
            except Exception:
                q = None

        # Base (playback) selection window
        base_start = float(raw_start)
        base_end = float(raw_end)
        if bool(snap_to_grid) and q and q > 1e-9:
            try:
                base_start = float(math.floor(float(raw_start) / float(q)) * float(q))
                base_end = float(math.ceil(float(raw_end) / float(q)) * float(q))
            except Exception:
                base_start = float(raw_start)
                base_end = float(raw_end)

        # Tail is part of the resulting clip length
        content_end = float(base_end) + max(0.0, float(tail_beats or 0.0))

        # Render window includes handles
        hb = max(0.0, float(handles_beats or 0.0))
        render_start = float(base_start) - float(hb)
        if render_start < 0.0:
            render_start = 0.0
        render_end = float(content_end) + float(hb)
        if render_end <= render_start + 1e-9:
            return None

        pre_handle = float(base_start) - float(render_start)
        clip_length_beats = float(max(0.25, float(content_end) - float(base_start)))
        render_length_beats = float(max(0.25, float(render_end) - float(render_start)))

        # Build a temporary minimal project for rendering only these clips
        try:
            from pydaw.model.project import Project, Track, Clip
            from pydaw.audio.arrangement_renderer import prepare_clips, ArrangementState
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception:
            return None

        tmp = Project(
            version=str(getattr(proj, 'version', '')),
            name=str(getattr(proj, 'name', '')),
            sample_rate=int(getattr(proj, 'sample_rate', 48000) or 48000),
            bpm=float(getattr(proj, 'bpm', 120.0) or 120.0),
            time_signature=str(getattr(proj, 'time_signature', '4/4') or '4/4'),
            snap_division=str(getattr(proj, 'snap_division', '1/16') or '1/16'),
        )

        # Minimal track (keep same id so renderer maps)
        tmp_track = Track(id=str(track_id), kind='audio', name='Audio Track')
        tmp.tracks = [tmp_track]

        # Copy clips with shifted start, and ignore internal fades (safe)
        first_id = str(getattr(clips[0], 'id', ''))
        last_id = str(getattr(clips[-1], 'id', ''))
        for c in clips:
            cc = Clip(kind='audio', track_id=str(track_id))
            for attr in (
                'length_beats','offset_beats','offset_seconds','label','media_id','source_path','source_bpm',
                'gain','pan','pitch','formant','stretch','reversed','muted',
                'fade_in_beats','fade_out_beats','clip_automation','stretch_markers'
            ):
                try:
                    setattr(cc, attr, getattr(c, attr))
                except Exception:
                    pass
            try:
                cc.start_beats = float(getattr(c, 'start_beats', 0.0) or 0.0) - float(render_start)
            except Exception:
                cc.start_beats = 0.0

            # Ignore internal boundary fades so they won't be baked accidentally
            try:
                if str(getattr(c, 'id', '')) != first_id:
                    cc.fade_in_beats = 0.0
                if str(getattr(c, 'id', '')) != last_id:
                    cc.fade_out_beats = 0.0
            except Exception:
                pass

            tmp.clips.append(cc)

        sr = int(getattr(tmp, 'sample_rate', 48000) or 48000)
        bpm = float(getattr(tmp, 'bpm', 120.0) or 120.0)
        beats_per_second = bpm / 60.0
        sppb = float(sr) / max(1e-9, beats_per_second)
        frames = int(round(float(render_length_beats) * float(sppb)))
        if frames <= 0:
            return None

        prepared, midi_events, _ = prepare_clips(tmp, int(sr))
        st = ArrangementState(prepared, int(sr), 0.0, float(bpm), False, 0.0, 0.0, midi_events=midi_events)
        try:
            audio = st.render(int(frames))
        except Exception:
            return None
        if audio is None:
            return None

        # Optional normalize
        if bool(normalize):
            try:
                peak = float(np.max(np.abs(audio))) if audio.size else 0.0
                if peak > 1e-9:
                    audio = audio * (0.99 / peak)
            except Exception:
                pass

        audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)

        # Write into media
        media_dir = self.ctx.resolve_media_dir()
        try:
            media_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        fname = f"{str(label).strip().replace(' ', '_')}_arr_{new_id('wav')}.wav"
        out_path = media_dir / fname
        try:
            sf.write(str(out_path), audio, int(sr))
        except Exception:
            return None

        # Register media
        try:
            load_path, media_id = self.import_audio_to_project(str(track_id), Path(out_path), label=str(label))
        except Exception:
            load_path, media_id = (str(out_path), '')

        # Create new clip in REAL project
        newc = Clip(kind='audio', track_id=str(track_id), label=str(label))
        newc.start_beats = float(base_start)
        newc.length_beats = float(clip_length_beats)
        newc.media_id = str(media_id) if media_id else None
        newc.source_path = str(load_path)
        newc.source_bpm = None

        # Keep timing: offset skips pre-handle audio
        newc.offset_beats = float(pre_handle)
        newc.offset_seconds = 0.0

        # baked-neutral
        newc.gain = 1.0
        newc.pan = 0.0
        newc.pitch = 0.0
        newc.formant = 0.0
        newc.stretch = 1.0
        newc.reversed = False
        newc.muted = False
        newc.fade_in_beats = 0.0
        newc.fade_out_beats = 0.0

        # --- Non-destructive render metadata ---
        try:
            badges = ['CONSOL']
            if hb > 1e-9:
                badges.append('+HANDLES')
            if float(tail_beats or 0.0) > 1e-9:
                badges.append('+TAIL')
            if bool(normalize):
                badges.append('NORM')
            newc.render_meta = {
                'badges': badges,
                'render': {
                    'kind': 'arranger_audio_bounce',
                    'snap_to_grid': bool(snap_to_grid),
                    'snap_beats': float(q or 0.0),
                    'base_start_beats': float(base_start),
                    'base_end_beats': float(base_end),
                    'tail_beats': float(max(0.0, float(tail_beats or 0.0))),
                    'handles_beats': float(hb),
                    'render_start_beats': float(render_start),
                    'render_end_beats': float(render_end),
                    'pre_handle_beats': float(pre_handle),
                    'clip_length_beats': float(clip_length_beats),
                    'render_length_beats': float(render_length_beats),
                    'normalize': bool(normalize),
                    'delete_originals': bool(delete_originals),
                },
                'sources': {
                    'clip_ids': [str(getattr(c, 'id', '')) for c in clips],
                    'clips': [
                        {
                            'id': str(getattr(c, 'id', '')),
                            'label': str(getattr(c, 'label', '') or ''),
                            'start_beats': float(getattr(c, 'start_beats', 0.0) or 0.0),
                            'length_beats': float(getattr(c, 'length_beats', 0.0) or 0.0),
                            'source_path': str(getattr(c, 'source_path', '') or ''),
                            'reversed': bool(getattr(c, 'reversed', False)),
                        }
                        for c in clips
                    ],
                },
            }
        except Exception:
            pass

        proj.clips.append(newc)

        if delete_originals:
            for c in clips:
                try:
                    self.delete_clip(str(getattr(c, 'id', '')))
                except Exception:
                    pass

        try:
            self.select_clip(str(newc.id))
        except Exception:
            pass

        self._emit_updated()
        return str(newc.id)

    def join_audio_events_to_new_clip(
        self,
        source_clip_id: str,
        event_ids: List[str],
        *,
        replace_in_launcher: bool = True,
        snap_to_bars: bool = True,
        label_suffix: str = " Joined",
    ) -> str | None:
        """Create a NEW audio clip from selected AudioEvents, preserving ALL selected events.

        Why this exists:
        - In Pro-DAWs, Ctrl+J is often used as a "Glue" / "Consolidate to Clip" workflow.
        - Users expect selected segments to become a *clip* (container), not a single bounced sample.
        - Our previous Ctrl+J wired to `consolidate_audio_events()` which can collapse N events → 1.

        Behavior (safe, non-destructive):
        - Does NOT modify or delete the source clip.
        - Creates a new clip spanning the selected range (optionally snapped to bars).
        - Copies selected AudioEvents into the new clip (new event ids), shifting them so the
          new clip starts at 0.
        - If the source clip is used in the Clip-Launcher and `replace_in_launcher=True`, the
          slot mapping(s) are updated to point to the new clip (source clip is kept).
        """
        src_id = str(source_clip_id or '').strip()
        if not src_id:
            return None

        try:
            wanted = [str(x) for x in (event_ids or []) if str(x).strip()]
        except Exception:
            wanted = []
        if not wanted:
            return None

        src = next((c for c in (self.ctx.project.clips or []) if str(getattr(c, 'id', '')) == src_id), None)
        if not src or str(getattr(src, 'kind', '')) != 'audio':
            return None

        # Ensure events exist
        try:
            self._ensure_audio_events(src)
        except Exception:
            pass
        try:
            evs = list(getattr(src, 'audio_events', []) or [])
        except Exception:
            evs = []
        if not evs:
            return None

        want_set = set(wanted)
        sel = [e for e in evs if str(getattr(e, 'id', '')) in want_set]
        if len(sel) < 2:
            # Joining to a "clip" makes only sense for multiple events.
            return None

        def _st(e: Any) -> float:
            return float(getattr(e, 'start_beats', 0.0) or 0.0)

        def _en(e: Any) -> float:
            return float(getattr(e, 'start_beats', 0.0) or 0.0) + float(getattr(e, 'length_beats', 0.0) or 0.0)

        min_start = min(_st(e) for e in sel)
        max_end = max(_en(e) for e in sel)

        # Snap selection window to bars (DAW-like): makes "2 Bar" clips deterministic.
        snap_start = float(min_start)
        snap_end = float(max_end)
        if snap_to_bars:
            try:
                ts = str(getattr(self.ctx.project, 'time_signature', '4/4') or '4/4')
                num = int(str(ts).split('/')[0]) if '/' in ts else 4
                beats_per_bar = max(1, int(num))
            except Exception:
                beats_per_bar = 4
            try:
                snap_start = float(math.floor(float(min_start) / float(beats_per_bar)) * float(beats_per_bar))
                snap_end = float(math.ceil(float(max_end) / float(beats_per_bar)) * float(beats_per_bar))
            except Exception:
                snap_start = float(min_start)
                snap_end = float(max_end)

        length = max(0.25, float(snap_end - snap_start))

        # Determine whether this clip lives in launcher (preferred for AudioEvent playback).
        try:
            launcher_keys = [k for (k, v) in (self.ctx.project.clip_launcher or {}).items() if str(v) == src_id]
        except Exception:
            launcher_keys = []
        in_launcher = bool(launcher_keys) or bool(getattr(src, 'launcher_only', False))

        # Build new clip (deep copy of clip-level settings; events filtered/shifted below)
        from pydaw.model.project import Clip, AudioEvent
        try:
            base_label = str(getattr(src, 'label', 'Clip') or 'Clip')
        except Exception:
            base_label = 'Clip'
        suf = str(label_suffix or ' Joined')
        new_label = base_label if base_label.endswith(suf) else (base_label + suf)

        newc = Clip(
            kind='audio',
            track_id=str(getattr(src, 'track_id', '') or self.ensure_audio_track()),
            start_beats=0.0,
            length_beats=float(length),
            label=str(new_label),
            media_id=getattr(src, 'media_id', None),
            source_path=getattr(src, 'source_path', None),
            source_bpm=getattr(src, 'source_bpm', None),
        )

        # Copy clip-level non-destructive params (safe)
        for attr in (
            'offset_beats', 'offset_seconds',
            'gain', 'pan', 'pitch', 'formant', 'stretch',
            'reversed', 'muted',
            'fade_in_beats', 'fade_out_beats',
            'launcher_start_quantize', 'launcher_alt_start_quantize',
            'launcher_playback_mode', 'launcher_alt_playback_mode',
            'launcher_release_action', 'launcher_alt_release_action',
            'launcher_q_on_loop', 'launcher_next_action', 'launcher_next_action_count',
            'launcher_shuffle', 'launcher_accent', 'launcher_seed', 'launcher_color',
        ):
            try:
                if hasattr(src, attr):
                    setattr(newc, attr, getattr(src, attr))
            except Exception:
                pass

        # Loop = full clip by default (2 Bar clip feels right immediately)
        try:
            newc.loop_start_beats = 0.0
            newc.loop_end_beats = float(length)
        except Exception:
            pass

        # Placement: launcher clips stay launcher_only; arranger clips become a region at the selection position.
        try:
            newc.launcher_only = bool(in_launcher)
        except Exception:
            pass
        if not in_launcher:
            try:
                # Place new clip at the selection's position in the Arranger.
                newc.start_beats = float(getattr(src, 'start_beats', 0.0) or 0.0) + float(snap_start)
            except Exception:
                newc.start_beats = 0.0

        # Copy selected events into new clip (preserve count)
        out_events: List[AudioEvent] = []
        for e in sel:
            try:
                s = float(getattr(e, 'start_beats', 0.0) or 0.0)
                l = float(getattr(e, 'length_beats', 0.0) or 0.0)
                o = float(getattr(e, 'source_offset_beats', 0.0) or 0.0)
                r = bool(getattr(e, 'reversed', False))
            except Exception:
                continue
            if l <= 1e-9:
                continue
            ns = float(s - float(snap_start))
            # clamp inside new clip bounds
            ns = max(0.0, min(ns, max(0.0, float(length) - float(l))))
            ne = AudioEvent(start_beats=float(ns), length_beats=float(l), source_offset_beats=float(o))
            try:
                ne.reversed = bool(r)
            except Exception:
                pass
            out_events.append(ne)

        if not out_events:
            return None
        out_events.sort(key=lambda x: float(getattr(x, 'start_beats', 0.0) or 0.0))
        newc.audio_events = out_events

        # Derive slices for legacy UI
        try:
            self._sync_slices_from_events(newc)
        except Exception:
            pass

        # Crop + shift clip automation to selection window (best-effort)
        try:
            src_auto = dict(getattr(src, 'clip_automation', {}) or {})
        except Exception:
            src_auto = {}
        out_auto: dict = {}
        for pname, pts in (src_auto or {}).items():
            try:
                out_pts = []
                for pt in (pts or []):
                    if not isinstance(pt, dict):
                        continue
                    b = float(pt.get('beat', 0.0) or 0.0)
                    if b < (snap_start - 1e-6) or b > (snap_end + 1e-6):
                        continue
                    out_pts.append({'beat': max(0.0, min(float(length), float(b - snap_start))), 'value': float(pt.get('value', 0.0) or 0.0)})
                if out_pts:
                    out_pts.sort(key=lambda x: float(x.get('beat', 0.0) or 0.0))
                    out_auto[str(pname)] = out_pts
            except Exception:
                continue
        newc.clip_automation = out_auto

        # Warp markers: crop + shift (best-effort)
        try:
            raw_markers = list(getattr(src, 'stretch_markers', []) or [])
        except Exception:
            raw_markers = []
        out_markers: list = []
        for mm in raw_markers:
            if not isinstance(mm, dict):
                continue
            try:
                src_b = float(mm.get('src', mm.get('beat', 0.0)) or 0.0)
                dst_b = float(mm.get('dst', mm.get('beat', src_b)) or 0.0)
            except Exception:
                continue
            if src_b < (snap_start - 1e-6) or src_b > (snap_end + 1e-6):
                continue
            out_markers.append({'src': float(src_b - snap_start), 'dst': float(dst_b - snap_start)})
        out_markers.sort(key=lambda x: float(x.get('src', 0.0) or 0.0))
        newc.stretch_markers = out_markers

        self.ctx.project.clips.append(newc)

        # If used in launcher: replace mapping so user immediately sees/uses the new clip.
        if in_launcher and replace_in_launcher and launcher_keys:
            for k in launcher_keys:
                try:
                    self.ctx.project.clip_launcher[str(k)] = str(newc.id)
                except Exception:
                    continue

        try:
            self.select_clip(str(newc.id))
        except Exception:
            pass
        try:
            self.status.emit(f"Clip erstellt aus {len(out_events)} Events ({length:0.2f} Beats)")
        except Exception:
            pass
        self._emit_updated()
        return str(newc.id)

    # --- Legacy wrappers (Phase 1 API) -----------------

    def add_audio_slice(self, clip_id: str, at_beats: float) -> None:
        """Legacy: Knife marker. Now implemented as AudioEvent split."""
        self.split_audio_event(clip_id, at_beats)

    def remove_audio_slice_near(self, clip_id: str, at_beats: float, *, tolerance_beats: float = 0.05) -> None:
        """Legacy: remove slice marker. Now implemented as AudioEvent merge."""
        self.merge_audio_events_near(clip_id, at_beats, tolerance_beats=tolerance_beats)
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

    def import_audio_to_project(self, track_id: str, path: Path, label: str = "") -> tuple:
        """Import an audio file into <project>/media/ and return (abs_path, media_id).

        This is the primary API for instrument plugins (Sampler, DrumMachine)
        to ensure samples are stored inside the project folder — Bitwig/Ableton-style.

        Returns:
            (str, str): (absolute_load_path, media_id)
        """
        p = Path(path)
        if not p.exists():
            return (str(p), "")
        try:
            item = fm_import_audio(p, self.ctx)
            return (str(item.path), str(item.id))
        except Exception as exc:
            log.warning("import_audio_to_project failed: %s", exc)
            return (str(p), "")

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
                        # Optional notation fields (backward compatible)
                        "accidental": int(getattr(n, "accidental", 0) or 0),
                        "tie_to_next": bool(getattr(n, "tie_to_next", False)),
                        # v0.0.20.196: per-note expressions (JSON-safe)
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

    # ---------- Note Expressions (v0.0.20.196 foundation) ----------

    def set_note_expression_points(
        self,
        clip_id: str,
        note_index: int,
        param: str,
        points: list[dict] | None,
        *,
        label: str = "Edit Note Expression",
    ) -> None:
        """Set per-note expression points (JSON-safe) with undo support.

        This is a foundation API for the upcoming Bitwig/Cubase-style
        expression editor UI.
        """
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
                # best-effort legacy fallback
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

        # Ensure model sees mutated list (same list instance, but we re-set to be explicit).
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
        self._cancel_pending_auto_undo_capture(sync_to_current=True)
        cmd = MidiNotesEditCommand(
            clip_id=str(clip_id),
            before=list(before or []),
            after=list(after or []),
            label=str(label or "Edit MIDI"),
            apply_snapshot=self._apply_midi_snapshot,
        )
        self.undo_stack.push(cmd, already_done=True)
        self._sync_auto_undo_baseline()
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
        if not self.undo_stack.can_undo():
            return
        self._auto_undo_restore_in_progress = True
        try:
            self._cancel_pending_auto_undo_capture(sync_to_current=False)
            self.undo_stack.undo()
            self._sync_auto_undo_baseline()
            self._emit_updated()
            self.project_changed.emit()
            self.undo_changed.emit()
        except Exception as e:
            print(f"Undo failed: {e}")
        finally:
            self._auto_undo_restore_in_progress = False

    def redo(self):
        """Führe Redo aus."""
        if not self.undo_stack.can_redo():
            return
        self._auto_undo_restore_in_progress = True
        try:
            self._cancel_pending_auto_undo_capture(sync_to_current=False)
            self.undo_stack.redo()
            self._sync_auto_undo_baseline()
            self._emit_updated()
            self.project_changed.emit()
            self.undo_changed.emit()
        except Exception as e:
            print(f"Redo failed: {e}")
        finally:
            self._auto_undo_restore_in_progress = False

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
