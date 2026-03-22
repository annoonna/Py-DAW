# -*- coding: utf-8 -*-
"""JIT-kompilierte Audio-DSP-Kernels für PyDAW (v0.0.20.66).

Diese Funktionen laufen komplett ohne GIL und erreichen C++-ähnliche Performance.
Alle Funktionen sind auf float32 spezialisiert, um Re-Compilation zu vermeiden.

Architektur-Prinzipien:
─────────────────────────────────────────────────────────────────────────────────
1. KEINE Python-Objekte innerhalb @njit (nur Arrays, Primitive, andere JIT-Funktionen)
2. Explizite Signaturen für AOT-Compilation (kein Lazy-JIT beim ersten Ton)
3. nogil=True für echte Multi-Core-Parallelität
4. fastmath=True für SIMD-Optimierungen (IEEE-754 Trade-off ist für Audio akzeptabel)
5. cache=True für persistente Compilation über App-Neustarts

Pre-Warming:
─────────────────────────────────────────────────────────────────────────────────
Alle Funktionen MÜSSEN beim App-Start einmal mit Dummy-Daten aufgerufen werden,
um JIT-Glitches (Audio-Dropouts) beim ersten Abspielen zu vermeiden.
Siehe: pydaw/services/jit_prewarm_service.py
"""
from __future__ import annotations

import math
import numpy as np

# Numba-Import mit Fallback
try:
    from numba import njit, float32, int32, boolean, prange
    from numba.typed import List as NumbaList
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Fallback-Dekorator (keine JIT-Optimierung)
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
    float32 = None
    int32 = None
    boolean = None
    prange = range
    NumbaList = list

# ═══════════════════════════════════════════════════════════════════════════════
# Konstanten (Pre-calculated für Performance)
# ═══════════════════════════════════════════════════════════════════════════════
_TWO_PI = np.float32(2.0 * math.pi)
_HALF_PI = np.float32(math.pi / 2.0)
_PI = np.float32(math.pi)

# ═══════════════════════════════════════════════════════════════════════════════
# OSZILLATOREN
# ═══════════════════════════════════════════════════════════════════════════════

@njit(
    "float32[:](float32, float32, float32, int32)",
    cache=True, fastmath=True, nogil=True
)
def render_sine_wave(frequency: float, phase: float, sample_rate: float, 
                     buffer_size: int) -> np.ndarray:
    """High-Performance Sinus-Oszillator.
    
    Args:
        frequency: Frequenz in Hz
        phase: Aktuelle Phase in Radiant (0 bis 2π)
        sample_rate: Sample-Rate in Hz
        buffer_size: Anzahl der Samples
        
    Returns:
        NumPy-Array (float32) mit den berechneten Samples
        
    Note:
        Phase-Wrapping verhindert Präzisionsverlust bei langen Playbacks.
    """
    output = np.empty(buffer_size, dtype=np.float32)
    step = np.float32(_TWO_PI * frequency / sample_rate)
    
    current_phase = np.float32(phase)
    for i in range(buffer_size):
        output[i] = np.float32(math.sin(current_phase))
        current_phase += step
        # Phase Wrapping (wichtig für Präzision bei langen Sessions)
        if current_phase > _TWO_PI:
            current_phase -= _TWO_PI
            
    return output


@njit(
    "float32[:](float32, float32, float32, int32)",
    cache=True, fastmath=True, nogil=True
)
def render_saw_wave(frequency: float, phase: float, sample_rate: float,
                    buffer_size: int) -> np.ndarray:
    """High-Performance Sägezahn-Oszillator (Bandlimited PolyBLEP).
    
    Verwendet PolyBLEP Anti-Aliasing für sauberen Sound.
    """
    output = np.empty(buffer_size, dtype=np.float32)
    step = np.float32(frequency / sample_rate)
    
    current_phase = np.float32(phase / _TWO_PI)  # Normalisiert auf 0..1
    
    for i in range(buffer_size):
        # Naive Sägezahn: 2 * phase - 1
        value = np.float32(2.0 * current_phase - 1.0)
        
        # PolyBLEP Korrektur am Übergang
        t = current_phase
        dt = step
        if t < dt:
            t = t / dt
            value -= np.float32(t + t - t * t - 1.0)
        elif t > 1.0 - dt:
            t = (t - 1.0) / dt
            value -= np.float32(t * t + t + t + 1.0)
            
        output[i] = value
        current_phase += step
        if current_phase >= 1.0:
            current_phase -= 1.0
            
    return output


