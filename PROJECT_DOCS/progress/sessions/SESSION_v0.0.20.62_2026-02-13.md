# Session Log — v0.0.20.62 — 2026-02-13

## Task
UI: Device/FX Browser Einträge für Note-FX + Audio-FX (Add/Remove/Reorder, Presets) — MVP Drag&Drop Browser → Device-Chain.

## Changes (Engine-first, Pro-DAW UX)
- Effects Browser rewritten: catalog lists (Note-FX / Audio-FX) with Drag&Drop mime payload.
- Instrument Browser now supports Drag&Drop too (creates new instance on drop).
- DevicePanel now:
  - Accepts drops from Browser (Copy action).
  - Renders chain as modules: Note-FX → Instruments → CHAIN (WetGain+Mix) → Audio-FX.
  - Add/remove audio/note FX modifies Track.note_fx_chain / Track.audio_fx_chain.
  - Calls AudioEngine.rebuild_fx_maps(project_snapshot) after Audio-FX changes for realtime rewiring.
- New built-in Audio-FX: Distortion (tanh waveshaper) with drive+mix params and RT keys.
- FX param UI modules (MVP):
  - CHAIN: WetGain %, Mix %
  - Gain: Gain dB slider/spin
  - Distortion: Drive + Mix
  - Transpose Note-FX: semitones

## Files
- pydaw/ui/fx_specs.py
- pydaw/ui/effects_browser.py
- pydaw/ui/fx_device_widgets.py
- pydaw/ui/device_browser.py (Effects tab now uses EffectsBrowserWidget)
- pydaw/ui/device_panel.py (DnD + chain rendering + add/remove)
- pydaw/ui/instrument_browser.py (DnD payload)
- pydaw/audio/fx_chain.py (DistortionFx compile + processing)

## Notes
- Browser entries remain templates; dropping creates a new instance. Browser list never changes.
- Reorder inside chain is still TODO (Up/Down or drag reorder in DevicePanel).
- Presets: existing preset buttons in old chain editors are not wired into module UI yet.
