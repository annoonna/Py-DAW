"""LauncherService (v0.0.11).

Coordinates Clip Launcher launches with TransportService for quantization.

v0.0.10:
- Pending queue; fire on playhead ticks
- Quantize: Off / 1 Beat / 1 Bar (assumed 4/4)

v0.0.11:
- Time-signature-aware bar quantize:
  - uses Project.time_signature (e.g. "4/4", "3/4", "6/8")
  - beat unit is quarter-note beats
  - beats_per_bar = numerator * (4 / denominator)
- Stop All can optionally reset playhead (parameter)
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List

from PyQt6.QtCore import QObject, pyqtSignal

from pydaw.services.project_service import ProjectService
from pydaw.services.transport_service import TransportService


@dataclass
class _PendingLaunch:
    at_beat: float
    kind: str  # "slot" | "scene"
    key: str   # slot_key or scene_index str
    quantize: str = "Off"
    fired: bool = False


class LauncherService(QObject):
    # UI: pending (quantized) launches for "queued" indicator
    pending_changed = pyqtSignal(object)  # list[dict{kind,key,at_beat}]

    def __init__(self, project: ProjectService, transport: TransportService):
        super().__init__()
        self.project = project
        self.transport = transport
        self._pending: List[_PendingLaunch] = []

        self.transport.playhead_changed.connect(self._on_playhead)

    # --- public API

    def pending_snapshot(self):
        """Return a snapshot of pending quantized launches (UI-only).

        Each entry: {kind: 'slot'|'scene', key: slot_key or scene_index str, at_beat: float, quantize: str}
        """
        out = []
        try:
            for p in (self._pending or []):
                if getattr(p, 'fired', False):
                    continue
                out.append({'kind': str(getattr(p, 'kind', '')), 'key': str(getattr(p, 'key', '')), 'at_beat': float(getattr(p, 'at_beat', 0.0) or 0.0), 'quantize': str(getattr(p, 'quantize', 'Off') or 'Off')})
        except Exception:
            return []
        return out

    def _emit_pending(self) -> None:
        try:
            self.pending_changed.emit(self.pending_snapshot())
        except Exception:
            pass

    def launch_slot(self, slot_key: str) -> None:
        # Resolve per-clip quantize (v0.0.20.147: Bitwig-Style per-clip override)
        q = self._get_effective_quantize(slot_key)
        # B: Launch startet den Transport automatisch (für quantized Start)
        try:
            if not bool(getattr(self.transport, "playing", False)):
                self.transport.set_playing(True)
                self.project.status.emit("Transport gestartet (Clip Launch)")
        except Exception:
            pass
        at = self._compute_fire_beat(q)
        if self._should_fire_now(q):
            getattr(self.project, 'cliplauncher_launch_immediate', getattr(self.project, 'cliplauncher_launch', None))(slot_key, at_beat=float(at)) if (hasattr(self.project,'cliplauncher_launch_immediate') or hasattr(self.project,'cliplauncher_launch')) else self.project.status.emit('Launch: API fehlt (cliplauncher).')
            self._emit_pending()
            return
        self._pending.append(_PendingLaunch(at_beat=at, kind="slot", key=str(slot_key), quantize=str(q)))
        self._emit_pending()
        self.project.status.emit(f"Launch queued: Slot @ beat {at:0.2f} (Quantize: {q})")

    def launch_scene(self, scene_index: int) -> None:
        q = getattr(self.project.ctx.project, "launcher_quantize", "1 Bar")
        # B: Launch startet den Transport automatisch (für quantized Start)
        try:
            if not bool(getattr(self.transport, "playing", False)):
                self.transport.set_playing(True)
                self.project.status.emit("Transport gestartet (Clip Launch)")
        except Exception:
            pass
        at = self._compute_fire_beat(q)
        if self._should_fire_now(q):
            getattr(self.project, 'cliplauncher_launch_scene_immediate', getattr(self.project, 'cliplauncher_launch_scene', None))(int(scene_index), at_beat=float(at)) if (hasattr(self.project,'cliplauncher_launch_scene_immediate') or hasattr(self.project,'cliplauncher_launch_scene')) else self.project.status.emit('Scene Launch: API fehlt (cliplauncher).')
            self._emit_pending()
            return
        self._pending.append(_PendingLaunch(at_beat=at, kind="scene", key=str(int(scene_index)), quantize=str(q)))
        self._emit_pending()
        self.project.status.emit(f"Scene queued: {scene_index} @ beat {at:0.2f} (Quantize: {q})")

    def stop_all(self, reset_playhead: bool = False) -> None:
        self._pending.clear()
        self._emit_pending()
        self.project.cliplauncher_stop_all()
        # User-Request: Stop All stoppt nur Clips (Transport bleibt aktiv)
        if reset_playhead:
            self.transport.reset()

    # --- internal

    def _should_fire_now(self, quantize: str) -> bool:
        # Off always immediate.
        if str(quantize) == "Off":
            return True
        return False

    def _get_effective_quantize(self, slot_key: str) -> str:
        """Resolve per-clip quantize override (v0.0.20.147 Bitwig-Style).

        If the clip has launcher_start_quantize != "Project", use the clip's setting.
        Otherwise fall back to the project-level launcher_quantize.
        """
        project_q = getattr(self.project.ctx.project, "launcher_quantize", "1 Bar")
        # Try to find the clip for this slot
        try:
            cid = str(getattr(self.project.ctx.project, "clip_launcher", {}).get(str(slot_key), "") or "")
            if cid:
                clip = next(
                    (c for c in (getattr(self.project.ctx.project, 'clips', []) or [])
                     if str(getattr(c, 'id', '')) == cid),
                    None,
                )
                if clip:
                    per_clip_q = str(getattr(clip, 'launcher_start_quantize', 'Project') or 'Project')
                    if per_clip_q and per_clip_q != "Project":
                        # Map Bitwig-style values to our internal format
                        q_map = {
                            "Off": "Off",
                            "8 Bar": "1 Bar",  # approximate: treat as 1 bar for now
                            "4 Bar": "1 Bar",
                            "2 Bar": "1 Bar",
                            "1 Bar": "1 Bar",
                            "1/2": "1 Beat",
                            "1/4": "1 Beat",
                            "1/8": "Off",
                            "1/16": "Off",
                        }
                        return q_map.get(per_clip_q, per_clip_q)
        except Exception:
            pass
        return str(project_q)

    def _beats_per_bar(self) -> float:
        ts = str(getattr(self.project.ctx.project, "time_signature", "4/4") or "4/4")
        try:
            num_s, den_s = ts.split("/", 1)
            num = max(1, int(num_s.strip()))
            den = max(1, int(den_s.strip()))
            return float(num) * (4.0 / float(den))
        except Exception:
            return 4.0

    def _compute_fire_beat(self, quantize: str) -> float:
        q = str(quantize)
        cur = float(self.transport.current_beat)
        if q == "Off":
            return cur
        if q == "1 Beat":
            return math.ceil(cur)
        if q == "1 Bar":
            bpb = self._beats_per_bar()
            return math.ceil(cur / bpb) * bpb
        # default to bar
        bpb = self._beats_per_bar()
        return math.ceil(cur / bpb) * bpb

    def _on_playhead(self, beat: float) -> None:
        if not self._pending:
            return
        eps = 1e-2
        for p in self._pending:
            if p.fired:
                continue
            if float(beat) + eps >= float(p.at_beat):
                p.fired = True
                if p.kind == "slot":
                    getattr(self.project, 'cliplauncher_launch_immediate', getattr(self.project, 'cliplauncher_launch', None))(p.key, at_beat=float(p.at_beat)) if (hasattr(self.project,'cliplauncher_launch_immediate') or hasattr(self.project,'cliplauncher_launch')) else self.project.status.emit('Launch: API fehlt (cliplauncher).')
                elif p.kind == "scene":
                    getattr(self.project, 'cliplauncher_launch_scene_immediate', getattr(self.project, 'cliplauncher_launch_scene', None))(int(p.key), at_beat=float(p.at_beat)) if (hasattr(self.project,'cliplauncher_launch_scene_immediate') or hasattr(self.project,'cliplauncher_launch_scene')) else self.project.status.emit('Scene Launch: API fehlt (cliplauncher).')
        self._pending = [p for p in self._pending if not p.fired]
        self._emit_pending()
