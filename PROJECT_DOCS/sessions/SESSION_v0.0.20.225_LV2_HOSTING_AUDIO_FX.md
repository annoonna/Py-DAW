# SESSION v0.0.20.225 — LV2 Hosting (Audio-FX) + MVP UI + Offline Tool

**Date:** 2026-03-04
**Assignee:** GPT-5.2 Thinking (ChatGPT)
**Directive:** ✅ Oberste Direktive: *nichts kaputt machen* → LV2 Hosting ist **optional** und fällt sauber auf No-Op zurück.

## Ziel
User möchte „Plugins laden“ → mindestens LV2 soll **in der Device-Chain hörbar** werden.
Dabei soll das System weiterhin stabil bleiben (keine Engine-Refactors, keine neuen Hard-Dependencies).

## Umsetzung (safe)

### 1) Audio Engine Integration
- `audio/fx_chain.py` erkennt jetzt `plugin_id` **`ext.lv2:<URI>`**.
- Ein neuer Processor `Lv2Fx` (in `audio/lv2_host.py`) wird gebaut und als `AudioFxBase` in die Chain aufgenommen.
- Wenn `python-lilv` fehlt oder die URI nicht gefunden wird → **No-Op**, kein Crash.

### 2) Realtime Safety
- Port-Buffers (Audio + Control) werden **einmalig** angelegt.
- `process_inplace()` macht nur:
  - Control-Scalars aus RTParamStore lesen
  - Audio rein/raus kopieren
  - `instance.run(frames)` aufrufen

### 3) Parameter UI (MVP)
- `ui/fx_device_widgets.py`: `Lv2AudioFxWidget`
  - Auto-Controls via `describe_controls(uri)`
  - Slider + Spinbox pro Port
  - Search/Filter
  - Persist: schreibt Werte in `device.params[symbol]`
  - Realtime: RTParamStore Key `afx:<track>:<device>:lv2:<symbol>`

### 4) Offline Tool (Debug)
- `ui/plugins_browser.py`: Kontextmenü
  - „Offline: Render WAV through LV2…“
  - Nutzt `offline_process_wav()` aus `audio/lv2_host.py`.

## Dependencies / Install
- Optional: `python-lilv` (+ `lilv-utils`)
  - Debian/Ubuntu: `sudo apt install python3-lilv lilv-utils`
- Optional für Offline-Tool: `soundfile` (meist eh vorhanden)

## Dateien
- `pydaw/audio/lv2_host.py` (neu)
- `pydaw/audio/fx_chain.py`
- `pydaw/audio/audio_engine.py`
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/ui/plugins_browser.py`
- `VERSION`, `pydaw/version.py`

## Hinweis / Next safe steps
- LADSPA/DSSI/VST Hosting bleibt **separat** (andere APIs/Dependencies → riskanter).
- Nächster LV2 Schritt (safe):
  - Bypass/Power pro LV2 Device ohne rebuild (per RT flag)
  - optional: LV2 State Save/Load (nicht nötig für MVP)
