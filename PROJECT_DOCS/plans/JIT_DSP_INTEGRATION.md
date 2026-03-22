# PyDAW JIT-DSP Integration (v0.0.20.66)

## Übersicht

Diese Version integriert Numba-basierte JIT-Compilation für alle kritischen
Audio-DSP-Operationen. Ziel ist es, die `process()`-Methode des Audio-Streams
unter **2ms für 512 Samples** zu halten.

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SETUP PHASE (Python/PyQt6)                            │
│  - Parameter-Initialisierung                                                  │
│  - Filter-Koeffizienten berechnen                                            │
│  - RT-Parameter-Store Setup                                                   │
│  - JIT Pre-Warming beim App-Start                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RENDER PHASE (JIT/No-GIL)                             │
│  - @njit(cache=True, fastmath=True, nogil=True)                             │
│  - Keine Python-Objekte                                                       │
│  - Keine Speicher-Allokationen                                               │
│  - Kein GIL → echte Multi-Core-Parallelität                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Neue Dateien

### 1. `pydaw/audio/jit_kernels.py`
Low-Level JIT-kompilierte DSP-Funktionen:

- **Oszillatoren**: `render_sine_wave`, `render_saw_wave`, `render_pulse_wave`, `render_triangle_wave`
- **Filter**: `apply_onepole_lowpass`, `apply_biquad_lowpass/highpass/bandpass`
- **Gain/Pan**: `apply_gain_stereo_inplace`, `apply_pan_stereo_inplace`, `compute_pan_gains`
- **Effekte**: `apply_soft_clip_inplace`, `apply_tanh_distortion_inplace`, `apply_wet_dry_mix_inplace`
- **Limiter**: `apply_hard_limiter_inplace`, `compute_peak_with_release`
- **Envelope**: `generate_adsr_envelope`
- **Utils**: `mono_to_stereo`, `stereo_to_mono`, `resample_linear`

### 2. `pydaw/audio/jit_effects.py`
High-Level Effekt-Klassen für die FX-Chain:

- `JitGainFx` - Gain-Kontrolle
- `JitDistortionFx` - Tanh-Distortion mit Wet/Dry
- `JitFilterFx` - Biquad LP/HP/BP Filter
- `JitSoftClipFx` - Soft-Clipping/Sättigung
- `JitLimiterFx` - Hard-Limiter (Brickwall)
- `JitOnePoleFilterFx` - Einfacher One-Pole Filter

### 3. `pydaw/services/jit_prewarm_service.py`
Pre-Warming Service für glitchfreien Start:

```python
from pydaw.services.jit_prewarm_service import JitPrewarmService

# Im SplashScreen:
prewarm = JitPrewarmService()
prewarm.progress_changed.connect(update_splash_bar)
prewarm.finished.connect(show_main_window)
prewarm.start()
```

## Installation

```bash
# Neue Dependencies (bereits in requirements.txt)
pip install numba>=0.59 llvmlite>=0.42
```

## Verwendung in der Audio-Engine

### Beispiel: JIT-Effekte in ChainFx integrieren

```python
# In fx_chain.py oder arrangement_renderer.py

from pydaw.audio.jit_effects import create_jit_effect

def _compile_device(self, device_spec, track_id, rt_params):
    plugin_id = device_spec.get("plugin_id", "")
    device_id = device_spec.get("id", "")
    params = device_spec.get("params", {})
    
    # JIT-Effekt erstellen
    jit_fx = create_jit_effect(plugin_id, device_id, track_id, params, rt_params)
    if jit_fx:
        return jit_fx
    
    # Fallback auf Python-Implementierung
    return LegacyPythonEffect(device_spec)
```

### Beispiel: Direct JIT-Kernel Usage

```python
from pydaw.audio.jit_kernels import (
    render_sine_wave,
    apply_biquad_lowpass,
    apply_gain_stereo_inplace
)
import numpy as np

# Oszillator
buffer = render_sine_wave(440.0, 0.0, 44100.0, 512)

# Filter mit State
mono_data = np.zeros(512, dtype=np.float32)
filtered, z1, z2 = apply_biquad_lowpass(mono_data, 1000.0, 0.707, 44100.0, 0.0, 0.0)

# Gain (in-place)
stereo_buf = np.zeros((512, 2), dtype=np.float32)
apply_gain_stereo_inplace(stereo_buf, 0.8)
```

