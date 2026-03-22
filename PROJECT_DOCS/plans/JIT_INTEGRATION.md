# PyDAW JIT-Integration Guide (v0.0.20.66)

## Übersicht

Dieses Dokument beschreibt die Integration von **Numba JIT-Compilation** in PyDAW, um C++-ähnliche Performance für Audio-DSP-Operationen zu erreichen.

### Ziel
Die `process()`-Methode unseres Audio-Streams muss unter **2ms für 512 Samples** bleiben, um Echtzeit-Audio ohne Glitches zu ermöglichen.

### Lösung
Wir lagern alle mathematischen Operationen aus dem Standard-Python-Interpreter in **JIT-kompilierte Machine-Code-Blöcke** aus.

---

## Installation

```bash
pip install numba llvmlite --break-system-packages
```

Oder über requirements.txt:
```bash
pip install -r requirements.txt --break-system-packages
```

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SETUP PHASE (Python/PyQt6)                            │
│  - Parameter-Initialisierung                                                  │
│  - Filter-Koeffizienten berechnen                                            │
│  - RT-Parameter-Store Setup                                                   │
│  - JIT Pre-Warming (beim App-Start)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RENDER PHASE (JIT/No-GIL)                             │
│  - process_inplace() → Ruft JIT-Kernels auf                                  │
│  - KEINE Python-Objekte (nur Arrays, Primitive)                              │
│  - KEINE Speicher-Allokationen                                               │
│  - KEIN GIL (echte Multi-Core-Parallelität)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Neue Dateien

### 1. `pydaw/audio/jit_kernels.py`
Enthält die Basis-DSP-Funktionen mit Numba:
- Oszillatoren (Sine, Saw, Pulse, Triangle)
- Filter (One-Pole, Biquad LP/HP/BP)
- Gain/Pan
- Effekte (Soft-Clip, Tanh-Distortion)
- Limiter
- Envelope Generator

### 2. `pydaw/audio/jit_effects.py`
Enthält JIT-optimierte Effekt-Klassen:
- `JitGainFx` - Gain mit RT-Parameter
- `JitDistortionFx` - Tanh-Distortion
- `JitFilterFx` - Biquad Filter (LP/HP/BP)
- `JitSoftClipFx` - Soft-Clipper
- `JitLimiterFx` - Hard-Limiter
- `JitOnePoleFilterFx` - Simple One-Pole

### 3. `pydaw/services/jit_prewarm_service.py`
Pre-Warming Service für App-Startup:
- Kompiliert alle JIT-Kernels beim Start
- Verhindert Audio-Dropouts beim ersten Ton
- Unterstützt SplashScreen-Progress

---

## Integration in bestehenden Code

### 1. App-Startup (main.py oder app.py)

```python
# In main.py
from pydaw.services.jit_prewarm_service import JitPrewarmService

def main():
    app = QApplication(sys.argv)
    
    # JIT Pre-Warming beim Start (im SplashScreen)
    splash = QSplashScreen()
    splash.show()
    
    prewarm = JitPrewarmService()
    prewarm.progress_changed.connect(
        lambda p, msg: splash.showMessage(f"{p}%: {msg}")
    )
    prewarm.finished.connect(lambda: show_main_window())
    prewarm.start()
    
    return app.exec()
```

### 2. FX-Chain Integration (fx_chain.py)

```python
# In fx_chain.py, _compile_devices() erweitern:

from pydaw.audio.jit_effects import create_jit_effect, NUMBA_AVAILABLE

def _compile_devices(self, devices_spec: Any) -> None:
    self.devices = []
    
    for dev in devices_spec:
        pid = str(dev.get("plugin_id") or "")
        did = str(dev.get("id") or "")
        params = dev.get("params", {})
        
        # JIT-Effekt versuchen
        if NUMBA_AVAILABLE:
            jit_fx = create_jit_effect(
                plugin_id=pid,
                device_id=did,
                track_id=self.track_id,
                params=params,
                rt_params=self.rt_params
            )
            if jit_fx is not None:
                self.devices.append(jit_fx)
                continue
        
        # Fallback auf Python-Effekte
        if pid in ("chrono.fx.gain", "gain"):
            self.devices.append(GainFx(...))
        # ... etc
```

### 3. DSP-Engine Integration (dsp_engine.py)

Die JIT-Kernels können auch direkt in der DSP-Engine verwendet werden:

```python
from pydaw.audio.jit_kernels import (
    compute_pan_gains,
    apply_gain_stereo_inplace,
    apply_hard_limiter_inplace,
)

def render_callback(self, frames: int, in_bufs, out_bufs, sr: int) -> bool:
    # ... existierender Code ...
    
    # JIT-optimiertes Pan
    if abs(pan) > 0.005:
        gl, gr = compute_pan_gains(np.float32(1.0), np.float32(pan))
        # ... verwende gl, gr ...
    
    # JIT-optimiertes Limiter
    apply_hard_limiter_inplace(mix[:frames, :])
    
    return True
```

---

## Performance-Messung

