# -*- coding: utf-8 -*-
"""Audio-FX DSP Processors (v0.0.20.107).

Numpy-basierte Echtzeit-Prozessoren für alle Bitwig-Style Effekte.

v107 Fixes:
- PitchShifter: Proper dual-grain PSOLA mit Hann-Fenster (war kaputt)
- Reverb: Comb-Delays skalieren mit Samplerate, bessere Diffusion+Stereo
- Chorus: 3-voice Modulation für reicheren Sound
- EQ5: Peak-EQ korrekt über biquad type 4
"""
from __future__ import annotations
import math
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None

try:
    from pydaw.audio.fx_chain import AudioFxBase
except ImportError:
    class AudioFxBase:
        def process_inplace(self, buf, frames: int, sr: int) -> None:
            raise NotImplementedError


def _c01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def _rtg(rt, key: str, default: float = 0.0) -> float:
    try:
        if rt is None: return float(default)
        for attr in ("get_smooth", "get_param", "get_target"):
            fn = getattr(rt, attr, None)
            if fn is not None: return float(fn(key, default))
    except Exception: pass
    return float(default)

def _biquad_coeffs(ftype: int, fc: float, q: float, sr: float, gain_db: float = 0.0):
    fc = max(20.0, min(fc, sr * 0.45))
    q = max(0.1, min(q, 20.0))
    w0 = 2.0 * math.pi * fc / sr
    sin_w0 = math.sin(w0)
    cos_w0 = math.cos(w0)
    alpha = sin_w0 / (2.0 * q)
    if ftype == 1:       # HP
        b0, b1, b2 = (1+cos_w0)/2, -(1+cos_w0), (1+cos_w0)/2
        a0 = 1 + alpha
    elif ftype == 2:     # BP
        b0, b1, b2 = alpha, 0.0, -alpha
        a0 = 1 + alpha
    elif ftype == 3:     # Notch
        b0, b1, b2 = 1.0, -2*cos_w0, 1.0
        a0 = 1 + alpha
    elif ftype == 4:     # Peak EQ
        A = 10.0 ** (gain_db / 40.0)
        b0 = 1 + alpha * A; b1 = -2 * cos_w0; b2 = 1 - alpha * A
        a0 = 1 + alpha / A
    else:                # LP
        b0, b1, b2 = (1-cos_w0)/2, 1-cos_w0, (1-cos_w0)/2
        a0 = 1 + alpha
    return b0/a0, b1/a0, b2/a0, (-2*cos_w0)/a0, (1-alpha)/a0 if ftype != 4 else (1-alpha/A)/a0

def _bq_stereo(buf, frames, b0, b1, b2, a1, a2, st):
    for ch in range(2):
        z1, z2 = st[ch*2], st[ch*2+1]
        for i in range(frames):
            xi = float(buf[i, ch])
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            buf[i, ch] = yi
        st[ch*2], st[ch*2+1] = z1, z2


# 1. EQ-5
class EQ5Fx(AudioFxBase):
    _FD = [80.0, 400.0, 1310.0, 3600.0, 12000.0]
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix
        self.states = [[0.0]*4 for _ in range(5)]
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            for i in range(5):
                g_db = _rtg(self.rt, f"{self.p}:b{i}_g", 0.0)
                if abs(g_db) < 0.1: continue
                freq = max(20, min(20000, _rtg(self.rt, f"{self.p}:b{i}_f", self._FD[i])))
                q = max(0.1, min(18, _rtg(self.rt, f"{self.p}:b{i}_q", 0.71)))
                A = 10.0 ** (g_db / 40.0)
                w0 = 2.0 * math.pi * freq / sr
                sw = math.sin(w0); cw = math.cos(w0)
                al = sw / (2.0 * q)
                a0 = 1 + al / A
                _bq_stereo(buf[:frames], frames,
                    (1+al*A)/a0, (-2*cw)/a0, (1-al*A)/a0, (-2*cw)/a0, (1-al/A)/a0,
                    self.states[i])
            out_db = _rtg(self.rt, f"{self.p}:output", 0.0)
            if abs(out_db) > 0.05:
                np.multiply(buf[:frames], 10.0**(out_db/20.0), out=buf[:frames])
        except Exception: pass