## Design-Prinzipien

### 1. Striktes Typ-Design (float32)
Alle JIT-Funktionen sind auf `float32` spezialisiert, um Re-Compilation zu vermeiden:

```python
@njit(
    "float32[:](float32, float32, float32, int32)",
    cache=True, fastmath=True, nogil=True
)
def render_sine_wave(frequency, phase, sample_rate, buffer_size):
    # ...
```

### 2. No-Python-Zone
Innerhalb `@njit` dürfen nur verwendet werden:
- NumPy-Arrays
- Primitive Datentypen (int, float)
- Andere JIT-kompilierte Funktionen

**VERBOTEN:**
- Python-Listen, Dicts, Sets
- Klassen-Instanzen
- String-Operationen
- Exception-Handling (außer sehr simple)

### 3. Pre-Warming
JIT kompiliert normalerweise beim ersten Aufruf ("Lazy"). Das führt zu CPU-Spikes.
**Lösung:** Jede Funktion beim App-Start einmal mit Dummy-Daten aufrufen.

```python
def prewarm_all_kernels():
    dummy_mono = np.zeros(512, dtype=np.float32)
    dummy_stereo = np.zeros((512, 2), dtype=np.float32)
    
    # Jede Funktion einmal aufrufen
    render_sine_wave(440.0, 0.0, 44100.0, 512)
    apply_biquad_lowpass(dummy_mono, 1000.0, 0.707, 44100.0, 0.0, 0.0)
    # ...
```

### 4. Zero-Allocation in Render-Schleife
Buffer werden einmal beim Start allokiert und wiederverwendet:

```python
class AudioEngine:
    def __init__(self):
        self._mix_buf = np.zeros((8192, 2), dtype=np.float32)
        self._tmp_buf = np.zeros((8192, 2), dtype=np.float32)
    
    def render_callback(self, frames):
        # Nur Slicing, keine Allokation
        mix = self._mix_buf[:frames]
        mix.fill(0.0)
        # ...
```

## Performance-Erwartungen

| Operation | Pure Python | Mit Numba JIT |
|-----------|-------------|---------------|
| Sine Wave (512 samples) | ~0.5ms | ~0.01ms |
| Biquad Filter (512 samples) | ~0.8ms | ~0.02ms |
| Gain + Pan (Stereo) | ~0.3ms | ~0.005ms |
| Komplette FX-Chain (3 Effekte) | ~2.5ms | ~0.1ms |

## Benchmarking

```python
import time
import numpy as np
from pydaw.audio.jit_kernels import render_sine_wave, apply_biquad_lowpass

# Warm-up
render_sine_wave(440.0, 0.0, 44100.0, 512)

# Benchmark
iterations = 10000
start = time.perf_counter_ns()

for _ in range(iterations):
    render_sine_wave(440.0, 0.0, 44100.0, 512)

elapsed_ns = time.perf_counter_ns() - start
per_call_us = (elapsed_ns / iterations) / 1000

print(f"Pro Aufruf: {per_call_us:.2f} µs")
```

## Fehlerbehandlung

Falls Numba nicht verfügbar ist, fallen alle Funktionen automatisch auf
reine Python-Implementierungen zurück:

```python
try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
```

## Nächste Schritte

1. **Sampler-DSP**: JIT-Optimierung für Sample-Playback mit Pitch-Shifting
2. **Convolution-Reverb**: FFT-basierter Reverb mit Numba
3. **Parallel-Rendering**: Multi-Track Rendering mit `prange` parallelisieren
4. **SIMD-Optimierung**: AVX/AVX2 für weitere Performance-Gewinne

## Kontakt

Bei Fragen zur JIT-Integration: Siehe `pydaw/audio/jit_kernels.py` für
detaillierte Kommentare und Beispiele.

---
*Letzte Aktualisierung: 2026-02-13*
*Version: v0.0.20.66*
