# -*- coding: utf-8 -*-
"""Bach Orgel Engine (pull-based, lightweight additive synth).

v0.0.20.104 — Klang-Overhaul: Warm + Organisch statt blechern/kratzig.

Änderungen gegenüber v103:
- Pipe-Detuning: Jede Harmonische leicht verstimmt (±1-4 Cent) → organischer Chor-Effekt
- Chorus-Drift: Langsame, subtile Pitch-Modulation pro Pfeife → lebendiger Klang
- Besseres Stereo: Allpass-Dekorrelation statt np.roll-Kammfilter → kein metallisches Kratzen
- Subtiles Air/Wind-Noise: Hauch von Windgeräusch → Pfeifen-Realismus
- Sanftere Sättigung: Kubischer Soft-Clip statt hartem tanh bei niedrigem Drive
- Weichere Oszillatoren: Mehr Sine-Anteil in Triangle/Square/Saw
- Presets: Default-Werte weicher abgestimmt

KEINE Änderungen an: API, SamplerRegistry-Contract, Widget, anderen Instrumenten.

Goals:
- Integrate like existing sampler/drum instruments (SamplerRegistry + pull-source)
- Provide organ-style timbres for PianoRoll/Notation preview/playback
- Keep implementation self-contained and safe (no core engine changes)

Notes:
- `note_off()` has no pitch in SamplerRegistry, so we release all active voices.
  This matches the current registry contract used by existing instruments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import threading
from typing import Any, Dict, List, Optional

import numpy as np


TWOPI = 2.0 * math.pi

# --- Pipe detuning table (in cents, per harmonic multiplier) ---
# Echte Kirchenorgeln haben minimale Verstimmungen zwischen Pfeifen.
# Das erzeugt den warmen, "schwebenden" Choreffekt.
_PIPE_DETUNE_CENTS = {
    0.5:  -1.8,   # Sub-Oktave leicht tiefer
    1.0:   0.0,   # Grundton bleibt rein
    2.0:   1.2,   # Oktave leicht höher
    3.0:  -0.9,   # Quinte
    4.0:   2.1,   # Doppeloktave
    5.0:  -1.5,   # Terz-Oberton
    6.0:   0.7,
    7.0:  -2.2,
    8.0:   1.6,
    10.0: -1.0,
}


def _detune_freq(base_freq: float, mult: float) -> float:
    """Berechne leicht verstimmte Frequenz für eine Pfeife."""
    cents = _PIPE_DETUNE_CENTS.get(mult, 0.0)
    return base_freq * mult * (2.0 ** (cents / 1200.0))


@dataclass
class OrganVoice:
    pitch: int
    freq: float
    velocity: float
    phase: float = 0.0
    # Pro-Pipe Phasen für unabhängige Drift
    pipe_phases: Optional[Dict[float, float]] = field(default=None)
    age_samples: int = 0
    released: bool = False
    release_age_samples: int = 0
    release_level: float = 1.0
    preview_frames_left: Optional[int] = None
    note_on_seq: int = 0
    release_override_samples: Optional[int] = None
    # --- MPE v2: continuous micropitch curve ---
    micropitch_curve: list = field(default_factory=list)
    micropitch_duration: int = 0
    micropitch_elapsed: int = 0
    base_freq: float = 0.0  # freq without micropitch offset, for re-computation


class BachOrgelEngine:
    """Simple additive organ synth compatible with PyDAW pull-source routing.

    v104: Warmer, organischer Klang durch Pipe-Detuning, Chorus-Drift,
    besseres Stereo und subtiles Air-Noise.
    """

    # Pipe multipliers die wir tracken
    _PIPE_MULTS = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0)

    def __init__(self, target_sr: int = 48000):
        self.target_sr = int(target_sr or 48000)
        self._lock = threading.RLock()
        self._voices: List[OrganVoice] = []
        self._seq = 0
        self._lfo_phase = 0.0
        self._drift_phase = 0.0  # Langsame Chorus-Drift
        self._last_mix = None
        # Filter-States (2-Pole für sanfteren Rolloff)
        self._lp_state = 0.0
        self._lp2_state = 0.0
        self._hp_state = 0.0
        # Air-noise state
        self._air_lp = 0.0
        self._params: Dict[str, Any] = {
            # control
            'instr': 'organ',
            'wave': 'sine',
            'voicing': 'warm',
            # synth-ish section (0..1 unless documented)
            'cut': 0.72,        # v104: etwas dunkler als Default
            'res': 0.18,        # v104: weniger Resonanz
            'attack': 0.025,    # v104: minimal sanfterer Attack
            'env_amt': 0.45,    # v104: weniger Envelope-Modulation
            'tune': 0.0,
            'env': 0.65,
            'dec': 0.20,
            'release': 0.35,    # v104: etwas längerer Release
            'accent': 0.20,
            # organ stops / colors
            'stop16': 0.18,
            'stop8': 0.88,      # v104: leicht reduziert
            'stop4': 0.55,      # v104: reduziert (weniger Obertöne = weniger blechern)
            'stop2': 0.18,      # v104: deutlich reduziert
            'gain': 0.62,
            'mix': 0.18,
            'reed': 0.04,       # v104: weniger Reed
            'click': 0.02,      # v104: sanfterer Click
            'drv': 0.02,        # v104: weniger Drive
            'trem_rate': 4.5,
            'trem_depth': 0.06, # v104: subtileres Tremolo
            # FX section
            'fx_drv': 0.04,     # v104: weniger FX-Drive
            'fx_lvl': 0.82,
            # Air/Wind (NEU v104)
            'air': 0.06,        # Subtiles Windgeräusch
            # tempo knob
            'tempo': 0.45,
        }
        self._preset_name: str = 'Barock Plenum'

    # ---------------- public control API
    def set_param(self, key: str, value: Any) -> None:
        with self._lock:
            if key in ('instr', 'wave', 'voicing'):
                self._params[key] = str(value)
                return
            try:
                fv = float(value)
            except Exception:
                return
            if key == 'tune':
                self._params[key] = max(-12.0, min(12.0, fv))
            elif key == 'trem_rate':
                self._params[key] = max(0.05, min(12.0, fv))
            elif key in ('tempo',):
                self._params[key] = max(0.0, min(1.0, fv))
            else:
                self._params[key] = max(0.0, min(1.0, fv))
            # keep helper params in sync
            if key == 'tempo':
                self._params['trem_rate'] = 0.25 + self._params['tempo'] * 9.75
            elif key == 'trem_rate':
                self._params['tempo'] = (self._params['trem_rate'] - 0.25) / 9.75

    def get_param(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._params.get(key, default)

    def set_preset_name(self, name: str) -> None:
        with self._lock:
            self._preset_name = str(name or '')

    def get_preset_name(self) -> str:
        with self._lock:
            return str(self._preset_name)

    # ---------------- midi/note APIs (SamplerRegistry contract)
    def trigger_note(self, pitch: int, velocity: int = 100, duration_ms: int | None = 180) -> bool:
        ok = self.note_on(pitch, velocity)
        if not ok:
            return False
        with self._lock:
            if self._voices:
                v = self._voices[-1]
                if duration_ms is not None:
                    try:
                        v.preview_frames_left = max(1, int((float(duration_ms) / 1000.0) * self.target_sr))
                    except Exception:
                        v.preview_frames_left = None
        return True

    def note_on(self, pitch: int, velocity: int = 100, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        try:
            p = int(pitch)
            vel = int(max(1, min(127, velocity)))
        except Exception:
            return False
        tune_semi = float(self.get_param('tune', 0.0) or 0.0)
        freq = 440.0 * (2.0 ** (((((float(p) + float(pitch_offset_semitones or 0.0)) - 69) + tune_semi) / 12.0)))
        base_freq_no_mp = 440.0 * (2.0 ** ((((float(p) - 69) + tune_semi) / 12.0)))
        if not (10.0 <= freq <= 12000.0):
            return False
        with self._lock:
            self._seq += 1
            # Initialisiere unabhängige Phasen pro Pfeife (für Detuning/Drift)
            pipe_phases = {m: 0.0 for m in self._PIPE_MULTS}
            v = OrganVoice(
                pitch=p,
                freq=float(freq),
                velocity=vel / 127.0,
                pipe_phases=pipe_phases,
                note_on_seq=self._seq,
                micropitch_curve=list(micropitch_curve or []),
                micropitch_duration=max(0, int(note_duration_samples or 0)),
                micropitch_elapsed=0,
                base_freq=float(base_freq_no_mp),
            )
            self._voices.append(v)
            max_voices = 24
            if len(self._voices) > max_voices:
                self._voices = self._voices[-max_voices:]
        return True

    def note_off(self) -> None:
        # Registry contract doesn't pass pitch -> release all active voices.
        # IMPORTANT: use a short gated release so 16th notes don't ring across gaps.
        self._release_all_voices(fast=True)

    def all_notes_off(self) -> None:
        # Panic/transport stop should be at least fast, not endless tails.
        self._release_all_voices(fast=True)

    def _release_all_voices(self, fast: bool = False) -> None:
        with self._lock:
            for v in self._voices:
                if v.released:
                    continue
                v.released = True
                v.release_age_samples = 0
                v.release_level = self._estimate_voice_level(v)
                if fast:
                    v.release_override_samples = self._gate_release_samples()

    def stop_all(self) -> None:
        with self._lock:
            self._voices.clear()

    # ---------------- state IO
    def export_state(self) -> dict:
        with self._lock:
            return {
                'params': dict(self._params),
                'preset_name': str(self._preset_name),
            }

    def import_state(self, d: dict) -> None:
        if not isinstance(d, dict):
            return
        with self._lock:
            params = d.get('params', {}) or {}
            if isinstance(params, dict):
                for k, v in params.items():
                    # reuse validation and sync logic
                    self.set_param(str(k), v)
            if 'preset_name' in d:
                self._preset_name = str(d.get('preset_name') or '')

    # ---------------- audio render
    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        frames = int(frames)
        if frames <= 0:
            return None
        sr = int(sr or self.target_sr or 48000)
        if sr <= 0:
            sr = 48000
        if sr != int(self.target_sr):
            # follow host sample rate to avoid silence / pitch mismatch surprises
            self.target_sr = sr

        with self._lock:
            if not self._voices:
                return None
            params = dict(self._params)
            voices = list(self._voices)

        out = np.zeros((frames,), dtype=np.float32)
        t_idx = np.arange(frames, dtype=np.float32)

        # Global tremolo shared by engine for a cohesive organ feel
        trem_rate = float(params.get('trem_rate', 4.0) or 4.0)
        trem_depth = float(params.get('trem_depth', 0.0) or 0.0)
        lfo_inc = (TWOPI * trem_rate) / float(sr)
        trem_phase = self._lfo_phase + lfo_inc * t_idx
        trem = (1.0 - trem_depth) + trem_depth * (0.5 + 0.5 * np.sin(trem_phase, dtype=np.float32))
        self._lfo_phase = float((trem_phase[-1] + lfo_inc) % TWOPI)

        # Chorus-Drift: langsame Pitch-Modulation (~0.3 Hz) für Lebendigkeit
        drift_rate = 0.31  # Hz — sehr langsam, kaum hörbar als Vibrato
        drift_inc = (TWOPI * drift_rate) / float(sr)
        drift_phase = self._drift_phase + drift_inc * t_idx
        # ±0.8 cent Drift (sehr subtil, aber erzeugt organische Lebendigkeit)
        drift_cents = 0.8 * np.sin(drift_phase, dtype=np.float32)
        drift_ratio = np.power(2.0, drift_cents / 1200.0).astype(np.float32)
        self._drift_phase = float((drift_phase[-1] + drift_inc) % TWOPI)

        # Render voices outside lock, then commit state afterwards
        new_voices: List[OrganVoice] = []
        for v in voices:
            block, v_alive, v_new = self._render_voice(v, frames, sr, params, t_idx, drift_ratio)
            if block is not None:
                out[: len(block)] += block.astype(np.float32, copy=False)
            if v_alive:
                new_voices.append(v_new)

        # Subtiles Air/Wind-Noise (v104 NEU)
        air_amt = float(params.get('air', 0.04) or 0.0)
        voicing = str(params.get('voicing', 'warm') or 'warm').lower()
        if air_amt > 1e-4 and len(new_voices) > 0:
            # Band-limitiertes Rauschen (tiefpass-gefiltert) — klingt wie Wind in Pfeifen
            noise = np.random.randn(frames).astype(np.float32) * 0.12
            # Einfacher Tiefpass auf ~800 Hz für weiches Rauschen
            air_fc = 800.0
            air_a = math.exp(-TWOPI * air_fc / float(sr))
            air_lp = float(self._air_lp)
            for i in range(frames):
                air_lp = air_a * air_lp + (1.0 - air_a) * noise[i]
                noise[i] = air_lp
            self._air_lp = air_lp
            out += noise * np.float32(air_amt)

        # Sanfte Sättigung (v104: Soft-Clip statt hartem tanh)
        drive = float(params.get('drv', 0.0) or 0.0)
        fx_drv = float(params.get('fx_drv', 0.0) or 0.0)
        if voicing == 'warm':
            total_drive = 1.0 + (drive * 0.40) + (fx_drv * 0.55)
        else:
            total_drive = 1.0 + (drive * 0.90) + (fx_drv * 1.20)
        if total_drive > 1.03:
            # v104: Soft-Clip erzeugt weniger harsche Obertöne als tanh
            out = self._soft_clip(out * total_drive)

        # Klang glätten (gegen blechern/kratzig): sanfter Tone-Filter + leichter DC/edge cleanup
        out = self._shape_tone(out, sr, params)

        # output level
        gain = float(params.get('gain', 0.7) or 0.7)
        lvl = float(params.get('fx_lvl', 0.8) or 0.8)
        base_mul = 0.58 if voicing == 'warm' else 0.65
        out *= np.float32(max(0.0, min(1.10, gain * lvl * base_mul)))
        out *= trem.astype(np.float32, copy=False)

        # safety limiter (verhindert kratziges Überfahren)
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 0.95:
            out *= np.float32(0.95 / max(peak, 1e-9))

        # v104: Stereo via Allpass-Dekorrelation statt np.roll-Kammfilter
        mix = float(params.get('mix', 0.0) or 0.0)
        stereo = self._make_stereo(out, mix, voicing, frames, sr)

        # commit updated voices
        with self._lock:
            self._voices = new_voices

        return stereo

    # ---------------- internals
    def _estimate_voice_level(self, v: OrganVoice) -> float:
        atk = self._attack_seconds()
        if atk <= 1e-5:
            return 1.0
        atk_samples = max(1.0, atk * float(self.target_sr))
        return float(max(0.0, min(1.0, v.age_samples / atk_samples)))

    def _attack_seconds(self) -> float:
        p_attack = float(self.get_param('attack', 0.02) or 0.02)
        p_env = float(self.get_param('env', 0.6) or 0.6)
        return 0.001 + (p_attack * 0.35) + (1.0 - p_env) * 0.03

    def _release_seconds(self) -> float:
        p_release = float(self.get_param('release', 0.3) or 0.3)
        p_dec = float(self.get_param('dec', 0.2) or 0.2)
        return 0.005 + p_release * 1.25 + p_dec * 0.15

    def _gate_release_samples(self) -> int:
        """Short release used for sequencer/live note_off to avoid long ringing gaps."""
        p_release = float(self.get_param('release', 0.3) or 0.3)
        p_dec = float(self.get_param('dec', 0.2) or 0.2)
        # Organ should stop cleanly on short notes; keep a tiny tail to avoid clicks.
        sec = 0.008 + p_release * 0.070 + p_dec * 0.015
        sec = max(0.008, min(0.090, sec))
        return max(1, int(sec * float(max(1, self.target_sr))))

    @staticmethod
    def _soft_clip(x: np.ndarray) -> np.ndarray:
        """Weichere Sättigung als tanh — erzeugt weniger harsche Obertöne.

        Kubische Soft-Clip Kurve: y = x - x^3/3 für |x| < 1, clipped bei +/-2/3.
        Klingt wärmer als tanh weil weniger hochfrequente Verzerrungsprodukte.
        """
        out = np.where(
            np.abs(x) < 1.0,
            x - (x * x * x) / 3.0,
            np.sign(x) * (2.0 / 3.0)
        )
        return out.astype(np.float32, copy=False)

    def _make_stereo(self, mono: np.ndarray, mix: float, voicing: str,
                     frames: int, sr: int) -> np.ndarray:
        """Stereo-Widening via Allpass-Dekorrelation statt np.roll.

        v104 FIX: np.roll erzeugte Kammfilter-Artefakte = metallischer Klang.
        Jetzt: Leichter Allpass + Mid/Side für natürliche Breite ohne Kratzen.
        """
        width = (0.02 + 0.06 * mix) if voicing == 'warm' else (0.03 + 0.12 * mix)

        # Dekorreliertes Signal via leichter Allpass-Approximation
        # (phasenverschoben ohne destruktive Interferenz / Kammfilter)
        allpass_fc = 220.0 + 180.0 * mix
        ap_coeff = math.exp(-TWOPI * allpass_fc / float(sr))

        decorr = np.empty_like(mono)
        state = 0.0
        prev_x = 0.0
        for i in range(frames):
            xi = float(mono[i])
            state = ap_coeff * (xi - state) + prev_x
            decorr[i] = state
            prev_x = xi

        # Mid/Side Encoding — natürliche Breite
        mid = mono
        side = (mono - decorr.astype(np.float32)) * np.float32(width)

        stereo = np.empty((frames, 2), dtype=np.float32)
        stereo[:, 0] = mid + side
        stereo[:, 1] = mid - side
        return stereo

    def _shape_tone(self, x: np.ndarray, sr: int, params: dict) -> np.ndarray:
        """Sanfte Klangformung gegen aliasing/kratzige Höhen (v104: wärmerer Filter)."""
        if x is None or x.size == 0:
            return x
        cut = float(params.get('cut', 0.72) or 0.72)
        res = float(params.get('res', 0.18) or 0.18)
        voicing = str(params.get('voicing', 'warm') or 'warm').lower()

        # v104: Tiefere Grenzfrequenz = wärmerer Grundklang
        if voicing == 'warm':
            fc = 350.0 + (cut ** 1.15) * 2800.0
            fc *= (1.0 - 0.20 * max(0.0, min(1.0, res)))
            fc = max(160.0, min(4500.0, fc))
        else:
            fc = 550.0 + (cut ** 1.30) * 4800.0
            fc *= (1.0 - 0.22 * max(0.0, min(1.0, res)))
            fc = max(200.0, min(8000.0, fc))

        a = math.exp(-TWOPI * fc / max(1.0, float(sr)))

        # 2-Pole Tiefpass (warm) oder 1-Pole (clean)
        y = np.empty_like(x, dtype=np.float32)
        lp = float(self._lp_state)
        lp2 = float(self._lp2_state)
        for i in range(int(x.shape[0])):
            xi = float(x[i])
            lp = a * lp + (1.0 - a) * xi
            if voicing == 'warm':
                lp2 = a * lp2 + (1.0 - a) * lp
                y[i] = lp2
            else:
                y[i] = lp
        self._lp_state = lp
        self._lp2_state = lp2

        # leichter HP/edge-cleanup (entfernt Kratzen/DC ohne Bassverlust)
        hp_fc = 18.0
        ah = math.exp(-TWOPI * hp_fc / max(1.0, float(sr)))
        hp = float(self._hp_state)
        z = np.empty_like(y, dtype=np.float32)
        for i in range(int(y.shape[0])):
            yi = float(y[i])
            hp = ah * hp + (1.0 - ah) * yi
            z[i] = yi - hp
        self._hp_state = hp
        return z

    def _render_voice(self, v: OrganVoice, frames: int, sr: int, params: dict,
                      t_idx: np.ndarray, drift_ratio: np.ndarray):
        """Render einer Stimme — v104: mit Pipe-Detuning und Chorus-Drift."""

        # --- MPE v2: update freq from continuous micropitch curve ---
        if v.micropitch_curve and v.micropitch_duration > 0 and v.base_freq > 0.0:
            t_norm = float(v.micropitch_elapsed) / float(v.micropitch_duration)
            if t_norm > 1.0:
                t_norm = 1.0
            curve = v.micropitch_curve
            mp_semi = 0.0
            if t_norm <= curve[0][0]:
                mp_semi = curve[0][1]
            elif t_norm >= curve[-1][0]:
                mp_semi = curve[-1][1]
            else:
                prev_t, prev_v = curve[0]
                for ci in range(1, len(curve)):
                    nxt_t, nxt_v = curve[ci]
                    if t_norm <= nxt_t:
                        seg_len = nxt_t - prev_t
                        if seg_len > 1e-9:
                            a = (t_norm - prev_t) / seg_len
                            mp_semi = (1.0 - a) * prev_v + a * nxt_v
                        else:
                            mp_semi = nxt_v
                        break
                    prev_t, prev_v = nxt_t, nxt_v
            # Update voice frequency with micropitch bend
            v.freq = v.base_freq * (2.0 ** (mp_semi / 12.0))
            v.micropitch_elapsed += frames

        wave = str(params.get('wave', 'sine') or 'sine').lower()
        instr = str(params.get('instr', 'organ') or 'organ').lower()
        voicing = str(params.get('voicing', 'warm') or 'warm').lower()

        # organ stops / harmonics
        w16 = float(params.get('stop16', 0.0) or 0.0)
        w8 = float(params.get('stop8', 1.0) or 1.0)
        w4 = float(params.get('stop4', 0.0) or 0.0)
        w2 = float(params.get('stop2', 0.0) or 0.0)
        reed = float(params.get('reed', 0.0) or 0.0)
        cut = float(params.get('cut', 0.72) or 0.72)
        res = float(params.get('res', 0.18) or 0.18)
        click = float(params.get('click', 0.0) or 0.0)
        accent = float(params.get('accent', 0.2) or 0.2)
        env_amt = float(params.get('env_amt', 0.5) or 0.5)

        # timbre profile by instrument mode
        if instr == 'bass':
            w16 *= 1.35; w8 *= 0.85; w4 *= 0.55; w2 *= 0.25
            reed *= 0.5
        elif instr == 'flute':
            reed *= 0.2; w16 *= 0.7; w4 *= 0.7; w2 *= 0.4
        elif instr == 'choral':
            reed *= 0.9; w4 *= 1.15; w2 *= 0.9

        # Pipe-Phasen holen oder initialisieren
        pipe_phases = v.pipe_phases
        if pipe_phases is None:
            pipe_phases = {m: 0.0 for m in self._PIPE_MULTS}

        new_pipe_phases = {}

        if voicing == 'warm':
            # ===== WARM VOICING (v104: mit Pipe-Detuning + Drift) =====
            mix_amt = float(max(0.0, min(1.0, params.get('mix', 0.0) or 0.0)))
            reed = min(reed, 0.50)
            click = min(click, 0.25)

            # Wave-Tint: nur ein Hauch, Grundklang bleibt sauber-additiv
            tint = 0.0 if wave == 'sine' else (0.06 if wave == 'triangle' else 0.09)

            def render_pipe(mult: float, weight: float) -> np.ndarray:
                """Rendere eine einzelne Orgelpfeife mit eigenem Detuning + Drift."""
                if abs(weight) < 1e-5:
                    new_pipe_phases[mult] = pipe_phases.get(mult, 0.0)
                    return np.zeros(frames, dtype=np.float32)

                # Verstimmte Frequenz pro Pfeife (echtes Orgel-Detuning)
                det_freq = _detune_freq(v.freq, mult)
                # Plus globaler Chorus-Drift
                phase_inc_base = (TWOPI * det_freq) / float(sr)

                # Phase mit Drift-Modulation (drift_ratio variiert pro Sample)
                p0 = pipe_phases.get(mult, 0.0)
                phase_incs = np.float32(phase_inc_base) * drift_ratio
                ph = np.float32(p0) + np.cumsum(phase_incs)
                new_pipe_phases[mult] = float(ph[-1] % TWOPI)

                base = np.sin(ph, dtype=np.float32)
                if tint > 1e-6:
                    col = self._osc(ph, wave)
                    return ((base * (1.0 - tint) + col * tint) * weight).astype(np.float32, copy=False)
                return (base * weight).astype(np.float32, copy=False)

            # Hauptregister (16', 8', 4', 2')
            s = (
                render_pipe(0.5, w16 * 0.90)
                + render_pipe(1.0, w8 * 1.00)
                + render_pipe(2.0, w4 * 0.90)
                + render_pipe(4.0, w2 * 0.78)
            )

            # Mix-Harmonische (Mutations / Aliquoten)
            if mix_amt > 0.01:
                s += (
                    render_pipe(6.0, mix_amt * 0.14)
                    + render_pipe(8.0, mix_amt * 0.10)
                    + render_pipe(10.0, mix_amt * 0.07)
                )

            # Reed-Register (Zungen — ungeradzahlige Harmonische)
            if reed > 0.01:
                s += (
                    render_pipe(3.0, reed * 0.18)
                    + render_pipe(5.0, reed * 0.12)
                    + render_pipe(7.0, reed * 0.07)
                )

            # Normalisierung
            norm = (abs(w16) + abs(w8) + abs(w4) + abs(w2) + abs(mix_amt) * 0.25 + abs(reed) * 0.35)
            if norm > 1e-6:
                s *= np.float32(1.0 / max(1.0, norm))

        else:
            # ===== CLEAN VOICING (original-ähnlich, leicht verbessert) =====
            brightness = 0.10 + 0.90 * cut
            q_boost = 1.0 + 0.5 * res  # v104: weniger Q-Boost
            h_decay = 0.30 + (1.2 - brightness)
            def hw(k: float) -> float:
                return float(math.exp(-max(0.0, k - 1.0) * h_decay))

            # Basis-Phase mit Drift (kein Pipe-Detuning im Clean-Mode)
            phase_inc = (TWOPI * float(v.freq)) / float(sr)
            phase_incs = np.float32(phase_inc) * drift_ratio
            ph = np.float32(v.phase) + np.cumsum(phase_incs)

            s = (
                w16 * hw(0.5) * self._osc(ph * 0.5, wave)
                + w8 * hw(1.0) * self._osc(ph * 1.0, wave)
                + w4 * hw(2.0) * self._osc(ph * 2.0, wave)
                + w2 * hw(4.0) * self._osc(ph * 4.0, wave)
                + reed * q_boost * (
                    0.60 * hw(3.0) * self._osc(ph * 3.0, 'saw')  # v104: etwas weniger Reed
                    + 0.25 * hw(5.0) * self._osc(ph * 5.0, 'square')
                )
            ).astype(np.float32, copy=False)

            norm = (abs(w16) + abs(w8) + abs(w4) + abs(w2) + abs(reed) * 0.7)
            if norm > 1e-6:
                s *= np.float32(1.0 / max(1.0, norm))

            # Speichere Clean-Phase
            new_pipe_phases = dict(pipe_phases)

        # organ key click / chiff (v104: sanfter, kürzer)
        if click > 1e-4:
            age = int(v.age_samples)
            if voicing == 'warm' and 1.0 in new_pipe_phases:
                click_ph_inc = (TWOPI * _detune_freq(v.freq, 1.0)) / float(sr)
            else:
                click_ph_inc = (TWOPI * v.freq) / float(sr)
            click_ph = click_ph_inc * t_idx

            click_len = max(6, int(sr * (0.002 + 0.005 * click)))  # v104: kürzerer Click
            local_n = age + np.arange(frames, dtype=np.int32)
            mask = local_n < click_len
            if np.any(mask):
                tt = local_n.astype(np.float32) / max(1.0, float(click_len))
                envc = np.exp(-10.0 * tt, dtype=np.float32)  # v104: schnellerer Decay
                rnd = (np.random.rand(frames).astype(np.float32) * 2.0 - 1.0)
                # v104: Gefiltertes Rauschen (weicher als rohes Noise)
                rnd = (rnd + np.roll(rnd, 1) + np.roll(rnd, 2)) / 3.0
                chiff = (np.sin(click_ph * 3.0) * 0.2 + rnd * 0.8)
                amp = 0.018 * click  # v104: leiser
                s += (mask.astype(np.float32) * envc * chiff * np.float32(amp))

        # velocity / accent response
        vel_gain = 0.45 + 0.55 * float(v.velocity)
        vel_gain *= (1.0 + accent * 0.30 * max(0.0, float(v.velocity) - 0.5))

        # envelope (attack + release only, stable and cheap)
        atk_s = self._attack_seconds()
        rel_s = self._release_seconds()
        atk_n = max(1, int(atk_s * sr))
        rel_n = max(1, int(rel_s * sr))

        if not v.released:
            a0 = int(v.age_samples)
            env = np.clip((a0 + np.arange(frames, dtype=np.float32)) / float(atk_n), 0.0, 1.0)
            # optional mild body contour from env_amt/dec
            if env_amt > 1e-4:
                body = 1.0 - (0.12 * float(params.get('dec', 0.2) or 0.2))
                env = (env * (1.0 - env_amt * 0.12)) + (body * env_amt * 0.12)

            v_new = OrganVoice(
                pitch=v.pitch, freq=v.freq, velocity=v.velocity,
                phase=new_pipe_phases.get(1.0, v.phase),
                pipe_phases=new_pipe_phases,
                age_samples=a0 + frames,
                released=False,
                release_age_samples=0,
                release_level=1.0,
                preview_frames_left=v.preview_frames_left,
                note_on_seq=v.note_on_seq,
                release_override_samples=v.release_override_samples,
                micropitch_curve=v.micropitch_curve,
                micropitch_duration=v.micropitch_duration,
                micropitch_elapsed=v.micropitch_elapsed,
                base_freq=v.base_freq,
            )
            if v.preview_frames_left is not None:
                left = int(v.preview_frames_left) - frames
                v_new.preview_frames_left = left
                if left <= 0:
                    v_new.released = True
                    v_new.release_age_samples = 0
                    v_new.release_override_samples = None
                    try:
                        v_new.release_level = float(env[-1])
                    except Exception:
                        v_new.release_level = 1.0
            block = s * env.astype(np.float32, copy=False) * np.float32(vel_gain)
            return block, True, v_new

        # released
        r0 = int(v.release_age_samples)
        rel_n = int(v.release_override_samples) if getattr(v, 'release_override_samples', None) not in (None, 0) else rel_n
        rel_n = max(1, rel_n)
        env_r = np.clip(1.0 - ((r0 + np.arange(frames, dtype=np.float32)) / float(rel_n)), 0.0, 1.0)
        env = env_r * np.float32(max(0.0, min(1.2, float(v.release_level))))

        v_new = OrganVoice(
            pitch=v.pitch, freq=v.freq, velocity=v.velocity,
            phase=new_pipe_phases.get(1.0, v.phase),
            pipe_phases=new_pipe_phases,
            age_samples=int(v.age_samples) + frames,
            released=True,
            release_age_samples=r0 + frames,
            release_level=v.release_level,
            preview_frames_left=v.preview_frames_left,
            note_on_seq=v.note_on_seq,
            release_override_samples=v.release_override_samples,
            micropitch_curve=v.micropitch_curve,
            micropitch_duration=v.micropitch_duration,
            micropitch_elapsed=v.micropitch_elapsed,
            base_freq=v.base_freq,
        )
        alive = bool(v_new.release_age_samples < rel_n and float(np.max(env)) > 1e-4)
        block = s * env.astype(np.float32, copy=False) * np.float32(vel_gain)
        return block, alive, v_new

    @staticmethod
    def _osc(phase: np.ndarray, wave: str) -> np.ndarray:
        """Oszillatoren — v104: weichere Wellenformen."""
        w = str(wave or 'sine').lower()
        if w == 'triangle':
            x = ((phase / np.float32(TWOPI)) % 1.0).astype(np.float32, copy=False)
            tri = (4.0 * np.abs(x - 0.5) - 1.0).astype(np.float32, copy=False)
            # v104: mehr Sine-Anteil (0.25 statt 0.15) = weicher
            return (0.75 * tri + 0.25 * np.sin(phase, dtype=np.float32)).astype(np.float32, copy=False)
        if w == 'square':
            # v104: sanfterer Soft-Square (1.8 statt 2.2)
            return np.tanh(1.8 * np.sin(phase, dtype=np.float32)).astype(np.float32, copy=False)
        if w == 'saw':
            # v104: weniger Harmonische (3 statt 4) = weicher
            s1 = np.sin(phase, dtype=np.float32)
            s2 = np.sin(phase * 2.0, dtype=np.float32) * 0.38
            s3 = np.sin(phase * 3.0, dtype=np.float32) * 0.18
            return (s1 + s2 + s3).astype(np.float32, copy=False)
        if w == 'noise':
            return ((np.random.rand(*phase.shape).astype(np.float32) * 2.0 - 1.0) * 0.30)
        # default sine
        return np.sin(phase, dtype=np.float32)