# 2. DELAY-2
class Delay2Fx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix
        self._maxd = 48000 * 4
        if np is not None:
            self._bl = np.zeros(self._maxd, dtype=np.float32)
            self._br = np.zeros(self._maxd, dtype=np.float32)
        else: self._bl = self._br = None
        self._pl = self._pr = 0
    def process_inplace(self, buf, frames, sr):
        if np is None or self._bl is None: return
        try:
            tl = max(0.001, min(4.0, _rtg(self.rt, f"{self.p}:time_l", 1.0)))
            tr = max(0.001, min(4.0, _rtg(self.rt, f"{self.p}:time_r", 1.0)))
            fbl = _c01(_rtg(self.rt, f"{self.p}:fb_l", 30) / 100)
            fbr = _c01(_rtg(self.rt, f"{self.p}:fb_r", 30) / 100)
            cfl = _c01(_rtg(self.rt, f"{self.p}:cf_l", 0) / 100)
            cfr = _c01(_rtg(self.rt, f"{self.p}:cf_r", 0) / 100)
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 30) / 100)
            dl = min(int(tl * sr), self._maxd - 1)
            dr = min(int(tr * sr), self._maxd - 1)
            M = self._maxd
            for i in range(frames):
                ol = float(self._bl[(self._pl - dl) % M])
                orr = float(self._br[(self._pr - dr) % M])
                il_ = float(buf[i, 0]); ir_ = float(buf[i, 1])
                self._bl[self._pl] = il_ + ol * fbl + orr * cfl
                self._br[self._pr] = ir_ + orr * fbr + ol * cfr
                self._pl = (self._pl + 1) % M
                self._pr = (self._pr + 1) % M
                buf[i, 0] = il_ * (1 - mix) + ol * mix
                buf[i, 1] = ir_ * (1 - mix) + orr * mix
        except Exception: pass


# 3. REVERB — Schroeder 4-Comb + 2-Allpass (SR-scaled, stereo, damping)
class ReverbFx(AudioFxBase):
    _CD_BASE = [1557, 1617, 1491, 1422]
    _AD_BASE = [225, 556]
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix
        self._sr = 0; self._cb = None; self._ab = None
        self._cp = [0]*4; self._ap = [0]*2
        self._cd = list(self._CD_BASE); self._ad = list(self._AD_BASE)
        self._lpf = [0.0]*4
    def _init_buffers(self, sr):
        if np is None: return
        self._sr = sr
        sc = sr / 44100.0
        self._cd = [max(10, int(d * sc)) for d in self._CD_BASE]
        self._ad = [max(10, int(d * sc)) for d in self._AD_BASE]
        self._cb = [np.zeros(d + int(sr * 0.5), dtype=np.float32) for d in self._cd]
        self._ab = [np.zeros(d + int(sr * 0.1), dtype=np.float32) for d in self._ad]
        self._cp = [0]*4; self._ap = [0]*2; self._lpf = [0.0]*4
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        if self._sr != sr or self._cb is None:
            self._init_buffers(sr)
            if self._cb is None: return
        try:
            decay = max(0.01, min(5.0, _rtg(self.rt, f"{self.p}:decay", 126) / 100.0))
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 50) / 100)
            diff = _c01(_rtg(self.rt, f"{self.p}:diffusion", 50) / 100)
            width = _c01(_rtg(self.rt, f"{self.p}:width", 50) / 100)
            fb = min(0.97, 0.4 + 0.55 * min(1.0, decay))
            ag = 0.3 + 0.4 * diff
            damp = 0.3 + 0.5 * diff
            for i in range(frames):
                mono = (float(buf[i, 0]) + float(buf[i, 1])) * 0.5
                cs_l = 0.0; cs_r = 0.0
                for c in range(4):
                    bl = len(self._cb[c])
                    rd = (self._cp[c] - self._cd[c]) % bl
                    oc = float(self._cb[c][rd])
                    self._lpf[c] = self._lpf[c] * damp + oc * (1 - damp)
                    self._cb[c][self._cp[c] % bl] = mono + self._lpf[c] * fb
                    self._cp[c] = (self._cp[c] + 1) % bl
                    if c < 2: cs_l += oc
                    else: cs_r += oc
                x_l = (cs_l * (0.5 + width*0.5) + cs_r * (0.5 - width*0.5)) * 0.5
                x_r = (cs_r * (0.5 + width*0.5) + cs_l * (0.5 - width*0.5)) * 0.5
                for a in range(2):
                    bl = len(self._ab[a])
                    rd = (self._ap[a] - self._ad[a]) % bl
                    dl_v = float(self._ab[a][rd])
                    oa = dl_v - ag * x_l
                    self._ab[a][self._ap[a] % bl] = x_l + ag * dl_v
                    self._ap[a] = (self._ap[a] + 1) % bl
                    x_l = oa; x_r = x_r * 0.7 + oa * 0.3
                buf[i, 0] = float(buf[i, 0]) * (1-mix) + x_l * mix
                buf[i, 1] = float(buf[i, 1]) * (1-mix) + x_r * mix
        except Exception: pass


