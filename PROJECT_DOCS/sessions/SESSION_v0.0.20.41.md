# Session Log — v0.0.20.41 Direct Peak VU Metering Fix

**Date:** 2026-02-09  
**Developer:** Claude Opus 4.6  
**Duration:** ~45 min  

## Task

VU-Meter im Mixer schlugen nicht aus (User-reported Bug).

## Analyse

Die Metering-Datenkette hatte 4 Schichten mit stummen Exception-Handlern:
`AudioCallback → TrackMeterRing → HybridBridge → MixerStrip`

Jede Schicht konnte still fehlschlagen → Meter bekam immer (0.0, 0.0).

## Lösung

Neuer direkter Datenweg: `AudioEngine._direct_peaks` dict
- Audio-Thread schreibt per-track und master Peaks direkt ins dict
- GUI-Thread liest direkt aus dem dict → nur 1 Schicht statt 4
- Alle alten Pfade bleiben als Fallback

## Geänderte Dateien

- `pydaw/audio/audio_engine.py` — _direct_peaks storage + read methods + callback writing
- `pydaw/audio/hybrid_engine.py` — _direct_peaks_ref wiring + peak writing in __call__ + render_for_jack
- `pydaw/ui/mixer.py` — _update_vu_meter reads from direct peaks first
- `pydaw/version.py`, `VERSION` → 0.0.20.41

## Nächste Schritte

- Testen: Play drücken und prüfen ob VU-Meter ausschlagen
- Bei weiterhin stummen Metern: Debug-Logging in _update_vu_meter einschalten
- Ggf. _HYBRID_AVAILABLE prüfen (Terminal-Output beim Start beachten)