### Benchmarking-Code

```python
import time
import numpy as np
from pydaw.audio.jit_kernels import render_sine_wave, apply_biquad_lowpass

def benchmark_sine(iterations=1000, buffer_size=512):
    total_time = 0
    
    for _ in range(iterations):
        start = time.perf_counter_ns()
        render_sine_wave(440.0, 0.0, 44100.0, buffer_size)
        total_time += time.perf_counter_ns() - start
    
    avg_us = (total_time / iterations) / 1000
    print(f"Sine-Oszillator: {avg_us:.2f}µs pro {buffer_size} Samples")
    return avg_us

def benchmark_filter(iterations=1000, buffer_size=512):
    data = np.random.randn(buffer_size).astype(np.float32)
    total_time = 0
    z1, z2 = 0.0, 0.0
    
    for _ in range(iterations):
        start = time.perf_counter_ns()
        _, z1, z2 = apply_biquad_lowpass(data, 1000.0, 0.707, 44100.0, z1, z2)
        total_time += time.perf_counter_ns() - start
    
    avg_us = (total_time / iterations) / 1000
    print(f"Biquad-Filter: {avg_us:.2f}µs pro {buffer_size} Samples")
    return avg_us

if __name__ == "__main__":
    # Pre-Warming (WICHTIG!)
    from pydaw.audio.jit_kernels import prewarm_all_kernels
    prewarm_all_kernels()
    
    # Benchmarks
    print("\n=== Performance-Test ===")
    benchmark_sine()
    benchmark_filter()
```

### Erwartete Ergebnisse

| Operation | Ohne JIT | Mit JIT | Speedup |
|-----------|----------|---------|---------|
| Sine 512 Samples | ~50µs | ~5µs | 10x |
| Biquad Filter | ~100µs | ~8µs | 12x |
| Gain Stereo | ~20µs | ~2µs | 10x |

---

## Best Practices

### 1. Type-Strictness

```python
# RICHTIG: Explizite float32 Typen
@njit(float32[:](float32, float32, float32, int32), ...)
def my_function(freq, phase, sr, size):
    output = np.empty(size, dtype=np.float32)
    # ...

# FALSCH: Keine Typisierung
@njit
def my_function(freq, phase, sr, size):
    # Numba muss Typen raten → Re-Compilation möglich!
```

### 2. No-Python-Zone

```python
# RICHTIG: Nur primitive Typen und Arrays
@njit(nogil=True)
def process(data: np.ndarray) -> np.ndarray:
    result = np.empty_like(data)
    for i in range(len(data)):
        result[i] = data[i] * 0.5
    return result

# FALSCH: Python-Objekte innerhalb @njit
@njit
def process(data: np.ndarray, settings: dict) -> np.ndarray:
    gain = settings['gain']  # ❌ dict ist ein Python-Objekt!
```

### 3. Pre-Warming

```python
# IMMER Pre-Warming beim App-Start!
from pydaw.services.jit_prewarm_service import prewarm_audio_engine_sync

if __name__ == "__main__":
    prewarm_audio_engine_sync()  # ← Vor dem ersten Audio-Callback!
    # ... App starten
```

### 4. State-Management

```python
@dataclass
class JitFilterFx:
    # Filter-State als Instanz-Attribute (nicht im JIT)
    _z1: float = 0.0
    _z2: float = 0.0
    
    def process_inplace(self, buf, frames, sr):
        # State aus Python-Ebene lesen
        z1, z2 = self._z1, self._z2
        
        # JIT-Kernel aufrufen (State als Parameter)
        result, new_z1, new_z2 = apply_biquad_lowpass(
            buf, cutoff, q, sr, z1, z2
        )
        
        # State zurückschreiben
        self._z1, self._z2 = new_z1, new_z2
```

---

## Troubleshooting

### Problem: "Numba not available"

```bash
# Lösung: Numba installieren
pip install numba llvmlite --break-system-packages

# Bei Problemen mit llvmlite:
pip install --upgrade llvmlite --break-system-packages
```

### Problem: Audio-Dropouts beim ersten Ton

```python
# Lösung: Pre-Warming vergessen!
from pydaw.audio.jit_kernels import prewarm_all_kernels
prewarm_all_kernels()  # ← VOR dem ersten Audio-Callback!
```

### Problem: Langsame Compilation beim Start

```bash
# Lösung: Cache aktivieren (bereits standardmäßig aktiv)
# Überprüfe, ob .nbc Dateien im Cache-Verzeichnis sind:
ls ~/.cache/numba/
```

---

## Nächste Schritte

1. **Alle DSP-Klassen identifizieren**, die von JIT profitieren würden
2. **JIT-Varianten erstellen** für: Sampler-DSP, Synth-Oszillatoren, weitere Filter
3. **Benchmarks erstellen** für Performance-Vergleich
4. **Integration testen** mit echtem Audio-Setup

---

## Kontakt

Bei Fragen zur JIT-Integration: siehe `PROJECT_DOCS/sessions/` für Session-Logs.