# 4. COMB
class CombFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix
        self._maxd = 4800
        self._dl = np.zeros((self._maxd, 2), dtype=np.float32) if np is not None else None
        self._pos = 0
    def process_inplace(self, buf, frames, sr):
        if np is None or self._dl is None: return
        try:
            freq = max(20, min(2000, _rtg(self.rt, f"{self.p}:freq", 267)))
            fb = max(-1, min(1, _rtg(self.rt, f"{self.p}:feedback", 0) / 100))
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 50) / 100)
            ds = max(1, min(self._maxd-1, int(sr / freq)))
            M = self._maxd
            for i in range(frames):
                rd = (self._pos - ds) % M
                for ch in range(2):
                    d = float(self._dl[rd, ch]); inp = float(buf[i, ch])
                    self._dl[self._pos, ch] = inp + d * fb
                    buf[i, ch] = inp * (1-mix) + d * mix
                self._pos = (self._pos + 1) % M
        except Exception: pass


# 5. COMPRESSOR
class CompressorFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._env = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            th_db = _rtg(self.rt, f"{self.p}:thresh", -200) / 10.0
            ratio = max(1.0, _rtg(self.rt, f"{self.p}:ratio", 40) / 10.0)
            att_ms = max(0.1, _rtg(self.rt, f"{self.p}:attack", 10))
            rel_ms = max(1.0, _rtg(self.rt, f"{self.p}:release", 200))
            in_db = _rtg(self.rt, f"{self.p}:input", 0) / 10.0
            out_db = _rtg(self.rt, f"{self.p}:output", 0) / 10.0
            makeup = bool(_rtg(self.rt, f"{self.p}:makeup", 0))
            th_lin = 10 ** (th_db / 20); ig = 10 ** (in_db / 20); og = 10 ** (out_db / 20)
            ac = math.exp(-1/(att_ms*0.001*sr)) if att_ms > 0 else 0
            rc = math.exp(-1/(rel_ms*0.001*sr)) if rel_ms > 0 else 0
            if makeup and ratio > 1: og *= 10 ** ((-th_db * (1-1/ratio)) / 20)
            if abs(ig-1) > 0.001: np.multiply(buf[:frames], ig, out=buf[:frames])
            env = self._env
            for i in range(frames):
                pk = max(abs(float(buf[i, 0])), abs(float(buf[i, 1])))
                env = ac*env + (1-ac)*pk if pk > env else rc*env + (1-rc)*pk
                if env > th_lin and env > 1e-10:
                    gr = 10 ** (-(20*math.log10(env/th_lin)*(1-1/ratio))/20)
                else: gr = 1.0
                buf[i, 0] *= gr; buf[i, 1] *= gr
            self._env = env
            if abs(og-1) > 0.001: np.multiply(buf[:frames], og, out=buf[:frames])
        except Exception: pass


