# 📝 SESSION LOG — Live Mode Track-Faders + Meter Fix (v0.0.20.26)

**Datum:** 2026-02-08  
**Kollege:** GPT-5.2 Thinking  
**Scope:** Hotfix nach Runtime-Test (Live/Loop Mode)

---

## Problem (vom User gemeldet)

- **VU Meter bewegt sich nicht**
- Im **Live Mode / Loop Mode** funktioniert nur **Master** live.
- Track-Fader (Instrument/Bus/Audio) greifen **erst nach Stop → Play**.

---

## Ursache

### 1) Mixer VU war an falsche Quelle gebunden
`pydaw/ui/mixer.py` erwartete `audio_engine._hybrid_callback`, aber `AudioEngine` hat dieses Attribut nicht.
→ VU-Update lief ins Leere.

### 2) ClipLauncher Playback nutzte Track-Gain/Pan nur als Snapshot
`pydaw/services/cliplauncher_playback.py` berechnet `track_gain`/`track_pan` beim Voice-Building.
Während laufendem Playback werden Fader-Änderungen nicht neu ausgewertet.
→ Erst Stop/Play (Rebuild) übernimmt die neuen Werte.

### 3) Preview/Silence Callback schrieb keine Master-Meter Daten
Im sounddevice Preview/Monitoring (`_run_sounddevice_silence`) wurde zwar gemischt, aber nicht in die Hybrid-Meter-Ring geschrieben.
→ Master-Meter konnte im Live Mode 0 bleiben.

---

## Fix (v0.0.20.26)

### A) Mixer: Metering immer über HybridEngineBridge (fallback AudioEngine)
- Master: `hybrid_bridge.read_master_peak()`
- Tracks: `hybrid_bridge.callback.get_track_meter(track_idx).read_and_decay()`

### B) ClipLauncher: Track-Fader/Mute/Solo/Pan live aus RTParamStore
- In `pull()` wird `rt_params` verwendet (smooth, lock-free).
- Jeder Voice-Mix nutzt pro Block:
  - `rt.get_track_vol(track_id)`
  - `rt.get_track_pan(track_id)`
  - `rt.is_track_muted(track_id)`
  - Solo-Gating via `rt.any_solo()` + `rt.is_track_solo(track_id)`

### C) Live Mode Metering
- ClipLauncher aktualisiert (optional) TrackMeterRing direkt beim Mix:
  - `meter.update_from_block(chunk, gl, gr)`
- Preview/Silence Callback schreibt Master-Block in Hybrid meter ring.

---

## Geänderte Dateien

- `pydaw/ui/mixer.py`
- `pydaw/services/cliplauncher_playback.py`
- `pydaw/audio/audio_engine.py`
- `pydaw/audio/hybrid_engine.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

---

## Test-Checklist (bitte jetzt)

1) **Live Mode**: ClipLauncher starten → Track-Fader bewegen → Lautstärke muss **sofort** reagieren (ohne Stop/Play).
2) **Mute/Solo**: im Live Mode testen.
3) **VU Meter**:
   - Master: bewegt sich in Live Mode
   - Track: bewegt sich bei ClipLauncher Playback (Track-Meter)
4) **Arranger Mode**: Play im Arranger → per-track Meter/Params weiterhin ok.

