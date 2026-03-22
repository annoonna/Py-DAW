# -*- coding: utf-8 -*-
"""MidiManager (v0.0.20.x)

Ziel
----
Ein zentraler MIDI-Manager, der:
- verfügbare MIDI-Geräte erkennt (mido/python-rtmidi)
- eingehende MIDI Messages nicht-blockierend ins Qt-Eventloop forwardet
- Live-Monitoring + Recording in den aktiven MIDI-Clip (Transport-Sync)
- Live-Visualisierung (Ghost Notes) via Qt-Signale
- Panic / All Notes Off (No-Hang)

Hinweis:
Dieses Modul ist bewusst *MVP-sicher* gehalten:
- keine exklusiven Locks auf GUI-Daten aus dem MIDI-Thread
- Processing der MIDI-Messages im Qt-Thread via Queue+QTimer
"""

from __future__ import annotations

import threading
import time
import queue
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

try:
    import mido  # type: ignore
except Exception:  # noqa: BLE001
    mido = None  # type: ignore


@dataclass
class _ActiveNote:
    clip_id: str
    track_id: str
    channel: int
    pitch: int
    velocity: int
    start_global_beat: float
    start_clip_beat: float
    start_time: float


class MidiManager(QObject):
    # Backwards-compat status text
    message_received = pyqtSignal(str)
    # Raw message object (mido.Message) for services like MidiMappingService
    message_obj = pyqtSignal(object)

    # Live routing outputs (Pro-DAW-like triple output – at least for editors)
    live_note_on = pyqtSignal(str, str, int, int, int, float)   # clip_id, track_id, pitch, velocity, channel, start_clip_beats
    live_note_off = pyqtSignal(str, str, int, int)              # clip_id, track_id, pitch, channel

    # Panic / No-Hang
    panic = pyqtSignal(str)  # reason text

    # v0.0.20.406: Signal emitted when the set of connected inputs changes
    inputs_changed = pyqtSignal()

    def __init__(
        self,
        *,
        project_service=None,
        transport=None,
        status_cb: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self._status = status_cb or (lambda _m: None)

        self._project = project_service
        self._transport = transport

        # --- Live monitoring vs recording ---
        # Monitor/thru: hear notes on an armed track even without recording.
        # Recording: write notes into the active MIDI clip ONLY when enabled
        # (UI: Piano Roll "Record" toggle). This matches typical DAW behavior.
        self._midi_record_enabled: bool = False

        self._lock = threading.Lock()

        # v0.0.20.406: Multi-device support
        # Dict: port_name -> {"port": mido_port, "thread": Thread, "stop": bool}
        self._inputs: Dict[str, Dict] = {}

        # MIDI thread -> Qt thread queue
        self._queue: "queue.Queue[object]" = queue.Queue()
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(5)  # low-latency drain
        self._drain_timer.timeout.connect(self._drain_queue)
        self._drain_timer.start()

        # active notes for duration calculation (Note Lifetime)
        # key: (track_id, channel, pitch) -> stack[list]
        self._active_notes: Dict[Tuple[str, int, int], List[_ActiveNote]] = {}

        # Transport stop -> panic
        try:
            if self._transport is not None and hasattr(self._transport, "playing_changed"):
                self._transport.playing_changed.connect(self._on_transport_playing_changed)
        except Exception:
            pass

    # ---------------- device enumeration ----------------

    def list_inputs(self) -> List[str]:
        if mido is None:
            return []
        try:
            return list(mido.get_input_names())
        except Exception:  # noqa: BLE001
            return []

    def list_outputs(self) -> List[str]:
        if mido is None:
            return []
        try:
            return list(mido.get_output_names())
        except Exception:  # noqa: BLE001
            return []

    def current_input(self) -> str:
        """Backwards-compat: return first connected input name."""
        with self._lock:
            names = list(self._inputs.keys())
        return names[0] if names else ""

    def connected_inputs(self) -> List[str]:
        """Return list of all currently connected input port names (v0.0.20.406)."""
        with self._lock:
            return list(self._inputs.keys())

    # ---------------- live record toggle ----------------

    def set_record_enabled(self, enabled: bool) -> None:
        """Enable/disable MIDI recording into the active clip.

        When disabled, live MIDI still passes through (monitoring) but nothing
        is committed to the project/clip. UI hook: Piano Roll "Record" button.
        """
        self._midi_record_enabled = bool(enabled)
        try:
            self._status(
                "MIDI Record: ON (schreibt in Clip)" if self._midi_record_enabled
                else "MIDI Record: OFF (nur Monitoring)"
            )
        except Exception:
            pass

    def is_record_enabled(self) -> bool:
        return bool(self._midi_record_enabled)

    # ---------------- connect / disconnect ----------------

    def connect_input(self, name: str) -> bool:
        """Connect to a MIDI input port. Multiple ports can be connected simultaneously (v0.0.20.406)."""
        if mido is None:
            self._status("MIDI: mido nicht verfügbar (pip install mido python-rtmidi).")
            return False

        name = str(name)

        # Already connected?
        with self._lock:
            if name in self._inputs:
                self._status(f"MIDI: {name} ist bereits verbunden.")
                return True

        try:
            port = mido.open_input(str(name))
        except Exception as exc:  # noqa: BLE001
            self._status(f"MIDI: Input konnte nicht geöffnet werden: {exc}")
            return False

        entry = {"port": port, "thread": None, "stop": False}
        with self._lock:
            self._inputs[name] = entry

        self._status(f"MIDI: Input verbunden: {name}")
        self._start_reader_thread(name)
        try:
            self.inputs_changed.emit()
        except Exception:
            pass
        return True

    def disconnect_input(self, name: str = "") -> None:
        """Disconnect a specific input port, or ALL ports if name is empty (v0.0.20.406)."""
        if not name:
            with self._lock:
                names = list(self._inputs.keys())
            for n in names:
                self._disconnect_one(n)
            return
        self._disconnect_one(name)

    def _disconnect_one(self, name: str) -> None:
        """Disconnect and clean up a single MIDI input port."""
        with self._lock:
            entry = self._inputs.pop(name, None)

        if entry is None:
            return

        entry["stop"] = True
        port = entry.get("port")
        thread = entry.get("thread")

        # flush active notes (avoid hangs)
        try:
            self.panic_all(f"disconnect:{name}")
        except Exception:
            pass

        if port is not None:
            try:
                port.close()
            except Exception:
                pass

        if thread is not None:
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass

        self._status(f"MIDI: {name} getrennt.")
        try:
            self.inputs_changed.emit()
        except Exception:
            pass

    def shutdown(self) -> None:
        self.disconnect_input()

    # ---------------- panic / no hang ----------------

    def panic_all(self, reason: str = "panic") -> None:
        """Clear internal active-notes and notify listeners."""
        with self._lock:
            self._active_notes.clear()
        try:
            self.panic.emit(str(reason))
        except Exception:
            pass
        try:
            self.message_received.emit("MIDI: PANIC / All Notes Off")
        except Exception:
            pass

    def _on_transport_playing_changed(self, playing: bool) -> None:
        # When transport stops we want to avoid hanging notes.
        if not bool(playing):
            self.panic_all("transport_stop")

    # ---------------- internal threading ----------------

    def _start_reader_thread(self, name: str) -> None:
        with self._lock:
            entry = self._inputs.get(name)
            if entry is None:
                return
            if entry.get("thread") is not None and entry["thread"].is_alive():
                return
            t = threading.Thread(target=self._run_reader, args=(name,), daemon=True)
            entry["thread"] = t
        t.start()

    def _run_reader(self, name: str) -> None:
        """Poll one input port. Messages go into the shared queue."""
        while True:
            with self._lock:
                entry = self._inputs.get(name)
                if entry is None or entry.get("stop"):
                    return
                port = entry.get("port")
            if port is None:
                return

            try:
                for msg in port.iter_pending():
                    try:
                        self._queue.put((name, msg))  # v0.0.20.608: tag with source port
                    except Exception:
                        pass
            except Exception as exc:  # noqa: BLE001
                self._status(f"MIDI [{name}]: Fehler beim Lesen: {exc}")
                time.sleep(0.2)

            time.sleep(0.001)  # low latency

    # ---------------- Qt thread processing ----------------

    def _drain_queue(self) -> None:
        # Process many messages per tick to avoid lag.
        for _ in range(128):
            try:
                item = self._queue.get_nowait()
            except Exception:
                return
            try:
                # v0.0.20.608: items are (source_port, msg) tuples
                if isinstance(item, tuple) and len(item) == 2:
                    source_port, msg = item
                else:
                    source_port, msg = "", item  # backwards compat
                self._handle_message(msg, source_port=str(source_port or ""))
            except Exception:
                # never crash the GUI
                continue

    def _handle_message(self, msg, *, source_port: str = "") -> None:  # noqa: ANN001
        # broadcast raw message for other services (MIDI Learn, CC dispatch)
        try:
            self.message_obj.emit(msg)
        except Exception:
            pass

        # v0.0.20.414: Status text — notes always, CC throttled (every 80ms max)
        mtype = str(getattr(msg, "type", "") or "")
        if mtype in ("note_on", "note_off"):
            try:
                self.message_received.emit(f"MIDI: {mtype} {msg}")
            except Exception:
                pass
        elif mtype == "control_change":
            import time
            now = time.monotonic()
            if now - getattr(self, "_last_cc_status_t", 0.0) > 0.08:
                self._last_cc_status_t = now
                try:
                    self.message_received.emit(f"MIDI: {msg}")
                except Exception:
                    pass
        if not mtype:
            return

        # Note-on/off normalization
        if mtype == "note_on" and int(getattr(msg, "velocity", 0)) <= 0:
            mtype = "note_off"

        if mtype not in ("note_on", "note_off"):
            return

        pitch = int(getattr(msg, "note", 0))
        vel = int(getattr(msg, "velocity", 0))
        ch = int(getattr(msg, "channel", 0))

        # Determine routing target.
        # Monitoring should work with an armed track even if no clip is active.
        # Recording still requires an active MIDI clip (handled later).
        target = self._resolve_target(source_port=source_port, midi_channel=ch)
        if target is None:
            return
        clip_id, track_id, clip_start, clip_offset = target

        # Global beat from master clock
        gbeat = 0.0
        try:
            if self._transport is not None:
                gbeat = float(self._transport.get_beat())
        except Exception:
            gbeat = 0.0

        # Clip-relative position for record + editor ghost.
        clip_beat = float(gbeat - clip_start + clip_offset)
        if clip_beat < 0.0:
            clip_beat = 0.0

        if mtype == "note_on":
            self._on_note_on(clip_id, track_id, ch, pitch, vel, gbeat, clip_beat)
        else:
            self._on_note_off(clip_id, track_id, ch, pitch, gbeat)

    # ---------------- v0.0.20.608: MIDI Input Routing (Bitwig-Style) ----------------

    def _midi_input_accepts(self, track, source_port: str) -> bool:
        """Check if a track's midi_input setting accepts messages from source_port.

        Routing rules (matching Bitwig Studio behavior):
        - "No input"          → reject all MIDI
        - "All ins"           → accept from any hardware port
        - "Computer Keyboard" → accept only from virtual keyboard source
        - specific port name  → accept only from that exact port
        - "track:<id>"        → accept from internal track routing (future)
        - "" (empty/auto)     → instrument tracks = "All ins", others = "No input"
        """
        raw = str(getattr(track, "midi_input", "") or "")

        # Auto-detect default based on track type
        if not raw:
            kind = str(getattr(track, "kind", "") or "")
            plugin = str(getattr(track, "plugin_type", "") or "")
            sf2 = str(getattr(track, "sf2_path", "") or "")
            if kind == "instrument" or plugin or sf2:
                raw = "All ins"
            else:
                raw = "No input"

        if raw == "No input":
            return False
        if raw == "All ins":
            # Accept any hardware MIDI port (not virtual sources like computer_keyboard/touch_keyboard)
            return source_port not in ("computer_keyboard", "touch_keyboard", "osc")
        if raw == "Computer Keyboard":
            return source_port == "computer_keyboard"
        if raw == "Touch Keyboard":
            return source_port == "touch_keyboard"
        if raw == "OSC - OSC":
            return source_port == "osc"
        if raw.startswith("track:"):
            # Future: MIDI from another track (internal routing)
            return source_port.startswith("track:")
        # Specific port name — exact match
        return raw == source_port

    def _midi_channel_accepts(self, track, midi_channel: int) -> bool:
        """Check if a track's midi_channel_filter accepts this MIDI channel (v0.0.20.609).

        -1 (Omni) = accept all channels. 0-15 = accept only that channel.
        """
        filt = int(getattr(track, "midi_channel_filter", -1) or -1)
        if filt < 0:
            return True  # Omni — accept all
        return filt == int(midi_channel)

    def _resolve_target(self, *, source_port: str = "", midi_channel: int = -1) -> Optional[tuple[str, str, float, float]]:
        """Return (clip_id, track_id, clip_start_beats, clip_offset_beats) or None.

        v0.0.20.608: Bitwig-style MIDI input routing — only route to tracks
        whose midi_input setting matches the source port.
        v0.0.20.609: MIDI channel filter — only route to tracks accepting this channel.
        """
        ps = self._project
        if ps is None:
            return None

        # Which track is armed?
        try:
            tracks = list(getattr(ps.ctx.project, "tracks", []) or [])
        except Exception:
            tracks = []
        armed = [t for t in tracks if bool(getattr(t, "record_arm", False))]
        sel_tid = ""
        try:
            sel_tid = str(getattr(ps, "selected_track_id", "") or "")
        except Exception:
            sel_tid = ""

        # v0.0.20.608: Filter armed tracks by MIDI input routing
        if source_port:
            armed = [t for t in armed if self._midi_input_accepts(t, source_port)]

        # v0.0.20.609: Filter by MIDI channel
        if midi_channel >= 0:
            armed = [t for t in armed if self._midi_channel_accepts(t, midi_channel)]

        track = None
        if armed:
            # Prefer selected track if it is armed; else first armed.
            track = next((t for t in armed if str(getattr(t, "id", "")) == sel_tid), None) or armed[0]
        else:
            # No armed track -> do not record/route by default (Pro-DAW-like).
            return None

        track_id = str(getattr(track, "id", "") or "")
        if not track_id:
            return None

        # Active clip is optional for monitoring.
        try:
            clip_id = str(ps.active_clip_id() or "")
        except Exception:
            clip_id = ""

        if not clip_id:
            # Monitoring-only mode (no active clip)
            return ("", track_id, 0.0, 0.0)

        clip = None
        try:
            for c in list(getattr(ps.ctx.project, "clips", []) or []):
                if str(getattr(c, "id", "")) == clip_id:
                    clip = c
                    break
        except Exception:
            clip = None

        if clip is None:
            return ("", track_id, 0.0, 0.0)
        if str(getattr(clip, "kind", "")) != "midi":
            return ("", track_id, 0.0, 0.0)
        if str(getattr(clip, "track_id", "")) != track_id:
            return ("", track_id, 0.0, 0.0)

        try:
            clip_start = float(getattr(clip, "start_beats", 0.0))
        except Exception:
            clip_start = 0.0
        try:
            clip_offset = float(getattr(clip, "offset_beats", 0.0))
        except Exception:
            clip_offset = 0.0

        return (clip_id, track_id, clip_start, clip_offset)

    def _on_note_on(
        self,
        clip_id: str,
        track_id: str,
        channel: int,
        pitch: int,
        velocity: int,
        start_global_beat: float,
        start_clip_beat: float,
    ) -> None:
        key = (str(track_id), int(channel), int(pitch))
        an = _ActiveNote(
            clip_id=str(clip_id),
            track_id=str(track_id),
            channel=int(channel),
            pitch=int(pitch),
            velocity=int(max(0, min(127, velocity))),
            start_global_beat=float(start_global_beat),
            start_clip_beat=float(start_clip_beat),
            start_time=float(time.time()),
        )
        with self._lock:
            self._active_notes.setdefault(key, []).append(an)

        # Live ghost for editors
        try:
            self.live_note_on.emit(str(clip_id), str(track_id), int(pitch), int(velocity), int(channel), float(start_clip_beat))
        except Exception:
            pass

    def _on_note_off(
        self,
        clip_id: str,
        track_id: str,
        channel: int,
        pitch: int,
        end_global_beat: float,
    ) -> None:
        key = (str(track_id), int(channel), int(pitch))
        an: Optional[_ActiveNote] = None
        with self._lock:
            lst = self._active_notes.get(key, [])
            if lst:
                an = lst.pop(0)
            if not lst and key in self._active_notes:
                self._active_notes.pop(key, None)

        # Remove live ghost immediately (even if we can't record)
        try:
            self.live_note_off.emit(str(clip_id), str(track_id), int(pitch), int(channel))
        except Exception:
            pass

        if an is None:
            return

        # Duration calculation (Transport-Sync + Note Lifetime)
        dur_beats = 0.25
        try:
            playing = bool(getattr(self._transport, "playing", False)) if self._transport is not None else False
            if playing:
                dur_beats = float(end_global_beat) - float(an.start_global_beat)
            else:
                # fallback to wall-clock
                bpm = float(getattr(self._transport, "bpm", 120.0)) if self._transport is not None else 120.0
                dur_beats = (float(time.time()) - float(an.start_time)) * (float(bpm) / 60.0)
        except Exception:
            dur_beats = 0.25
        if dur_beats <= 0.0:
            dur_beats = 0.0625  # 1/16 minimum
        if dur_beats > 64.0:
            dur_beats = 64.0

        # If MIDI record is disabled, do NOT write into the clip.
        # Live monitoring is handled via live_note_on/off signals.
        if not bool(self._midi_record_enabled):
            return

        # Recording needs a valid active clip id.
        if not str(getattr(an, "clip_id", "") or ""):
            return

        # Commit note into the active clip (recording-ready)
        ps = self._project
        if ps is None:
            return

        cid = str(an.clip_id)
        start_b = float(an.start_clip_beat)

        # v0.0.20.605: Record Quantize — snap incoming note to grid
        try:
            clip_obj = next((c for c in ps.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
            if clip_obj:
                rq = str(getattr(clip_obj, 'launcher_record_quantize', 'Off') or 'Off')
                grid_map = {'1/16': 0.25, '1/8': 0.5, '1/4': 1.0, '1 Bar': 4.0}
                grid = grid_map.get(rq, 0.0)
                if grid > 0.0:
                    start_b = round(start_b / grid) * grid
        except Exception:
            pass

        # v0.0.20.605: Replace mode — delete overlapping notes before adding
        try:
            clip_obj = next((c for c in ps.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
            if clip_obj and str(getattr(clip_obj, 'launcher_record_mode', 'Overdub') or 'Overdub') == 'Replace':
                notes_list = ps.ctx.project.midi_notes.get(cid, [])
                if notes_list:
                    end_b = start_b + dur_beats
                    # Remove notes that overlap the new note's time range on same pitch
                    to_remove = []
                    for i, n in enumerate(notes_list):
                        try:
                            ns = float(n.start_beats if hasattr(n, 'start_beats') else n.get('start_beats', n.get('start', 0)))
                            nl = float(n.length_beats if hasattr(n, 'length_beats') else n.get('length_beats', n.get('length', 0)))
                            np_ = int(n.pitch if hasattr(n, 'pitch') else n.get('pitch', -1))
                            if np_ == int(an.pitch) and ns < end_b and (ns + nl) > start_b:
                                to_remove.append(i)
                        except Exception:
                            pass
                    for i in reversed(to_remove):
                        try:
                            notes_list.pop(i)
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            ps.add_midi_note(
                cid,
                pitch=int(an.pitch),
                start_beats=float(start_b),
                length_beats=float(dur_beats),
                velocity=int(an.velocity),
            )
        except Exception:
            return

    # ---------------- v0.0.20.608: Virtual MIDI sources ----------------

    def inject_message(self, msg, *, source: str = "computer_keyboard") -> None:
        """Inject a MIDI message from a virtual source (Computer Keyboard, OSC, Track routing).

        The source tag is used by _midi_input_accepts() to match against the
        track's midi_input setting. This allows the Computer Keyboard, OSC,
        and inter-track MIDI routing to participate in Bitwig-style input filtering.

        Usage from UI (e.g. QWERTY keyboard handler):
            midi_manager.inject_message(mido.Message('note_on', note=60, velocity=100),
                                        source='computer_keyboard')
        """
        try:
            self._queue.put((str(source or "computer_keyboard"), msg))
        except Exception:
            pass

    def forward_track_midi(self, source_track_id: str, msg) -> None:
        """Forward a MIDI message from one track to others (v0.0.20.609).

        Used by the audio engine to implement inter-track MIDI routing.
        When Track A has midi_input="track:<source_track_id>", it will
        receive messages forwarded through this method.

        Usage from engine:
            midi_manager.forward_track_midi("trk_abc123",
                mido.Message('note_on', note=60, velocity=100))
        """
        try:
            self._queue.put((f"track:{source_track_id}", msg))
        except Exception:
            pass