# 6. FILTER+
class FilterPlusFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._st = [0.0]*4; self._lfo_ph = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            drv_db = _rtg(self.rt, f"{self.p}:drive_db", 8)
            freq = max(20, min(20000, _rtg(self.rt, f"{self.p}:freq", 1050)))
            res = max(0.1, min(18, _rtg(self.rt, f"{self.p}:res", 25) * 0.18))
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 100) / 100)
            lfo_r = max(0.01, _rtg(self.rt, f"{self.p}:lfo_rate", 1.0))
            if abs(drv_db) > 0.1: np.multiply(buf[:frames], 10**(drv_db/20), out=buf[:frames])
            inc = lfo_r / sr; ph = self._lfo_ph
            for i in range(frames):
                mod = math.sin(2*math.pi*ph) * freq * 0.3
                fc = max(20, min(sr*0.45, freq + mod))
                b0,b1,b2,a1,a2 = _biquad_coeffs(0, fc, max(0.1, res), sr)
                for ch in range(2):
                    xi = float(buf[i, ch])
                    z1, z2 = self._st[ch*2], self._st[ch*2+1]
                    yi = b0*xi + z1; z1 = b1*xi - a1*yi + z2; z2 = b2*xi - a2*yi
                    self._st[ch*2], self._st[ch*2+1] = z1, z2
                    buf[i, ch] = xi*(1-mix) + yi*mix
                ph = (ph + inc) % 1.0
            self._lfo_ph = ph
        except Exception: pass


# 7. DISTORTION+
class DistortionPlusFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw): self.rt, self.p = rt, prefix
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            drive = _c01(_rtg(self.rt, f"{self.p}:drive", 25) / 100)
            symm = _rtg(self.rt, f"{self.p}:symm", 0) / 100
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 100) / 100)
            if drive < 0.001 or mix < 0.001: return
            k = 1 + 30 * drive
            for i in range(frames):
                for ch in range(2):
                    x = float(buf[i, ch]); wet = math.tanh((x + symm*0.5) * k)
                    buf[i, ch] = x*(1-mix) + wet*mix
        except Exception: pass


# 8. DYNAMICS
class DynamicsFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._env = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            hi_db = _rtg(self.rt, f"{self.p}:hi_thresh", -100) / 10
            hi_r = max(1.0, _rtg(self.rt, f"{self.p}:hi_ratio", 10) / 10)
            att_ms = max(0.1, _rtg(self.rt, f"{self.p}:attack", 10))
            rel_ms = max(1.0, _rtg(self.rt, f"{self.p}:release", 200))
            out_db = _rtg(self.rt, f"{self.p}:output", 0) / 10
            hi_lin = 10**(hi_db/20)
            ac = math.exp(-1/(att_ms*0.001*sr)) if att_ms > 0 else 0
            rc = math.exp(-1/(rel_ms*0.001*sr)) if rel_ms > 0 else 0
            og = 10**(out_db/20); env = self._env
            for i in range(frames):
                pk = max(abs(float(buf[i, 0])), abs(float(buf[i, 1])))
                env = ac*env+(1-ac)*pk if pk > env else rc*env+(1-rc)*pk
                gr = 10**(-(20*math.log10(env/hi_lin)*(1-1/hi_r))/20) if env > hi_lin and env > 1e-10 else 1.0
                buf[i, 0] *= gr; buf[i, 1] *= gr
            self._env = env
            if abs(og-1) > 0.001: np.multiply(buf[:frames], og, out=buf[:frames])
        except Exception: pass