@njit(
    "float32[:](float32, float32, float32, float32, int32)",
    cache=True, fastmath=True, nogil=True
)
def render_pulse_wave(frequency: float, phase: float, pulse_width: float,
                      sample_rate: float, buffer_size: int) -> np.ndarray:
    """High-Performance Puls-Oszillator mit variabler Pulsbreite.
    
    Args:
        pulse_width: 0.0 bis 1.0 (0.5 = Rechteck)
    """
    output = np.empty(buffer_size, dtype=np.float32)
    step = np.float32(frequency / sample_rate)
    pw = np.float32(max(0.01, min(0.99, pulse_width)))
    
    current_phase = np.float32(phase / _TWO_PI)
    
    for i in range(buffer_size):
        # Naive Puls
        if current_phase < pw:
            value = np.float32(1.0)
        else:
            value = np.float32(-1.0)
            
        output[i] = value
        current_phase += step
        if current_phase >= 1.0:
            current_phase -= 1.0
            
    return output


@njit(
    "float32[:](float32, float32, float32, int32)",
    cache=True, fastmath=True, nogil=True
)
def render_triangle_wave(frequency: float, phase: float, sample_rate: float,
                         buffer_size: int) -> np.ndarray:
    """High-Performance Dreieck-Oszillator."""
    output = np.empty(buffer_size, dtype=np.float32)
    step = np.float32(frequency / sample_rate)
    
    current_phase = np.float32(phase / _TWO_PI)
    
    for i in range(buffer_size):
        # Dreieck aus Sägezahn: 2 * |2 * phase - 1| - 1
        value = np.float32(4.0 * abs(current_phase - 0.5) - 1.0)
        output[i] = value
        current_phase += step
        if current_phase >= 1.0:
            current_phase -= 1.0
            
    return output


# ═══════════════════════════════════════════════════════════════════════════════
# FILTER
# ═══════════════════════════════════════════════════════════════════════════════

@njit(
    "float32[:](float32[:], float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def apply_onepole_lowpass(data: np.ndarray, alpha: float, 
                          last_val: float) -> np.ndarray:
    """Einfacher One-Pole Low-Pass Filter (6dB/Oktave).
    
    Args:
        data: Input-Buffer (float32)
        alpha: Filterkoeffizient (0 = keine Filterung, 1 = maximale Glättung)
        last_val: Letzter Output-Wert vom vorherigen Buffer
        
    Returns:
        Gefilterter Output-Buffer
        
    Formel:
        y[n] = y[n-1] + alpha * (x[n] - y[n-1])
    """
    result = np.empty_like(data)
    current = np.float32(last_val)
    a = np.float32(alpha)
    
    for i in range(len(data)):
        current = current + a * (data[i] - current)
        result[i] = current
        
    return result


@njit(
    "Tuple((float32[:], float32, float32))(float32[:], float32, float32, float32, float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def apply_biquad_lowpass(data: np.ndarray, cutoff: float, q: float, 
                         sample_rate: float, z1: float, z2: float):
    """Biquad Low-Pass Filter (12dB/Oktave) mit State.
    
    Args:
        data: Input-Buffer
        cutoff: Cutoff-Frequenz in Hz
        q: Resonanz (0.5 bis 20)
        sample_rate: Sample-Rate
        z1, z2: Filter-State vom vorherigen Buffer
        
    Returns:
        Tuple: (output_buffer, new_z1, new_z2)
    """
    # Koeffizienten berechnen
    omega = np.float32(_TWO_PI * cutoff / sample_rate)
    sin_omega = np.float32(math.sin(omega))
    cos_omega = np.float32(math.cos(omega))
    alpha = np.float32(sin_omega / (2.0 * q))
    
    b0 = np.float32((1.0 - cos_omega) / 2.0)
    b1 = np.float32(1.0 - cos_omega)
    b2 = np.float32((1.0 - cos_omega) / 2.0)
    a0 = np.float32(1.0 + alpha)
    a1 = np.float32(-2.0 * cos_omega)
    a2 = np.float32(1.0 - alpha)
    
    # Normalisieren
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    
    result = np.empty_like(data)
    z1_cur = np.float32(z1)
    z2_cur = np.float32(z2)
    
    for i in range(len(data)):
        x = data[i]
        y = np.float32(b0 * x + z1_cur)
        z1_cur = b1 * x - a1 * y + z2_cur
        z2_cur = b2 * x - a2 * y
        result[i] = y
        
    return result, z1_cur, z2_cur


