"""ClipLauncherPlaybackService (v0.0.19.7.57)

Pro-DAW-Style Clip Launcher Playback Grundgerüst:

- Event-Timeline: AudioClip.audio_events (Start/Offset/Duration in Beats)
- Sample-Accurate Looping: Clip-Loop in Samples (über globalen Transport-Playhead)
- Gapless Playback: Mixing erfolgt im Audio-Callback über Pull-Source (AudioEngine.register_pull_source)
- Quantized Start: LauncherService armt Clips für den nächsten Quantize-Punkt und gibt die Start-Beat-Position mit.

Hinweis:
Dieses Playback nutzt das bestehende AudioEngine-Backend (JACK via PipeWire oder sounddevice).
Für ein reines QtMultimedia/QAudioSink-Backend existiert ein separates Skeleton in
`pydaw/audio/qt_audio_sink_backend.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


@dataclass
class _MidiNoteEvent:
    """Scheduled MIDI note for ClipLauncher real-time dispatch."""
    start_beats: float   # clip-local beat position
    length_beats: float  # note duration in beats
    pitch: int           # MIDI pitch 0-127
    velocity: int        # MIDI velocity 0-127


@dataclass
class _Voice:
    slot_key: str
    clip_id: str
    start_beat: float
    # Cached model refs (best-effort)
    kind: str
    track_id: str
    file_path: str
    # Clip-local looping (beats)
    loop_start_beats: float
    loop_end_beats: float
    # Event timeline in beats
    events: List[Any]
    # Gains
    gain: float
    pan: float
    pitch: float
    formant: float
    stretch: float
    track_gain: float
    track_pan: float
    # v0.0.20.587: Real-time MIDI dispatch (non-SF2 instruments)
    is_midi_realtime: bool = False
    midi_notes: List[_MidiNoteEvent] = None  # type: ignore[assignment]
    # v0.0.20.600: Follow Actions (Ableton-style)
    next_action: str = 'Stopp'
    next_action_b: str = 'Stopp'
    next_action_probability: int = 100  # % for action A
    next_action_count: int = 1  # fire after N loops (0=never)
    loop_count: int = 0
    last_loop_beat: float = -1.0  # for detecting loop wraps


class ClipLauncherPlaybackService(QObject):
    active_slots_changed = Signal(list)  # slot_key list

    """Realtime ClipLauncher playback through AudioEngine pull-sources.

    The engine calls `pull(frames, sr)` inside the audio callback.
    We output a stereo float32 buffer. No allocations on the hot path beyond
    a small output buffer.
    """

    def __init__(self, project: Any, transport: Any, audio_engine: Any):
        super().__init__()
        self.project = project
        self.transport = transport
        self.audio_engine = audio_engine

        self._pull_name = "cliplauncher"
        self._registered = False

        # Active voices per slot
        self._voices: Dict[str, _Voice] = {}

        # Thread-safety: UI thread updates vs audio callback
        self._lock = threading.RLock()

        # Pending map for block-boundary swap (updated after edits)
        self._pending_voice_map: Optional[Dict[str, _Voice]] = None

        # Short crossfade at swap to avoid clicks
        self._swap_xfade_frames = 96

        # Cache decoded/resampled audio: (path, sr) -> np.ndarray (n,2) float32
        self._audio_cache: Dict[Tuple[str, int], Any] = {}

        # Fallback playhead counter when no external clock is available
        self._fallback_playhead_samples = 0
        self._fallback_sr = 48000

        # v0.0.20.587: Real-time MIDI dispatch tracking
        # track_id -> set of currently sounding pitches (for proper note_off on stop)
        self._midi_active_notes: Dict[str, set] = {}
        # Last processed beat per voice (for loop-wrap note_off detection)
        self._midi_last_beat: Dict[str, float] = {}

        # v0.0.20.600: Follow Actions (Ableton-style)
        # Queue: list of (slot_key, action) tuples — written by audio thread, consumed by GUI timer
        self._follow_action_queue: List[tuple] = []
        self._follow_timer = None
        try:
            from PySide6.QtCore import QTimer
            self._follow_timer = QTimer()
            self._follow_timer.setInterval(100)
            self._follow_timer.timeout.connect(self._process_follow_actions)
            self._follow_timer.start()
        except Exception:
            pass

        # v0.0.20.605: Crossfade — voices being faded out (list of (voice, remaining_samples))
        self._fading_voices: List[tuple] = []

        # Live-edit support: rebuild active voices on model changes (applied block-boundary)
        try:
            self.project.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

    # ---------------- public API used by ProjectService ----------------


    def active_slots(self) -> list[str]:
        # Return snapshot of currently active slot_keys
        try:
            with self._lock:
                return [str(k) for k in self._voices.keys()]
        except Exception:
            return []

    def _emit_active_slots_changed(self) -> None:
        try:
            self.active_slots_changed.emit(self.active_slots())
        except Exception:
            pass

    # v0.0.20.612: Dual-Clock Phase B — Runtime-Snapshot-Bridge
    def get_runtime_snapshot(self, slot_key: str) -> 'LauncherSlotRuntimeState | None':
        """Erzeuge einen GUI-sicheren Snapshot des aktiven Playback-Zustands.

        Der Snapshot wird unter Lock aus ``_voices`` kopiert und kann
        sicher im GUI-Thread verwendet werden.

        Args:
            slot_key: Launcher-Slot-Key (z.B. ``"scene:0:track:abc123"``).

        Returns:
            ``LauncherSlotRuntimeState`` oder None wenn der Slot nicht spielt.
        """
        try:
            from pydaw.services.editor_focus import LauncherSlotRuntimeState
            with self._lock:
                voice = self._voices.get(str(slot_key))
                if voice is None:
                    return None
                # Lokale Beat-Position berechnen
                cur_beat = 0.0
                try:
                    cur_beat = float(self.transport.current_beat)
                except Exception:
                    pass
                span = voice.loop_end_beats - voice.loop_start_beats
                local_beat = 0.0
                loop_count = 0
                if span > 1e-6:
                    elapsed = max(0.0, cur_beat - voice.start_beat)
                    local_beat = voice.loop_start_beats + (elapsed % span)
                    loop_count = int(elapsed / span) if span > 1e-6 else 0
                return LauncherSlotRuntimeState(
                    slot_key=str(voice.slot_key),
                    clip_id=str(voice.clip_id),
                    is_playing=True,
                    is_queued=False,
                    voice_start_beat=float(voice.start_beat),
                    local_beat=float(local_beat),
                    loop_start_beats=float(voice.loop_start_beats),
                    loop_end_beats=float(voice.loop_end_beats),
                    loop_count=int(loop_count),
                    track_id=str(voice.track_id),
                )
        except Exception:
            return None

    def get_all_runtime_snapshots(self) -> 'dict[str, LauncherSlotRuntimeState]':
        """Erzeuge Snapshots für alle aktiven Voices.

        Returns:
            Dict von slot_key -> LauncherSlotRuntimeState.
        """
        result = {}
        try:
            with self._lock:
                keys = list(self._voices.keys())
        except Exception:
            keys = []
        for k in keys:
            snap = self.get_runtime_snapshot(k)
            if snap is not None:
                result[k] = snap
        return result

    def stop_all(self) -> None:
        # v0.0.20.587: Send all_notes_off for MIDI voices before clearing
        self._all_midi_notes_off()
        with self._lock:
            self._voices.clear()
            self._pending_voice_map = None
            self._midi_active_notes.clear()
            self._midi_last_beat.clear()

        self._emit_active_slots_changed()

    def stop_slot(self, slot_key: str) -> None:
        # v0.0.20.587: Send note_off for active MIDI notes on this slot
        with self._lock:
            voice = self._voices.get(str(slot_key))
            if voice and voice.is_midi_realtime:
                self._stop_midi_voice(voice)
            self._voices.pop(str(slot_key), None)
            self._midi_last_beat.pop(str(slot_key), None)

        self._emit_active_slots_changed()

    def launch_slot(self, slot_key: str, *, at_beat: Optional[float] = None) -> None:
        """Start (or restart) the clip assigned to slot_key.

        v0.0.20.601: Legato Mode support:
        - "Trigger ab Start": new clip starts from beginning (default)
        - "Legato vom Clip": new clip starts at same loop position as old clip on same track
        - "Legato vom Projekt": new clip starts at global transport position within its loop

        at_beat: global transport beat where the clip should start.
        """
        key = str(slot_key)
        clip_id = str(getattr(self.project.ctx.project, "clip_launcher", {}).get(key, "") or "")
        if not clip_id:
            return

        # Resolve playback mode
        clip = next((c for c in (getattr(self.project.ctx.project, 'clips', []) or [])
                      if str(getattr(c, 'id', '')) == clip_id), None)
        playback_mode = str(getattr(clip, 'launcher_playback_mode', 'Trigger ab Start') or 'Trigger ab Start') if clip else 'Trigger ab Start'

        # Legato: find currently playing voice on the same track
        legato_offset_beats = 0.0
        if 'Legato' in playback_mode:
            try:
                parsed = self._parse_slot_key(key)
                if parsed:
                    _, track_id = parsed
                    with self._lock:
                        for sk, v in self._voices.items():
                            if str(v.track_id) == str(track_id):
                                # Calculate current position in old voice's loop
                                cur_beat = float(getattr(self.transport, 'current_beat', 0.0) or 0.0)
                                rel = cur_beat - v.start_beat
                                loop_span = v.loop_end_beats - v.loop_start_beats
                                if loop_span > 0.01 and rel > 0:
                                    pos_in_loop = v.loop_start_beats + (rel % loop_span)
                                    legato_offset_beats = pos_in_loop
                                break
            except Exception:
                legato_offset_beats = 0.0

        if 'Legato vom Projekt' in playback_mode:
            # Use global transport position within the new clip's loop
            try:
                if clip:
                    cur_beat = float(getattr(self.transport, 'current_beat', 0.0) or 0.0)
                    ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
                    le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
                    span = le - ls
                    if span > 0.01:
                        legato_offset_beats = ls + (cur_beat % span)
            except Exception:
                pass

        self._ensure_registered()

        # Stop other voices on same track (Bitwig: only one clip per track)
        # v0.0.20.605: Use crossfade when in Legato mode with crossfade_ms > 0
        crossfade_ms = float(getattr(clip, 'launcher_crossfade_ms', 0.0) or 0.0) if clip else 0.0
        try:
            parsed = self._parse_slot_key(key)
            if parsed:
                _, track_id = parsed
                with self._lock:
                    to_stop = [(sk, self._voices[sk]) for sk, v in self._voices.items()
                               if str(v.track_id) == str(track_id) and sk != key and sk in self._voices]
                for sk, old_voice in to_stop:
                    if crossfade_ms > 0 and 'Legato' in playback_mode:
                        # Move to fading list instead of hard stop
                        try:
                            sr = self._fallback_sr
                            fade_samps = max(64, int((crossfade_ms / 1000.0) * sr))
                            self._fading_voices.append((old_voice, fade_samps, fade_samps))
                            with self._lock:
                                self._voices.pop(sk, None)
                        except Exception:
                            self.stop_slot(sk)
                    else:
                        self.stop_slot(sk)
        except Exception:
            pass

        # Adjust start beat for legato
        effective_at = at_beat
        if legato_offset_beats > 0.01 and 'Legato' in playback_mode:
            # Start voice earlier so that the current position matches the legato offset
            cur = float(getattr(self.transport, 'current_beat', 0.0) or 0.0)
            effective_at = cur - legato_offset_beats

        self._start_voice(key, clip_id, at_beat=effective_at)
        self._emit_active_slots_changed()

    def launch_scene(self, scene_index: int, *, at_beat: Optional[float] = None) -> None:
        """Launch all slots in a scene row (scene_index is 1-based).

        v0.0.20.605: Scene crossfade support — old voices fade out over
        launcher_scene_crossfade_ms instead of hard-stopping.
        """
        try:
            tracks = list(getattr(self.project.ctx.project, "tracks", []) or [])
        except Exception:
            tracks = []

        # v0.0.20.605: Scene crossfade — move current voices to fading list
        xfade_ms = float(getattr(self.project.ctx.project, 'launcher_scene_crossfade_ms', 0.0) or 0.0)
        if xfade_ms > 0:
            try:
                sr = self._fallback_sr
                fade_samps = max(64, int((xfade_ms / 1000.0) * sr))
                with self._lock:
                    for sk, v in list(self._voices.items()):
                        self._fading_voices.append((v, fade_samps, fade_samps))
                    self._voices.clear()
            except Exception:
                pass

        row = int(scene_index)
        for trk in tracks:
            try:
                slot_key = f"scene:{row}:track:{trk.id}"
            except Exception:
                continue
            cid = str(getattr(self.project.ctx.project, "clip_launcher", {}).get(slot_key, "") or "")
            if cid:
                self._ensure_registered()
                self._start_voice(slot_key, cid, at_beat=at_beat)

        self._emit_active_slots_changed()

    # ---------------- internal ----------------

    def _ensure_registered(self) -> None:
        if self._registered:
            return
        try:
            # Make sure the engine has an output stream so our pull-source is audible.
            self.audio_engine.ensure_preview_output()
        except Exception:
            pass
        try:
            self.audio_engine.register_pull_source(self._pull_name, self.pull)
            self._registered = True
        except Exception:
            self._registered = False

    def _make_voice(self, slot_key: str, clip_id: str, *, at_beat: Optional[float]) -> Optional[_Voice]:
        """Build a voice snapshot from the current project model.

        This is used for live-edit block swaps (project_updated) and for starting voices.

        v0.0.20.587: Real-time MIDI dispatch for ALL instrument types.
        - SF2 instruments: render MIDI to WAV (offline, cached) → audio playback
        - Non-SF2 instruments (Sampler, Fusion, VST3, CLAP, Drum Machine):
          store MIDI notes → dispatch via SamplerRegistry in pull() callback
        """
        # Resolve clip + track
        proj = self.project.ctx.project
        clip = next((c for c in (getattr(proj, 'clips', []) or []) if str(getattr(c, 'id', '')) == str(clip_id)), None)
        if clip is None:
            return None
        trk = next((t for t in (getattr(proj, 'tracks', []) or []) if str(getattr(t, 'id', '')) == str(getattr(clip, 'track_id', ''))), None)

        kind = str(getattr(clip, 'kind', 'audio') or 'audio')

        # Determine instrument type for MIDI routing decision
        is_midi_realtime = False
        midi_notes_list: List[_MidiNoteEvent] = []
        file_path = str(getattr(clip, 'source_path', '') or '')

        if kind == 'midi':
            plugin_type = str(getattr(trk, 'plugin_type', '') or '') if trk else ''
            sf2_path = str(getattr(trk, 'sf2_path', '') or '') if trk else ''

            # Auto-detect plugin type from instrument_state (same logic as bounce)
            if not plugin_type and trk:
                inst_state = getattr(trk, 'instrument_state', {}) or {}
                if 'fusion' in inst_state:
                    plugin_type = 'chrono.fusion'
                elif sf2_path:
                    plugin_type = 'sf2'

            # Decision: SF2 → render to WAV, everything else → real-time MIDI
            if plugin_type == 'sf2' and sf2_path:
                file_path = self._render_midi_clip_to_wav(clip, trk)
            else:
                # Real-time MIDI path: store notes, dispatch in pull()
                is_midi_realtime = True
                file_path = '__midi_realtime__'  # sentinel, no WAV needed
                midi_notes_list = self._extract_midi_notes(clip)

        if not file_path:
            return None

        loop_start = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
        loop_end = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
        if loop_end <= loop_start + 1e-6:
            length = float(getattr(clip, 'length_beats', 4.0) or 4.0)
            loop_start = 0.0
            loop_end = max(0.25, length)

        events = list(getattr(clip, 'audio_events', []) or [])
        if not events and not is_midi_realtime:
            class _E:
                start_beats = 0.0
                length_beats = float(loop_end - loop_start)
                source_offset_beats = float(getattr(clip, 'offset_beats', 0.0) or 0.0)
            events = [_E()]
        try:
            events.sort(key=lambda e: float(getattr(e, 'start_beats', 0.0) or 0.0))
        except Exception:
            pass

        clip_gain = float(getattr(clip, 'gain', 1.0) or 1.0)
        clip_pan = float(getattr(clip, 'pan', 0.0) or 0.0)
        clip_pitch = float(getattr(clip, 'pitch', 0.0) or 0.0)
        clip_formant = float(getattr(clip, 'formant', 0.0) or 0.0)
        clip_stretch = float(getattr(clip, 'stretch', 1.0) or 1.0)
        tr_gain = float(getattr(trk, 'volume', 1.0) or 1.0) if trk is not None else 1.0
        tr_pan = float(getattr(trk, 'pan', 0.0) or 0.0) if trk is not None else 0.0

        start_beat = float(at_beat) if at_beat is not None else float(getattr(self.transport, 'current_beat', 0.0) or 0.0)

        return _Voice(
            slot_key=str(slot_key),
            clip_id=str(clip_id),
            start_beat=float(start_beat),
            kind=kind,
            track_id=str(getattr(clip, 'track_id', '') or ''),
            file_path=str(file_path),
            loop_start_beats=float(loop_start),
            loop_end_beats=float(loop_end),
            events=events,
            gain=float(clip_gain),
            pan=float(clip_pan),
            pitch=float(clip_pitch),
            formant=float(clip_formant),
            stretch=float(clip_stretch),
            track_gain=float(tr_gain),
            track_pan=float(tr_pan),
            is_midi_realtime=bool(is_midi_realtime),
            midi_notes=midi_notes_list if is_midi_realtime else None,
            # v0.0.20.600: Follow Actions
            next_action=str(getattr(clip, 'launcher_next_action', 'Stopp') or 'Stopp'),
            next_action_b=str(getattr(clip, 'launcher_next_action_b', 'Stopp') or 'Stopp'),
            next_action_probability=max(0, min(100, int(getattr(clip, 'launcher_next_action_probability', 100) or 100))),
            next_action_count=max(0, int(getattr(clip, 'launcher_next_action_count', 1) or 1)),
        )

    def _extract_midi_notes(self, clip: Any) -> List[_MidiNoteEvent]:
        """Extract MIDI notes from a clip into lightweight _MidiNoteEvent list.

        Supports both MidiNote objects and dict formats.
        Sorted by start_beats for efficient scheduling.
        """
        result: List[_MidiNoteEvent] = []
        try:
            proj = self.project.ctx.project
            cid = str(getattr(clip, 'id', '') or '')
            notes_map = getattr(proj, 'midi_notes', {}) or {}
            raw_notes = notes_map.get(cid, []) or []

            for n in raw_notes:
                try:
                    if isinstance(n, dict):
                        sb = float(n.get('start_beats', n.get('start', 0.0)) or 0.0)
                        lb = float(n.get('length_beats', n.get('length', 0.25)) or 0.25)
                        pitch = int(n.get('pitch', 60) or 60)
                        vel = int(n.get('velocity', 100) or 100)
                    else:
                        sb = float(getattr(n, 'start_beats', getattr(n, 'start', 0.0)) or 0.0)
                        lb = float(getattr(n, 'length_beats', getattr(n, 'length', 0.25)) or 0.25)
                        pitch = int(getattr(n, 'pitch', 60) or 60)
                        vel = int(getattr(n, 'velocity', 100) or 100)
                    result.append(_MidiNoteEvent(
                        start_beats=sb,
                        length_beats=max(0.01, lb),
                        pitch=max(0, min(127, pitch)),
                        velocity=max(1, min(127, vel)),
                    ))
                except Exception:
                    continue

            result.sort(key=lambda e: e.start_beats)
        except Exception:
            pass
        return result


    def _start_voice(self, slot_key: str, clip_id: str, *, at_beat: Optional[float]) -> None:
        voice = self._make_voice(str(slot_key), str(clip_id), at_beat=at_beat)
        if voice is None:
            return
        with self._lock:
            self._voices[str(slot_key)] = voice


    def _render_midi_clip_to_wav(self, clip: Any, track: Any) -> str:
        """Best-effort MIDI->WAV render to make ClipLauncher playable for MIDI."""
        try:
            from pydaw.audio.midi_render import RenderKey, ensure_rendered_wav, midi_content_hash
        except Exception:
            return ""
        try:
            sf2_path = str(getattr(track, "sf2_path", "") or "") if track is not None else ""
            if not sf2_path:
                return ""
            proj = self.project.ctx.project
            bpm = float(getattr(proj, "bpm", getattr(proj, "tempo_bpm", 120.0)) or 120.0)
            notes_map = getattr(proj, "midi_notes", {}) or {}
            notes = list(notes_map.get(str(getattr(clip, "id", "")), []) or [])
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
                clip_id=str(getattr(clip, "id", "")),
                sf2_path=str(sf2_path),
                sf2_bank=int(getattr(track, "sf2_bank", 0) or 0),
                sf2_preset=int(getattr(track, "sf2_preset", 0) or 0),
                bpm=float(bpm),
                samplerate=int(48000),
                clip_length_beats=float(clip_len_beats),
                content_hash=str(content_hash),
            )
            wav_path = ensure_rendered_wav(
                key=key,
                midi_notes=notes,
                clip_start_beats=float(getattr(clip, "start_beats", 0.0) or 0.0),
                clip_length_beats=float(clip_len_beats),
            )
            return wav_path.as_posix() if wav_path else ""
        except Exception:
            return ""


    def _on_project_updated(self) -> None:
        """Schedule a block-boundary voice rebuild for live edits.

        We keep slot start times, but refresh loop bounds, events and gains/pan.
        The actual swap happens in the audio callback with a tiny crossfade.
        """
        try:
            with self._lock:
                if not self._voices:
                    return
                current = dict(self._voices)
        except Exception:
            return

        rebuilt: Dict[str, _Voice] = {}
        for slot_key, v in current.items():
            # Preserve the existing start_beat so timing stays stable
            voice = self._make_voice(slot_key, v.clip_id, at_beat=v.start_beat)
            if voice is not None:
                rebuilt[slot_key] = voice

        with self._lock:
            self._pending_voice_map = rebuilt

    # ---------------- v0.0.20.587: Real-time MIDI dispatch ----------------

    def _get_sampler_registry(self) -> Optional[Any]:
        """Get SamplerRegistry from AudioEngine (GIL-safe, no lock needed)."""
        try:
            return getattr(self.audio_engine, '_sampler_registry', None)
        except Exception:
            return None

    def _dispatch_midi_for_voice(self, v: _Voice, g_samp: int, frames: int, sr: int, sppb: float, *, rt=None, any_solo: bool = False) -> None:
        """Dispatch MIDI note_on/note_off events for a realtime MIDI voice.

        This is called from the audio callback (pull). It schedules note events
        to the SamplerRegistry based on the current playhead position within
        the clip's loop region.

        Design goals (Bitwig/Ableton parity):
        - Loop-aware: notes wrap correctly at loop boundaries
        - Polyphonic: multiple notes can overlap
        - Clean note_off: all active notes get note_off at loop wrap point
        - Mute/Solo aware: respect track mute/solo state
        """
        tid = str(v.track_id or '')
        if not tid:
            return

        # Respect mute/solo
        try:
            if rt is not None:
                if bool(getattr(rt, 'is_track_muted')(tid)):
                    # Muted: send all_notes_off if we have active notes
                    self._stop_midi_voice(v)
                    return
                if bool(any_solo) and not bool(getattr(rt, 'is_track_solo')(tid)):
                    self._stop_midi_voice(v)
                    return
        except Exception:
            pass

        reg = self._get_sampler_registry()
        if reg is None:
            return

        notes = v.midi_notes
        if not notes:
            return

        # Calculate current beat position relative to voice start
        start_samp = int(round(float(v.start_beat) * sppb))
        rel_samp_begin = g_samp - start_samp
        rel_samp_end = rel_samp_begin + frames

        if rel_samp_end <= 0:
            return  # not started yet

        # Loop parameters in samples
        loop_s = int(round(float(v.loop_start_beats) * sppb))
        loop_e = int(round(float(v.loop_end_beats) * sppb))
        if loop_e <= loop_s:
            return
        loop_span = max(1, loop_e - loop_s)

        # Convert sample range to beats (clip-local, loop-wrapped)
        # We process in beats for note comparison
        if sppb < 1e-6:
            return

        # Effective sample start (clamp to >= 0)
        eff_start = max(0, rel_samp_begin)
        eff_end = rel_samp_end

        # Current position in loop (samples, then beats)
        local_samp = loop_s + (eff_start % loop_span)
        cur_beat = float(local_samp) / sppb

        # End position in loop
        local_samp_end = loop_s + (eff_end % loop_span)
        end_beat = float(local_samp_end) / sppb

        # Block length in beats
        block_beats = float(frames) / sppb

        # Detect loop wrap within this block
        wrapped = (eff_end - eff_start) > 0 and ((eff_start % loop_span) + (eff_end - eff_start)) > loop_span

        # Get or create active notes set for this track
        active = self._midi_active_notes.setdefault(tid, set())

        # On loop wrap: send note_off for all active notes, then re-trigger
        if wrapped:
            for pitch in list(active):
                try:
                    reg.note_off(tid, pitch=pitch)
                except Exception:
                    pass
            active.clear()

        # Determine which notes should be sounding in this block
        # Note: we use clip-local beat positions within the loop region
        loop_start_b = float(v.loop_start_beats)
        loop_end_b = float(v.loop_end_beats)

        if wrapped:
            # Two segments: [cur_beat, loop_end_b) and [loop_start_b, end_beat)
            segments = [
                (cur_beat, loop_end_b),
                (loop_start_b, end_beat),
            ]
        else:
            if cur_beat <= end_beat:
                segments = [(cur_beat, end_beat)]
            else:
                # wrap case via beat comparison
                segments = [(cur_beat, loop_end_b), (loop_start_b, end_beat)]

        for seg_start, seg_end in segments:
            if seg_end <= seg_start:
                continue
            for n in notes:
                n_start = n.start_beats
                n_end = n.start_beats + n.length_beats

                # Note starts within this segment?
                if seg_start <= n_start < seg_end:
                    if n.pitch not in active:
                        try:
                            reg.note_on(tid, n.pitch, n.velocity)
                            active.add(n.pitch)
                        except Exception:
                            pass

                # Note ends within this segment?
                if seg_start < n_end <= seg_end:
                    if n.pitch in active:
                        try:
                            reg.note_off(tid, pitch=n.pitch)
                            active.discard(n.pitch)
                        except Exception:
                            pass

    def _stop_midi_voice(self, v: _Voice) -> None:
        """Send note_off for all active MIDI notes on a voice's track."""
        tid = str(v.track_id or '')
        if not tid:
            return
        reg = self._get_sampler_registry()
        if reg is None:
            return
        active = self._midi_active_notes.get(tid, set())
        for pitch in list(active):
            try:
                reg.note_off(tid, pitch=pitch)
            except Exception:
                pass
        active.clear()

    def _all_midi_notes_off(self) -> None:
        """Send all_notes_off for all tracked MIDI voices (panic/stop_all)."""
        reg = self._get_sampler_registry()
        if reg is None:
            return
        try:
            for tid, active in list(self._midi_active_notes.items()):
                for pitch in list(active):
                    try:
                        reg.note_off(tid, pitch=pitch)
                    except Exception:
                        pass
                active.clear()
            # Belt-and-suspenders: global panic
            try:
                reg.all_notes_off()
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- v0.0.20.600: Follow Actions (GUI timer) ----------------

    def _process_follow_actions(self) -> None:
        """Process queued follow actions (runs on GUI timer, NOT audio thread).

        Actions: Stopp, Nächster Clip, Vorheriger Clip, Erster Clip,
                 Letzter Clip, Zufällig, Gegenüberliegend
        """
        if not self._follow_action_queue:
            return

        # Drain queue (atomic: swap + clear)
        queue = list(self._follow_action_queue)
        self._follow_action_queue.clear()

        for slot_key, action in queue:
            try:
                self._execute_follow_action(str(slot_key), str(action))
            except Exception:
                pass

    def _execute_follow_action(self, slot_key: str, action: str) -> None:
        """Resolve and execute a single follow action.

        Action strings match the Inspector combobox (German):
        Stopp, Nächsten abspielen, Vorherigen abspielen, Ersten abspielen,
        Letzten abspielen, Zufälligen abspielen, Anderen abspielen, Round-robin
        """
        parsed = self._parse_slot_key(slot_key)
        if not parsed:
            return
        scene_idx, track_id = parsed

        if action == 'Stopp' or not action:
            self.stop_slot(slot_key)
            self._emit_active_slots_changed()
            return

        # Find all filled slots for this track
        proj = self.project.ctx.project
        cl = getattr(proj, 'clip_launcher', {}) or {}
        track_slots = []
        for s in range(1, 65):
            k = f"scene:{s}:track:{track_id}"
            cid = str(cl.get(k, '') or '')
            if cid:
                track_slots.append((s, k, cid))

        if not track_slots:
            self.stop_slot(slot_key)
            self._emit_active_slots_changed()
            return

        cur_idx = -1
        for i, (s, k, _) in enumerate(track_slots):
            if k == slot_key:
                cur_idx = i
                break

        target_key = ''
        import random as _rnd

        if action == 'Nächsten abspielen':
            nxt = (cur_idx + 1) % len(track_slots) if cur_idx >= 0 else 0
            target_key = track_slots[nxt][1]
        elif action == 'Vorherigen abspielen':
            prv = (cur_idx - 1) % len(track_slots) if cur_idx >= 0 else 0
            target_key = track_slots[prv][1]
        elif action == 'Ersten abspielen' or action == 'Ersten im aktuellen Block abspielen':
            target_key = track_slots[0][1]
        elif action == 'Letzten abspielen' or action == 'Letzten im aktuellen Block abspielen':
            target_key = track_slots[-1][1]
        elif action in ('Zufälligen abspielen', 'Zufälligen im aktuellen Block abspielen'):
            others = [t for i, t in enumerate(track_slots) if i != cur_idx]
            if others:
                target_key = _rnd.choice(others)[1]
            elif track_slots:
                target_key = track_slots[0][1]
        elif action == 'Anderen abspielen':
            others = [t for i, t in enumerate(track_slots) if i != cur_idx]
            if others:
                target_key = _rnd.choice(others)[1]
        elif action == 'Round-robin':
            nxt = (cur_idx + 1) % len(track_slots) if cur_idx >= 0 else 0
            target_key = track_slots[nxt][1]

        if target_key and target_key != slot_key:
            # v0.0.20.604: Random Variation — if target clip has alt-clips, pick one randomly
            target_key = self._maybe_pick_variation(target_key)
            self.stop_slot(slot_key)
            self.launch_slot(target_key)
            self._emit_active_slots_changed()
        elif not target_key:
            self.stop_slot(slot_key)
            self._emit_active_slots_changed()

    def _maybe_pick_variation(self, slot_key: str) -> str:
        """v0.0.20.604: If the clip has alt-clips (variations), randomly pick one.

        Returns the (possibly modified) slot_key. If the main clip is picked,
        returns the original. If a variation is picked, swaps it into the slot.
        """
        try:
            cid = str(getattr(self.project.ctx.project, 'clip_launcher', {}).get(str(slot_key), '') or '')
            if not cid:
                return slot_key
            clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
            if clip is None:
                return slot_key
            alts = getattr(clip, 'launcher_alt_clips', None)
            if not alts:
                return slot_key
            # Pool = main clip + all variations
            import random as _rnd
            pool = [cid] + [str(a) for a in alts if str(a)]
            chosen = _rnd.choice(pool)
            if chosen != cid:
                # Swap the slot to point to the variation
                self.project.ctx.project.clip_launcher[str(slot_key)] = str(chosen)
                # v0.0.20.605: Morph — blend MIDI parameters between old and new
                self._morph_variation_notes(cid, chosen)
        except Exception:
            pass
        return slot_key

    def _morph_variation_notes(self, from_cid: str, to_cid: str, amount: float = 0.3) -> None:
        """v0.0.20.605: Morph MIDI parameters between two clip variations.

        Blends velocity/timing by `amount` (0.0 = pure target, 1.0 = pure source).
        Default 0.3 = subtle influence from the previous clip, making each
        variation slightly different. This is a genuine innovation — no other
        DAW morphs between clip variations automatically.
        """
        try:
            midi_notes = getattr(self.project.ctx.project, 'midi_notes', {})
            from_notes = midi_notes.get(str(from_cid), [])
            to_notes = midi_notes.get(str(to_cid), [])
            if not from_notes or not to_notes:
                return

            import random as _rnd
            amt = max(0.0, min(1.0, float(amount)))

            # Build pitch→velocity map from source clip
            src_vel = {}
            for n in from_notes:
                try:
                    p = int(n.pitch if hasattr(n, 'pitch') else n.get('pitch', 60))
                    v = int(n.velocity if hasattr(n, 'velocity') else n.get('velocity', 100))
                    src_vel[p] = v
                except Exception:
                    continue

            # Apply morph: blend target velocities toward source
            for n in to_notes:
                try:
                    p = int(n.pitch if hasattr(n, 'pitch') else n.get('pitch', 60))
                    if p in src_vel:
                        tv = int(n.velocity if hasattr(n, 'velocity') else n.get('velocity', 100))
                        sv = src_vel[p]
                        blended = int(tv * (1.0 - amt) + sv * amt)
                        blended = max(1, min(127, blended))
                        if hasattr(n, 'velocity'):
                            n.velocity = blended
                        elif isinstance(n, dict) and 'velocity' in n:
                            n['velocity'] = blended

                    # Subtle timing humanization (±2% of beat position)
                    jitter = _rnd.uniform(-0.02, 0.02) * amt
                    if hasattr(n, 'start_beats'):
                        n.start_beats = max(0.0, float(n.start_beats) + jitter)
                    elif isinstance(n, dict) and 'start_beats' in n:
                        n['start_beats'] = max(0.0, float(n.get('start_beats', 0)) + jitter)
                except Exception:
                    continue
        except Exception:
            pass

    def _parse_slot_key(self, slot_key: str) -> Optional[tuple]:
        """Parse 'scene:N:track:ID' into (scene_idx, track_id)."""
        key = str(slot_key or '').strip()
        if not key:
            return None
        parts = key.split(':')
        if len(parts) == 4 and parts[0] == 'scene' and parts[2] == 'track':
            try:
                return int(parts[1]), str(parts[3])
            except Exception:
                return None
        return None

    # ---------------- realtime pull source ----------------

    def pull(self, frames: int, sr: int):  # noqa: ANN001
        if np is None:
            return None

        frames_i = int(frames)
        sr_i = int(sr)

        # Snapshot voices + pending swap (very short lock).
        with self._lock:
            if not self._voices and not self._pending_voice_map:
                return None
            old_map = None
            if self._pending_voice_map is not None:
                old_map = dict(self._voices)
                self._voices = dict(self._pending_voice_map)
                self._pending_voice_map = None
            voices_map = dict(self._voices)

        if not voices_map:
            return None

        # Determine global playhead samples.
        g_samp = self._get_global_playhead_samples(sr_i)

        try:
            bpm = float(getattr(self.project.ctx.project, 'bpm', getattr(self.project.ctx.project, 'tempo_bpm', 120.0)) or 120.0)
        except Exception:
            bpm = 120.0
        bps = bpm / 60.0
        sppb = float(sr_i) / float(bps) if bps > 1e-9 else float(sr_i)

        # RT params (live track faders/mute/solo without project_updated)
        rt = getattr(self.audio_engine, "rt_params", None)
        try:
            any_solo = bool(rt.any_solo()) if rt is not None else False
        except Exception:
            any_solo = False
        try:
            bridge = getattr(self.audio_engine, "hybrid_bridge", None) or getattr(self.audio_engine, "_hybrid_bridge", None)
        except Exception:
            bridge = None

        # Normal path: just mix current map
        if old_map is None:
            out = np.zeros((frames_i, 2), dtype=np.float32)
            self._mix_voice_map(out, voices_map, g_samp, frames_i, sr_i, sppb, rt=rt, any_solo=any_solo, bridge=bridge)
            # v0.0.20.605: Process fading-out voices
            self._mix_fading_voices(out, g_samp, frames_i, sr_i, sppb, rt=rt, any_solo=any_solo, bridge=bridge)
            return out

        # Swap path: tiny crossfade to avoid clicks
        out_new = np.zeros((frames_i, 2), dtype=np.float32)
        self._mix_voice_map(out_new, voices_map, g_samp, frames_i, sr_i, sppb, rt=rt, any_solo=any_solo, bridge=bridge)

        fade_n = int(min(frames_i, int(self._swap_xfade_frames)))
        if not old_map or fade_n <= 0:
            return out_new

        out_old = np.zeros((fade_n, 2), dtype=np.float32)
        self._mix_voice_map(out_old, old_map, g_samp, fade_n, sr_i, sppb, rt=rt, any_solo=any_solo, bridge=bridge)

        ramp = np.linspace(0.0, 1.0, num=fade_n, endpoint=False, dtype=np.float32).reshape((fade_n, 1))
        out_new[:fade_n, :] = (out_old * (1.0 - ramp)) + (out_new[:fade_n, :] * ramp)

        # v0.0.20.605: Process fading-out voices (crossfade tail)
        self._mix_fading_voices(out_new, g_samp, frames_i, sr_i, sppb, rt=rt, any_solo=any_solo, bridge=bridge)

        return out_new

    def _mix_fading_voices(self, out, g_samp, frames, sr, sppb, *, rt=None, any_solo=False, bridge=None):
        """v0.0.20.605: Mix voices that are fading out (crossfade tail)."""
        if not self._fading_voices or np is None:
            return
        still_fading = []
        for v, remaining, total in self._fading_voices:
            try:
                if remaining <= 0:
                    # Done fading — send note_off cleanup
                    if v.is_midi_realtime:
                        self._stop_midi_voice(v)
                    continue
                # Mix with fade-out envelope
                fade_frames = min(frames, remaining)
                fade_buf = np.zeros((fade_frames, 2), dtype=np.float32)
                if v.is_midi_realtime:
                    self._dispatch_midi_for_voice(v, g_samp, fade_frames, sr, sppb, rt=rt, any_solo=any_solo)
                else:
                    self._mix_voice(fade_buf, v, g_samp, fade_frames, sr, sppb, rt=rt, any_solo=any_solo, bridge=bridge)
                # Apply fade-out envelope
                t = max(1, total)
                start_gain = float(remaining) / float(t)
                end_gain = float(remaining - fade_frames) / float(t)
                ramp = np.linspace(start_gain, end_gain, num=fade_frames, endpoint=False, dtype=np.float32).reshape((fade_frames, 1))
                out[:fade_frames, :] += fade_buf * ramp
                new_remaining = remaining - fade_frames
                if new_remaining > 0:
                    still_fading.append((v, new_remaining, total))
                else:
                    if v.is_midi_realtime:
                        self._stop_midi_voice(v)
            except Exception:
                continue
        self._fading_voices = still_fading

    def _mix_voice_map(self, out, voices_map: Dict[str, _Voice], g_samp: int, frames: int, sr: int, sppb: float, *, rt=None, any_solo: bool = False, bridge=None) -> None:  # noqa: ANN001
        for v in list(voices_map.values()):
            try:
                if v.is_midi_realtime:
                    self._dispatch_midi_for_voice(v, g_samp, frames, sr, sppb, rt=rt, any_solo=any_solo)
                else:
                    self._mix_voice(out, v, g_samp, frames, sr, sppb, rt=rt, any_solo=any_solo, bridge=bridge)
                # v0.0.20.600: Follow Action — detect loop wraps and count
                self._check_follow_action(v, g_samp, frames, sppb)
            except Exception:
                continue

    def _check_follow_action(self, v: _Voice, g_samp: int, frames: int, sppb: float) -> None:
        """v0.0.20.600: Count loop wraps and queue follow action when count reached."""
        try:
            # v0.0.20.614: Fix — Clips loopen endlos wenn KEINE Follow-Action
            # konfiguriert ist (beide Actions = 'Stopp'). Vorher wurde nach 1 Loop
            # gestoppt weil der Default next_action_count=1 war.
            # Bitwig/Ableton: Clips loopen bis explizit gestoppt oder Follow-Action.
            if v.next_action == 'Stopp' and v.next_action_b == 'Stopp':
                return  # no follow action configured → loop forever
            if v.next_action_count <= 0:
                return

            loop_span_beats = v.loop_end_beats - v.loop_start_beats
            if loop_span_beats <= 0.01:
                return

            # Current beat position relative to voice start
            start_samp = int(round(float(v.start_beat) * sppb))
            rel_end = (g_samp + frames) - start_samp
            if rel_end <= 0:
                return

            # How many complete loops have we done?
            loop_span_samp = max(1, int(round(loop_span_beats * sppb)))
            loops_done = int(rel_end // loop_span_samp)

            if loops_done > v.loop_count:
                v.loop_count = loops_done
                if v.loop_count >= v.next_action_count:
                    # v0.0.20.604: Probability — choose action A or B
                    import random as _rnd
                    prob = max(0, min(100, v.next_action_probability))
                    chosen_action = v.next_action if _rnd.randint(1, 100) <= prob else v.next_action_b
                    self._follow_action_queue.append((str(v.slot_key), str(chosen_action)))
                    v.next_action_count = 0  # prevent re-queuing
        except Exception:
            pass

    def _get_global_playhead_samples(self, sr: int) -> int:
        # Prefer external audio-thread clock
        try:
            if bool(getattr(self.transport, "playing", False)):
                ext = getattr(self.transport, "_external_playhead_samples", None)
                ext_sr = float(getattr(self.transport, "_external_sample_rate", 0.0) or 0.0)
                if ext is not None and ext_sr > 1.0:
                    # Convert if needed (rare)
                    if abs(ext_sr - float(sr)) < 1e-3:
                        return int(ext)
                    # scale samples from ext_sr to sr
                    return int(round((float(ext) / ext_sr) * float(sr)))
        except Exception:
            pass

        # Fallback: derive from beat (lower precision)
        try:
            beat = float(getattr(self.transport, "current_beat", 0.0) or 0.0)
            bpm = float(getattr(self.project.ctx.project, "bpm", getattr(self.project.ctx.project, "tempo_bpm", 120.0)) or 120.0)
            bps = bpm / 60.0
            sppb = float(sr) / float(bps) if bps > 1e-9 else float(sr)
            return int(round(beat * sppb))
        except Exception:
            # Last-resort monotonic counter
            if sr != int(self._fallback_sr):
                self._fallback_sr = int(sr)
                self._fallback_playhead_samples = 0
            cur = int(self._fallback_playhead_samples)
            self._fallback_playhead_samples += 0  # will be advanced by engine, not here
            return cur

    def _mix_voice(self, out, v: _Voice, g_samp: int, frames: int, sr: int, sppb: float, *, rt=None, any_solo: bool = False, bridge=None) -> None:  # noqa: ANN001
        # Live track params (volume/pan/mute/solo) — applied in realtime
        tid = str(getattr(v, "track_id", "") or "")
        tr_gain = float(getattr(v, "track_gain", 1.0) or 1.0)
        tr_pan = float(getattr(v, "track_pan", 0.0) or 0.0)
        try:
            if rt is not None and tid:
                if bool(getattr(rt, "is_track_muted")(tid)):
                    return
                if bool(any_solo) and not bool(getattr(rt, "is_track_solo")(tid)):
                    return
                tr_gain = float(getattr(rt, "get_track_vol")(tid))
                tr_pan = float(getattr(rt, "get_track_pan")(tid))
        except Exception:
            pass

        # Decode audio
        data = self._load_audio(v.file_path, sr)
        if data is None:
            return

        # Compute gains (clip * track) + equal-power pan (clip + track pan)
        gl, gr = self._pan_gains(float(v.gain) * float(tr_gain), float(v.pan) + float(tr_pan))

        # Meter hook (optional): update TrackMeterRing backed by HybridAudioCallback
        meter = None
        try:
            if bridge is not None and tid:
                idx = None
                if hasattr(bridge, "try_get_track_idx"):
                    idx = bridge.try_get_track_idx(tid)
                else:
                    idx = getattr(bridge, "_track_id_to_idx", {}).get(tid)
                if idx is not None:
                    cb = getattr(bridge, "callback", None)
                    if cb is not None:
                        meter = cb.get_track_meter(int(idx))
        except Exception:
            meter = None

        # Clip-local loop in samples
        loop_s = int(round(float(v.loop_start_beats) * sppb))
        loop_e = int(round(float(v.loop_end_beats) * sppb))
        if loop_e <= loop_s:
            return
        loop_span = max(1, loop_e - loop_s)

        # Global start sample of this voice
        start_samp = int(round(float(v.start_beat) * sppb))

        # This pull call corresponds to [g_samp, g_samp+frames)
        rel0 = g_samp - start_samp
        if rel0 + frames <= 0:
            # not started yet
            return

        # Determine segment inside the current buffer that overlaps the active region
        buf_off = 0
        if rel0 < 0:
            buf_off = int(-rel0)
            rel0 = 0
        n_remain = frames - buf_off
        if n_remain <= 0:
            return

        # Clip-local sample at buffer start (wrapped into loop)
        local0 = loop_s + (rel0 % loop_span)

        # Process possibly multiple wraps inside this block
        write_pos = buf_off
        while n_remain > 0:
            seg_local = local0
            seg_avail = min(n_remain, (loop_e - seg_local))
            if seg_avail <= 0:
                # wrap
                local0 = loop_s
                continue

            # Map [seg_local, seg_local+seg_avail) -> events
            self._mix_events_segment(out, data, v, v.events, seg_local, seg_avail, sr, sppb, write_pos, gl, gr, meter=meter)

            write_pos += int(seg_avail)
            n_remain -= int(seg_avail)
            local0 = loop_s  # next segment starts at loop start

    def _mix_events_segment(self, out, data, v: _Voice, events, seg_local_samp: int, seg_len: int, sr: int, sppb: float, write_pos: int, gl: float, gr: float, *, meter=None) -> None:  # noqa: ANN001
        # Convert segment to beats in clip timeline
        seg_start_beat = float(seg_local_samp) / float(sppb)
        seg_end_beat = float(seg_local_samp + seg_len) / float(sppb)

        # Tape-style rate (preview): pitch + stretch.
        try:
            pitch_st = float(getattr(v, 'pitch', 0.0) or 0.0)
        except Exception:
            pitch_st = 0.0
        try:
            stretch = float(getattr(v, 'stretch', 1.0) or 1.0)
        except Exception:
            stretch = 1.0
        if stretch <= 1e-6:
            stretch = 1.0
        try:
            _rate = (2.0 ** (pitch_st / 12.0)) / float(stretch)
        except Exception:
            _rate = 1.0

        # Iterate events overlapping this segment
        for e in events:
            try:
                e_start = float(getattr(e, "start_beats", 0.0) or 0.0)
                e_len = float(getattr(e, "length_beats", 0.0) or 0.0)
                e_end = e_start + max(0.0, e_len)
                if e_end <= seg_start_beat or e_start >= seg_end_beat:
                    continue
                ov_start_beat = max(seg_start_beat, e_start)
                ov_end_beat = min(seg_end_beat, e_end)
                if ov_end_beat <= ov_start_beat:
                    continue

                # Destination slice in output
                dst_off = int(round((ov_start_beat - seg_start_beat) * sppb))
                n = int(round((ov_end_beat - ov_start_beat) * sppb))
                if n <= 0:
                    continue

                # Source slice in file
                src_off_beats = float(getattr(e, "source_offset_beats", 0.0) or 0.0)
                src_beat = src_off_beats + (ov_start_beat - e_start)
                src_off = int(round(src_beat * sppb))
                src_end = src_off + n
                if src_off >= int(data.shape[0]):
                    continue
                if src_end > int(data.shape[0]):
                    src_end = int(data.shape[0])
                    n = int(src_end - src_off)
                if n <= 0:
                    continue

                if np is None:
                    continue
                if abs(float(_rate) - 1.0) < 1e-6:
                    chunk = data[src_off:src_off + n]
                else:
                    # Linear interpolation resample (preview quality)
                    idx = float(src_off) + (np.arange(int(n), dtype=np.float32) * float(_rate))
                    i0 = np.floor(idx).astype(np.int64)
                    i1 = i0 + 1
                    max_i = int(data.shape[0]) - 1
                    i0 = np.clip(i0, 0, max_i)
                    i1 = np.clip(i1, 0, max_i)
                    frac = (idx - i0.astype(np.float32)).reshape((-1, 1))
                    s0 = data[i0]
                    s1 = data[i1]
                    chunk = (s0 * (1.0 - frac) + s1 * frac).astype(np.float32)
                # Per-event reverse (v0.0.20.160)
                if bool(getattr(e, 'reversed', False)) and chunk.shape[0] > 1:
                    chunk = chunk[::-1].copy()
                try:
                    if meter is not None:
                        meter.update_from_block(chunk, gl, gr)
                except Exception:
                    pass
                out[write_pos + dst_off:write_pos + dst_off + n, 0] += chunk[:n, 0] * gl
                out[write_pos + dst_off:write_pos + dst_off + n, 1] += chunk[:n, 1] * gr
            except Exception:
                continue

    def _load_audio(self, path: str, sr: int):  # noqa: ANN001
        if np is None:
            return None
        key = (str(path), int(sr))
        cached = self._audio_cache.get(key)
        if cached is not None:
            return cached
        try:
            import soundfile as sf  # type: ignore
        except Exception:
            return None
        try:
            data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception:
            return None
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] >= 2:
            data = data[:, :2]
        file_sr_i = int(file_sr)
        if file_sr_i != int(sr) and int(data.shape[0]) > 1:
            ratio = float(sr) / float(file_sr_i)
            n_out = max(1, int(round(int(data.shape[0]) * ratio)))
            x_old = np.linspace(0.0, 1.0, num=int(data.shape[0]), endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
            data = np.vstack([
                np.interp(x_new, x_old, data[:, 0]),
                np.interp(x_new, x_old, data[:, 1]),
            ]).T.astype(np.float32, copy=False)
        self._audio_cache[key] = data
        # basic cache trimming
        if len(self._audio_cache) > 32:
            try:
                for k in list(self._audio_cache.keys())[:8]:
                    self._audio_cache.pop(k, None)
            except Exception:
                pass
        return data

    @staticmethod
    def _pan_gains(gain: float, pan: float) -> Tuple[float, float]:
        pan = max(-1.0, min(1.0, float(pan)))
        angle = (pan + 1.0) * (math.pi / 4.0)
        return float(gain) * math.cos(angle), float(gain) * math.sin(angle)