# 9. FLANGER
class FlangerFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._maxd = 4800
        self._dl = np.zeros((self._maxd, 2), dtype=np.float32) if np is not None else None
        self._pos = 0; self._ph = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None or self._dl is None: return
        try:
            rate = max(0.01, _rtg(self.rt, f"{self.p}:rate", 0.44))
            tp = _c01(_rtg(self.rt, f"{self.p}:time", 50) / 100)
            fb = max(-1, min(1, _rtg(self.rt, f"{self.p}:feedback", 0) / 100))
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 50) / 100)
            bd = max(1, int(tp * 0.01 * sr)); ld = max(1, int(bd * 0.8))
            inc = rate / sr; M = self._maxd; ph = self._ph
            for i in range(frames):
                lfo = math.sin(2*math.pi*ph)
                ds = max(1, min(M-1, int(bd + lfo*ld)))
                rd = (self._pos - ds) % M
                for ch in range(2):
                    d = float(self._dl[rd, ch]); inp = float(buf[i, ch])
                    self._dl[self._pos, ch] = inp + d*fb
                    buf[i, ch] = inp*(1-mix) + d*mix
                self._pos = (self._pos+1) % M; ph = (ph+inc) % 1.0
            self._ph = ph
        except Exception: pass


# 10. PITCH SHIFTER — Proper dual-grain PSOLA
class PitchShifterFx(AudioFxBase):
    """Granularer Pitch Shifter mit 2 ueberlappenden Hann-Fenstern.
    Zwei Lese-Koepfe laufen mit Pitch-Ratio durch einen Ring-Buffer.
    Jeder Kopf hat ein Hann-Fenster, 50% phasenverschoben."""
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix
        self._blen = 48000
        self._rb = np.zeros((self._blen, 2), dtype=np.float32) if np is not None else None
        self._wp = 0
        self._rp0 = 0.0; self._rp1 = 0.0
        self._gp0 = 0.0; self._gp1 = 0.5
    def process_inplace(self, buf, frames, sr):
        if np is None or self._rb is None: return
        try:
            semi = _rtg(self.rt, f"{self.p}:semi", 0)
            grain_pct = _c01(_rtg(self.rt, f"{self.p}:grain", 50) / 100)
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 100) / 100)
            if mix < 0.001 or abs(semi) < 0.01: return
            ratio = 2.0 ** (semi / 12.0)
            grain_ms = 5.0 + grain_pct * 75.0
            grain_samples = max(64, int(grain_ms * 0.001 * sr))
            grain_inc = 1.0 / grain_samples
            B = self._blen; TWO_PI = 2.0 * math.pi
            rp0 = self._rp0; rp1 = self._rp1
            gp0 = self._gp0; gp1 = self._gp1
            for i in range(frames):
                for ch in range(2):
                    self._rb[self._wp, ch] = float(buf[i, ch])
                # Grain 0
                ri0 = int(rp0) % B; ri0b = (ri0+1) % B; frac0 = rp0 - int(rp0)
                w0 = 0.5 * (1.0 - math.cos(TWO_PI * gp0))
                # Grain 1
                ri1 = int(rp1) % B; ri1b = (ri1+1) % B; frac1 = rp1 - int(rp1)
                w1 = 0.5 * (1.0 - math.cos(TWO_PI * gp1))
                for ch in range(2):
                    s0 = float(self._rb[ri0, ch])*(1-frac0) + float(self._rb[ri0b, ch])*frac0
                    s1 = float(self._rb[ri1, ch])*(1-frac1) + float(self._rb[ri1b, ch])*frac1
                    wet = s0 * w0 + s1 * w1
                    buf[i, ch] = float(buf[i, ch]) * (1-mix) + wet * mix
                self._wp = (self._wp + 1) % B
                rp0 = (rp0 + ratio) % B; rp1 = (rp1 + ratio) % B
                gp0 += grain_inc; gp1 += grain_inc
                if gp0 >= 1.0:
                    gp0 = 0.0; rp0 = float((self._wp - grain_samples) % B)
                if gp1 >= 1.0:
                    gp1 = 0.0; rp1 = float((self._wp - grain_samples) % B)
            self._rp0 = rp0; self._rp1 = rp1
            self._gp0 = gp0; self._gp1 = gp1
        except Exception: pass


