# -*- coding: utf-8 -*-
"""JIT-optimierte Audio-Effekte für PyDAW (v0.0.20.66).

Diese Effekte nutzen die JIT-Kernels aus jit_kernels.py und sind vollständig
kompatibel mit der bestehenden ChainFx-Architektur in fx_chain.py.

Architektur:
─────────────────────────────────────────────────────────────────────────────────
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SETUP PHASE (Python/PyQt6)                            │
│  - Parameter-Initialisierung                                                  │
│  - Filter-Koeffizienten berechnen                                            │
│  - RT-Parameter-Store Setup                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RENDER PHASE (JIT/No-GIL)                             │
│  - process_inplace() → Ruft JIT-Kernels auf                                  │
│  - Keine Python-Objekte                                                       │
│  - Keine Speicher-Allokationen                                               │
│  - Kein GIL                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    # In ChainFx._compile_devices():
    from pydaw.audio.jit_effects import JitGainFx, JitDistortionFx, JitFilterFx
    
    if pid == "chrono.fx.filter":
        device = JitFilterFx(...)
        device.prewarm()  # <-- Wichtig!
        self.devices.append(device)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Dict
import math

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# JIT-Kernels importieren
try:
    from .jit_kernels import (
        NUMBA_AVAILABLE,
        apply_gain_stereo_inplace,
        apply_pan_stereo_inplace,
        compute_pan_gains,
        apply_tanh_distortion_inplace,
        apply_wet_dry_mix_inplace,
        apply_biquad_lowpass,
        apply_biquad_highpass,
        apply_biquad_bandpass,
        apply_soft_clip_inplace,
        apply_hard_limiter_inplace,
        apply_onepole_lowpass,
        compute_peak_with_release,
    )
except ImportError:
    NUMBA_AVAILABLE = False


def _clamp(x: float, min_val: float, max_val: float) -> float:
    """Clamp-Funktion."""
    return max(min_val, min(max_val, float(x)))


def _rt_get_smooth(rt, key: str, default: float = 0.0) -> float:
    """RT-Parameter lesen (tolerant gegenüber verschiedenen API-Versionen)."""
    try:
        if rt is None:
            return float(default)
        if hasattr(rt, "get_smooth"):
            return float(rt.get_smooth(key, default))
        if hasattr(rt, "get_param"):
            return float(rt.get_param(key, default))
        if hasattr(rt, "get_target"):
            return float(rt.get_target(key, default))
    except Exception:
        pass
    return float(default)


# ═══════════════════════════════════════════════════════════════════════════════
# BASIS-KLASSE
# ═══════════════════════════════════════════════════════════════════════════════

class JitAudioFxBase:
    """Basis-Klasse für JIT-optimierte Audio-Effekte.
    
    Alle Unterklassen MÜSSEN:
    1. process_inplace() implementieren
    2. prewarm() aufrufen vor dem ersten Audio-Callback
    3. Keinen Python-Code in der kritischen Render-Schleife haben
    """
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        """Effekt auf Buffer anwenden (in-place).
        
        WICHTIG: Diese Methode wird im Audio-Thread aufgerufen!
        Keine Allokationen, keine Python-Objekte, kein GIL!
        """
        raise NotImplementedError
    
    def prewarm(self) -> None:
        """JIT-Kernels vorwärmen. Muss vor erstem Audio-Callback aufgerufen werden."""
        pass
    
    def reset_state(self) -> None:
        """Filter-State zurücksetzen (z.B. bei Seek)."""
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# GAIN-EFFEKT (JIT-optimiert)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitGainFx(JitAudioFxBase):
    """JIT-optimierter Gain-Effekt.
    
    Attribute:
        gain_key: RT-Parameter-Key für Gain (linear, 0.0 - 2.0)
        rt_params: Referenz auf RTParamStore
    """
    gain_key: str = ""
    rt_params: Any = None
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            g = float(_rt_get_smooth(self.rt_params, self.gain_key, 1.0))
        except Exception:
            g = 1.0
        if abs(g - 1.0) < 0.0001:
            return  # Skip wenn Gain ~1.0
        try:
            apply_gain_stereo_inplace(buf[:frames, :], np.float32(g))
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros((64, 2), dtype=np.float32)
            apply_gain_stereo_inplace(dummy, np.float32(0.5))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# DISTORTION-EFFEKT (JIT-optimiert)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitDistortionFx(JitAudioFxBase):
    """JIT-optimierte Tanh-Distortion.
    
    Attribute:
        drive_key: RT-Parameter-Key für Drive (0.0 - 1.0)
        mix_key: RT-Parameter-Key für Wet/Dry Mix (0.0 - 1.0)
        rt_params: Referenz auf RTParamStore
    """
    drive_key: str = ""
    mix_key: str = ""
    rt_params: Any = None
    # Pre-allokierte Buffer für Wet-Signal
    _wet_buf: Any = field(default=None, repr=False)
    _max_frames: int = 8192
    
    def __post_init__(self):
        if np is not None:
            self._wet_buf = np.zeros((self._max_frames, 2), dtype=np.float32)
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            drive = _clamp(_rt_get_smooth(self.rt_params, self.drive_key, 0.25), 0.0, 1.0)
            mix = _clamp(_rt_get_smooth(self.rt_params, self.mix_key, 1.0), 0.0, 1.0)
        except Exception:
            drive, mix = 0.25, 1.0
            
        if drive <= 0.001 or mix <= 0.001:
            return
            
        try:
            # Drive auf 1.0 - 21.0 mappen
            drive_factor = np.float32(1.0 + 20.0 * drive)
            
            if mix >= 0.999:
                # 100% wet: direkt anwenden
                apply_tanh_distortion_inplace(buf[:frames, :], drive_factor)
            else:
                # Wet-Buffer kopieren und verzerren
                wet = self._wet_buf[:frames, :]
                np.copyto(wet, buf[:frames, :])
                apply_tanh_distortion_inplace(wet, drive_factor)
                apply_wet_dry_mix_inplace(buf[:frames, :], wet, np.float32(mix))
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros((64, 2), dtype=np.float32)
            apply_tanh_distortion_inplace(dummy, np.float32(2.0))
            apply_wet_dry_mix_inplace(dummy, dummy.copy(), np.float32(0.5))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# FILTER-EFFEKT (JIT-optimiert, Biquad)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitFilterFx(JitAudioFxBase):
    """JIT-optimierter Biquad-Filter (LP/HP/BP).
    
    Attribute:
        cutoff_key: RT-Parameter-Key für Cutoff (20 - 20000 Hz)
        q_key: RT-Parameter-Key für Q/Resonanz (0.5 - 20)
        filter_type_key: RT-Parameter-Key für Typ (0=LP, 1=HP, 2=BP)
        rt_params: Referenz auf RTParamStore
    """
    cutoff_key: str = ""
    q_key: str = ""
    filter_type_key: str = ""
    rt_params: Any = None
    # Filter-State (persistiert zwischen Blocks)
    _z1_l: float = field(default=0.0, repr=False)
    _z2_l: float = field(default=0.0, repr=False)
    _z1_r: float = field(default=0.0, repr=False)
    _z2_r: float = field(default=0.0, repr=False)
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            cutoff = _clamp(_rt_get_smooth(self.rt_params, self.cutoff_key, 1000.0), 20.0, sr * 0.45)
            q = _clamp(_rt_get_smooth(self.rt_params, self.q_key, 0.707), 0.5, 20.0)
            ftype = int(_rt_get_smooth(self.rt_params, self.filter_type_key, 0.0))
        except Exception:
            cutoff, q, ftype = 1000.0, 0.707, 0
            
        try:
            # Linken Kanal filtern
            left = buf[:frames, 0].astype(np.float32)
            if ftype == 1:
                left, self._z1_l, self._z2_l = apply_biquad_highpass(
                    left, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_l), np.float32(self._z2_l))
            elif ftype == 2:
                left, self._z1_l, self._z2_l = apply_biquad_bandpass(
                    left, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_l), np.float32(self._z2_l))
            else:
                left, self._z1_l, self._z2_l = apply_biquad_lowpass(
                    left, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_l), np.float32(self._z2_l))
            buf[:frames, 0] = left
            
            # Rechten Kanal filtern
            right = buf[:frames, 1].astype(np.float32)
            if ftype == 1:
                right, self._z1_r, self._z2_r = apply_biquad_highpass(
                    right, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_r), np.float32(self._z2_r))
            elif ftype == 2:
                right, self._z1_r, self._z2_r = apply_biquad_bandpass(
                    right, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_r), np.float32(self._z2_r))
            else:
                right, self._z1_r, self._z2_r = apply_biquad_lowpass(
                    right, np.float32(cutoff), np.float32(q), np.float32(sr),
                    np.float32(self._z1_r), np.float32(self._z2_r))
            buf[:frames, 1] = right
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros(64, dtype=np.float32)
            apply_biquad_lowpass(dummy, np.float32(1000.0), np.float32(0.707), 
                                np.float32(44100.0), np.float32(0.0), np.float32(0.0))
            apply_biquad_highpass(dummy, np.float32(100.0), np.float32(0.707),
                                 np.float32(44100.0), np.float32(0.0), np.float32(0.0))
            apply_biquad_bandpass(dummy, np.float32(1000.0), np.float32(1.0),
                                 np.float32(44100.0), np.float32(0.0), np.float32(0.0))
        except Exception:
            pass
    
    def reset_state(self) -> None:
        self._z1_l = self._z2_l = self._z1_r = self._z2_r = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SOFT-CLIP (JIT-optimiert)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitSoftClipFx(JitAudioFxBase):
    """JIT-optimierter Soft-Clipper (Sättigung).
    
    Attribute:
        threshold_key: RT-Parameter-Key für Threshold (0.0 - 1.0)
        ratio_key: RT-Parameter-Key für Ratio (0.0 - 1.0)
        rt_params: Referenz auf RTParamStore
    """
    threshold_key: str = ""
    ratio_key: str = ""
    rt_params: Any = None
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            th = _clamp(_rt_get_smooth(self.rt_params, self.threshold_key, 0.8), 0.1, 1.0)
            ratio = _clamp(_rt_get_smooth(self.rt_params, self.ratio_key, 0.3), 0.0, 1.0)
        except Exception:
            th, ratio = 0.8, 0.3
            
        try:
            apply_soft_clip_inplace(buf[:frames, :], np.float32(th), np.float32(ratio))
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros((64, 2), dtype=np.float32)
            apply_soft_clip_inplace(dummy, np.float32(0.8), np.float32(0.3))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# LIMITER (JIT-optimiert)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitLimiterFx(JitAudioFxBase):
    """JIT-optimierter Hard-Limiter (Brickwall).
    
    Attribute:
        ceiling_key: RT-Parameter-Key für Ceiling (-0.1dB bis 0dB)
        rt_params: Referenz auf RTParamStore
    """
    ceiling_key: str = ""
    rt_params: Any = None
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            apply_hard_limiter_inplace(buf[:frames, :])
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros((64, 2), dtype=np.float32)
            apply_hard_limiter_inplace(dummy)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE LOW-PASS (One-Pole, sehr CPU-effizient)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JitOnePoleFilterFx(JitAudioFxBase):
    """JIT-optimierter One-Pole Filter (6dB/Oktave).
    
    Sehr CPU-effizient, ideal für Smoothing oder subtile Klangformung.
    
    Attribute:
        alpha_key: RT-Parameter-Key für Alpha (0.0 - 1.0)
        rt_params: Referenz auf RTParamStore
    """
    alpha_key: str = ""
    rt_params: Any = None
    _last_l: float = field(default=0.0, repr=False)
    _last_r: float = field(default=0.0, repr=False)
    
    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            alpha = _clamp(_rt_get_smooth(self.rt_params, self.alpha_key, 0.5), 0.0, 1.0)
        except Exception:
            alpha = 0.5
            
        if alpha <= 0.001:
            return  # Keine Filterung
            
        try:
            # Links
            left = buf[:frames, 0].astype(np.float32)
            filtered_l = apply_onepole_lowpass(left, np.float32(alpha), np.float32(self._last_l))
            buf[:frames, 0] = filtered_l
            self._last_l = float(filtered_l[-1]) if len(filtered_l) > 0 else self._last_l
            
            # Rechts
            right = buf[:frames, 1].astype(np.float32)
            filtered_r = apply_onepole_lowpass(right, np.float32(alpha), np.float32(self._last_r))
            buf[:frames, 1] = filtered_r
            self._last_r = float(filtered_r[-1]) if len(filtered_r) > 0 else self._last_r
        except Exception:
            pass
    
    def prewarm(self) -> None:
        if np is None or not NUMBA_AVAILABLE:
            return
        try:
            dummy = np.zeros(64, dtype=np.float32)
            apply_onepole_lowpass(dummy, np.float32(0.5), np.float32(0.0))
        except Exception:
            pass
    
    def reset_state(self) -> None:
        self._last_l = self._last_r = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY-FUNKTION
# ═══════════════════════════════════════════════════════════════════════════════

def create_jit_effect(plugin_id: str, device_id: str, track_id: str, 
                      params: Dict[str, Any], rt_params: Any) -> Optional[JitAudioFxBase]:
    """Factory-Funktion zum Erstellen von JIT-Effekten.
    
    Args:
        plugin_id: Plugin-Typ (z.B. "chrono.fx.filter")
        device_id: Eindeutige Device-ID
        track_id: Track-ID für RT-Parameter-Keys
        params: Initial-Parameter aus der Device-Spec
        rt_params: Referenz auf RTParamStore
        
    Returns:
        JIT-Effekt-Instanz oder None
    """
    prefix = f"jfx:{track_id}:{device_id}"
    
    if plugin_id in ("chrono.fx.gain", "jit.gain", "gain"):
        gain = float(params.get("gain", 1.0) or 1.0)
        gain_key = f"{prefix}:gain"
        if hasattr(rt_params, "ensure"):
            rt_params.ensure(gain_key, gain)
        fx = JitGainFx(gain_key=gain_key, rt_params=rt_params)
        fx.prewarm()
        return fx
        
    elif plugin_id in ("chrono.fx.distortion", "jit.distortion", "distortion"):
        drive = float(params.get("drive", 0.25) or 0.25)
        mix = float(params.get("mix", 1.0) or 1.0)
        drive_key = f"{prefix}:drive"
        mix_key = f"{prefix}:mix"
        if hasattr(rt_params, "ensure"):
            rt_params.ensure(drive_key, drive)
            rt_params.ensure(mix_key, mix)
        fx = JitDistortionFx(drive_key=drive_key, mix_key=mix_key, rt_params=rt_params)
        fx.prewarm()
        return fx
        
    elif plugin_id in ("chrono.fx.filter", "jit.filter", "filter"):
        cutoff = float(params.get("cutoff", 1000.0) or 1000.0)
        q = float(params.get("q", 0.707) or 0.707)
        filter_type = int(params.get("filter_type", 0) or 0)
        cutoff_key = f"{prefix}:cutoff"
        q_key = f"{prefix}:q"
        type_key = f"{prefix}:type"
        if hasattr(rt_params, "ensure"):
            rt_params.ensure(cutoff_key, cutoff)
            rt_params.ensure(q_key, q)
            rt_params.ensure(type_key, float(filter_type))
        fx = JitFilterFx(
            cutoff_key=cutoff_key, q_key=q_key, filter_type_key=type_key, 
            rt_params=rt_params
        )
        fx.prewarm()
        return fx
        
    elif plugin_id in ("chrono.fx.softclip", "jit.softclip", "softclip"):
        threshold = float(params.get("threshold", 0.8) or 0.8)
        ratio = float(params.get("ratio", 0.3) or 0.3)
        th_key = f"{prefix}:threshold"
        ratio_key = f"{prefix}:ratio"
        if hasattr(rt_params, "ensure"):
            rt_params.ensure(th_key, threshold)
            rt_params.ensure(ratio_key, ratio)
        fx = JitSoftClipFx(threshold_key=th_key, ratio_key=ratio_key, rt_params=rt_params)
        fx.prewarm()
        return fx
        
    elif plugin_id in ("chrono.fx.limiter", "jit.limiter", "limiter"):
        fx = JitLimiterFx(ceiling_key="", rt_params=rt_params)
        fx.prewarm()
        return fx
        
    elif plugin_id in ("chrono.fx.onepole", "jit.onepole", "onepole"):
        alpha = float(params.get("alpha", 0.5) or 0.5)
        alpha_key = f"{prefix}:alpha"
        if hasattr(rt_params, "ensure"):
            rt_params.ensure(alpha_key, alpha)
        fx = JitOnePoleFilterFx(alpha_key=alpha_key, rt_params=rt_params)
        fx.prewarm()
        return fx
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-WARMING
# ═══════════════════════════════════════════════════════════════════════════════

def prewarm_all_jit_effects() -> bool:
    """Alle JIT-Effekte vorwärmen.
    
    Returns:
        True wenn erfolgreich
    """
    if not NUMBA_AVAILABLE:
        print("[JIT-Effects] Numba nicht verfügbar")
        return False
        
    print("[JIT-Effects] Pre-warming JIT effects...")
    
    try:
        # Dummy-Instanzen erstellen und prewarm aufrufen
        JitGainFx(gain_key="", rt_params=None).prewarm()
        JitDistortionFx(drive_key="", mix_key="", rt_params=None).prewarm()
        JitFilterFx(cutoff_key="", q_key="", filter_type_key="", rt_params=None).prewarm()
        JitSoftClipFx(threshold_key="", ratio_key="", rt_params=None).prewarm()
        JitLimiterFx(ceiling_key="", rt_params=None).prewarm()
        JitOnePoleFilterFx(alpha_key="", rt_params=None).prewarm()
        
        print("[JIT-Effects] ✓ Alle JIT-Effekte vorgewärmt")
        return True
    except Exception as e:
        print(f"[JIT-Effects] Pre-warming Fehler: {e}")
        return False


if __name__ == "__main__":
    print(f"Numba verfügbar: {NUMBA_AVAILABLE}")
    prewarm_all_jit_effects()
