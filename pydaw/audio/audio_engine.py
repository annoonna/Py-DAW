"""Audio engine abstraction (PipeWire preferred).

v0.0.2 goals:
- Detect a suitable audio backend automatically.
  * Preferred: JACK client (typically provided by PipeWire via pipewire-jack)
  * Fallback: sounddevice (PortAudio)
- Provide device/port enumeration for an Audio Settings dialog.
- Provide a non-blocking start/stop skeleton (threaded), so the GUI never freezes.

Notes for Linux/PipeWire:
- If pipewire-jack is installed and PipeWire is running, JACK ports will appear
  in qpwgraph and are routable like a modern DAW graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
from typing import List, Optional, Literal, Dict, Any, Tuple
import copy
import math
import shutil
import threading

import os
import contextlib
import time

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None

from .midi_render import RenderKey, ensure_rendered_wav, midi_content_hash
from .note_expression_eval import effective_velocity, should_play_note, effective_micropitch_note_start

from .arrangement_renderer import prepare_clips, ArrangementState

# v0.0.20.14 Hybrid Engine imports (Phase 2: per-track + JACK + default callback)
try:
    from .hybrid_engine import (
        HybridAudioCallback, HybridEngineBridge, get_hybrid_bridge,
        PARAM_MASTER_VOL, PARAM_MASTER_PAN,
    )
    from .ring_buffer import (
        ParamRingBuffer, AudioRingBuffer, TrackParamState,
        track_param_id, TRACK_VOL, TRACK_PAN, TRACK_MUTE, TRACK_SOLO,
    )
    from .async_loader import get_async_loader, get_sample_cache
    _HYBRID_AVAILABLE = True
except Exception:
    _HYBRID_AVAILABLE = False

# v0.0.20.14: Essentia Worker Pool
try:
    from .essentia_pool import get_essentia_pool, EssentiaWorkerPool
    _ESSENTIA_POOL_AVAILABLE = True
except Exception:
    _ESSENTIA_POOL_AVAILABLE = False


class _PullCallableAdapter:
    """Adapter so we can register plain callables as pull sources.

    A pull source is expected to provide .pull(frames, sr) -> np.ndarray.
    Some widgets register a function (frames, sr) -> np.ndarray; this wraps it.
    """

    def __init__(self, fn, name: str | None = None):
        self._fn = fn
        self._name = name or getattr(fn, "__name__", "pull_fn")

    def pull(self, frames: int, sr: int):
        return self._fn(frames, sr)

    def __repr__(self) -> str:
        return f"<PullCallableAdapter {self._name}>"

def _normalize_pull_source(pull_source, name: str | None = None):
    """Return an object that has a .pull(frames, sr) method."""
    if pull_source is None:
        return None
    if hasattr(pull_source, "pull") and callable(getattr(pull_source, "pull")):
        return pull_source
    if callable(pull_source):
        return _PullCallableAdapter(pull_source, name=name)
    return pull_source


# v0.0.20.539: Instrument Layer Dispatcher — fans MIDI to multiple engines
class _InstrumentLayerDispatcher:
    """Wraps multiple instrument engines for an Instrument Layer (Stack).

    Implements note_on/note_off/all_notes_off so the SamplerRegistry can
    dispatch MIDI events to ALL layer engines simultaneously.

    v0.0.20.540: Per-layer Velocity-Split and Key-Range filtering.
    v0.0.20.543: Velocity-Crossfade — soft transitions between velocity zones.
    v0.0.20.553: Bitwig-style audio summing — pull() sums ALL layer outputs
    with per-layer volume. This is the core of the Container-Device model.
    """

    def __init__(self, track_id: str, engines: list, layer_ranges: list | None = None,
                 layer_volumes: list | None = None):
        self.track_id = str(track_id)
        self._engines = list(engines)  # list of instrument engine instances
        self._ok = bool(self._engines)
        # v0.0.20.557: Flag to prevent double MIDI routing
        # (SamplerRegistry already handles MIDI → dispatcher,
        #  _route_live_note_to_vst must skip dispatchers)
        self._is_layer_dispatcher = True
        # Per-layer ranges: [(vel_min, vel_max, key_min, key_max, vel_crossfade), ...]
        if layer_ranges and len(layer_ranges) == len(self._engines):
            self._ranges = list(layer_ranges)
        else:
            self._ranges = [(0, 127, 0, 127, 0)] * len(self._engines)
        # Per-layer volumes (0.0 - 1.0)
        if layer_volumes and len(layer_volumes) == len(self._engines):
            self._volumes = [float(v) for v in layer_volumes]
        else:
            self._volumes = [1.0] * len(self._engines)

    def note_on(self, pitch: int, velocity: int = 100, **kwargs) -> bool:
        ok = False
        p = int(pitch)
        v = int(velocity)
        for i, eng in enumerate(self._engines):
            try:
                rng = self._ranges[i]
                vel_min = rng[0]
                vel_max = rng[1]
                key_min = rng[2]
                key_max = rng[3]
                crossfade = rng[4] if len(rng) > 4 else 0

                # Key-Range check (hard cutoff)
                if p < key_min or p > key_max:
                    continue

                # Velocity check with optional crossfade
                effective_vel = v
                if crossfade > 0:
                    # Extended zone: [vel_min - crossfade, vel_max + crossfade]
                    ext_min = max(0, vel_min - crossfade)
                    ext_max = min(127, vel_max + crossfade)
                    if v < ext_min or v > ext_max:
                        continue
                    # Lower crossfade: fade in from ext_min to vel_min
                    if v < vel_min and crossfade > 0:
                        scale = float(v - ext_min) / float(crossfade)
                        effective_vel = max(1, int(v * scale))
                    # Upper crossfade: fade out from vel_max to ext_max
                    elif v > vel_max and crossfade > 0:
                        scale = float(ext_max - v) / float(crossfade)
                        effective_vel = max(1, int(v * scale))
                else:
                    # Hard cutoff (no crossfade)
                    if v < vel_min or v > vel_max:
                        continue

                if hasattr(eng, "note_on") and eng.note_on(p, effective_vel, **kwargs):
                    ok = True
            except Exception:
                pass
        return ok

    def note_off(self, pitch: int = -1) -> None:
        _pitch = int(pitch)
        for i, eng in enumerate(self._engines):
            try:
                if hasattr(eng, "note_off"):
                    # v0.0.20.557: Robust note_off for all engine types
                    import inspect
                    sig = inspect.signature(eng.note_off)
                    n_params = len([_p for _p in sig.parameters.values()
                                    if _p.name != "self"])
                    if n_params == 0:
                        # Monophonic: note_off() with no args
                        eng.note_off()
                    else:
                        # Polyphonic: note_off(pitch)
                        eng.note_off(_pitch)
            except Exception:
                # Last resort: try without args
                try:
                    eng.note_off()
                except Exception:
                    pass

    def all_notes_off(self) -> None:
        for eng in self._engines:
            try:
                if hasattr(eng, "all_notes_off"):
                    eng.all_notes_off()
            except Exception:
                pass

    def pull(self, frames: int, sr: int):
        """Bitwig-style: pull audio from ALL layer engines, apply volume, sum.

        v0.0.20.553: This is the core mixing stage. Each layer engine
        produces audio independently, we apply per-layer volume and
        sum into a single stereo output buffer.
        """
        import numpy as np
        result = None
        for i, eng in enumerate(self._engines):
            try:
                buf = eng.pull(frames, sr)
                if buf is None:
                    continue
                arr = np.asarray(buf, dtype=np.float32)
                # Apply per-layer volume
                vol = self._volumes[i] if i < len(self._volumes) else 1.0
                if vol != 1.0:
                    arr = arr * vol
                # Sum into result
                if result is None:
                    result = arr.copy()
                else:
                    # Ensure shapes match (mono → stereo promotion)
                    if result.shape != arr.shape:
                        if arr.ndim == 1 and result.ndim == 2:
                            arr = np.column_stack([arr, arr])
                        elif result.ndim == 1 and arr.ndim == 2:
                            result = np.column_stack([result, result])
                    result += arr
            except Exception:
                pass
        return result

    def shutdown(self) -> None:
        for eng in self._engines:
            try:
                if hasattr(eng, "shutdown"):
                    eng.shutdown()
            except Exception:
                pass
        self._engines.clear()
        self._ok = False


def _midi_notes_content_hash(notes) -> str:  # noqa: ANN001
    """Stable hash for MIDI note content.

    Used to invalidate the FluidSynth render cache when notes *or note
    expressions* change. Without expressions here, micropitch edits can stay
    inaudible until the user also moves a note.
    """
    import hashlib
    import json

    h = hashlib.sha1()
    include_params = ("velocity", "chance", "timbre", "pressure", "micropitch")
    for n in (notes or []):
        try:
            pitch = int(getattr(n, "pitch", 0))
            sb = float(getattr(n, "start_beats", 0.0))
            lb = float(getattr(n, "length_beats", 0.0))
            vel = int(getattr(n, "velocity", 0))
        except Exception:
            continue
        h.update(f"{pitch}:{sb:.6f}:{lb:.6f}:{vel};".encode("utf-8"))
        expr = getattr(n, "expressions", None)
        if isinstance(expr, dict):
            filtered = {k: expr.get(k) for k in include_params if k in expr}
            try:
                h.update(json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            except Exception:
                pass
        curve_types = getattr(n, "expression_curve_types", None)
        if isinstance(curve_types, dict):
            filtered_ct = {k: curve_types.get(k) for k in include_params if k in curve_types}
            try:
                h.update(json.dumps(filtered_ct, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            except Exception:
                pass
    return h.hexdigest()[:16]


@contextlib.contextmanager
def _suppress_stderr_fd():
    """Suppress C-level stderr (e.g., JACK/PortAudio noise) temporarily."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        try:
            os.dup2(old, 2)
            os.close(old)
        except Exception:
            pass

from PyQt6.QtCore import QObject, QThread, pyqtSignal

Backend = Literal["jack", "sounddevice", "none"]


@dataclass(frozen=True)
class AudioEndpoint:
    """Represents a selectable input/output endpoint."""
    id: str
    label: str


@dataclass
class AudioBackendInfo:
    backend: Backend
    available: bool
    details: str


