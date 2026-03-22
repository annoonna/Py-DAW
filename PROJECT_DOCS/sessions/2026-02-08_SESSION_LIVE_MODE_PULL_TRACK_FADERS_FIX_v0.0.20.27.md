# Session Log — v0.0.20.27
**Date:** 2026-02-08  
**Developer:** GPT-5.2 Thinking  
**Topic:** Live/Preview Mode: Track-Fader + Meter für Pull-Sources (Sampler)  

## Problem (User Report)
- Während **Play/Loop (Live Mode / Preview-Engine)** reagieren **nur Master-Fader** sofort.
- Track-Fader (Instrumente/Bus/Audio) wirken erst nach **Stop → Play**.
- VU-Meter bewegen sich nicht (v. a. auf Track-Strips).

## Root Cause
- In **Sounddevice-Silence/Preview Callback** wurden Pull-Sources nur **direkt in Master** gemischt.
  - Track-Fader (vol/pan/mute/solo) werden jedoch über **RTParamStore** verwaltet und müssen **pro Track** angewendet werden.
  - Außerdem wurden **Track-Meter-Rings** nicht aktualisiert (Mixer liest Track-Meter über HybridCallback).

- Sampler registrierte seinen Pull als **bound method** (`engine.pull`) ohne Track-ID-Metadaten.

## Fix (v0.0.20.27)
### 1) AudioEngine (Sounddevice Silence/Preview Callback)
- Pull-Sources werden jetzt optional **pro Track** gemischt, wenn der Pull-Fn eine Track-ID bereitstellt:
  - `_pydaw_track_id` (string oder callable → dynamic)
  - Anwendung von **Mute/Solo/Vol/Pan** über `RTParamStore`
  - Update der **Track-Meter** via `HybridEngineBridge.callback.get_track_meter(idx).update_from_block(...)`
- Audio-clock Looping im Silence/Preview Callback ergänzt (Transport-loop bei aktivem External Clock).

### 2) SamplerWidget
- Registriert Pull-Source jetzt über Wrapper-Fn (statt bound method) und taggt:
  - `pull._pydaw_track_id = lambda: self._track_id`
- So kann die Engine die Track-Fader live anwenden.

### 3) DSPJackEngine (JACK Live/Preview)
- Pull-Sources: per-Track gain/pan/mute/solo + Track-Meter update
- Optional HybridBridge-binding (`set_hybrid_bridge`) damit Mixer-Meter auch bei JACK Live/Preview laufen.

## Modified Files
- `pydaw/audio/audio_engine.py`
- `pydaw/plugins/sampler/sampler_widget.py`
- `pydaw/audio/dsp_engine.py`
- `VERSION`, `pydaw/version.py`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md` (Hotfix Task v0.0.20.27)

## Test Plan
1. Starten, Track mit Sampler aktivieren (oder bestehenden Sampler nutzen).
2. Play + Loop aktivieren.
3. Track-Fader bewegen (Instrument Track): Lautstärke muss **sofort** reagieren (ohne Stop/Play).
4. Mute/Solo testen in Live Mode.
5. VU-Meter sollten auf Track-Strips **live** ausschlagen.

