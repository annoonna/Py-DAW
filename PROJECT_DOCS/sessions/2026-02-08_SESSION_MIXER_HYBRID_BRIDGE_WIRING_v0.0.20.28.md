# Session Log — v0.0.20.28
**Date:** 2026-02-08  
**Developer:** GPT-5.2 Thinking  
**Topic:** Mixer Live-Fader + Meter Fix (HybridBridge Wiring)

## Problem (User Report)
- Während **Play/Loop** reagieren **nur Master-Fader** sofort.
- Track-Fader (Instrumente/Bus/Audio) wirken erst nach **Stop → Play** bzw. gar nicht zuverlässig.
- **VU-Meter** bewegen sich nicht.

## Root Cause
Der Mixer war **nicht mit der HybridEngineBridge verdrahtet**:
- `pydaw/ui/main_window.py` erzeugte `MixerPanel(...)` **ohne** `hybrid_bridge=...`.
- Dadurch liefen Track-Änderungen nur über `RTParamStore` (ClipLauncher/Preview),  
  aber **Arrangement-Playback** benutzt die **Hybrid Param-Ring** (lock-free) → Track-Fader hatten live keine Wirkung.
- VU-Meter bevorzugen HybridBridge (TrackMeterRing + Master AudioRingBuffer) → ohne Bridge bleibt alles statisch.

## Fix (v0.0.20.28)
### 1) MixerPanel / MixerStrip (Auto-Wire)
- Wenn `hybrid_bridge` nicht explizit übergeben wird, wird sie automatisch aus `AudioEngine._hybrid_bridge` (fallback: `AudioEngine.hybrid_bridge`) übernommen.
- Dadurch:
  - Track-Fader/Pan/Mute/Solo schreiben **in die Hybrid Param-Ring** (live wirksam)
  - VU-Meter lesen **TrackMeterRing/Master-Ring** (live Animation)

### 2) MainWindow (Explizite Übergabe)
- `main_window.py` übergibt zusätzlich `_hb` an `MixerPanel(..., hybrid_bridge=_hb)`.
  (Doppelte Absicherung – robust, auch wenn MixerPanel später anders instanziiert wird.)

## Modified Files
- `pydaw/ui/mixer.py`
- `pydaw/ui/main_window.py`
- `VERSION`, `pydaw/version.py`
- `CHANGELOG.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Test Notes
- Während laufendem Playback/Loop: Track-Fader sofort hörbar.
- VU-Meter: Master + Tracks bewegen sich in Echtzeit (Hybrid).