@njit(
    "Tuple((float32[:], float32, float32))(float32[:], float32, float32, float32, float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def apply_biquad_highpass(data: np.ndarray, cutoff: float, q: float, 
                          sample_rate: float, z1: float, z2: float):
    """Biquad High-Pass Filter (12dB/Oktave) mit State."""
    omega = np.float32(_TWO_PI * cutoff / sample_rate)
    sin_omega = np.float32(math.sin(omega))
    cos_omega = np.float32(math.cos(omega))
    alpha = np.float32(sin_omega / (2.0 * q))
    
    b0 = np.float32((1.0 + cos_omega) / 2.0)
    b1 = np.float32(-(1.0 + cos_omega))
    b2 = np.float32((1.0 + cos_omega) / 2.0)
    a0 = np.float32(1.0 + alpha)
    a1 = np.float32(-2.0 * cos_omega)
    a2 = np.float32(1.0 - alpha)
    
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    
    result = np.empty_like(data)
    z1_cur = np.float32(z1)
    z2_cur = np.float32(z2)
    
    for i in range(len(data)):
        x = data[i]
        y = np.float32(b0 * x + z1_cur)
        z1_cur = b1 * x - a1 * y + z2_cur
        z2_cur = b2 * x - a2 * y
        result[i] = y
        
    return result, z1_cur, z2_cur


@njit(
    "Tuple((float32[:], float32, float32))(float32[:], float32, float32, float32, float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def apply_biquad_bandpass(data: np.ndarray, cutoff: float, q: float, 
                          sample_rate: float, z1: float, z2: float):
    """Biquad Band-Pass Filter mit State."""
    omega = np.float32(_TWO_PI * cutoff / sample_rate)
    sin_omega = np.float32(math.sin(omega))
    cos_omega = np.float32(math.cos(omega))
    alpha = np.float32(sin_omega / (2.0 * q))
    
    b0 = np.float32(alpha)
    b1 = np.float32(0.0)
    b2 = np.float32(-alpha)
    a0 = np.float32(1.0 + alpha)
    a1 = np.float32(-2.0 * cos_omega)
    a2 = np.float32(1.0 - alpha)
    
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    
    result = np.empty_like(data)
    z1_cur = np.float32(z1)
    z2_cur = np.float32(z2)
    
    for i in range(len(data)):
        x = data[i]
        y = np.float32(b0 * x + z1_cur)
        z1_cur = b1 * x - a1 * y + z2_cur
        z2_cur = b2 * x - a2 * y
        result[i] = y
        
    return result, z1_cur, z2_cur


# ═══════════════════════════════════════════════════════════════════════════════
# GAIN / PAN / MIX
# ═══════════════════════════════════════════════════════════════════════════════

@njit(cache=True, fastmath=True, nogil=True)
def apply_gain_stereo_inplace(buf: np.ndarray, gain: float) -> None:
    """Gain auf Stereo-Buffer anwenden (in-place)."""
    g = np.float32(gain)
    for i in range(buf.shape[0]):
        buf[i, 0] *= g
        buf[i, 1] *= g


@njit(cache=True, fastmath=True, nogil=True)
def apply_pan_stereo_inplace(buf: np.ndarray, left_gain: float, 
                             right_gain: float) -> None:
    """Pan auf Stereo-Buffer anwenden (in-place, Equal-Power)."""
    gl = np.float32(left_gain)
    gr = np.float32(right_gain)
    for i in range(buf.shape[0]):
        buf[i, 0] *= gl
        buf[i, 1] *= gr