# 11. TREMOLO
class TremoloFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._ph = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            rate = max(0.01, _rtg(self.rt, f"{self.p}:rate", 316) / 100)
            depth = _c01(_rtg(self.rt, f"{self.p}:depth", 50) / 100)
            if depth < 0.001: return
            inc = rate / sr; ph = self._ph
            for i in range(frames):
                g = 1 - depth * (1 - (0.5 + 0.5*math.sin(2*math.pi*ph)))
                buf[i, 0] *= g; buf[i, 1] *= g
                ph = (ph + inc) % 1.0
            self._ph = ph
        except Exception: pass


# 12. PEAK LIMITER
class PeakLimiterFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._env = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            in_db = _rtg(self.rt, f"{self.p}:input", 0) / 10
            rel_ms = max(1.0, _rtg(self.rt, f"{self.p}:release", 300))
            ceil_db = min(0, _rtg(self.rt, f"{self.p}:ceiling", 0) / 10)
            ig = 10**(in_db/20); ceil = 10**(ceil_db/20)
            rc = math.exp(-1/(rel_ms*0.001*sr)) if rel_ms > 0 else 0
            if abs(ig-1) > 0.001: np.multiply(buf[:frames], ig, out=buf[:frames])
            env = self._env
            for i in range(frames):
                pk = max(abs(float(buf[i, 0])), abs(float(buf[i, 1])))
                env = pk if pk > env else rc*env + (1-rc)*pk
                if env > ceil and env > 1e-10:
                    gr = ceil / env; buf[i, 0] *= gr; buf[i, 1] *= gr
            self._env = env
        except Exception: pass


# 13. CHORUS (3-voice)
class ChorusFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._maxd = 9600
        self._dl = np.zeros((self._maxd, 2), dtype=np.float32) if np is not None else None
        self._pos = 0; self._ph = 0.0
    def process_inplace(self, buf, frames, sr):
        if np is None or self._dl is None: return
        try:
            dms = max(0.1, _rtg(self.rt, f"{self.p}:delay", 14.5))
            rate = max(0.01, _rtg(self.rt, f"{self.p}:rate", 31) / 100)
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 50) / 100)
            width = _c01(_rtg(self.rt, f"{self.p}:width", 50) / 100)
            bd = max(1, min(self._maxd-2, int(dms*0.001*sr)))
            md = max(1, int(bd*0.4)); inc = rate / sr; M = self._maxd; ph = self._ph
            TWO_PI = 2.0 * math.pi
            for i in range(frames):
                ll = math.sin(TWO_PI*ph); lr = math.sin(TWO_PI*(ph+0.33))
                lc = math.sin(TWO_PI*(ph+0.66))
                dl_ = max(1, min(M-2, int(bd+ll*md)))
                dr_ = max(1, min(M-2, int(bd+lr*md)))
                dc_ = max(1, min(M-2, int(bd+lc*md*0.7)))
                rl = (self._pos-dl_)%M; rr = (self._pos-dr_)%M; rc_ = (self._pos-dc_)%M
                for ch in range(2): self._dl[self._pos, ch] = float(buf[i, ch])
                wl = (float(self._dl[rl, 0]) + float(self._dl[rc_, 0])*0.4)*0.7
                wr = (float(self._dl[rr, 1]) + float(self._dl[rc_, 1])*0.4)*0.7
                mid_w = (wl+wr)*0.5
                wl = mid_w*(1-width) + wl*width; wr = mid_w*(1-width) + wr*width
                buf[i, 0] = float(buf[i, 0])*(1-mix) + wl*mix
                buf[i, 1] = float(buf[i, 1])*(1-mix) + wr*mix
                self._pos = (self._pos+1) % M; ph = (ph+inc) % 1.0
            self._ph = ph
        except Exception: pass