class _EngineThread(QThread):
    """Background thread for long-running audio operations.

    In v0.0.2 this is intentionally minimal: it demonstrates that audio work
    can live off the GUI thread and provides a place to host a realtime loop
    later (recording, transport sync, etc.).
    """

    started_ok = pyqtSignal(str)
    stopped_ok = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, backend: Backend, config: Dict[str, Any]):
        super().__init__()
        self._backend = backend
        self._config = config
        self._stop_flag = False

        # Optional: TransportService für sample-accurate UI-Sync.
        # Muss thread-safe sein (keine Qt-Signale vom Audio-Thread).
        self._transport_service = config.get("transport_service")

        # Small in-memory cache to avoid re-reading / re-decoding the same files
        # during rapid stop/play iterations. Keeps UI responsive on slower disks.
        # Key: (path, target_sr) -> cached stereo float32 array at target_sr.
        self._wav_cache = OrderedDict()
        self._wav_cache_max = int(config.get("wav_cache_max", 16) or 16)

    def request_stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        try:
            if self._backend == "sounddevice":
                mode = (self._config.get("mode") or "silence").lower()
                if mode == "arrangement" and self._config.get("project_snapshot") is not None:
                    self._run_sounddevice_arrangement()
                else:
                    self._run_sounddevice_silence()
            elif self._backend == "jack":
                # For JACK we do not start a stream here; connecting/processing
                # is handled via JACK callbacks in future versions.
                # We still keep a thread alive to show non-blocking structure.
                self.started_ok.emit("JACK bereit (Platzhalter-Engine-Thread aktiv)")
                while not self._stop_flag:
                    self.msleep(50)
            else:
                self.error.emit("Kein Audio-Backend verfügbar.")
        except Exception as exc:  # pragma: no cover
            self.error.emit(str(exc))
        finally:
            self.stopped_ok.emit()

    def _run_sounddevice_silence(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError(
                "sounddevice/numpy nicht verfügbar. Bitte requirements installieren."
            ) from exc

        sr = int(self._config.get("sample_rate") or 48000)
        bs = int(self._config.get("buffer_size") or 256)

        out_dev = self._config.get("output_device")
        out_dev = int(out_dev) if out_dev not in (None, "", "None") else None

        self.started_ok.emit(f"sounddevice gestartet (SR={sr}, Buffer={bs})")

        audio_engine_ref = self._config.get("audio_engine_ref")
        last_gen = -1
        pull_sources = []

        # v0.0.20.52: Scratch buffer for pull-source mixing (no alloc in callback)
        pull_tmp_buf = np.zeros((8192, 2), dtype=np.float32)

        # Sample-accurate playhead even in "silence" mode (needed for ClipLauncher).
        silence_playhead = 0
        scratch_buf = np.zeros((8192, 2), dtype=np.float32)

        def callback(outdata, frames, time, status):  # noqa: ANN001
            nonlocal last_gen, pull_sources, silence_playhead
            if status:
                pass

            # Start with silence (no allocations)
            outdata.fill(0)

            # Advance RT param smoothing
            rt = getattr(audio_engine_ref, "rt_params", None) if audio_engine_ref else None
            if rt is not None:
                try:
                    rt.advance(int(frames), int(sr))
                except Exception:
                    pass

            # Provide start playhead to Transport
            try:
                if self._transport_service is not None and bool(getattr(self._transport_service, "playing", False)):
                    self._transport_service._set_external_playhead_samples(int(silence_playhead), float(sr))
            except Exception:
                pass

            if audio_engine_ref is not None:
                # Update pull-source cache if needed
                try:
                    gen, srcs = audio_engine_ref._pull_sources_snapshot(last_gen)
                    if gen != last_gen:
                        last_gen = gen
                        pull_sources = srcs
                except Exception:
                    pass

                # Mix pull sources (per-track gain/pan/mute/solo when track-id metadata is present)
                any_solo = False
                try:
                    if rt is not None:
                        any_solo = bool(rt.any_solo())
                except Exception:
                    any_solo = False

                hb = getattr(audio_engine_ref, "_hybrid_bridge", None)
                hcb = getattr(hb, "callback", None) if hb is not None else None

                for fn in (pull_sources or []):
                    try:
                        b = fn(int(frames), int(sr))
                        if b is None:
                            continue

                        # Ensure 2ch
                        b2 = b[:frames, :2]

                        # Optional per-track routing via metadata on pull fn
                        tid_attr = getattr(fn, "_pydaw_track_id", None)
                        tid = tid_attr() if callable(tid_attr) else tid_attr
                        tid = str(tid) if tid not in (None, "", "None") else ""

                        if tid and rt is not None:
                            # Mute/Solo gating
                            try:
                                if rt.is_track_muted(tid):
                                    continue
                            except Exception:
                                pass
                            try:
                                if any_solo and (not rt.is_track_solo(tid)):
                                    continue
                            except Exception:
                                pass

                            # Smoothed track vol/pan
                            try:
                                tv = float(rt.get_track_vol(tid))
                            except Exception:
                                tv = 1.0
                            try:
                                tp = float(rt.get_track_pan(tid))
                            except Exception:
                                tp = 0.0

                            tp = max(-1.0, min(1.0, tp))
                            a = (tp + 1.0) * 0.25 * math.pi
                            gl, gr = math.cos(a) * tv, math.sin(a) * tv

                            # v0.0.20.56: Audio-FX chain (post-instrument, pre-fader)
                            src = b2
                            fx = None
                            try:
                                fx_map = getattr(audio_engine_ref, "_track_audio_fx_map", None)
                                fx = fx_map.get(tid) if fx_map else None
                            except Exception:
                                fx = None
                            if fx is not None:
                                try:
                                    tmp_fx = scratch_buf[:frames, :2]
                                    np.copyto(tmp_fx, b2, casting="unsafe")
                                    fx.process_inplace(tmp_fx, int(frames), int(sr))
                                    src = tmp_fx
                                except Exception:
                                    src = b2

                            # Track metering (so VU moves in Live/Preview mode)
                            try:
                                if hb is not None and hcb is not None:
                                    idx = None
                                    try_get = getattr(hb, "try_get_track_idx", None)
                                    if callable(try_get):
                                        idx = try_get(tid)
                                    if idx is None:
                                        idx = hb.get_track_idx(tid)
                                    if idx is not None:
                                        meter = hcb.get_track_meter(int(idx))
                                        meter.update_from_block(src, float(gl), float(gr))
                            except Exception:
                                pass

                            # Apply gains without allocations (reuse scratch buffer)
                            try:
                                tmp = scratch_buf[:frames, :2]
                                if src is tmp:
                                    tmp[:frames, 0] *= float(gl)
                                    tmp[:frames, 1] *= float(gr)
                                else:
                                    np.multiply(src, (float(gl), float(gr)), out=tmp, casting="unsafe")
                                outdata[:frames, :2] += tmp
                            except Exception:
                                outdata[:frames, :2] += b2 * np.array([gl, gr], dtype=np.float32)
                        else:
                            outdata[:frames, :2] += b2
                    except Exception:
                        pass

                # Master volume/pan (smoothed via RTParamStore)
                try:
                    if rt is not None:
                        master_vol = rt.get_smooth("master:vol", 0.8)
                        master_pan = rt.get_smooth("master:pan", 0.0)
                    else:
                        master_vol = float(getattr(audio_engine_ref, "_master_volume", 1.0))
                        master_pan = float(getattr(audio_engine_ref, "_master_pan", 0.0))

                    if master_vol != 1.0:
                        outdata[:frames, :2] *= master_vol

                    if abs(master_pan) > 0.01:
                        a = (master_pan + 1.0) * 0.25 * math.pi
                        gl, gr = math.cos(a), math.sin(a)
                        outdata[:frames, 0] *= gl
                        outdata[:frames, 1] *= gr
                except Exception:
                    pass

            # soft clip
            try:
                np.clip(outdata, -1.0, 1.0, out=outdata)
            except Exception:
                pass

            # Metering (Preview/Live Mode): push master block into hybrid meter ring
            # so the Mixer VU moves even when we are not in arrangement mode.
            try:
                hb = getattr(audio_engine_ref, "_hybrid_bridge", None)
                if hb is not None:
                    hb.meter_ring.write(outdata[:frames, :2])
            except Exception:
                pass

            # Advance playhead (only while transport is playing) + honor transport loop (audio-clock)
            try:
                if self._transport_service is not None and bool(getattr(self._transport_service, "playing", False)):
                    silence_playhead += int(frames)

                    # Audio-clock Looping (Transport loops only when no external clock is active)
                    try:
                        loop_enabled = bool(getattr(self._transport_service, "loop_enabled", False))
                        if loop_enabled:
                            bpm = float(getattr(self._transport_service, "bpm", 120.0) or 120.0)
                            ls_beat = float(getattr(self._transport_service, "loop_start", 0.0) or 0.0)
                            le_beat = float(getattr(self._transport_service, "loop_end", 0.0) or 0.0)
                            if le_beat > ls_beat + 1e-6:
                                bps = bpm / 60.0
                                if bps > 1e-9:
                                    sppb = float(sr) / bps
                                    ls = int(ls_beat * sppb)
                                    le = int(le_beat * sppb)
                                    if le > ls and silence_playhead >= le:
                                        silence_playhead = ls + (silence_playhead - le)
                    except Exception:
                        pass
            except Exception:
                pass


        with sd.OutputStream(
            samplerate=sr,
            blocksize=bs,
            device=out_dev,
            channels=2,
            dtype="float32",
            callback=callback,
        ):
            while not self._stop_flag:
                self.msleep(20)

    @dataclass
    class _PreparedAudioClip:
        start_sample: int
        end_sample: int
        offset_sample: int
        data: "np.ndarray"  # shape (n, 2)
        gain_l: float  # Fallback only (v0.0.20.34)
        gain_r: float  # Fallback only (v0.0.20.34)
        track_id: str  # NEW v0.0.20.34: For atomic dict lookup

    def _run_sounddevice_arrangement(self) -> None:
        """Arrangement playback via sounddevice.

        v0.0.20.14: Prefers HybridAudioCallback (zero-lock, zero-alloc)
        when available, falls back to legacy per-clip mixer.
        """
        if np is None:
            raise RuntimeError("numpy nicht verfügbar. Bitte requirements installieren.")

        try:
            import sounddevice as sd
            import soundfile as sf
        except Exception as exc:
            raise RuntimeError("sounddevice/soundfile nicht verfügbar. Bitte requirements installieren.") from exc

        sr = int(self._config.get("sample_rate") or 48000)
        bs = int(self._config.get("buffer_size") or 256)
        out_dev = self._config.get("output_device")
        out_dev = int(out_dev) if out_dev not in (None, "", "None") else None

        project = self._config.get("project_snapshot")
        start_beat = float(self._config.get("start_beat") or 0.0)

        bpm = float(getattr(project, "bpm", getattr(project, "tempo_bpm", 120.0)) or 120.0)

        # v0.0.20.14: Hybrid callback path (preferred)
        hybrid_bridge = self._config.get("hybrid_bridge")
        if hybrid_bridge is not None:
            try:
                loop_enabled = bool(self._config.get("loop_enabled", False))
                loop_start_beat = float(self._config.get("loop_start_beat", 0.0))
                loop_end_beat = float(self._config.get("loop_end_beat", 0.0))
                arranger_cache = self._config.get("arranger_cache_ref")

                # v0.0.20.25: Ensure deterministic track index mapping (project order)
                try:
                    if hasattr(hybrid_bridge, "set_track_index_map"):
                        mapping = {t.id: int(i) for i, t in enumerate(getattr(project, "tracks", []) or [])}
                        hybrid_bridge.set_track_index_map(mapping)
                except Exception:
                    pass

                prepared, midi_events, _bpm = prepare_clips(project, sr, cache=arranger_cache)
                arr_state = ArrangementState(
                    prepared=prepared, sr=sr,
                    start_beat=float(start_beat), bpm=float(_bpm),
                    loop_enabled=loop_enabled,
                    loop_start_beat=loop_start_beat,
                    loop_end_beat=loop_end_beat,
                    midi_events=midi_events,
                )
                hybrid_cb = hybrid_bridge.callback
                hybrid_cb.set_arrangement_state(arr_state)
                hybrid_cb.set_transport_ref(self._config.get("transport_service"))
                hybrid_bridge.set_sample_rate(sr)

                # v0.0.20.41: Wire direct peak storage for reliable VU metering
                ae_ref = self._config.get("audio_engine_ref")
                if ae_ref is not None and hasattr(ae_ref, "_direct_peaks"):
                    hybrid_cb._direct_peaks_ref = ae_ref._direct_peaks

                # v0.0.20.42: Wire sampler registry for real-time MIDI→Sampler
                sampler_reg = self._config.get("sampler_registry")
                if sampler_reg is not None:
                    hybrid_cb._sampler_registry = sampler_reg

                # v0.0.20.80: Wire instrument bypass set
                try:
                    tracks_sd = getattr(project, 'tracks', []) or []
                    bypassed_sd = {str(getattr(t, 'id', '')) for t in tracks_sd
                                   if not bool(getattr(t, 'instrument_enabled', True))}
                    hybrid_cb.set_bypassed_track_ids(bypassed_sd)
                except Exception:
                    pass

                self.started_ok.emit(f"Hybrid Engine (sounddevice, SR={sr}, Buffer={bs}, lock-free)")

                with sd.OutputStream(
                    samplerate=sr, blocksize=bs, device=out_dev,
                    channels=2, dtype="float32", callback=hybrid_cb,
                ):
                    while not self._stop_flag:
                        self.msleep(20)

                # Clear arrangement state on stop
                hybrid_cb.set_arrangement_state(None)
                return
            except Exception as e:
                # Fallback to legacy path
                try:
                    self.status.emit(f"Hybrid Engine fehlgeschlagen ({e}), Legacy-Modus…")
                except Exception:
                    pass

        # --- Legacy arrangement path (pre-v0.0.20.14) ---
        beats_per_second = bpm / 60.0
        samples_per_beat = sr / beats_per_second

        def beats_to_samples(beats: float) -> int:
            return int(round(beats * samples_per_beat))

        # Prepare track map
        tracks_by_id = {t.id: t for t in getattr(project, "tracks", [])}
        solos = [t for t in tracks_by_id.values() if getattr(t, "solo", False)]
        solo_ids = {t.id for t in solos}
        use_solo = len(solo_ids) > 0
        
        # FIXED v0.0.19.7.14: Reference to self for LIVE master volume! ✅
        engine_self = self  # Closure reference for callback
        audio_engine_ref = self._config.get("audio_engine_ref")
        arranger_cache = self._config.get("arranger_cache_ref")
        if arranger_cache is None:
            try:
                from pydaw.audio.arranger_cache import DEFAULT_ARRANGER_CACHE

                arranger_cache = DEFAULT_ARRANGER_CACHE
            except Exception:
                arranger_cache = None
        last_gen = -1
        pull_sources = []

        # Reused scratch buffer for pull-source mixing (no allocations in callback)
        pull_tmp_buf = np.zeros((8192, 2), dtype=np.float32)

        # Use a small LRU-style cache across play runs (per engine thread).
        # This dramatically reduces stutter when toggling Play/Stop quickly.
        def _cache_get(path: str, target_sr: int):
            """Decode/resample cache lookup.

            Prefer global ArrangerRenderCache if available, fallback to per-thread LRU.
            """
            if arranger_cache is not None:
                try:
                    v = arranger_cache.get_decoded(str(path), int(target_sr))
                    if v is not None:
                        return v
                except Exception:
                    pass
            key = (path, int(target_sr))
            try:
                v = self._wav_cache.get(key)
            except Exception:
                return None
            if v is None:
                return None
            try:
                # mark as recently used
                self._wav_cache.move_to_end(key)
            except Exception:
                pass
            return v

        def _cache_put(path: str, target_sr: int, arr):
            # Global cache stores itself inside get_decoded(). For fallback per-thread LRU we keep put().
            if arranger_cache is not None:
                return
            key = (path, int(target_sr))
            try:
                self._wav_cache[key] = arr
                self._wav_cache.move_to_end(key)
                while len(self._wav_cache) > int(self._wav_cache_max):
                    self._wav_cache.popitem(last=False)
            except Exception:
                pass
        prepared: List[_EngineThread._PreparedAudioClip] = []

        # Real-time MIDI events for non-SF2 instruments (Sampler/Drum/...).
        # These are dispatched during playback via the SamplerRegistry.
        from .arrangement_renderer import PreparedMidiEvent

        midi_events: List[PreparedMidiEvent] = []
        midi_cursor = 0

        def _reset_midi_cursor(target_playhead: int) -> int:
            idx = 0
            while idx < len(midi_events) and int(midi_events[idx].sample_pos) < int(target_playhead):
                idx += 1
            return idx

        def _pan_gains(vol: float, pan: float) -> Tuple[float, float]:
            # equal-power pan
            pan = max(-1.0, min(1.0, float(pan)))
            angle = (pan + 1.0) * (math.pi / 4.0)
            return float(vol) * math.cos(angle), float(vol) * math.sin(angle)

        for clip in getattr(project, "clips", []) or []:
            kind = str(getattr(clip, "kind", "") or "")
            track = tracks_by_id.get(getattr(clip, "track_id", ""))
            if not track:
                continue

            muted = bool(getattr(track, "muted", getattr(track, "mute", False)))
            if muted:
                continue
            if use_solo and track.id not in solo_ids:
                continue

            path = None
            file_sr = None
            data = None
            cache_path = None  # str path used for waveform cache

            if kind == "audio":
                path = getattr(clip, "source_path", None)
                if not path:
                    continue
                cache_path = str(path)
                cached = _cache_get(cache_path, sr)
                if cached is not None:
                    data = cached
                    file_sr = int(sr)
                else:
                    try:
                        data, file_sr = sf.read(path, dtype="float32", always_2d=True)
                    except Exception:
                        # Unsupported/failed read -> skip
                        continue

            elif kind == "midi":
                # v0.0.20.46: Plugin-Type basiertes MIDI Rendering (Pro-DAW-Style!)
                # Jeder Track kann ein eigenes Instrument-Plugin haben
                
                # Bestimme plugin_type (mit backwards compatibility)
                plugin_type = getattr(track, "plugin_type", None)
                sf2_path_legacy = getattr(track, "sf2_path", None)
                
                # Backwards compatibility: Wenn plugin_type=None aber sf2_path gesetzt, dann "sf2"
                if not plugin_type and sf2_path_legacy:
                    plugin_type = "sf2"

                # Hinweis: plugin_type kann hier None sein (z.B. Default-Sampler/Drum
                # im Device-Rack, ohne expliziten plugin_type). In diesem Fall
                # behandeln wir MIDI als Live-MIDI und dispatchen es an die
                # SamplerRegistry.
                
                # MIDI-Noten holen
                midi_notes_map = getattr(project, "midi_notes", {}) or {}
                notes_raw = list(midi_notes_map.get(getattr(clip, "id", ""), []) or [])
                
                # Apply notation tie markers for playback (non-destructive)
                try:
                    from .arrangement_renderer import _apply_ties_to_notes
                    notes = list(_apply_ties_to_notes(project, str(getattr(clip, "id", "")), notes_raw) or [])
                except Exception:
                    notes = list(notes_raw or [])
                
                clip_len_beats = float(getattr(clip, "length_beats", 4.0) or 4.0)
                
                # Extend render length to furthest note end
                try:
                    if notes:
                        note_end = max(float(getattr(n, "start_beats", 0.0)) + float(getattr(n, "length_beats", 0.0)) for n in notes)
                        clip_len_beats = max(clip_len_beats, float(note_end))
                except Exception:
                    pass
                
                # Plugin-spezifisches Rendering
                if plugin_type == "sf2":
                    # FluidSynth SF2 Rendering (wie bisher)
                    sf2_path = getattr(track, "sf2_path", None)
                    if not sf2_path:
                        continue
                    
                    content_hash = midi_content_hash(
                        notes=notes,
                        bpm=float(bpm),
                        clip_length_beats=float(clip_len_beats),
                        sf2_bank=int(getattr(track, "sf2_bank", 0)),
                        sf2_preset=int(getattr(track, "sf2_preset", 0)),
                    )
                    key = RenderKey(
                        clip_id=str(getattr(clip, "id", "")),
                        sf2_path=str(sf2_path),
                        sf2_bank=int(getattr(track, "sf2_bank", 0)),
                        sf2_preset=int(getattr(track, "sf2_preset", 0)),
                        bpm=float(bpm),
                        samplerate=int(sr),
                        clip_length_beats=float(clip_len_beats),
                        content_hash=str(content_hash),
                    )
                    wav_path = ensure_rendered_wav(
                        key=key,
                        midi_notes=notes,
                        clip_start_beats=float(getattr(clip, "start_beats", 0.0)),
                        clip_length_beats=float(clip_len_beats),
                    )
                    if not wav_path:
                        continue
                    cache_path = wav_path.as_posix()
                    cached = _cache_get(cache_path, sr)
                    if cached is not None:
                        data = cached
                        file_sr = int(sr)
                    else:
                        try:
                            data, file_sr = sf.read(wav_path.as_posix(), dtype="float32", always_2d=True)
                        except Exception:
                            continue
                
                else:
                    # Live-MIDI (Sampler/Drum/...) in Legacy-Fallback:
                    # Wir schedulen Note-On/Off Events und dispatchen sie im Callback
                    # an die SamplerRegistry (falls vorhanden).
                    if PreparedMidiEvent is None:
                        continue
                    track_id_str = str(getattr(track, "id", getattr(track, "track_id", "")))
                    clip_start_beats = float(getattr(clip, "start_beats", 0.0) or 0.0)
                    for note in notes:
                        pitch = int(getattr(note, "pitch", 60) or 60)
                        # Note Expressions: chance/velocity at note-on (safe)
                        try:
                            abs_start_for_chance = float(note_start_beats)  # set below
                        except Exception:
                            abs_start_for_chance = 0.0
                        # velocity default from note, override if expression exists
                        try:
                            vel = int(effective_velocity(note))
                        except Exception:
                            vel = int(getattr(note, "velocity", 100) or 100)

                        note_start_beats = clip_start_beats + float(getattr(note, "start_beats", 0.0) or 0.0)
                        abs_start_for_chance = float(note_start_beats)
                        try:
                            if not should_play_note(clip_id=str(getattr(clip, "id", "")), note=note, abs_start_beats=abs_start_for_chance):
                                continue
                        except Exception:
                            pass
                        note_len_beats = float(getattr(note, "length_beats", 0.0) or 0.0)
                        # NOTE: beats_to_samples() ist eine Closure (samples_per_beat basiert bereits auf bpm/sr).
                        # Frühere Refactors haben hier versehentlich eine alte Signatur benutzt (beats,bpm,sr)
                        # und dadurch einen Runtime-Error ausgelöst: "takes 1 positional argument but 3 were given".
                        on_sample = int(round(beats_to_samples(note_start_beats)))
                        length_samples = int(round(beats_to_samples(note_len_beats)))
                        if length_samples <= 0:
                            length_samples = 1
                        off_sample = on_sample + length_samples
                        pitch_off = 0.0
                        _mpe_curve = []
                        _note_dur_samples = 0
                        try:
                            from pydaw.core.settings_store import get_settings  # type: ignore
                            _qs = get_settings()
                            _mpe = str(_qs.value("audio/note_expr_mpe_mode", False)).strip().lower() in ("1", "true", "yes", "on")
                        except Exception:
                            _mpe = False
                        if _mpe:
                            try:
                                pitch_off = float(effective_micropitch_note_start(note) or 0.0)
                            except Exception:
                                pitch_off = 0.0
                            # MPE v2: pass full curve for continuous bend
                            try:
                                from .note_expression_eval import micropitch_curve_points
                                _mpe_curve = micropitch_curve_points(note, steps=24)
                                if _mpe_curve:
                                    _note_dur_samples = max(1, off_sample - on_sample)
                            except Exception:
                                _mpe_curve = []
                        midi_events.append(PreparedMidiEvent(sample_pos=on_sample, track_id=track_id_str, pitch=pitch, velocity=int(vel), is_note_on=True, pitch_offset_semitones=float(pitch_off), micropitch_curve=list(_mpe_curve), note_duration_samples=int(_note_dur_samples)))
                        midi_events.append(PreparedMidiEvent(sample_pos=off_sample, track_id=track_id_str, pitch=pitch, velocity=0, is_note_on=False))
                    continue
            else:
                continue

            # Normalize channels to stereo
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            elif data.shape[1] >= 2:
                data = data[:, :2]

            # Resample (linear) if needed
            if int(file_sr) != int(sr) and data.shape[0] > 1:
                ratio = float(sr) / float(file_sr)
                n_out = max(1, int(round(data.shape[0] * ratio)))
                x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                data = np.vstack([
                    np.interp(x_new, x_old, data[:, 0]),
                    np.interp(x_new, x_old, data[:, 1]),
                ]).T.astype(np.float32, copy=False)

            # Cache base waveform (stereo float32 at target sample rate) BEFORE any tempo-stretch.
            if cache_path and data is not None:
                _cache_put(cache_path, sr, data)
            # Optional tempo sync (pitch-preserving time-stretch):
            # If the clip has a known `source_bpm`, we time-stretch to match the project BPM
            # WITHOUT changing pitch. Additionally apply per-clip time factor `clip.stretch`.
            source_bpm = float(getattr(clip, "source_bpm", 0.0) or 0.0)
            user_stretch = float(getattr(clip, "stretch", 1.0) or 1.0)

            tempo_ratio = (bpm / source_bpm) if (source_bpm > 0.0) else 1.0
            # Effective play-rate: >1 faster/shorter, <1 slower/longer
            # `clip.stretch` is a length-multiplier (2.0 => twice as long), so it divides the play-rate.
            effective_rate = float(tempo_ratio) / max(1e-6, float(user_stretch))

            if 0.25 <= effective_rate <= 4.0 and abs(effective_rate - 1.0) > 1e-3 and data.shape[0] > 1:
                # Prefer shared ArrangerRenderCache (reuses stretched buffers across Play/Stop).
                if arranger_cache is not None and cache_path:
                    try:
                        stretched = arranger_cache.get_stretched(str(cache_path), int(sr), float(effective_rate))
                        if stretched is not None:
                            data = stretched
                        else:
                            # fallback to local compute
                            from .time_stretch import time_stretch_stereo
                            data = time_stretch_stereo(data, rate=effective_rate, sr=sr)
                    except Exception:
                        effective_rate = 1.0
                else:
                    try:
                        from .time_stretch import time_stretch_stereo
                        data = time_stretch_stereo(data, rate=effective_rate, sr=sr)
                    except Exception:
                        # Never crash playback because of a stretch failure.
                        effective_rate = 1.0

            offset_s = float(getattr(clip, "offset_seconds", 0.0) or 0.0)
            offset_sample = max(0, int(round((offset_s * sr) / max(1e-6, effective_rate))))

            start_sample = beats_to_samples(float(getattr(clip, "start_beats", 0.0) or 0.0))
            clip_len_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)
            # If length is zero/invalid, play full file from offset
            if clip_len_beats <= 0:
                clip_len_samples = max(0, data.shape[0] - offset_sample)
            else:
                clip_len_samples = beats_to_samples(clip_len_beats)

            end_sample = start_sample + max(0, clip_len_samples)

            gain_l, gain_r = _pan_gains(float(getattr(track, "volume", 1.0) or 1.0), float(getattr(track, "pan", 0.0) or 0.0))

            prepared.append(
                self._PreparedAudioClip(
                    start_sample=start_sample,
                    end_sample=end_sample,
                    offset_sample=offset_sample,
                    data=data,
                    gain_l=gain_l,  # Fallback only
                    gain_r=gain_r,  # Fallback only
                    track_id=str(track.id),  # NEW v0.0.20.34: For atomic dict lookup
                )
            )

        prepared.sort(key=lambda c: c.start_sample)

        self.started_ok.emit(f"sounddevice gestartet (ARRANGEMENT, SR={sr}, Buffer={bs})")

        playhead = beats_to_samples(start_beat)

        # Loop region from Transport (beats -> samples)
        loop_enabled = bool(self._config.get("loop_enabled", False))
        loop_start_samp = beats_to_samples(float(self._config.get("loop_start_beat", 0.0) or 0.0))
        loop_end_samp = beats_to_samples(float(self._config.get("loop_end_beat", 0.0) or 0.0))

        # Guardrails: disable invalid loop settings
        if loop_enabled:
            if loop_end_samp <= loop_start_samp:
                loop_enabled = False
            # If playhead starts outside the loop, snap to loop start
            elif playhead < loop_start_samp or playhead >= loop_end_samp:
                playhead = loop_start_samp

        def callback(outdata, frames, _time, status):  # noqa: ANN001
            nonlocal playhead, last_gen, pull_sources
            if status:
                pass
            out = np.zeros((frames, 2), dtype=np.float32)
            start = playhead
            end = playhead + frames

            # Provide the *start* playhead to Transport before pull-sources run,
            # so ClipLauncher can sync sample-accurately (no 1-buffer latency).
            try:
                if self._transport_service is not None:
                    self._transport_service._set_external_playhead_samples(int(start), float(sr))
            except Exception:
                pass

            for c in prepared:
                if c.end_sample <= start:
                    continue
                if c.start_sample >= end:
                    break
                # overlap
                o_start = max(start, c.start_sample)
                o_end = min(end, c.end_sample)
                n = o_end - o_start
                if n <= 0:
                    continue
                out_off = o_start - start
                rel = o_start - c.start_sample
                src_start = c.offset_sample + rel
                src_end = src_start + n
                if src_start >= c.data.shape[0]:
                    continue
                if src_end > c.data.shape[0]:
                    src_end = c.data.shape[0]
                    n = src_end - src_start
                if n <= 0:
                    continue
                chunk = c.data[src_start:src_end]
                
                # NEW v0.0.20.37: Get LIVE gains (EXACTLY like Master!)
                track_id = getattr(c, "track_id", None)
                if track_id and audio_engine_ref:
                    # Direct dict lookup with defaults (LIKE MASTER: _master_volume fallback!)
                    vol = audio_engine_ref._track_volumes.get(track_id, 1.0)  # Default: 1.0 like baked-in
                    pan = audio_engine_ref._track_pans.get(track_id, 0.0)  # Default: 0.0 (center)
                    gain_l, gain_r = _pan_gains(vol, pan)
                else:
                    # Ultimate fallback: use baked-in gains
                    gain_l, gain_r = c.gain_l, c.gain_r
                
                out[out_off:out_off + n, 0] += chunk[:, 0] * gain_l
                out[out_off:out_off + n, 1] += chunk[:, 1] * gain_r

                # v0.0.20.41: Write per-track peak directly to AudioEngine (most reliable path)
                try:
                    if audio_engine_ref is not None and track_id and n > 0:
                        pk_l = float(np.max(np.abs(chunk[:n, 0]))) * abs(gain_l)
                        pk_r = float(np.max(np.abs(chunk[:n, min(1, chunk.shape[1]-1)]))) * abs(gain_r)
                        dp = audio_engine_ref._direct_peaks
                        old = dp.get(track_id, (0.0, 0.0))
                        dp[track_id] = (max(old[0], pk_l), max(old[1], pk_r))
                except Exception:
                    pass

                # v0.0.20.40: Per-track metering in arrangement callback
                # Update TrackMeterRing so VU meters move for each track during playback
                try:
                    hb = getattr(audio_engine_ref, "_hybrid_bridge", None) if audio_engine_ref else None
                    if hb is not None and track_id:
                        hcb = getattr(hb, "callback", None)
                        if hcb is not None:
                            idx = None
                            try_get = getattr(hb, "try_get_track_idx", None)
                            if callable(try_get):
                                idx = try_get(track_id)
                            if idx is None:
                                idx = hb.get_track_idx(track_id)
                            if idx is not None:
                                meter = hcb.get_track_meter(int(idx))
                                meter.update_from_block(chunk[:n], float(gain_l), float(gain_r))
                except Exception:
                    pass

            # Add pull sources (Sampler preview, synths, etc.)
            if audio_engine_ref is not None:
                # Advance RT param smoothing
                rt = getattr(audio_engine_ref, "rt_params", None)
                if rt is not None:
                    try:
                        rt.advance(int(frames), int(sr))
                    except Exception:
                        pass

                try:
                    gen, srcs = audio_engine_ref._pull_sources_snapshot(last_gen)
                    if gen != last_gen:
                        last_gen = gen
                        pull_sources = srcs
                except Exception:
                    pass
                # v0.0.20.52: Pull sources (Sampler/Drum/etc.) WITH per-track gain/pan + metering
                # Mirrors DSPJackEngine (Master/Hybrid) behavior.
                any_solo = False
                try:
                    if rt is not None:
                        any_solo = bool(rt.any_solo())
                except Exception:
                    any_solo = False

                hb = getattr(audio_engine_ref, "_hybrid_bridge", None)
                hcb = getattr(hb, "callback", None) if hb is not None else None

                for fn in (pull_sources or []):
                    try:
                        b = fn(int(frames), int(sr))
                        if b is None:
                            continue

                        b2 = b[:frames, :2]

                        # Optional per-track routing via metadata on pull fn
                        tid_attr = getattr(fn, "_pydaw_track_id", None)
                        tid = tid_attr() if callable(tid_attr) else tid_attr
                        tid = str(tid) if tid not in (None, "", "None") else ""

                        if tid and rt is not None:
                            # Mute/Solo gating
                            try:
                                if rt.is_track_muted(tid):
                                    continue
                            except Exception:
                                pass
                            try:
                                if any_solo and (not rt.is_track_solo(tid)):
                                    continue
                            except Exception:
                                pass

                            # Smoothed track vol/pan (default matches Track.model volume: 0.8 = -1.9 dB)
                            try:
                                tv = float(rt.get_smooth(rt.track_vol_key(tid), 0.8))
                            except Exception:
                                tv = 0.8
                            try:
                                tp = float(rt.get_smooth(rt.track_pan_key(tid), 0.0))
                            except Exception:
                                tp = 0.0

                            gl, gr = _pan_gains(tv, tp)

                            # v0.0.20.410: Audio-FX chain (post-instrument, pre-fader)
                            src = b2
                            try:
                                _fx_map = getattr(audio_engine_ref, "_track_audio_fx_map", None)
                                _fx = _fx_map.get(tid) if _fx_map else None
                            except Exception:
                                _fx = None
                            if _fx is not None:
                                try:
                                    _tmp_fx = pull_tmp_buf[:frames, :2]
                                    np.copyto(_tmp_fx, b2, casting="unsafe")
                                    _fx.process_inplace(_tmp_fx, int(frames), int(sr))
                                    src = _tmp_fx
                                except Exception:
                                    src = b2

                            # Direct peaks for reliable Mixer VU
                            try:
                                if audio_engine_ref is not None:
                                    pk_l = float(np.max(np.abs(src[:frames, 0]))) * abs(gl)
                                    pk_r = float(np.max(np.abs(src[:frames, 1]))) * abs(gr)
                                    dp = audio_engine_ref._direct_peaks
                                    old = dp.get(tid, (0.0, 0.0))
                                    dp[tid] = (max(old[0], pk_l), max(old[1], pk_r))
                            except Exception:
                                pass

                            # Hybrid per-track meter ring (optional)
                            try:
                                if hb is not None and hcb is not None:
                                    idx = None
                                    try_get = getattr(hb, "try_get_track_idx", None)
                                    if callable(try_get):
                                        idx = try_get(tid)
                                    if idx is None:
                                        # Avoid registering tracks from audio thread when possible.
                                        idx = hb.try_get_track_idx(tid) if hasattr(hb, "try_get_track_idx") else None
                                    if idx is not None:
                                        meter = hcb.get_track_meter(int(idx))
                                        meter.update_from_block(src, float(gl), float(gr))
                            except Exception:
                                pass

                            # Apply gains without allocations
                            try:
                                tmp = pull_tmp_buf[:frames, :2]
                                np.multiply(src[:frames, :2], (float(gl), float(gr)), out=tmp, casting="unsafe")
                                out[:frames, :2] += tmp
                            except Exception:
                                out[:frames, :2] += src[:frames, :2] * np.array([gl, gr], dtype=np.float32)
                        else:
                            out[:frames, :2] += b2
                    except Exception:
                        pass

            # Apply MASTER Volume/Pan (smoothed via RTParamStore)
            try:
                rt = getattr(audio_engine_ref, "rt_params", None) if audio_engine_ref else None
                if rt is not None:
                    master_vol = rt.get_smooth("master:vol", 0.8)
                    master_pan = rt.get_smooth("master:pan", 0.0)
                elif audio_engine_ref is not None:
                    master_vol = float(getattr(audio_engine_ref, "_master_volume", 1.0))
                    master_pan = float(getattr(audio_engine_ref, "_master_pan", 0.0))
                else:
                    master_vol = float(getattr(engine_self, "_master_volume", 1.0))
                    master_pan = float(getattr(engine_self, "_master_pan", 0.0))
                
                out *= master_vol
                
                if abs(master_pan) > 0.01:
                    # IMPORTANT (RT-safe):
                    # Never import inside the real-time audio callback.
                    # Import statements bind names locally and can cause
                    # UnboundLocalError for outer-scope closures (as seen
                    # with `_pan_gains`), plus they add avoidable overhead.
                    # We already have a closure-scope `_pan_gains()` above.
                    gain_l, gain_r = _pan_gains(1.0, master_pan)
                    out[:, 0] *= gain_l
                    out[:, 1] *= gain_r
            except Exception:
                pass  # Silent - realtime critical!
            
            # soft clamp
            np.clip(out, -1.0, 1.0, out=out)
            outdata[:frames, :2] = out.astype(outdata.dtype, copy=False)
            if outdata.shape[1] > 2:
                outdata[:, 2:] = 0

            # v0.0.20.41: Write master peak directly to AudioEngine
            try:
                if audio_engine_ref is not None and frames > 0:
                    mk_l = float(np.max(np.abs(out[:frames, 0])))
                    mk_r = float(np.max(np.abs(out[:frames, 1])))
                    old_m = audio_engine_ref._direct_peaks.get("__master__", (0.0, 0.0))
                    audio_engine_ref._direct_peaks["__master__"] = (max(old_m[0], mk_l), max(old_m[1], mk_r))
            except Exception:
                pass

            # Metering (Arrangement Mode): push the master block into the hybrid meter ring
            # so the Mixer VU can move continuously while looping/playing.
            try:
                hb = getattr(audio_engine_ref, "_hybrid_bridge", None) if audio_engine_ref else None
                if hb is not None:
                    hb.meter_ring.write(out[:frames, :2])
            except Exception:
                pass
            # advance playhead, handle looping with overflow preservation
            next_playhead = playhead + frames
            if loop_enabled and next_playhead >= loop_end_samp:
                overflow = next_playhead - loop_end_samp
                span = max(1, loop_end_samp - loop_start_samp)
                # Wrap overflow inside the loop span
                overflow = overflow % span
                playhead = loop_start_samp + overflow
            else:
                playhead = next_playhead

            # Sample-accurate Sync: Transport bekommt Playhead in Samples.
            try:
                if self._transport_service is not None:
                    self._transport_service._set_external_playhead_samples(int(playhead), float(sr))
            except Exception:
                # Keine harten Fehler im Audio-Callback.
                pass

        with sd.OutputStream(
            samplerate=sr,
            blocksize=bs,
            device=out_dev,
            channels=2,
            dtype="float32",
            callback=callback,
        ):
            while not self._stop_flag:
                self.msleep(20)


