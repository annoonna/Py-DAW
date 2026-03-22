"""FluidSynth Realtime Engine for SF2 Live MIDI Playback.

v0.0.20.430: Enables live MIDI keyboard → SF2 SoundFont audio output.

Design (Best Practice — matches Bitwig/Ableton/Cubase approach):
- FluidSynth synthesizes audio in realtime (no offline WAV cache)
- Registered as pull-source in HybridAudioCallback (same as ProSamplerEngine)
- Registered in SamplerRegistry for MIDI dispatch (note_on/note_off)
- Audio output goes through track mixer (Volume/Pan/Mute/Solo/VU)

Architecture:
  MIDI Keyboard → MidiManager.live_note_on → SamplerRegistry.note_on(track_id)
                                                    ↓
                                         FluidSynthRealtimeEngine.note_on(pitch, vel)
                                                    ↓
                                         fluidsynth.Synth.noteon(channel, pitch, vel)
                                                    ↓
  Audio Callback → pull(frames, sr) → synth.get_samples(frames) → float32 stereo
                                                    ↓
                                         HybridAudioCallback mixes per-track
"""
from __future__ import annotations

import sys
import threading
from typing import Optional

import numpy as np


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


class FluidSynthRealtimeEngine:
    """Realtime FluidSynth engine for SF2 live MIDI playback.

    Implements the pull-source + SamplerRegistry interface:
    - note_on(pitch, vel, **kwargs) -> bool
    - note_off(pitch=...) -> None
    - all_notes_off() -> None
    - pull(frames, sr) -> np.ndarray (frames, 2) float32
    - shutdown() -> None
    """

    def __init__(self, sf2_path: str, bank: int = 0, preset: int = 0,
                 sr: int = 48000, track_id: str = "", gain: float = 0.8):
        self._ok = False
        self._err = ""
        self._synth = None
        self._sfid = -1
        self._lock = threading.Lock()
        self._sr = int(sr)
        self._track_id = str(track_id)
        self._sf2_path = str(sf2_path)
        self._bank = int(bank)
        self._preset = int(preset)
        self._active_notes: set = set()  # track active pitches for polyphonic note_off
        self._shutdown = False

        try:
            import fluidsynth as _fs
            self._fs_module = _fs
        except ImportError:
            self._err = "pyfluidsynth not installed"
            print(f"[SF2-RT] ERROR: {self._err}", file=sys.stderr, flush=True)
            return

        try:
            # Create synth WITHOUT audio driver — we pull samples manually
            self._synth = _fs.Synth(gain=float(gain), samplerate=float(sr))

            # Load soundfont
            self._sfid = self._synth.sfload(str(sf2_path))
            if self._sfid < 0:
                self._err = f"sfload failed for {sf2_path}"
                print(f"[SF2-RT] ERROR: {self._err}", file=sys.stderr, flush=True)
                return

            # Select bank/preset on channel 0
            self._synth.program_select(0, self._sfid, int(bank), int(preset))

            # Verify get_samples is available
            if not hasattr(self._synth, 'get_samples'):
                self._err = "pyfluidsynth version too old (no get_samples)"
                print(f"[SF2-RT] ERROR: {self._err}", file=sys.stderr, flush=True)
                return

            self._ok = True
            print(f"[SF2-RT] Engine created: track={track_id} sf2={sf2_path} "
                  f"bank={bank} preset={preset} sr={sr}", file=sys.stderr, flush=True)

        except Exception as exc:
            self._err = str(exc)
            print(f"[SF2-RT] Engine creation failed: {exc}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)

    @property
    def path(self) -> str:
        """Compatibility with VST engine reuse logic."""
        return self._sf2_path

    # ── MIDI Interface (called from SamplerRegistry / GUI thread) ──

    def note_on(self, pitch: int, velocity: int = 100, *,
                pitch_offset_semitones: float = 0.0,
                micropitch_curve: list = None,
                note_duration_samples: int = 0) -> bool:
        """Start a sustained note (live MIDI keyboard).

        Compatible with SamplerRegistry.note_on() dispatch.
        """
        if not self._ok or self._synth is None or self._shutdown:
            return False
        try:
            pitch = _clamp(int(pitch), 0, 127)
            velocity = _clamp(int(velocity), 1, 127)
            with self._lock:
                self._synth.noteon(0, pitch, velocity)
                self._active_notes.add(pitch)
            return True
        except Exception as exc:
            print(f"[SF2-RT] note_on error: {exc}", file=sys.stderr, flush=True)
            return False

    def note_off(self, pitch: int = -1) -> None:
        """Stop a note. If pitch >= 0: polyphonic release. If < 0: release all."""
        if not self._ok or self._synth is None or self._shutdown:
            return
        try:
            with self._lock:
                if pitch >= 0:
                    self._synth.noteoff(0, _clamp(int(pitch), 0, 127))
                    self._active_notes.discard(int(pitch))
                else:
                    # Release all active notes
                    for p in list(self._active_notes):
                        try:
                            self._synth.noteoff(0, int(p))
                        except Exception:
                            pass
                    self._active_notes.clear()
        except Exception as exc:
            print(f"[SF2-RT] note_off error: {exc}", file=sys.stderr, flush=True)

    def all_notes_off(self) -> None:
        """Panic: stop all notes on all channels."""
        if not self._ok or self._synth is None or self._shutdown:
            return
        try:
            with self._lock:
                for ch in range(16):
                    for p in range(128):
                        try:
                            self._synth.noteoff(ch, p)
                        except Exception:
                            pass
                self._active_notes.clear()
        except Exception:
            pass

    def trigger_note(self, pitch: int, velocity: int = 100,
                     duration_ms: int = 140) -> None:
        """One-shot note trigger (preview/audition)."""
        if not self._ok or self._synth is None or self._shutdown:
            return
        try:
            pitch = _clamp(int(pitch), 0, 127)
            velocity = _clamp(int(velocity), 1, 127)
            with self._lock:
                self._synth.noteon(0, pitch, velocity)
            # Schedule note-off after duration
            import threading as _th
            def _off():
                try:
                    with self._lock:
                        if self._synth is not None:
                            self._synth.noteoff(0, pitch)
                except Exception:
                    pass
            _th.Timer(max(0.01, float(duration_ms) / 1000.0), _off).start()
        except Exception:
            pass

    # ── Pull-Source Interface (called from Audio Thread) ──

    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Generate audio samples (called from HybridAudioCallback).

        Returns np.ndarray of shape (frames, 2) float32, or None if silent.
        """
        if not self._ok or self._synth is None or self._shutdown:
            return None

        try:
            with self._lock:
                # get_samples returns ctypes array of int16, interleaved stereo
                # Length = frames * 2 (L, R, L, R, ...)
                raw = self._synth.get_samples(int(frames))

            if raw is None:
                return None

            # Convert to numpy float32 stereo
            # raw is a ctypes array or numpy array of int16
            arr = np.frombuffer(raw, dtype=np.int16).copy()

            if len(arr) == 0:
                return None

            # Convert int16 → float32 normalized
            out = arr.astype(np.float32) / 32768.0

            # Reshape to (frames, 2) stereo
            if len(out) >= frames * 2:
                out = out[:frames * 2].reshape(frames, 2)
            else:
                # Pad if too short
                padded = np.zeros(frames * 2, dtype=np.float32)
                padded[:len(out)] = out
                out = padded.reshape(frames, 2)

            # Quick silence check — don't return zeros
            if np.max(np.abs(out)) < 1e-8:
                return None

            return out

        except Exception as exc:
            # Don't spam logs in audio thread
            return None

    # ── Program Change ──

    def set_program(self, bank: int = 0, preset: int = 0) -> None:
        """Change bank/preset (e.g. when user switches in SF2 widget)."""
        if not self._ok or self._synth is None or self._shutdown:
            return
        try:
            with self._lock:
                self._bank = int(bank)
                self._preset = int(preset)
                self._synth.program_select(0, self._sfid, int(bank), int(preset))
        except Exception as exc:
            print(f"[SF2-RT] set_program error: {exc}", file=sys.stderr, flush=True)

    # ── Lifecycle ──

    def shutdown(self) -> None:
        """Clean up FluidSynth resources."""
        self._shutdown = True
        self._ok = False
        try:
            with self._lock:
                if self._synth is not None:
                    try:
                        self.all_notes_off()
                    except Exception:
                        pass
                    try:
                        if self._sfid >= 0:
                            self._synth.sfunload(self._sfid)
                    except Exception:
                        pass
                    try:
                        self._synth.delete()
                    except Exception:
                        pass
                    self._synth = None
                    self._sfid = -1
        except Exception:
            pass
        print(f"[SF2-RT] Engine shutdown: track={self._track_id}", file=sys.stderr, flush=True)

    def __del__(self):
        try:
            if not self._shutdown:
                self.shutdown()
        except Exception:
            pass