# 14. XY FX
class XYFxFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw): self.rt, self.p = rt, prefix
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            x = _c01(_rtg(self.rt, f"{self.p}:x", 50) / 100)
            y = _c01(_rtg(self.rt, f"{self.p}:y", 50) / 100)
            wg = max(0, _rtg(self.rt, f"{self.p}:wet_gain", 100) / 100)
            mix = _c01(_rtg(self.rt, f"{self.p}:mix", 100) / 100)
            g = (0.5 + 0.5*y) * wg
            if abs(g-1) > 0.001 or abs(mix-1) > 0.001:
                mid = (buf[:frames,0] + buf[:frames,1]) * 0.5
                side = (buf[:frames,0] - buf[:frames,1]) * 0.5 * x
                wl = (mid + side) * g; wr = (mid - side) * g
                buf[:frames,0] = buf[:frames,0]*(1-mix) + wl*mix
                buf[:frames,1] = buf[:frames,1]*(1-mix) + wr*mix
        except Exception: pass


# 15. DE-ESSER
class DeEsserFx(AudioFxBase):
    def __init__(self, prefix, rt, params, **kw):
        self.rt, self.p = rt, prefix; self._env = 0.0; self._fst = [0.0, 0.0]
    def process_inplace(self, buf, frames, sr):
        if np is None: return
        try:
            freq = max(200, min(16000, _rtg(self.rt, f"{self.p}:freq", 4980)))
            amt = _c01(_rtg(self.rt, f"{self.p}:amount", 50) / 100)
            if amt < 0.01: return
            b0,b1,b2,a1,a2 = _biquad_coeffs(1, freq, 1.0, sr)
            ac = math.exp(-1/(0.001*sr)); rc = math.exp(-1/(0.05*sr))
            env = self._env
            for i in range(frames):
                mono = (float(buf[i, 0]) + float(buf[i, 1])) * 0.5
                z1, z2 = self._fst
                hp = b0*mono + z1; z1 = b1*mono - a1*hp + z2; z2 = b2*mono - a2*hp
                self._fst[0], self._fst[1] = z1, z2
                lv = abs(hp)
                env = ac*env+(1-ac)*lv if lv > env else rc*env+(1-rc)*lv
                gr = max(1-amt*env*10, 0.1) if env > 0.01 else 1.0
                buf[i, 0] *= gr; buf[i, 1] *= gr
            self._env = env
        except Exception: pass


# FACTORY
FX_PROCESSOR_MAP = {
    "chrono.fx.eq5": EQ5Fx, "chrono.fx.delay2": Delay2Fx,
    "chrono.fx.reverb": ReverbFx, "chrono.fx.comb": CombFx,
    "chrono.fx.compressor": CompressorFx, "chrono.fx.filter_plus": FilterPlusFx,
    "chrono.fx.distortion_plus": DistortionPlusFx, "chrono.fx.dynamics": DynamicsFx,
    "chrono.fx.flanger": FlangerFx, "chrono.fx.pitch_shifter": PitchShifterFx,
    "chrono.fx.tremolo": TremoloFx, "chrono.fx.peak_limiter": PeakLimiterFx,
    "chrono.fx.chorus": ChorusFx, "chrono.fx.xy_fx": XYFxFx,
    "chrono.fx.de_esser": DeEsserFx,
}

def create_fx_processor(plugin_id: str, prefix: str, rt_params: Any,
                        params: dict, max_frames: int = 8192):
    cls = FX_PROCESSOR_MAP.get(plugin_id)
    if cls is None: return None
    try: return cls(prefix=prefix, rt=rt_params, params=params, max_frames=max_frames)
    except Exception: return None