class AudioEngine(QObject):
    """High-level audio engine service."""

    backend_changed = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    running_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._backend: Backend = "none"
        self._engine_thread: Optional[_EngineThread] = None

        # Optional Binding: Project + Transport, um beim Abspielen echte
        # Audio-Clips aus dem Arranger auszugeben.
        self._bound_project_service: Any = None
        self._bound_transport_service: Any = None

        # Optional: JACK client service for realtime routing/playback
        self._bound_jack_service: Any = None
        self._jack_state: Any = None
        self._jack_prepare_thread = None
        
        # DSP engine (JACK mixing + master gain/pan)
        self._dsp_engine = None  # lazy

        # RT Parameter Store — smoothed, lock-free audio parameters
        from .rt_params import RTParamStore
        self.rt_params = RTParamStore(default_smooth_ms=5.0)
        self.rt_params.ensure("master:vol", 0.8)
        self.rt_params.ensure("master:pan", 0.0)

        # FIXED v0.0.19.7.14: Master Volume/Pan als LIVE Variable! ✅
        # Thread-Safe: Float read/write ist atomar in Python
        self._master_volume = 1.0  # 0.0 - 1.0
        self._master_pan = 0.0     # -1.0 - 1.0

        # NEW v0.0.20.33: Per-Track atomic storage (SAFE - not used by callback yet!)
        self._track_volumes = {}  # {track_id: float 0.0-1.0}
        self._track_pans = {}     # {track_id: float -1.0-1.0}
        self._track_mutes = {}    # {track_id: bool}
        self._track_solos = {}    # {track_id: bool}

        # v0.0.20.41: Direct peak storage — written from audio callback, read by mixer.
        # This bypasses the complex HybridBridge chain and provides reliable metering.
        # Keys: track_id (str) or "__master__". Values: (peak_l, peak_r) linear.
        self._direct_peaks: dict = {}  # {track_id_or_master: (float, float)}
        self._direct_peaks_decay = 0.92  # per GUI-read decay

        # v0.0.20.42: Sampler registry — wired to audio callback for live MIDI→Sampler
        self._sampler_registry: Any = None

        # v0.0.20.56: Compiled per-track Audio-FX chains (track_id -> ChainFx)
        # Stored in AudioEngine for sounddevice preview mixing and pushed into HybridEngineBridge.
        self._track_audio_fx_map: Dict[str, Any] = {}
        self._master_track_id: str = ""

        # v0.0.20.380: VST instrument engines (track_id -> Vst3InstrumentEngine)
        self._vst_instrument_engines: Dict[str, Any] = {}
        self._failed_vst_paths: set = set()  # v0.0.20.723: paths that failed deferred retry — don't retry again

        # v0.0.20.430: SF2 realtime engines (track_id -> FluidSynthRealtimeEngine)
        self._sf2_instrument_engines: Dict[str, Any] = {}

        # Shared arrangement render cache (decoded/resampled + tempo-stretched).
        # Used by both JACK prepare thread and sounddevice arrangement thread.
        try:
            from .arranger_cache import DEFAULT_ARRANGER_CACHE

            self._arranger_cache = DEFAULT_ARRANGER_CACHE
        except Exception:
            self._arranger_cache = None

        # v0.0.20.13: Hybrid Engine Bridge (lock-free ring-buffer communication)
        self._hybrid_bridge: Any = None
        if _HYBRID_AVAILABLE:
            try:
                self._hybrid_bridge = get_hybrid_bridge(rt_params=self.rt_params)
                self._hybrid_bridge.set_transport_ref(None)  # set later via bind_transport
            except Exception:
                self._hybrid_bridge = None

        # v0.0.20.13: Async Sample Loader
        self._async_loader = None
        if _HYBRID_AVAILABLE:
            try:
                self._async_loader = get_async_loader()
            except Exception:
                self._async_loader = None

        # v0.0.20.14: Essentia Worker Pool for time-stretch jobs
        self._essentia_pool = None
        if _ESSENTIA_POOL_AVAILABLE:
            try:
                self._essentia_pool = get_essentia_pool(
                    num_workers=4, cache_ref=self._arranger_cache)
            except Exception:
                self._essentia_pool = None


        # Pull sources (Sampler preview, synths, etc.)
        # Thread-safe: we replace the cached list object on updates.
        self._pull_sources_lock = threading.RLock()
        self._pull_sources_dict: Dict[str, Any] = {}
        self._pull_sources_list: List[Any] = []
        self._pull_sources_gen: int = 0
        self._backend = self.detect_best_backend().backend
        self.backend_changed.emit(self._backend)

    # --- public helpers

    def get_effective_sample_rate(self) -> int:
        """Return the currently configured sample-rate.

        We need a single source of truth for widgets that create realtime engines
        (ProSampler/ProDrum). Those engines used to be hard-coded to 48 kHz.
        If the user config uses 44.1 kHz, the engines would silently output
        nothing because their pull() functions checked sr==target_sr.

        Strategy:
        - If an audio thread is running and has a config, use it.
        - Otherwise fall back to QSettings (audio/sample_rate).
        - Last resort: 48000.
        """
        try:
            cfg = getattr(self, "_config", None)
            if isinstance(cfg, dict):
                sr = cfg.get("sample_rate", None)
                if sr is not None:
                    return int(sr)
        except Exception:
            pass

        try:
            from pydaw.core.settings import SettingsKeys
            from pydaw.core.settings_store import get_value

            keys = SettingsKeys()
            return int(get_value(keys.sample_rate, 48000))
        except Exception:
            return 48000

    # --- detection

    def detect_best_backend(self) -> AudioBackendInfo:
        """Prefer JACK (PipeWire-JACK), otherwise sounddevice."""
        jack_info = self._probe_jack()
        if jack_info.available:
            return jack_info

        sd_info = self._probe_sounddevice()
        if sd_info.available:
            return sd_info

        return AudioBackendInfo(backend="none", available=False, details="Kein Backend gefunden")

    def _probe_jack(self) -> AudioBackendInfo:
        pw_cli = shutil.which("pw-cli")
        qpwgraph = shutil.which("qpwgraph")
        pipewire_hint = []
        if pw_cli:
            pipewire_hint.append("pw-cli gefunden")
        if qpwgraph:
            pipewire_hint.append("qpwgraph gefunden")

        try:
            import jack  # type: ignore
        except Exception:
            details = "python-jack-client nicht installiert. "
            if pipewire_hint:
                details += f"PipeWire-Hinweis: {', '.join(pipewire_hint)}"
            else:
                details += "(PipeWire/JACK Status unbekannt)"
            return AudioBackendInfo(backend="jack", available=False, details=details)

        try:
            # Attempt to connect to JACK server (PipeWire-JACK or jackd)
            with _suppress_stderr_fd():
                c = jack.Client("pydaw_probe", no_start_server=True)  # type: ignore
            c.deactivate()
            c.close()
            details = "JACK Server erreichbar (evtl. PipeWire-JACK)."
            if pipewire_hint:
                details += f" {', '.join(pipewire_hint)}"
            return AudioBackendInfo(backend="jack", available=True, details=details)
        except Exception as exc:
            details = f"JACK Client vorhanden, aber Server nicht erreichbar: {exc}"
            if pipewire_hint:
                details += f" | {', '.join(pipewire_hint)}"
            return AudioBackendInfo(backend="jack", available=False, details=details)

    def _probe_sounddevice(self) -> AudioBackendInfo:
        try:
            import sounddevice as sd  # type: ignore
            with _suppress_stderr_fd():
                _ = sd.query_devices()
            return AudioBackendInfo(
                backend="sounddevice",
                available=True,
                details="sounddevice (PortAudio) verfügbar.",
            )
        except Exception as exc:
            return AudioBackendInfo(
                backend="sounddevice",
                available=False,
                details=f"sounddevice nicht verfügbar: {exc}",
            )

    # --- enumeration

    def list_inputs(self, backend: Optional[Backend] = None) -> List[AudioEndpoint]:
        b = backend or self._backend
        if b == "jack":
            return self._jack_list_capture_sources()
        if b == "sounddevice":
            return self._sd_list_inputs()
        return []

    def list_outputs(self, backend: Optional[Backend] = None) -> List[AudioEndpoint]:
        b = backend or self._backend
        if b == "jack":
            return self._jack_list_playback_sinks()
        if b == "sounddevice":
            return self._sd_list_outputs()
        return []

    def _sd_list_inputs(self) -> List[AudioEndpoint]:
        try:
            import sounddevice as sd  # type: ignore
            devs = sd.query_devices()
        except Exception:
            return []
        out: List[AudioEndpoint] = []
        for idx, d in enumerate(devs):
            if int(d.get("max_input_channels", 0)) > 0:
                out.append(AudioEndpoint(id=str(idx), label=f"[{idx}] {d.get('name')}"))  # type: ignore
        return out

    def _sd_list_outputs(self) -> List[AudioEndpoint]:
        try:
            import sounddevice as sd  # type: ignore
            devs = sd.query_devices()
        except Exception:
            return []
        out: List[AudioEndpoint] = []
        for idx, d in enumerate(devs):
            if int(d.get("max_output_channels", 0)) > 0:
                out.append(AudioEndpoint(id=str(idx), label=f"[{idx}] {d.get('name')}"))  # type: ignore
        return out

    def _jack_list_capture_sources(self) -> List[AudioEndpoint]:
        try:
            import jack  # type: ignore
            # libjack prints directly to stderr when no server is reachable.
            # We suppress that here to avoid terminal spam from mere enumeration.
            with _suppress_stderr_fd():
                c = jack.Client("pydaw_enum", no_start_server=True)  # type: ignore
            ports = list(c.get_ports(is_output=True))
            # PipeWire-JACK may not mark ports as physical; prefer system:capture* when present.
            sys_ports = [p for p in ports if p.name.startswith('system:')]
            if sys_ports:
                ports = [p for p in sys_ports if ('capture' in p.name.lower()) or ('input' in p.name.lower()) or p.name.startswith('system:')]
            else:
                ports = [p for p in ports if ('capture' in p.name.lower()) or ('input' in p.name.lower())]
            if not ports:
                ports = list(c.get_ports(is_output=True))
            out = [AudioEndpoint(id=p.name, label=p.name) for p in ports]
            c.close()
            return out
        except Exception:
            return []

    def _jack_list_playback_sinks(self) -> List[AudioEndpoint]:
        try:
            import jack  # type: ignore
            with _suppress_stderr_fd():
                c = jack.Client("pydaw_enum", no_start_server=True)  # type: ignore
            ports = list(c.get_ports(is_input=True))
            sys_ports = [p for p in ports if p.name.startswith('system:')]
            if sys_ports:
                ports = [p for p in sys_ports if ('playback' in p.name.lower()) or ('output' in p.name.lower()) or p.name.startswith('system:')]
            else:
                ports = [p for p in ports if ('playback' in p.name.lower()) or ('output' in p.name.lower())]
            if not ports:
                ports = list(c.get_ports(is_input=True))
            out = [AudioEndpoint(id=p.name, label=p.name) for p in ports]
            c.close()
            return out
        except Exception:
            return []

    # --- lifecycle (non-blocking skeleton)

    def start(self, backend: Optional[Backend] = None, config: Optional[Dict[str, Any]] = None) -> None:
        if self._engine_thread and self._engine_thread.isRunning():
            self.status.emit("Audio läuft bereits.")
            return

        b = backend or self._backend
        cfg = dict(config or {})
        cfg.setdefault("audio_engine_ref", self)

        self._engine_thread = _EngineThread(b, cfg)
        self._engine_thread.started_ok.connect(self.status.emit)
        self._engine_thread.error.connect(self.error.emit)
        self._engine_thread.stopped_ok.connect(lambda: self.status.emit("Audio gestoppt."))
        self._engine_thread.start()

    def stop(self) -> None:
        """Stoppt jede aktive Wiedergabe (sounddevice *und* JACK).

        Wichtig: JACK-Playback nutzt aktuell keinen _EngineThread (es läuft über
        einen Render-Callback im JackClientService). In diesem Modus MUSS stop()
        trotzdem den Callback entfernen – sonst läuft Audio trotz Transport-Stop
        weiter.
        """

        # 1) sounddevice / thread-based engine
        try:
            if self._engine_thread is not None:
                self._engine_thread.request_stop()
                self._engine_thread.wait(1500)
        finally:
            self._engine_thread = None

        # 2) JACK: Render callback entfernen + State zurücksetzen
        # Clear DSP arrangement source (if present)
        try:
            if self._dsp_engine is not None:
                self._dsp_engine.set_arrangement_state(None)
        except Exception:
            pass
        try:
            if self._bound_jack_service is not None:
                self._bound_jack_service.clear_render_callback()
        except Exception:
            pass

        # 2b) Clear hybrid bridge state (prevents ghost audio after stop)
        try:
            hb = getattr(self, "_hybrid_bridge", None)
            if hb is not None:
                hcb = getattr(hb, "callback", None)
                if hcb is not None:
                    if hasattr(hcb, "set_arrangement_state"):
                        hcb.set_arrangement_state(None)
        except Exception:
            pass

        try:
            self._jack_state = None
        except Exception:
            pass

        # 3) Flush VU meters / direct peaks (prevents ghost meters after stop)
        try:
            dp = getattr(self, "_direct_peaks", None)
            if dp is not None:
                dp.clear()
        except Exception:
            pass

        # 4) Transport-Clock (Audio-Engine) wieder freigeben
        try:
            if self._bound_transport_service is not None:
                # beide Namen existieren je nach Version
                if hasattr(self._bound_transport_service, "_clear_external_playhead"):
                    self._bound_transport_service._clear_external_playhead()
                elif hasattr(self._bound_transport_service, "_clear_external_clock"):
                    self._bound_transport_service._clear_external_clock()
        except Exception:
            pass

    def bind_transport(self, project_service: Any, transport_service: Any) -> None:
        """Bindet ProjectService + TransportService, sodass Transport-Play
        automatisch Audio-Clips aus dem Arranger ausgibt.

        Diese Bindung ist optional; ohne Bindung bleibt der Engine-Output bei
        "Silence" (nur Status/Backendverwaltung).
        """
        self._bound_project_service = project_service
        self._bound_transport_service = transport_service

        # v0.0.20.13: Wire transport to hybrid bridge
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_transport_ref(transport_service)
                # v0.0.20.28: ensure stable track-id→index mapping for Live/Preview per-track faders
                try:
                    proj = getattr(project_service, "ctx", None).project if hasattr(project_service, "ctx") else None
                    tracks = getattr(proj, "tracks", []) if proj is not None else []
                    mapping = {str(getattr(t, "id", "")): int(i) for i, t in enumerate(tracks) if str(getattr(t, "id", ""))}
                    if mapping:
                        self._hybrid_bridge.set_track_index_map(mapping)
                except Exception:
                    pass
        except Exception:
            pass

        # v0.0.20.56: Build/push per-track Audio-FX maps on bind
        try:
            proj = None
            try:
                proj = copy.deepcopy(getattr(project_service, "ctx", None).project) if hasattr(project_service, "ctx") else None
            except Exception:
                proj = getattr(project_service, "ctx", None).project if hasattr(project_service, "ctx") else None
            if proj is not None:
                self.rebuild_fx_maps(proj)
        except Exception:
            pass

        # Transport->Audio: Beim Starten Wiedergabe anwerfen, beim Stoppen schließen
        try:
            transport_service.playing_changed.connect(self._on_transport_playing_changed)
            transport_service.loop_changed.connect(self._on_transport_params_changed)
            transport_service.bpm_changed.connect(self._on_transport_params_changed)
            transport_service.time_signature_changed.connect(self._on_transport_params_changed)
        except Exception:
            # Nicht hart fehlschlagen – UI kann trotzdem laufen.
            pass


    def rebuild_fx_maps(self, project_snapshot: Any) -> None:
        """Compile per-track Audio-FX chains and push them to the audio thread.

        v0.0.20.56:
        - Build `ChainFx` objects from each track's `audio_fx_chain`
        - Ensure RTParamStore parameters exist for those FX
        - Push dict(track_id -> ChainFx) into HybridEngineBridge + keep a copy for preview mixing
        """
        try:
            from .fx_chain import build_track_fx_map, ensure_track_fx_params
        except Exception:
            return

        try:
            ensure_track_fx_params(project_snapshot, self.rt_params)
        except Exception:
            pass

        try:
            sr = 48000
            try:
                sr = int(self.get_effective_sample_rate())
            except Exception:
                sr = 48000
            fx_map = build_track_fx_map(project_snapshot, self.rt_params, max_frames=8192, sr=sr)
        except Exception:
            fx_map = {}

        try:
            self._track_audio_fx_map = dict(fx_map) if fx_map else {}
        except Exception:
            self._track_audio_fx_map = {}

        try:
            tracks = list(getattr(project_snapshot, "tracks", []) or [])
            master = next((t for t in tracks if str(getattr(t, "kind", "") or "") == "master"), None)
            self._master_track_id = str(getattr(master, "id", "") or "") if master is not None else ""
        except Exception:
            self._master_track_id = ""

        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "set_track_audio_fx_map"):
                self._hybrid_bridge.set_track_audio_fx_map(self._track_audio_fx_map)
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "set_master_track_id"):
                self._hybrid_bridge.set_master_track_id(self._master_track_id)
        except Exception:
            pass

        # v0.0.20.357: Compute and push group-bus routing map
        # v0.0.20.641: Extended with output_target_id (AP5 Phase 5C)
        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "callback"):
                hcb = self._hybrid_bridge.callback
                if hasattr(hcb, "set_group_bus_map"):
                    tracks = list(getattr(project_snapshot, "tracks", []) or [])
                    idx_map = {str(getattr(t, "id", "")): int(i) for i, t in enumerate(tracks) if str(getattr(t, "id", ""))}
                    child_to_group: dict = {}     # child_track_idx -> group_track_idx
                    group_idxs: set = set()        # group track indices
                    child_id_to_group: dict = {}   # child_track_id -> group_track_idx
                    for t in tracks:
                        if str(getattr(t, "kind", "") or "") == "group":
                            gid = str(getattr(t, "id", "") or "")
                            gi = idx_map.get(gid)
                            if gi is not None:
                                group_idxs.add(int(gi))
                                # Find children of this group
                                for ct in tracks:
                                    if str(getattr(ct, "track_group_id", "") or "") == gid:
                                        ci = idx_map.get(str(getattr(ct, "id", "") or ""))
                                        if ci is not None:
                                            child_to_group[int(ci)] = int(gi)
                                            child_id_to_group[str(getattr(ct, "id", ""))] = int(gi)
                    # v0.0.20.641: output_target_id overrides group routing (AP5 Phase 5C)
                    # If a track has explicit output_target_id → route there instead of master
                    for t in tracks:
                        out_id = str(getattr(t, "output_target_id", "") or "").strip()
                        if not out_id:
                            continue
                        tid = str(getattr(t, "id", "") or "")
                        ti = idx_map.get(tid)
                        oi = idx_map.get(out_id)
                        if ti is not None and oi is not None and ti != oi:
                            child_to_group[int(ti)] = int(oi)
                            child_id_to_group[tid] = int(oi)
                            # Ensure target is in group_idxs so it gets processed
                            group_idxs.add(int(oi))
                    hcb.set_group_bus_map(child_to_group, group_idxs, child_id_to_group)
        except Exception:
            pass

        # v0.0.20.518: Compute and push send-FX bus routing map
        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "callback"):
                hcb = self._hybrid_bridge.callback
                if hasattr(hcb, "set_send_bus_map"):
                    tracks = list(getattr(project_snapshot, "tracks", []) or [])
                    idx_map = {str(getattr(t, "id", "")): int(i) for i, t in enumerate(tracks) if str(getattr(t, "id", ""))}
                    send_map: dict = {}        # source_idx -> [(fx_idx, amount, pre_fader)]
                    fx_idxs: set = set()       # FX track indices
                    send_id_map: dict = {}     # source_tid -> [(fx_idx, amount, pre_fader)]
                    # Collect FX tracks
                    for t in tracks:
                        if str(getattr(t, "kind", "") or "") == "fx":
                            fi = idx_map.get(str(getattr(t, "id", "") or ""))
                            if fi is not None:
                                fx_idxs.add(int(fi))
                    # Collect sends from all tracks
                    for t in tracks:
                        sends = list(getattr(t, "sends", []) or [])
                        if not sends:
                            continue
                        src_id = str(getattr(t, "id", "") or "")
                        si = idx_map.get(src_id)
                        if si is None:
                            continue
                        for s in sends:
                            if not isinstance(s, dict):
                                continue
                            target_id = str(s.get("target_track_id") or "").strip()
                            amount = float(s.get("amount", 0.0) or 0.0)
                            pre_fader = bool(s.get("pre_fader", False))
                            fi = idx_map.get(target_id)
                            if fi is not None and amount > 0.0:
                                entry = (int(fi), float(amount), bool(pre_fader))
                                send_map.setdefault(int(si), []).append(entry)
                                send_id_map.setdefault(src_id, []).append(entry)
                    hcb.set_send_bus_map(send_map, fx_idxs, send_id_map)
        except Exception:
            pass

        # v0.0.20.641: Compute and push sidechain routing map (AP5 Phase 5B)
        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "callback"):
                hcb = self._hybrid_bridge.callback
                if hasattr(hcb, "set_sidechain_map"):
                    tracks = list(getattr(project_snapshot, "tracks", []) or [])
                    idx_map = {str(getattr(t, "id", "")): int(i) for i, t in enumerate(tracks) if str(getattr(t, "id", ""))}
                    sc_map: dict = {}      # dest_track_idx -> source_track_idx
                    sc_id_map: dict = {}   # dest_track_id -> source_track_id
                    for t in tracks:
                        sc_src = str(getattr(t, "sidechain_source_id", "") or "").strip()
                        if not sc_src:
                            continue
                        dest_id = str(getattr(t, "id", "") or "")
                        di = idx_map.get(dest_id)
                        si = idx_map.get(sc_src)
                        if di is not None and si is not None and di != si:
                            sc_map[int(di)] = int(si)
                            sc_id_map[dest_id] = sc_src
                    hcb.set_sidechain_map(sc_map, sc_id_map)
        except Exception:
            pass

        # v0.0.20.641: Compute and push channel config map (AP5 Phase 5C)
        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "callback"):
                hcb = self._hybrid_bridge.callback
                if hasattr(hcb, "set_channel_config_map"):
                    tracks = list(getattr(project_snapshot, "tracks", []) or [])
                    cc_map: dict = {}
                    for i, t in enumerate(tracks):
                        ch = str(getattr(t, "channel_config", "stereo") or "stereo").strip()
                        if ch == "mono":
                            cc_map[int(i)] = "mono"
                    hcb.set_channel_config_map(cc_map)
        except Exception:
            pass

        # v0.0.20.653: Compute and push multi-output plugin routing map (AP5 Phase 5C wiring)
        try:
            if self._hybrid_bridge is not None and hasattr(self._hybrid_bridge, "set_plugin_output_map"):
                tracks = list(getattr(project_snapshot, "tracks", []) or [])
                po_map: dict = {}  # parent_track_id -> {output_idx: child_track_id}
                for t in tracks:
                    routing = getattr(t, "plugin_output_routing", None)
                    if not isinstance(routing, dict) or not routing:
                        continue
                    output_count = int(getattr(t, "plugin_output_count", 0) or 0)
                    if output_count < 2:
                        continue
                    parent_tid = str(getattr(t, "id", "") or "")
                    if not parent_tid:
                        continue
                    out_routes: dict = {}
                    for out_idx_raw, child_tid in routing.items():
                        try:
                            out_idx = int(out_idx_raw)
                            child_tid = str(child_tid or "").strip()
                            if out_idx >= 1 and child_tid:
                                out_routes[out_idx] = child_tid
                        except (ValueError, TypeError):
                            continue
                    if out_routes:
                        po_map[parent_tid] = out_routes
                self._hybrid_bridge.set_plugin_output_map(po_map)
                # Tag existing pull sources with their output count so the audio
                # callback can split multi-channel buffers correctly.
                if po_map:
                    try:
                        with self._pull_sources_lock:
                            for _name, fn in self._pull_sources_dict.items():
                                try:
                                    tid_attr = getattr(fn, "_pydaw_track_id", None)
                                    tid_val = tid_attr() if callable(tid_attr) else tid_attr
                                    tid_val = str(tid_val) if tid_val not in (None, "", "None") else ""
                                    if tid_val and tid_val in po_map:
                                        # Find the track's output count
                                        for t in tracks:
                                            if str(getattr(t, "id", "")) == tid_val:
                                                oc = int(getattr(t, "plugin_output_count", 1) or 1)
                                                fn._pydaw_output_count = oc  # type: ignore[attr-defined]
                                                break
                                    else:
                                        fn._pydaw_output_count = 1  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            pass

        # v0.0.20.380: Create Vst3InstrumentEngine for VST instruments detected in FX chains
        # These are instruments (MIDI→Audio) that were skipped in ChainFx._compile_devices
        # and must be hosted as pull sources with SamplerRegistry MIDI routing.
        try:
            self._create_vst_instrument_engines(fx_map, sr, project_snapshot)
        except Exception as _ie_exc:
            import traceback
            print(f"[VST3-INST] instrument engine creation failed: {_ie_exc}", file=__import__('sys').stderr, flush=True)
            traceback.print_exc(file=__import__('sys').stderr)

        # v0.0.20.430: Create FluidSynth realtime engines for SF2 instrument tracks
        # Enables live MIDI keyboard → SF2 SoundFont audio output.
        try:
            self._create_sf2_instrument_engines(sr, project_snapshot)
        except Exception as _sf2_exc:
            import traceback
            print(f"[SF2-RT] SF2 engine creation failed: {_sf2_exc}", file=__import__('sys').stderr, flush=True)
            traceback.print_exc(file=__import__('sys').stderr)

    def bind_jack(self, jack_service: Any) -> None:
        """Bind JackClientService for JACK backend playback/recording."""
        self._bound_jack_service = jack_service

    def _create_vst_instrument_engines(self, fx_map: Dict[str, Any], sr: int,
                                        project_snapshot: Any = None) -> None:
        """Create or REUSE Vst3InstrumentEngine instances for VST instruments.

        v0.0.20.384: CRITICAL FIX — reuse existing engines if they match the same
        VST path. Previously, every rebuild_fx_maps() call destroyed and recreated
        the Surge XT plugin from scratch (load_plugin takes ~2s), causing:
        - GUI freeze ("python3 antwortet nicht")
        - Audio glitches (plugin destroyed mid-playback → 'NoneType' process error)
        - Wrong pitches ("bleeps in C8 range" from uninitialized plugin state)
        Now: if an engine already exists and is _ok for the same track+path, keep it.
        """
        import sys

        # Save old engines — we'll reuse matching ones instead of destroying
        old_engines = dict(self._vst_instrument_engines)
        self._vst_instrument_engines = {}

        try:
            from pydaw.audio.vst3_host import Vst3InstrumentEngine
        except ImportError:
            Vst3InstrumentEngine = None

        # v0.0.20.392: Also import VST2 instrument engine
        try:
            from pydaw.audio.vst2_host import Vst2InstrumentEngine
        except ImportError:
            Vst2InstrumentEngine = None

        # v0.0.20.457: Also import CLAP instrument engine
        try:
            from pydaw.audio.clap_host import ClapInstrumentEngine
        except ImportError:
            ClapInstrumentEngine = None

        if Vst3InstrumentEngine is None and Vst2InstrumentEngine is None and ClapInstrumentEngine is None:
            for old_eng in old_engines.values():
                try:
                    if hasattr(old_eng, "shutdown"):
                        old_eng.shutdown()
                except Exception:
                    pass
            return

        # ── Phase 1: Collect instrument specs from ChainFx detection ──
        inst_candidates: list = []  # [(tid, did, params, vst_ref, vst_plugin_name)]

        if fx_map:
            for tid, chain_fx in fx_map.items():
                if chain_fx is None:
                    continue
                inst_specs = getattr(chain_fx, "instrument_device_specs", None)
                if not inst_specs:
                    continue
                spec = inst_specs[0]
                # Support both VST and CLAP instrument specs
                ref = str(spec.get("vst_ref") or spec.get("clap_ref") or "")
                name = str(spec.get("vst_plugin_name") or spec.get("clap_plugin_id") or "")
                inst_candidates.append((
                    tid,
                    str(spec.get("id") or ""),
                    spec.get("params") or {},
                    ref,
                    name,
                ))

        # ── Phase 2: Fallback — scan project for ext.vst3 that failed in ChainFx ──
        already_found = {c[0] for c in inst_candidates}
        if project_snapshot is not None:
            try:
                tracks = list(getattr(project_snapshot, "tracks", []) or [])
                for t in tracks:
                    tid = str(getattr(t, "id", "") or "")
                    if not tid or tid in already_found:
                        continue
                    chain = getattr(t, "audio_fx_chain", None)
                    if not isinstance(chain, dict):
                        continue
                    devices = chain.get("devices") or []
                    if not isinstance(devices, list):
                        continue
                    for dev in devices:
                        if not isinstance(dev, dict):
                            continue
                        if dev.get("enabled", True) is False:
                            continue
                        pid = str(dev.get("plugin_id") or dev.get("type") or "")
                        if not (pid.startswith("ext.vst3:") or pid.startswith("ext.vst2:") or pid.startswith("ext.clap:")):
                            continue
                        did = str(dev.get("id") or dev.get("device_id") or "")
                        params = dev.get("params", {}) if isinstance(dev.get("params", {}), dict) else {}
                        vst_ref = pid.split(":", 1)[1] if ":" in pid else ""
                        vst_ref = str(params.get("__ext_ref") or vst_ref)
                        vst_plugin_name = str(params.get("__ext_plugin_name") or "")
                        has_working_fx = False
                        if fx_map:
                            chain_fx_obj = fx_map.get(tid)
                            if chain_fx_obj is not None:
                                for fx_dev in getattr(chain_fx_obj, "devices", []):
                                    if str(getattr(fx_dev, "device_id", "")) == did:
                                        if getattr(fx_dev, "_ok", False):
                                            has_working_fx = True
                                        break
                        if has_working_fx:
                            continue
                        inst_candidates.append((tid, did, params, vst_ref, vst_plugin_name))
                        break
            except Exception:
                pass

        # ── Phase 3: Create or REUSE engines ──
        reused_tids = set()
        for (tid, did, params, vst_ref, vst_plugin_name) in inst_candidates:
            if not vst_ref:
                continue

            # v0.0.20.384 / v0.0.20.471: CHECK if we already have a working engine for this track.
            # CLAP refs are stored as "/path/plugin.clap::plugin.id" while the live
            # ClapInstrumentEngine keeps `path` and `plugin_id_str` separately.  A plain
            # `engine.path == vst_ref` comparison therefore fails for CLAP and forces an
            # unnecessary engine reload on harmless UI/project refreshes.  That can leave
            # the editor attached to an older instance while audio renders from a fresh
            # default-state engine, which makes preset changes appear ineffective.
            old_eng = old_engines.get(tid)
            _is_clap = vst_ref.endswith(".clap") or ("::" in vst_ref and vst_ref.split("::")[0].rstrip().endswith(".clap"))
            _is_vst2 = (not _is_clap) and vst_ref.endswith(".so") and not vst_ref.endswith(".vst3")
            _can_reuse = False
            if (old_eng is not None and getattr(old_eng, "_ok", False)
                    and getattr(old_eng, "_plugin", None) is not None):
                try:
                    if _is_clap:
                        from pydaw.audio.clap_host import split_plugin_reference
                        _old_path = str(getattr(old_eng, "path", "") or "")
                        _old_pid = str(getattr(old_eng, "plugin_id_str", "") or "")
                        _ref_path, _ref_pid = split_plugin_reference(vst_ref)
                        if not _ref_pid:
                            _ref_pid = vst_plugin_name
                        _can_reuse = (_old_path == str(_ref_path or "") and _old_pid == str(_ref_pid or ""))
                    else:
                        _can_reuse = (getattr(old_eng, "path", "") == vst_ref)
                except Exception:
                    _can_reuse = False
            if _can_reuse:
                # REUSE — don't reload the plugin!
                self._vst_instrument_engines[tid] = old_eng
                reused_tids.add(tid)
                _reuse_label = "CLAP-INST" if _is_clap else "VST3-INST"
                print(f"[{_reuse_label}] Reusing existing engine for track={tid} (no reload)",
                      file=sys.stderr, flush=True)
            else:
                # Create new engine — pick VST2, VST3, or CLAP based on file type / reference
                # v0.0.20.723: Probe plugin in child process before loading in main process.
                # If probe crashes (SEGFAULT), plugin is blacklisted and skipped.
                _probe_path = vst_ref
                _probe_type = "vst3"
                _probe_name = vst_plugin_name
                _probe_id = ""
                if _is_clap:
                    _probe_type = "clap"
                    try:
                        from pydaw.audio.clap_host import split_plugin_reference
                        _p, _pid = split_plugin_reference(vst_ref)
                        _probe_path = _p
                        _probe_id = _pid or vst_plugin_name
                    except Exception:
                        pass
                elif _is_vst2:
                    _probe_type = "vst2"

                try:
                    from pydaw.services.plugin_probe import is_plugin_safe
                    if not is_plugin_safe(_probe_path, _probe_type,
                                          plugin_name=_probe_name,
                                          plugin_id=_probe_id):
                        print(f"[PROBE] 💀 Skipping crashed plugin for track {tid}: {vst_ref}",
                              file=sys.stderr, flush=True)
                        continue
                except ImportError:
                    pass  # probe module not available — proceed without check
                except Exception as exc:
                    print(f"[PROBE] Warning: probe failed for {vst_ref}: {exc}",
                          file=sys.stderr, flush=True)

                # IMPORTANT: Check .clap BEFORE :: because VST3 refs also use :: format
                try:
                    if _is_clap and ClapInstrumentEngine is not None:
                        from pydaw.audio.clap_host import split_plugin_reference
                        clap_path, clap_pid = split_plugin_reference(vst_ref)
                        if not clap_pid:
                            clap_pid = vst_plugin_name
                        engine = ClapInstrumentEngine(
                            path=clap_path,
                            plugin_id=clap_pid,
                            track_id=tid,
                            sr=sr,
                            block_size=8192,
                            params=params,
                        )
                        _label = "CLAP-INST"
                    elif _is_vst2 and Vst2InstrumentEngine is not None:
                        engine = Vst2InstrumentEngine(
                            path=vst_ref,
                            plugin_name=vst_plugin_name,
                            track_id=tid,
                            device_id=did,
                            rt_params=self.rt_params,
                            params=params,
                            sr=sr,
                            max_frames=8192,
                        )
                        _label = "VST2-INST"
                    elif Vst3InstrumentEngine is not None:
                        engine = Vst3InstrumentEngine(
                            path=vst_ref,
                            plugin_name=vst_plugin_name,
                            track_id=tid,
                            device_id=did,
                            rt_params=self.rt_params,
                            params=params,
                            sr=sr,
                            max_frames=8192,
                        )
                        _label = "VST3-INST"
                    else:
                        print(f"[VST-INST] No engine class available for {vst_ref}",
                              file=sys.stderr, flush=True)
                        continue
                except Exception as exc:
                    print(f"[{_label if '_label' in dir() else 'VST-INST'}] Failed to create engine for track {tid}: {exc}",
                          file=sys.stderr, flush=True)
                    continue

                if not getattr(engine, "_ok", False):
                    _err = getattr(engine, "_err", "unknown")
                    print(f"[{_label}] Engine not OK for track {tid}: {_err}",
                          file=sys.stderr, flush=True)
                    continue

                self._vst_instrument_engines[tid] = engine
                print(f"[{_label}] Created NEW engine for track={tid}",
                      file=sys.stderr, flush=True)

            engine = self._vst_instrument_engines[tid]

            # Register in SamplerRegistry (MIDI routing) — ALWAYS, not conditional
            try:
                reg = self._sampler_registry
                if reg is not None:
                    reg.register(tid, engine)
                    print(f"[VST3-INST] SamplerRegistry: track={tid} ✓", file=sys.stderr, flush=True)
                else:
                    print(f"[VST3-INST] WARNING: _sampler_registry is None!", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[VST3-INST] SamplerRegistry FAILED for {tid}: {exc}", file=sys.stderr, flush=True)

            # Register/update pull source (audio output)
            try:
                pull_name = f"vstinst:{tid}:{did}"
                _engine_ref = engine
                def _pull_fn(frames, sr, _eng=_engine_ref):
                    return _eng.pull(frames, sr)
                _pull_fn._pydaw_track_id = tid  # type: ignore[attr-defined]
                # v0.0.20.653: Tag output count for multi-output plugin routing
                _pull_fn._pydaw_output_count = 1  # type: ignore[attr-defined]
                self.register_pull_source(pull_name, _pull_fn)
                print(f"[VST3-INST] Pull source: {pull_name} ✓", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[VST3-INST] Pull source registration failed for {tid}: {exc}",
                      file=sys.stderr, flush=True)

        # ── Phase 3b (v0.0.20.539): Instrument Layer containers ──
        # Scan project for chrono.container.instrument_layer devices.
        # For each layer with an instrument, create a separate engine.
        # Register a dispatcher that fans MIDI to all layer engines.
        if project_snapshot is not None:
            try:
                tracks = list(getattr(project_snapshot, "tracks", []) or [])
                print(f"[INST-LAYER] Scanning {len(tracks)} tracks for instrument layers...",
                      file=sys.stderr, flush=True)
                for t in tracks:
                    tid = str(getattr(t, "id", "") or "")
                    if not tid:
                        continue
                    # v0.0.20.552: Don't skip tracks with normal instruments —
                    # instrument layers can coexist (they use different registry keys)
                    chain = getattr(t, "audio_fx_chain", None)
                    if not isinstance(chain, dict):
                        continue
                    devices = chain.get("devices") or []
                    if not isinstance(devices, list):
                        continue
                    for dev in devices:
                        if not isinstance(dev, dict):
                            continue
                        pid = str(dev.get("plugin_id") or "")
                        if pid != "chrono.container.instrument_layer":
                            continue
                        print(f"[INST-LAYER] Found container on track {tid}",
                              file=sys.stderr, flush=True)
                        layers = dev.get("layers", []) or []
                        layer_engines = []
                        for li, layer in enumerate(layers):
                            if not isinstance(layer, dict):
                                continue
                            if not bool(layer.get("enabled", True)):
                                continue
                            inst_pid = str(layer.get("instrument") or "")
                            if not inst_pid:
                                continue
                            # Determine format and create engine
                            _layer_key = f"{tid}:ilayer:{li}"
                            # Check for reuse
                            old_layer_eng = old_engines.get(_layer_key)
                            if old_layer_eng is not None and getattr(old_layer_eng, "_ok", False):
                                layer_engines.append(old_layer_eng)
                                self._vst_instrument_engines[_layer_key] = old_layer_eng
                                reused_tids.add(_layer_key)
                                print(f"[INST-LAYER] Reusing engine for {_layer_key}",
                                      file=sys.stderr, flush=True)
                                continue
                            # Parse instrument reference
                            inst_params = {}
                            _is_vst3 = inst_pid.startswith("ext.vst3:")
                            _is_vst2 = inst_pid.startswith("ext.vst2:")
                            _is_clap = inst_pid.startswith("ext.clap:")
                            _is_builtin = inst_pid.startswith("chrono.")
                            ref = inst_pid.split(":", 1)[1] if ":" in inst_pid else ""
                            try:
                                engine = None
                                # v0.0.20.542: Built-in instrument support for layers
                                if _is_builtin:
                                    if inst_pid == "chrono.aeterna":
                                        try:
                                            from pydaw.plugins.aeterna.aeterna_engine import AeternaEngine
                                            engine = AeternaEngine(target_sr=sr)
                                        except Exception:
                                            pass
                                    elif inst_pid == "chrono.sampler":
                                        try:
                                            from pydaw.plugins.sampler.sampler_engine import ProSamplerEngine
                                            engine = ProSamplerEngine(target_sr=sr)
                                        except Exception:
                                            pass
                                    elif inst_pid == "chrono.drum_machine":
                                        try:
                                            from pydaw.plugins.drum_machine.drum_engine import DrumMachineEngine
                                            engine = DrumMachineEngine(target_sr=sr)
                                        except Exception:
                                            pass
                                    elif inst_pid == "chrono.bach_orgel":
                                        try:
                                            from pydaw.plugins.bach_orgel.bach_orgel_engine import BachOrgelEngine
                                            engine = BachOrgelEngine(target_sr=sr)
                                        except Exception:
                                            pass
                                    elif inst_pid == "chrono.fusion":
                                        # v0.0.20.574: Fusion semi-modular synth
                                        try:
                                            from pydaw.plugins.fusion.fusion_engine import FusionEngine
                                            engine = FusionEngine(target_sr=sr)
                                        except Exception:
                                            pass
                                    elif inst_pid == "chrono.sf2":
                                        # v0.0.20.543: SF2 Soundfont as layer instrument
                                        try:
                                            from pydaw.audio.sf2_engine import FluidSynthRealtimeEngine
                                            _sf2_path = str(layer.get("sf2_path") or "")
                                            _sf2_bank = int(layer.get("sf2_bank", 0))
                                            _sf2_preset = int(layer.get("sf2_preset", 0))
                                            if _sf2_path:
                                                engine = FluidSynthRealtimeEngine(
                                                    sf2_path=_sf2_path, bank=_sf2_bank,
                                                    preset=_sf2_preset, sr=sr, track_id=tid,
                                                )
                                        except Exception:
                                            pass
                                    # Built-in engines don't have _ok; check for note_on + pull
                                    if engine is not None and hasattr(engine, "note_on") and hasattr(engine, "pull"):
                                        engine._ok = True  # Tag for reuse check
                                        layer_engines.append(engine)
                                        self._vst_instrument_engines[_layer_key] = engine
                                        print(f"[INST-LAYER] Created built-in engine for {_layer_key}: {inst_pid}",
                                              file=sys.stderr, flush=True)
                                        engine = None  # Prevent generic append below
                                    elif engine is not None:
                                        print(f"[INST-LAYER] Built-in engine missing interface for {_layer_key}: {inst_pid}",
                                              file=sys.stderr, flush=True)
                                        engine = None  # Prevent generic append below
                                elif _is_clap and ClapInstrumentEngine is not None:
                                    from pydaw.audio.clap_host import split_plugin_reference
                                    clap_path, clap_pid = split_plugin_reference(ref)
                                    engine = ClapInstrumentEngine(
                                        path=clap_path, plugin_id=clap_pid or "",
                                        track_id=tid, sr=sr, block_size=8192,
                                        params=inst_params,
                                    )
                                elif _is_vst2 and Vst2InstrumentEngine is not None:
                                    engine = Vst2InstrumentEngine(
                                        path=ref, plugin_name="", track_id=tid,
                                        device_id="", rt_params=self.rt_params,
                                        params=inst_params, sr=sr, max_frames=8192,
                                    )
                                elif _is_vst3 and Vst3InstrumentEngine is not None:
                                    engine = Vst3InstrumentEngine(
                                        path=ref, plugin_name="", track_id=tid,
                                        device_id="", rt_params=self.rt_params,
                                        params=inst_params, sr=sr, max_frames=8192,
                                    )
                                if engine is not None and getattr(engine, "_ok", False):
                                    layer_engines.append(engine)
                                    self._vst_instrument_engines[_layer_key] = engine
                                    print(f"[INST-LAYER] Created engine for {_layer_key}: {inst_pid}",
                                          file=sys.stderr, flush=True)
                                elif engine is not None:
                                    print(f"[INST-LAYER] Engine not OK for {_layer_key}: {getattr(engine, '_err', '?')}",
                                          file=sys.stderr, flush=True)
                            except Exception as exc:
                                print(f"[INST-LAYER] Failed for {_layer_key}: {exc}",
                                      file=sys.stderr, flush=True)

                        if layer_engines:
                            # v0.0.20.540: Extract per-layer velocity/key ranges
                            layer_ranges = []
                            layer_volumes = []
                            for _li2, _lyr2 in enumerate(layers):
                                if not isinstance(_lyr2, dict):
                                    continue
                                if not bool(_lyr2.get("enabled", True)):
                                    continue
                                if not str(_lyr2.get("instrument") or ""):
                                    continue
                                vel_min = int(_lyr2.get("vel_min", 0))
                                vel_max = int(_lyr2.get("vel_max", 127))
                                key_min = int(_lyr2.get("key_min", 0))
                                key_max = int(_lyr2.get("key_max", 127))
                                vel_crossfade = int(_lyr2.get("vel_crossfade", 0))
                                layer_ranges.append((
                                    max(0, min(127, vel_min)),
                                    max(0, min(127, vel_max)),
                                    max(0, min(127, key_min)),
                                    max(0, min(127, key_max)),
                                    max(0, min(64, vel_crossfade)),
                                ))
                                layer_volumes.append(float(_lyr2.get("volume", 1.0)))
                            # v0.0.20.553: Bitwig-style — dispatcher sums all layers
                            dispatcher = _InstrumentLayerDispatcher(
                                tid, layer_engines, layer_ranges, layer_volumes
                            )
                            # Register dispatcher for MIDI routing
                            try:
                                reg = self._sampler_registry
                                if reg is not None:
                                    reg.register(tid, dispatcher)
                                    print(f"[INST-LAYER] SamplerRegistry: track={tid} ({len(layer_engines)} layers) ✓",
                                          file=sys.stderr, flush=True)
                            except Exception as exc:
                                print(f"[INST-LAYER] SamplerRegistry FAILED for {tid}: {exc}",
                                      file=sys.stderr, flush=True)
                            # Register DISPATCHER as main pull source for track
                            # (Bitwig model: container sums all layer audio)
                            try:
                                pull_name = f"vstinst:{tid}"
                                _disp_ref = dispatcher
                                def _disp_pull(frames, sr, _d=_disp_ref):
                                    return _d.pull(frames, sr)
                                _disp_pull._pydaw_track_id = tid
                                self.register_pull_source(pull_name, _disp_pull)
                                self._vst_instrument_engines[tid] = dispatcher
                                print(f"[INST-LAYER] Pull source: {pull_name} (summing {len(layer_engines)} layers) ✓",
                                      file=sys.stderr, flush=True)
                            except Exception as exc:
                                print(f"[INST-LAYER] Pull source registration failed for {tid}: {exc}",
                                      file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[INST-LAYER] Scan failed: {exc}", file=sys.stderr, flush=True)

        # ── Phase 4: Shut down engines that are no longer needed ──
        for old_tid, old_eng in old_engines.items():
            if old_tid in self._vst_instrument_engines:
                continue  # Still in use (reused)
            # No longer needed — clean up
            try:
                with self._pull_sources_lock:
                    to_remove = [k for k in self._pull_sources_dict if k.startswith(f"vstinst:{old_tid}")]
                for k in to_remove:
                    self.unregister_pull_source(k)
            except Exception:
                pass
            try:
                reg = self._sampler_registry
                if reg is not None and reg.get_engine(old_tid) is old_eng:
                    reg.unregister(old_tid)
            except Exception:
                pass
            try:
                if hasattr(old_eng, "shutdown"):
                    old_eng.shutdown()
            except Exception:
                pass

        if self._vst_instrument_engines:
            n_reused = len(reused_tids)
            n_new = len(self._vst_instrument_engines) - n_reused
            print(f"[VST3-INST] Total: {len(self._vst_instrument_engines)} engine(s) ({n_reused} reused, {n_new} new)",
                  file=sys.stderr, flush=True)

            # ALWAYS ensure audio output is running with the right buffer size
            try:
                engine_thread = getattr(self, "_engine_thread", None)
                if engine_thread is not None and engine_thread.isRunning():
                    if n_new > 0:
                        print("[VST3-INST] Restarting audio stream with larger buffer (8192)",
                              file=sys.stderr, flush=True)
                        self.stop()
                        import time; time.sleep(0.1)
                        self.ensure_preview_output()
                else:
                    print("[VST3-INST] Starting audio preview output (buffer=8192)",
                          file=sys.stderr, flush=True)
                    self.ensure_preview_output()
            except Exception as exc:
                print(f"[VST3-INST] Audio output setup failed: {exc}", file=sys.stderr, flush=True)

        # v0.0.20.390: Schedule deferred retry for candidates that failed with
        # "main thread" errors. Surge XT sometimes fails on first load even from
        # the GUI thread if Qt isn't fully settled. A 2-second delay usually fixes it.
        _failed_candidates = [c for c in inst_candidates
                              if c[0] not in self._vst_instrument_engines and c[3]]
        if _failed_candidates:
            print(f"[VST3-INST] {len(_failed_candidates)} engine(s) failed — scheduling deferred retry in 2s",
                  file=sys.stderr, flush=True)
            try:
                from PyQt6.QtCore import QTimer
                _self = self  # capture for closure
                _fc = list(_failed_candidates)
                _sr = sr
                def _deferred_retry():
                    _self._retry_failed_vst_instruments(_fc, _sr)
                QTimer.singleShot(2000, _deferred_retry)
            except Exception:
                pass

    # ── v0.0.20.722: Active Instrument Status (for Sandbox Dialog) ──

    def get_active_instruments(self) -> list:
        """Return status of all active instrument engines.

        Returns a list of dicts with:
            track_id, plugin_name, plugin_type, plugin_path, status, is_ok
        Safe to call from any thread. Used by SandboxStatusDialog.
        """
        result = []
        try:
            for tid, eng in dict(self._vst_instrument_engines).items():
                try:
                    info = {
                        "track_id": str(tid),
                        "plugin_name": getattr(eng, "plugin_name", "?"),
                        "plugin_type": "vst3",
                        "plugin_path": getattr(eng, "path", ""),
                        "is_ok": getattr(eng, "_ok", False),
                        "status": "running" if getattr(eng, "_ok", False) else "error",
                        "error": getattr(eng, "_err", ""),
                        "mode": "in-process",
                    }
                    # Detect actual type from class name
                    cls_name = type(eng).__name__
                    if "Clap" in cls_name:
                        info["plugin_type"] = "clap"
                    elif "Vst2" in cls_name:
                        info["plugin_type"] = "vst2"
                    elif "Layer" in cls_name or "Dispatcher" in cls_name:
                        info["plugin_type"] = "layer"
                    result.append(info)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for tid, eng in dict(self._sf2_instrument_engines).items():
                try:
                    result.append({
                        "track_id": str(tid),
                        "plugin_name": getattr(eng, "_sf2_name", "SF2"),
                        "plugin_type": "sf2",
                        "plugin_path": getattr(eng, "_sf2_path", ""),
                        "is_ok": getattr(eng, "_ok", False),
                        "status": "running" if getattr(eng, "_ok", False) else "error",
                        "error": "",
                        "mode": "in-process",
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return result

    def _create_sf2_instrument_engines(self, sr: int, project_snapshot: Any) -> None:
        """Create or REUSE FluidSynthRealtimeEngine for SF2 instrument tracks.

        v0.0.20.430: Enables live MIDI keyboard → SF2 SoundFont audio.
        Best Practice (Bitwig/Ableton): SF2 is a realtime pull-source, not offline-only.
        """
        import sys

        try:
            from pydaw.audio.sf2_engine import FluidSynthRealtimeEngine
        except ImportError as _imp:
            print(f"[SF2-RT] sf2_engine import failed: {_imp}", file=sys.stderr, flush=True)
            return

        old_engines = dict(self._sf2_instrument_engines)
        self._sf2_instrument_engines = {}

        # Scan project tracks for plugin_type=="sf2"
        tracks = list(getattr(project_snapshot, "tracks", []) or [])
        for t in tracks:
            tid = str(getattr(t, "id", "") or "")
            if not tid:
                continue

            plugin_type = getattr(t, "plugin_type", None)
            sf2_path = getattr(t, "sf2_path", None)

            # Backwards compat: sf2_path without plugin_type
            if not plugin_type and sf2_path:
                plugin_type = "sf2"

            if plugin_type != "sf2" or not sf2_path:
                continue

            bank = int(getattr(t, "sf2_bank", 0) or 0)
            preset = int(getattr(t, "sf2_preset", 0) or 0)

            # Check if we can REUSE existing engine (same path/bank/preset)
            old_eng = old_engines.get(tid)
            if (old_eng is not None
                    and getattr(old_eng, "_ok", False)
                    and getattr(old_eng, "_sf2_path", "") == str(sf2_path)
                    and getattr(old_eng, "_bank", -1) == bank
                    and getattr(old_eng, "_preset", -1) == preset):
                self._sf2_instrument_engines[tid] = old_eng
                print(f"[SF2-RT] Reusing engine for track={tid}", file=sys.stderr, flush=True)
            else:
                # Create new engine
                try:
                    engine = FluidSynthRealtimeEngine(
                        sf2_path=str(sf2_path),
                        bank=bank,
                        preset=preset,
                        sr=sr,
                        track_id=tid,
                    )
                except Exception as exc:
                    print(f"[SF2-RT] Failed to create engine for track {tid}: {exc}",
                          file=sys.stderr, flush=True)
                    continue

                if not getattr(engine, "_ok", False):
                    _err = getattr(engine, "_err", "unknown")
                    print(f"[SF2-RT] Engine not OK for track {tid}: {_err}",
                          file=sys.stderr, flush=True)
                    continue

                self._sf2_instrument_engines[tid] = engine
                print(f"[SF2-RT] Created NEW engine for track={tid} sf2={sf2_path}",
                      file=sys.stderr, flush=True)

                # Shutdown old engine if it existed
                if old_eng is not None:
                    try:
                        old_eng.shutdown()
                    except Exception:
                        pass

            engine = self._sf2_instrument_engines[tid]

            # Register in SamplerRegistry (MIDI routing)
            try:
                reg = self._sampler_registry
                if reg is not None:
                    reg.register(tid, engine)
                    print(f"[SF2-RT] SamplerRegistry: track={tid} ✓", file=sys.stderr, flush=True)
                else:
                    print(f"[SF2-RT] WARNING: _sampler_registry is None!", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[SF2-RT] SamplerRegistry FAILED for {tid}: {exc}", file=sys.stderr, flush=True)

            # Register as pull source (audio output)
            try:
                pull_name = f"sf2rt:{tid}"
                _engine_ref = engine
                def _pull_fn(frames, sr, _eng=_engine_ref):
                    return _eng.pull(frames, sr)
                _pull_fn._pydaw_track_id = tid  # type: ignore[attr-defined]
                self.register_pull_source(pull_name, _pull_fn)
                print(f"[SF2-RT] Pull source: {pull_name} ✓", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[SF2-RT] Pull source registration failed for {tid}: {exc}",
                      file=sys.stderr, flush=True)

        # Shutdown engines that are no longer needed
        for old_tid, old_eng in old_engines.items():
            if old_tid in self._sf2_instrument_engines:
                continue
            try:
                self.unregister_pull_source(f"sf2rt:{old_tid}")
            except Exception:
                pass
            try:
                reg = self._sampler_registry
                if reg is not None and reg.get_engine(old_tid) is old_eng:
                    reg.unregister(old_tid)
            except Exception:
                pass
            try:
                old_eng.shutdown()
            except Exception:
                pass

        if self._sf2_instrument_engines:
            print(f"[SF2-RT] Total: {len(self._sf2_instrument_engines)} SF2 engine(s)",
                  file=sys.stderr, flush=True)

        # Ensure audio output is running (needed for live preview)
        if self._sf2_instrument_engines:
            try:
                self.ensure_preview_output()
            except Exception:
                pass

    def _retry_failed_vst_instruments(self, failed_candidates: list, sr: int) -> None:
        """Deferred retry for VST/CLAP instrument engines that failed on initial load.

        v0.0.20.725: Added CLAP instrument support + persistent blacklist integration.
        """
        import sys
        try:
            from pydaw.audio.vst3_host import Vst3InstrumentEngine
        except ImportError:
            Vst3InstrumentEngine = None
        try:
            from pydaw.audio.vst2_host import Vst2InstrumentEngine
        except ImportError:
            Vst2InstrumentEngine = None
        try:
            from pydaw.audio.clap_host import ClapInstrumentEngine
        except ImportError:
            ClapInstrumentEngine = None

        for (tid, did, params, vst_ref, vst_plugin_name) in failed_candidates:
            if tid in self._vst_instrument_engines:
                continue
            if not vst_ref:
                continue

            # v0.0.20.723: Skip plugins that already failed deferred retry before.
            if vst_ref in self._failed_vst_paths:
                continue

            # v0.0.20.725: Check persistent blacklist before retrying
            try:
                from pydaw.services.plugin_probe import is_blacklisted
                _is_clap = vst_ref.endswith(".clap") or (
                    "::" in vst_ref and vst_ref.split("::")[0].rstrip().endswith(".clap"))
                _probe_type = "clap" if _is_clap else "vst3"
                if is_blacklisted(vst_ref, _probe_type, vst_plugin_name):
                    print(f"[DEFERRED] Skipping blacklisted plugin: {vst_ref}",
                          file=sys.stderr, flush=True)
                    self._failed_vst_paths.add(vst_ref)
                    continue
            except ImportError:
                _is_clap = vst_ref.endswith(".clap") or (
                    "::" in vst_ref and vst_ref.split("::")[0].rstrip().endswith(".clap"))

            _is_vst2 = (not _is_clap) and vst_ref.endswith(".so") and not vst_ref.endswith(".vst3")
            if _is_clap:
                _label = "CLAP-INST"
            elif _is_vst2:
                _label = "VST2-INST"
            else:
                _label = "VST3-INST"

            print(f"[{_label}] Deferred retry: loading {vst_ref} for track={tid}",
                  file=sys.stderr, flush=True)
            try:
                if _is_clap and ClapInstrumentEngine is not None:
                    # CLAP: split path::plugin_id
                    _clap_path = vst_ref
                    _clap_pid = ""
                    if "::" in vst_ref:
                        parts = vst_ref.split("::", 1)
                        _clap_path = parts[0].strip()
                        _clap_pid = parts[1].strip()
                    engine = ClapInstrumentEngine(
                        path=_clap_path,
                        plugin_id_str=_clap_pid or vst_plugin_name,
                        track_id=tid, device_id=did,
                        rt_params=self.rt_params, params=params,
                        sr=sr, max_frames=8192,
                    )
                elif _is_vst2 and Vst2InstrumentEngine is not None:
                    engine = Vst2InstrumentEngine(
                        path=vst_ref, plugin_name=vst_plugin_name,
                        track_id=tid, device_id=did,
                        rt_params=self.rt_params, params=params,
                        sr=sr, max_frames=8192,
                    )
                elif Vst3InstrumentEngine is not None:
                    engine = Vst3InstrumentEngine(
                        path=vst_ref, plugin_name=vst_plugin_name,
                        track_id=tid, device_id=did,
                        rt_params=self.rt_params, params=params,
                        sr=sr, max_frames=8192,
                    )
                else:
                    continue
            except Exception as exc:
                print(f"[{_label}] Deferred retry FAILED for {tid}: {exc}",
                      file=sys.stderr, flush=True)
                self._failed_vst_paths.add(vst_ref)
                continue

            if not getattr(engine, "_ok", False):
                _err = getattr(engine, "_err", "unknown")
                print(f"[{_label}] Deferred retry not OK for {tid}: {_err}",
                      file=sys.stderr, flush=True)
                self._failed_vst_paths.add(vst_ref)  # Don't retry this path again
                continue

            self._vst_instrument_engines[tid] = engine
            print(f"[{_label}] Deferred retry SUCCESS for track={tid}",
                  file=sys.stderr, flush=True)

            # Register
            try:
                reg = self._sampler_registry
                if reg is not None:
                    reg.register(tid, engine)
                    print(f"[{_label}] SamplerRegistry: track={tid} ✓", file=sys.stderr, flush=True)
            except Exception:
                pass
            try:
                pull_name = f"vstinst:{tid}:{did}"
                _engine_ref = engine
                def _pull_fn(frames, sr, _eng=_engine_ref):
                    return _eng.pull(frames, sr)
                _pull_fn._pydaw_track_id = tid
                self.register_pull_source(pull_name, _pull_fn)
                print(f"[{_label}] Pull source: {pull_name} ✓", file=sys.stderr, flush=True)
            except Exception:
                pass

        # Ensure audio output if we now have engines
        if self._vst_instrument_engines:
            try:
                engine_thread = getattr(self, "_engine_thread", None)
                if engine_thread is None or not engine_thread.isRunning():
                    self.ensure_preview_output()
            except Exception:
                pass


    def _ensure_dsp_engine(self):
        # Lazy-create DSPJackEngine and keep its bindings minimal (no GUI changes).
        try:
            if self._dsp_engine is None:
                from pydaw.audio.dsp_engine import DSPJackEngine
                self._dsp_engine = DSPJackEngine(rt_params=self.rt_params)
                # Bind master getter as legacy fallback
                self._dsp_engine.set_master_getter(lambda: (float(self._master_volume), float(self._master_pan)))
                # v0.0.20.28: Bind HybridEngineBridge for metering + per-track pull-source mixing
                try:
                    if self._hybrid_bridge is not None and hasattr(self._dsp_engine, "set_hybrid_bridge"):
                        self._dsp_engine.set_hybrid_bridge(self._hybrid_bridge)
                except Exception:
                    pass
                # Bind transport ref for external playhead updates (optional)
                if self._bound_transport_service is not None:
                    self._dsp_engine.set_transport_ref(self._bound_transport_service)
            else:
                # refresh transport ref if it became available later
                if self._bound_transport_service is not None:
                    try:
                        self._dsp_engine.set_transport_ref(self._bound_transport_service)
                    except Exception:
                        pass
                try:
                    if self._hybrid_bridge is not None and hasattr(self._dsp_engine, "set_hybrid_bridge"):
                        self._dsp_engine.set_hybrid_bridge(self._hybrid_bridge)
                except Exception:
                    pass
            return self._dsp_engine
        except Exception:
            return None
    
    def set_master_volume(self, volume: float) -> None:
        """Set master volume (0.0-1.0) in REALTIME with smoothing.
        
        Writes to: atomic float (legacy) + RTParamStore (smoothed) + HybridRing (lock-free).
        """
        v = max(0.0, min(1.0, float(volume)))
        self._master_volume = v
        try:
            self.rt_params.set_param("master:vol", v)
        except Exception:
            pass
        # v0.0.20.13: Push to hybrid ring buffer (lock-free, zero-latency)
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_master_volume(v)
        except Exception:
            pass
    
    def set_master_pan(self, pan: float) -> None:
        """Set master pan (-1.0-1.0) in REALTIME with smoothing.
        
        Writes to: atomic float (legacy) + RTParamStore (smoothed) + HybridRing (lock-free).
        """
        p = max(-1.0, min(1.0, float(pan)))
        self._master_pan = p
        try:
            self.rt_params.set_param("master:pan", p)
        except Exception:
            pass
        # v0.0.20.13: Push to hybrid ring buffer (lock-free, zero-latency)
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_master_pan(p)
        except Exception:
            pass

    # NEW v0.0.20.33: Per-Track setters (LIKE MASTER, but for tracks!)
    # NOTE: Callback in v0.0.20.33 does NOT use these yet (stays safe!)
    # Future versions will use these for live fader response.
    
    def set_track_volume(self, track_id: str, volume: float) -> None:
        """Set track volume - writes to atomic dict + RTParamStore + HybridBridge."""
        v = max(0.0, min(1.0, float(volume)))
        self._track_volumes[str(track_id)] = v
        try:
            self.rt_params.set_track_vol(str(track_id), v)
        except Exception:
            pass
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_track_volume(str(track_id), v)
        except Exception:
            pass
    
    def set_track_pan(self, track_id: str, pan: float) -> None:
        """Set track pan - writes to atomic dict + RTParamStore + HybridBridge."""
        p = max(-1.0, min(1.0, float(pan)))
        self._track_pans[str(track_id)] = p
        try:
            self.rt_params.set_track_pan(str(track_id), p)
        except Exception:
            pass
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_track_pan(str(track_id), p)
        except Exception:
            pass
    
    def set_track_mute(self, track_id: str, muted: bool) -> None:
        """Set track mute - writes to atomic dict + RTParamStore + HybridBridge."""
        m = bool(muted)
        self._track_mutes[str(track_id)] = m
        try:
            self.rt_params.set_track_mute(str(track_id), m)
        except Exception:
            pass
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_track_mute(str(track_id), m)
        except Exception:
            pass
    
    def set_track_solo(self, track_id: str, solo: bool) -> None:
        """Set track solo - writes to atomic dict + RTParamStore + HybridBridge."""
        s = bool(solo)
        self._track_solos[str(track_id)] = s
        try:
            self.rt_params.set_track_solo(str(track_id), s)
        except Exception:
            pass
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_track_solo(str(track_id), s)
        except Exception:
            pass


    def read_track_peak(self, track_id: str) -> Tuple[float, float]:
        """Read per-track peak levels (GUI thread, lock-free)."""
        # v0.0.20.41: Try direct peaks first
        dp = self._direct_peaks.get(str(track_id))
        if dp is not None:
            l, r = dp
            decay = self._direct_peaks_decay
            self._direct_peaks[str(track_id)] = (l * decay, r * decay)
            if l > 0.0001 or r > 0.0001:
                return (l, r)
        try:
            if self._hybrid_bridge is not None:
                return self._hybrid_bridge.read_track_peak(track_id)
        except Exception:
            pass
        return (0.0, 0.0)

    def _pull_sources_snapshot(self, last_gen: int) -> Tuple[int, List[Any]]:
        """Return (gen, sources). Safe for realtime callbacks.

        We do NOT mutate the list in-place; updates replace the list object.
        """
        try:
            with self._pull_sources_lock:
                gen = int(self._pull_sources_gen)
                lst = self._pull_sources_list
            return gen, lst
        except Exception:
            return last_gen, []

    
    def add_source(self, source, name: str | None = None) -> str | None:  # noqa: ANN001
        """Compatibility helper: register a sampler/device as audible source.

        Accepts:
        - a callable: fn(frames, sr) -> (frames,2) float32
        - an object with .pull(frames, sr)

        Returns the registered name (or None on failure).
        """
        try:
            fn = None
            if callable(source):
                fn = source
            else:
                fn = getattr(source, "pull", None)
            if fn is None:
                return None
            if name is None:
                name = f"src:{source.__class__.__name__}:{id(source) & 0xFFFF:04x}"
            self.register_pull_source(str(name), fn)
            try:
                self.ensure_preview_output()
            except Exception:
                pass
            return str(name)
        except Exception:
            return None

    def register_pull_source(self, name: str, fn) -> None:  # noqa: ANN001
        """Register a pull-based audio source: fn(frames, sr) -> np.ndarray (frames,2)."""
        try:
            with self._pull_sources_lock:
                self._pull_sources_dict[str(name)] = fn
                self._pull_sources_list = list(self._pull_sources_dict.values())
                self._pull_sources_gen += 1
        except Exception:
            pass
        # Forward to JACK DSP engine if present
        try:
            dsp = self._ensure_dsp_engine()
            if dsp is not None:
                dsp.register_pull_source(str(name), fn)
        except Exception:
            pass
        # v0.0.20.13: Sync to hybrid bridge (atomic list swap)
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_pull_sources(self._pull_sources_list)
        except Exception:
            pass

    def unregister_pull_source(self, name: str) -> None:
        try:
            with self._pull_sources_lock:
                self._pull_sources_dict.pop(str(name), None)
                self._pull_sources_list = list(self._pull_sources_dict.values())
                self._pull_sources_gen += 1
        except Exception:
            pass
        try:
            if self._dsp_engine is not None:
                self._dsp_engine.unregister_pull_source(str(name))
        except Exception:
            pass
        # v0.0.20.13: Sync to hybrid bridge
        try:
            if self._hybrid_bridge is not None:
                self._hybrid_bridge.set_pull_sources(self._pull_sources_list)
        except Exception:
            pass

    def ensure_preview_output(self) -> None:
        """Ensure an output stream is running so pull sources are audible."""
        # If JACK is the selected backend, prefer that (PipeWire graph).
        # BUT: if no JACK server is reachable (common when not started via pw-jack),
        # we must fall back to sounddevice, otherwise the user hears nothing at all.
        try:
            if self._backend == "jack" and self._bound_jack_service is not None:
                jack_ok = True
                try:
                    probe = getattr(self._bound_jack_service, "probe_available", None)
                    if callable(probe):
                        jack_ok = bool(probe())
                except Exception:
                    jack_ok = True

                if jack_ok:
                    try:
                        self._bound_jack_service.start_async(client_name="PyDAW")
                    except Exception:
                        jack_ok = False

                if jack_ok:
                    # v0.0.20.14: Prefer HybridAudioCallback for JACK preview
                    try:
                        if _HYBRID_AVAILABLE and self._hybrid_bridge is not None:
                            hybrid_cb = self._hybrid_bridge.callback
                            hybrid_cb.set_arrangement_state(None)  # No arrangement, preview only
                            hybrid_cb.set_transport_ref(self._bound_transport_service)
                            # v0.0.20.67: Wire sampler registry for preview MIDI routing
                            if hasattr(self, "_sampler_registry") and self._sampler_registry is not None:
                                hybrid_cb._sampler_registry = self._sampler_registry
                            self._bound_jack_service.set_render_callback(hybrid_cb.render_for_jack)
                            return
                    except Exception:
                        pass

                    # Legacy fallback
                    dsp = None
                    try:
                        dsp = self._ensure_dsp_engine()
                    except Exception:
                        dsp = None
                    if dsp is not None:
                        try:
                            dsp.set_arrangement_state(None)
                        except Exception:
                            pass
                        try:
                            self._bound_jack_service.set_render_callback(dsp.render_callback)
                        except Exception:
                            pass
                    return

                # Fall back to sounddevice if JACK isn't available
                try:
                    self.status.emit(
                        "JACK nicht erreichbar → Monitoring/Preview via sounddevice (Starte mit 'pw-jack python3 main.py' für qpwgraph-Ports)."
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # sounddevice fallback
        try:
            if self._engine_thread is not None and self._engine_thread.isRunning():
                return
        except Exception:
            pass

        # v0.0.20.67: Use effective sample rate from settings, not hardcoded 48k
        sr = self.get_effective_sample_rate()
        # v0.0.20.388: Increase buffer size when VST instruments are loaded.
        # Surge XT's plugin.process() takes ~30ms per 1024 samples, which exceeds
        # the 21ms callback deadline at SR=48k. Buffer=8192 gives ~170ms headroom.
        _has_vst_inst = bool(getattr(self, "_vst_instrument_engines", None))
        _bs = 8192 if _has_vst_inst else 1024
        cfg: Dict[str, Any] = {
            "mode": "silence",
            "sample_rate": sr,
            "buffer_size": _bs,
            "audio_engine_ref": self,
            # v0.0.20.67: Pass sampler registry for MIDI dispatch
            "sampler_registry": self._sampler_registry,
        }
        try:
            self.start(backend="sounddevice", config=cfg)
        except Exception:
            # best-effort
            pass

    def _on_transport_params_changed(self, *args: Any, **kwargs: Any) -> None:
        """Wenn Transport-Parameter (Loop/BPM/TS) geändert werden, starte die
        Engine neu, damit die Audio-Config konsistent bleibt.

        Diese Strategie ist einfach und robust (Phase 4). Feingranulare
        Live-Updates der EngineConfig können später folgen.
        """
        try:
            if self._bound_transport_service is None:
                return
            if not bool(getattr(self._bound_transport_service, "is_playing", False)):
                return
        except Exception:
            return

        # Neustart: Stop -> Start mit aktuellem Beat
        try:
            self.stop()
        except Exception:
            pass
        try:
            self.start_arrangement_playback()
        except Exception as e:
            try:
                self.error.emit(str(e))
            except Exception:
                pass

    def _on_transport_playing_changed(self, playing: bool) -> None:
        if playing:
            self.start_arrangement_playback()
        else:
            self.stop()

    def start_arrangement_playback(self) -> None:
        """Startet Arrangement-Wiedergabe über das aktuell gewählte Backend.

        - Rust Engine: If migration controller says audio_playback is on Rust
        - JACK: Output erscheint als ein Client ("PyDAW") in qpwgraph; optional Monitoring bleibt additiv.
        - sounddevice: Fallback über PortAudio.
        """
        if not self._bound_project_service or not self._bound_transport_service:
            return

        # v0.0.20.662: Check if Rust engine should handle audio playback
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            migration = EngineMigrationController.instance()
            if migration.should_use_rust("audio_playback"):
                self._start_rust_arrangement_playback()
                return
        except Exception:
            pass  # Fallback to Python engine if migration check fails

        # Snapshot erzeugen (thread-safe)
        try:
            project_snapshot = copy.deepcopy(self._bound_project_service.ctx.project)
        except Exception:
            project_snapshot = getattr(self._bound_project_service, "ctx", None).project if hasattr(self._bound_project_service, "ctx") else None

        # v0.0.20.56: Compile/push Audio-FX maps (track Audio-FX chains)
        try:
            self.rebuild_fx_maps(project_snapshot)
        except Exception:
            pass

        start_beat = float(getattr(self._bound_transport_service, "current_beat", 0.0) or 0.0)
        loop_enabled = bool(getattr(self._bound_transport_service, "loop_enabled", False))
        loop_start_beat = float(getattr(self._bound_transport_service, "loop_start", 0.0) or 0.0)
        loop_end_beat = float(getattr(self._bound_transport_service, "loop_end", 0.0) or 0.0)

        # Prefer selected backend (set via Audio Settings dialog)
        backend = self._backend

        # Safety net: Backend can be forced to JACK in settings while the JACK server
        # is not running (common on PipeWire setups if not started via pw-jack).
        # In that case we fall back to sounddevice instead of silently producing no audio.
        if backend == "jack":
            try:
                from pydaw.services.jack_client_service import JackClientService

                if not JackClientService.probe_available():
                    self.status.emit(
                        "JACK nicht erreichbar – nutze SoundDevice (Tipp: 'pw-jack python3 main.py')."
                    )
                    backend = "sounddevice"
            except Exception:
                # Never block playback just because the probe failed.
                pass

        # JACK path
        if backend == "jack" and self._bound_jack_service is not None:
            # Ensure JACK client is running
            try:
                self._bound_jack_service.start_async(client_name="PyDAW")
            except Exception:
                pass

            # Prepare audio outside JACK process callback
            import threading

            def _prepare():
                try:
                    sr = int(getattr(self._bound_jack_service, "samplerate", 48000) or 48000)
                except Exception:
                    sr = 48000
                try:
                    self.status.emit("JACK: bereite Arrangement (Clips/MIDI-Renders) vor…")
                except Exception:
                    pass
                try:
                    prepared, midi_events, bpm = prepare_clips(project_snapshot, sr, cache=self._arranger_cache)
                    self._jack_state = ArrangementState(
                        prepared=prepared,
                        sr=sr,
                        start_beat=float(start_beat),
                        bpm=float(bpm),
                        loop_enabled=bool(loop_enabled),
                        loop_start_beat=float(loop_start_beat),
                        loop_end_beat=float(loop_end_beat),
                        midi_events=midi_events,
                    )
                except Exception as e:
                    self._jack_state = None
                    try:
                        self.error.emit(f"JACK: Arrange-Vorbereitung fehlgeschlagen: {e}")
                    except Exception:
                        pass
                    return

                # v0.0.20.14: Prefer HybridAudioCallback for JACK (lock-free)
                try:
                    if _HYBRID_AVAILABLE and self._hybrid_bridge is not None:
                        # v0.0.20.39: Ensure deterministic track-index mapping for JACK too (fixes live mixer faders)
                        try:
                            tracks = getattr(project_snapshot, 'tracks', None) or []
                            self._hybrid_bridge.set_track_index_map({getattr(t, 'id', str(i)): i for i, t in enumerate(tracks)})
                        except Exception:
                            pass
                        hybrid_cb = self._hybrid_bridge.callback
                        hybrid_cb.set_arrangement_state(self._jack_state)
                        hybrid_cb.set_transport_ref(self._bound_transport_service)
                        self._hybrid_bridge.set_sample_rate(sr)
                        # v0.0.20.80: Wire instrument bypass set
                        try:
                            bypassed = {str(getattr(t, 'id', '')) for t in tracks
                                        if not bool(getattr(t, 'instrument_enabled', True))}
                            hybrid_cb.set_bypassed_track_ids(bypassed)
                        except Exception:
                            pass
                        # v0.0.20.41: Wire direct peak storage for JACK VU metering
                        if hasattr(self, "_direct_peaks"):
                            hybrid_cb._direct_peaks_ref = self._direct_peaks
                        # v0.0.20.42: Wire sampler registry for real-time MIDI→Sampler
                        if hasattr(self, "_sampler_registry") and self._sampler_registry is not None:
                            hybrid_cb._sampler_registry = self._sampler_registry
                        self._bound_jack_service.set_render_callback(hybrid_cb.render_for_jack)
                        try:
                            self.status.emit("JACK: Hybrid Engine aktiv (lock-free, per-track mix)")
                        except Exception:
                            pass
                        return
                except Exception:
                    pass

                # Legacy fallback: DSP engine or direct render
                def _render_cb(frames, in_bufs, out_bufs, sr_int):  # noqa: ANN001
                    st = self._jack_state
                    if st is None:
                        return False
                    try:
                        buf = st.render(int(frames))
                    except Exception:
                        return False
                    try:
                        if len(out_bufs) >= 1:
                            out_bufs[0][:frames] += buf[:, 0]
                        if len(out_bufs) >= 2:
                            out_bufs[1][:frames] += buf[:, 1]
                        for ch in range(2, len(out_bufs)):
                            out_bufs[ch][:frames] += 0.0
                        try:
                            if self._bound_transport_service is not None:
                                self._bound_transport_service._set_external_playhead_samples(int(st.playhead), float(sr_int))
                        except Exception:
                            pass
                        return True
                    except Exception:
                        return False

                try:
                    dsp = None
                    try:
                        dsp = self._ensure_dsp_engine()
                    except Exception:
                        dsp = None
                    if dsp is not None:
                        try:
                            dsp.set_arrangement_state(self._jack_state)
                        except Exception:
                            pass
                        self._bound_jack_service.set_render_callback(dsp.render_callback)
                        self.status.emit("JACK: DSP Engine aktiv (Mix+Master)")
                    else:
                        self._bound_jack_service.set_render_callback(_render_cb)
                        self.status.emit("JACK: Arrangement aktiv")
                except Exception as e:
                    try:
                        self.error.emit(f"JACK: Render-Callback konnte nicht gesetzt werden: {e}")
                    except Exception:
                        pass

            # Start/replace worker
            try:
                if self._jack_prepare_thread and self._jack_prepare_thread.is_alive():
                    return
            except Exception:
                pass
            self._jack_prepare_thread = threading.Thread(target=_prepare, daemon=True)
            self._jack_prepare_thread.start()
            return

        # sounddevice path — v0.0.20.14: prefer Hybrid Callback as default
        bpm = getattr(project_snapshot, "bpm", getattr(project_snapshot, "tempo_bpm", 120.0)) if project_snapshot is not None else 120.0
        cfg: Dict[str, Any] = {
            "mode": "arrangement",
            "audio_engine_ref": self,
            "arranger_cache_ref": self._arranger_cache,
            "project_snapshot": project_snapshot,
            "transport_service": self._bound_transport_service,
            "bpm": float(bpm),
            "start_beat": float(start_beat),
            "loop_enabled": loop_enabled,
            "loop_start_beat": loop_start_beat,
            "loop_end_beat": loop_end_beat,
            "sample_rate": 48000,
            # v0.0.20.388: Adaptive buffer size for VST instrument headroom
            "buffer_size": 8192 if bool(getattr(self, "_vst_instrument_engines", None)) else 1024,
            # v0.0.20.14: Pass hybrid bridge for sounddevice hybrid mode
            "hybrid_bridge": self._hybrid_bridge if _HYBRID_AVAILABLE else None,
            # v0.0.20.42: Pass sampler registry for real-time MIDI→Sampler
            "sampler_registry": self._sampler_registry,
        }
        self.stop()
        self.start(backend="sounddevice", config=cfg)

    # --- v0.0.20.662: Rust Engine Delegation ---------------------------------

    def _start_rust_arrangement_playback(self) -> None:
        """Delegate arrangement playback to the Rust audio engine.

        This method:
        1. Starts the Rust engine if not already running
        2. Syncs project state (tracks, clips, tempo) to Rust via IPC
        3. Starts playback in the Rust engine
        4. Connects Rust engine events (playhead, meters) to Python signals

        Falls back to Python engine if any step fails.
        """
        try:
            from pydaw.services.rust_engine_bridge import RustEngineBridge
            bridge = RustEngineBridge.instance()

            # Start engine if needed
            if not bridge.is_connected:
                sr = self.get_effective_sample_rate()
                buf_size = 512
                try:
                    from PyQt6.QtCore import QSettings
                    s = QSettings()
                    buf_size = int(s.value("audio/buffer_size", 512))
                except Exception:
                    pass

                started = bridge.start_engine(sample_rate=sr, buffer_size=buf_size)
                if not started:
                    self.status.emit("Rust Engine konnte nicht gestartet werden — nutze Python Fallback")
                    self._fallback_to_python_playback()
                    return

            # Sync project state to Rust
            project = None
            try:
                project = self._bound_project_service.ctx.project
            except Exception:
                pass

            if project is None:
                self.status.emit("Kein Projekt geladen — nutze Python Fallback")
                self._fallback_to_python_playback()
                return

            ts = self._bound_transport_service

            # Sync tempo
            bpm = float(getattr(project, "bpm", getattr(project, "tempo_bpm", 120.0)))
            bridge.set_tempo(bpm)

            # Sync time signature
            try:
                num = int(getattr(ts, "numerator", 4))
                den = int(getattr(ts, "denominator", 4))
                bridge.set_time_signature(num, den)
            except Exception:
                pass

            # Sync loop
            try:
                bridge.set_loop(
                    enabled=bool(getattr(ts, "loop_enabled", False)),
                    start_beat=float(getattr(ts, "loop_start", 0.0)),
                    end_beat=float(getattr(ts, "loop_end", 0.0)),
                )
            except Exception:
                pass

            # Sync tracks
            tracks = getattr(project, "tracks", []) or []
            for i, track in enumerate(tracks):
                tid = str(getattr(track, "id", str(i)))
                kind = str(getattr(track, "kind", "audio"))
                bridge.add_track(tid, i, kind)

                # Volume/Pan/Mute/Solo
                try:
                    bridge.set_track_param(i, "Volume", float(getattr(track, "volume", 0.8)))
                    bridge.set_track_param(i, "Pan", float(getattr(track, "pan", 0.0)))
                    bridge.set_track_param(i, "Mute", 1.0 if getattr(track, "muted", False) else 0.0)
                    bridge.set_track_param(i, "Solo", 1.0 if getattr(track, "soloed", False) else 0.0)
                except Exception:
                    pass

            # Connect Rust engine events to transport service (playhead sync)
            try:
                bridge.playhead_changed.connect(
                    lambda beat, samp, playing: self._on_rust_playhead(beat, samp, playing),
                )
            except Exception:
                pass

            # Connect Rust metering to direct peaks
            try:
                bridge.master_meter_changed.connect(
                    lambda pl, pr, rl, rr: self._on_rust_master_meter(pl, pr),
                )
            except Exception:
                pass

            # Seek to current position and play
            start_beat = float(getattr(ts, "current_beat", 0.0) or 0.0)
            bridge.seek(start_beat)
            bridge.play()

            self.status.emit("Rust Audio Engine aktiv")
            self.running_changed.emit(True)

        except Exception as e:
            try:
                self.status.emit(f"Rust Engine Fehler: {e} — nutze Python Fallback")
            except Exception:
                pass
            self._fallback_to_python_playback()

    def _fallback_to_python_playback(self) -> None:
        """Fall back to Python engine if Rust fails.

        Automatically rolls back the migration controller to Python.
        """
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            ctrl.set_subsystem("audio_playback", "python")
        except Exception:
            pass
        # Re-enter start_arrangement_playback (now uses Python path)
        self.start_arrangement_playback()

    def _on_rust_playhead(self, beat: float, sample_pos: int, is_playing: bool):
        """Handle playhead updates from Rust engine."""
        try:
            ts = self._bound_transport_service
            if ts is not None:
                ts.current_beat = float(beat)
                ts.playhead_changed.emit(float(beat))
        except Exception:
            pass

    def _on_rust_master_meter(self, peak_l: float, peak_r: float):
        """Handle master meter updates from Rust engine."""
        try:
            self._direct_peaks["__master__"] = (float(peak_l), float(peak_r))
        except Exception:
            pass


    @property
    def backend(self) -> Backend:
        return self._backend

    def set_backend(self, backend: Backend) -> None:
        if backend != self._backend:
            self._backend = backend
            self.backend_changed.emit(self._backend)

    # v0.0.20.14: Hybrid Engine access (per-track ring + JACK + sounddevice default)
    @property
    def hybrid_bridge(self) -> Any:
        """Access the HybridEngineBridge for lock-free metering/params."""
        return self._hybrid_bridge

    @property
    def async_loader(self) -> Any:
        """Access the AsyncSampleLoader for background file loading."""
        return self._async_loader

    @property
    def essentia_pool(self) -> Any:
        """Access the EssentiaWorkerPool for background time-stretch jobs."""
        return self._essentia_pool

    def read_master_peak(self) -> Tuple[float, float]:
        """Read master peak levels (GUI thread, lock-free)."""
        # v0.0.20.41: Try direct peaks first (most reliable)
        dp = self._direct_peaks.get("__master__")
        if dp is not None:
            l, r = dp
            # Apply GUI-side decay
            decay = self._direct_peaks_decay
            self._direct_peaks["__master__"] = (l * decay, r * decay)
            if l > 0.0001 or r > 0.0001:
                return (l, r)
        # Fallback: hybrid bridge
        try:
            if self._hybrid_bridge is not None:
                return self._hybrid_bridge.read_master_peak()
        except Exception:
            pass
        return (0.0, 0.0)

    def read_direct_track_peak(self, track_id: str) -> Tuple[float, float]:
        """Read per-track peak from direct storage (v0.0.20.41, GUI thread)."""
        dp = self._direct_peaks.get(str(track_id))
        if dp is not None:
            l, r = dp
            decay = self._direct_peaks_decay
            self._direct_peaks[str(track_id)] = (l * decay, r * decay)
            return (l, r)
        return (0.0, 0.0)