@njit(
    "Tuple((float32, float32))(float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def compute_pan_gains(gain: float, pan: float):
    """Equal-Power Pan-Gains berechnen.
    
    Args:
        gain: Master-Gain (linear)
        pan: Pan-Position (-1.0 = links, 0.0 = mitte, 1.0 = rechts)
        
    Returns:
        Tuple (left_gain, right_gain)
    """
    pan = max(-1.0, min(1.0, float(pan)))
    x = (pan + 1.0) * 0.5
    return (np.float32(math.cos(x * _HALF_PI) * gain),
            np.float32(math.sin(x * _HALF_PI) * gain))


@njit(cache=True, fastmath=True, nogil=True)
def mix_buffers_inplace(dest: np.ndarray, src: np.ndarray) -> None:
    """Zwei Stereo-Buffer addieren (dest += src)."""
    for i in range(min(dest.shape[0], src.shape[0])):
        dest[i, 0] += src[i, 0]
        dest[i, 1] += src[i, 1]


@njit(cache=True, fastmath=True, nogil=True)
def mix_buffers_with_gain_inplace(dest: np.ndarray, src: np.ndarray, 
                                   gain: float) -> None:
    """Buffer mit Gain zum Ziel addieren (dest += src * gain)."""
    g = np.float32(gain)
    for i in range(min(dest.shape[0], src.shape[0])):
        dest[i, 0] += src[i, 0] * g
        dest[i, 1] += src[i, 1] * g


# ═══════════════════════════════════════════════════════════════════════════════
# EFFEKTE
# ═══════════════════════════════════════════════════════════════════════════════

@njit(cache=True, fastmath=True, nogil=True)
def apply_soft_clip_inplace(buf: np.ndarray, threshold: float, 
                            ratio: float) -> None:
    """Soft-Clipping (Sättigung) auf Stereo-Buffer (in-place).
    
    Args:
        threshold: Schwellenwert (0.0 - 1.0)
        ratio: Kompressionsrate über Schwelle
    """
    th = np.float32(abs(threshold))
    r = np.float32(ratio)
    
    for i in range(buf.shape[0]):
        for ch in range(2):
            x = buf[i, ch]
            if x > th:
                buf[i, ch] = th + (x - th) * r
            elif x < -th:
                buf[i, ch] = -th + (x + th) * r


@njit(cache=True, fastmath=True, nogil=True)
def apply_tanh_distortion_inplace(buf: np.ndarray, drive: float) -> None:
    """Tanh-Distortion (warme Sättigung) auf Stereo-Buffer (in-place).
    
    Args:
        drive: Stärke der Verzerrung (1.0 - 20.0 typisch)
    """
    d = np.float32(drive)
    for i in range(buf.shape[0]):
        buf[i, 0] = np.float32(math.tanh(buf[i, 0] * d))
        buf[i, 1] = np.float32(math.tanh(buf[i, 1] * d))


@njit(cache=True, fastmath=True, nogil=True)
def apply_wet_dry_mix_inplace(dry: np.ndarray, wet: np.ndarray, 
                              mix: float) -> None:
    """Wet/Dry-Mix auf Buffer anwenden (dry wird modifiziert).
    
    Args:
        dry: Original-Buffer (wird modifiziert!)
        wet: Effekt-Buffer
        mix: 0.0 = 100% dry, 1.0 = 100% wet
    """
    m = np.float32(max(0.0, min(1.0, mix)))
    d = np.float32(1.0 - m)
    for i in range(min(dry.shape[0], wet.shape[0])):
        dry[i, 0] = dry[i, 0] * d + wet[i, 0] * m
        dry[i, 1] = dry[i, 1] * d + wet[i, 1] * m


@njit(cache=True, fastmath=True, nogil=True)
def apply_hard_limiter_inplace(buf: np.ndarray) -> None:
    """Hard-Limiter (Brickwall) auf -1.0 bis 1.0."""
    for i in range(buf.shape[0]):
        buf[i, 0] = max(-1.0, min(1.0, buf[i, 0]))
        buf[i, 1] = max(-1.0, min(1.0, buf[i, 1]))


@njit(
    "Tuple((float32, float32))(float32[:, :], float32, float32, float32, float32)",
    cache=True, fastmath=True, nogil=True
)
def compute_peak_with_release(buffer: np.ndarray, last_peak_l: float,
                               last_peak_r: float, attack_coef: float,
                               release_coef: float):
    """Peak-Detektor mit Release für Metering/Limiter.
    
    Args:
        buffer: Audio-Buffer
        last_peak_l/r: Letzte Peak-Werte
        attack_coef: Attack-Koeffizient (schnell, ~0.01)
        release_coef: Release-Koeffizient (langsam, ~0.0001)
        
    Returns:
        Tuple (new_peak_l, new_peak_r)
    """
    peak_l = np.float32(last_peak_l)
    peak_r = np.float32(last_peak_r)
    rel = np.float32(release_coef)
    
    for i in range(buffer.shape[0]):
        abs_l = abs(buffer[i, 0])
        abs_r = abs(buffer[i, 1])
        
        if abs_l > peak_l:
            peak_l = abs_l  # Instant attack
        else:
            peak_l = peak_l * (np.float32(1.0) - rel)  # Slow release
            
        if abs_r > peak_r:
            peak_r = abs_r
        else:
            peak_r = peak_r * (np.float32(1.0) - rel)
            
    return peak_l, peak_r


# ═══════════════════════════════════════════════════════════════════════════════
# ENVELOPE
# ═══════════════════════════════════════════════════════════════════════════════

@njit(
    "float32[:](float32, float32, float32, float32, float32, int32, float32)",
    cache=True, fastmath=True, nogil=True
)
def generate_adsr_envelope(attack: float, decay: float, sustain: float,
                           release: float, sample_rate: float, 
                           buffer_size: int, current_level: float) -> np.ndarray:
    """ADSR-Envelope Generator.
    
    Args:
        attack: Attack-Zeit in Sekunden
        decay: Decay-Zeit in Sekunden
        sustain: Sustain-Level (0.0 - 1.0)
        release: Release-Zeit in Sekunden
        sample_rate: Sample-Rate
        buffer_size: Buffer-Größe
        current_level: Aktuelles Level für Fortsetzung
        
    Returns:
        Envelope-Array (float32)
    """
    output = np.empty(buffer_size, dtype=np.float32)
    
    attack_samples = int(attack * sample_rate)
    decay_samples = int(decay * sample_rate)
    
    level = np.float32(current_level)
    sustain_level = np.float32(sustain)
    
    attack_rate = np.float32(1.0 / max(1, attack_samples)) if attack_samples > 0 else np.float32(1.0)
    decay_rate = np.float32((1.0 - sustain_level) / max(1, decay_samples)) if decay_samples > 0 else np.float32(0.0)
    
    for i in range(buffer_size):
        output[i] = level
        # Vereinfachte State-Machine (Attack → Decay → Sustain)
        if level < 1.0:
            level = min(np.float32(1.0), level + attack_rate)
        elif level > sustain_level + 0.001:
            level = max(sustain_level, level - decay_rate)
            
    return output


# ═══════════════════════════════════════════════════════════════════════════════
# MONO-TO-STEREO / KANAL-KONVERTIERUNG
# ═══════════════════════════════════════════════════════════════════════════════

@njit(
    "float32[:, :](float32[:])",
    cache=True, fastmath=True, nogil=True
)
def mono_to_stereo(mono: np.ndarray) -> np.ndarray:
    """Mono-Buffer zu Stereo konvertieren."""
    stereo = np.empty((len(mono), 2), dtype=np.float32)
    for i in range(len(mono)):
        stereo[i, 0] = mono[i]
        stereo[i, 1] = mono[i]
    return stereo


@njit(
    "float32[:](float32[:, :])",
    cache=True, fastmath=True, nogil=True
)
def stereo_to_mono(stereo: np.ndarray) -> np.ndarray:
    """Stereo-Buffer zu Mono konvertieren (Durchschnitt)."""
    mono = np.empty(stereo.shape[0], dtype=np.float32)
    for i in range(stereo.shape[0]):
        mono[i] = np.float32((stereo[i, 0] + stereo[i, 1]) * 0.5)
    return mono


# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLE-INTERPOLATION (für Pitch-Shifting / Resampling)
# ═══════════════════════════════════════════════════════════════════════════════

@njit(
    "float32[:](float32[:], float32)",
    cache=True, fastmath=True, nogil=True
)
def resample_linear(data: np.ndarray, ratio: float) -> np.ndarray:
    """Lineares Resampling (einfach aber CPU-effizient).
    
    Args:
        data: Input-Samples
        ratio: Resample-Ratio (2.0 = doppelte Länge, 0.5 = halbe Länge)
        
    Returns:
        Resampled Array
    """
    in_len = len(data)
    out_len = int(in_len * ratio)
    output = np.empty(out_len, dtype=np.float32)
    
    step = np.float32(1.0 / ratio)
    pos = np.float32(0.0)
    
    for i in range(out_len):
        idx = int(pos)
        frac = pos - idx
        
        if idx + 1 < in_len:
            # Lineare Interpolation
            output[i] = np.float32(data[idx] * (1.0 - frac) + data[idx + 1] * frac)
        else:
            output[i] = data[min(idx, in_len - 1)]
            
        pos += step
        
    return output


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-WARMING FUNKTION
# ═══════════════════════════════════════════════════════════════════════════════

def prewarm_all_kernels() -> bool:
    """Alle JIT-Kernels vorwärmen, um Audio-Glitches zu vermeiden.
    
    Diese Funktion MUSS beim App-Start aufgerufen werden (z.B. im SplashScreen),
    BEVOR der erste Audio-Callback erfolgt.
    
    Returns:
        True wenn Numba verfügbar und Pre-Warming erfolgreich
    """
    if not NUMBA_AVAILABLE:
        print("[JIT] Numba nicht verfügbar - Fallback auf Pure Python")
        return False
        
    print("[JIT] Pre-compiling Audio Kernels...")
    
    # Dummy-Daten
    mono_buf = np.zeros(512, dtype=np.float32)
    stereo_buf = np.zeros((512, 2), dtype=np.float32)
    
    try:
        # Oszillatoren
        render_sine_wave(440.0, 0.0, 44100.0, 512)
        render_saw_wave(440.0, 0.0, 44100.0, 512)
        render_pulse_wave(440.0, 0.0, 0.5, 44100.0, 512)
        render_triangle_wave(440.0, 0.0, 44100.0, 512)
        
        # Filter
        apply_onepole_lowpass(mono_buf.copy(), 0.5, 0.0)
        apply_biquad_lowpass(mono_buf.copy(), 1000.0, 0.707, 44100.0, 0.0, 0.0)
        apply_biquad_highpass(mono_buf.copy(), 100.0, 0.707, 44100.0, 0.0, 0.0)
        apply_biquad_bandpass(mono_buf.copy(), 1000.0, 1.0, 44100.0, 0.0, 0.0)
        
        # Gain/Pan
        apply_gain_stereo_inplace(stereo_buf.copy(), 0.5)
        apply_pan_stereo_inplace(stereo_buf.copy(), 0.7, 0.7)
        compute_pan_gains(1.0, 0.0)
        mix_buffers_inplace(stereo_buf.copy(), stereo_buf.copy())
        mix_buffers_with_gain_inplace(stereo_buf.copy(), stereo_buf.copy(), 0.5)
        
        # Effekte
        apply_soft_clip_inplace(stereo_buf.copy(), 0.8, 0.3)
        apply_tanh_distortion_inplace(stereo_buf.copy(), 2.0)
        apply_wet_dry_mix_inplace(stereo_buf.copy(), stereo_buf.copy(), 0.5)
        
        # Limiter
        apply_hard_limiter_inplace(stereo_buf.copy())
        compute_peak_with_release(stereo_buf, 0.0, 0.0, 0.01, 0.0001)
        
        # Envelope
        generate_adsr_envelope(0.01, 0.1, 0.7, 0.3, 44100.0, 512, 0.0)
        
        # Konvertierung
        mono_to_stereo(mono_buf)
        stereo_to_mono(stereo_buf)
        
        # Resampling
        resample_linear(mono_buf, 0.5)
        
        print("[JIT] ✓ Alle Kernels erfolgreich kompiliert")
        return True
        
    except Exception as e:
        print(f"[JIT] Pre-Warming Fehler: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# MODUL-LEVEL INFO
# ═══════════════════════════════════════════════════════════════════════════════

def get_jit_status() -> dict:
    """Status der JIT-Engine abrufen."""
    return {
        "numba_available": NUMBA_AVAILABLE,
        "cache_enabled": True if NUMBA_AVAILABLE else False,
        "nogil_enabled": True if NUMBA_AVAILABLE else False,
        "fastmath_enabled": True if NUMBA_AVAILABLE else False,
    }


if __name__ == "__main__":
    # Test-Ausführung
    print("JIT Kernels Status:", get_jit_status())
    prewarm_all_kernels()
