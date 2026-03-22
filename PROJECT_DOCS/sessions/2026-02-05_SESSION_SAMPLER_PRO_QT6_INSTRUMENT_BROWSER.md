# Session Log — 2026-02-05 — v0.0.19.7.45

## Ziel
- Den "Professional Audio Sampler" (Qt5) als **Qt6-Instrument** in Py_DAW integrieren.
- Sampler soll **im Browser → Instruments** erscheinen (nicht hart im Device-Panel eingebettet).
- Device-Panel soll eine **Device-Chain** darstellen (mehrere Devices möglich) und Devices entfernen können.
- Sampler muss Audio über **AudioEngine Pull Sources** liefern (Preview-Output auch bei gestopptem Transport).

## Änderungen (Kurz)
### Browser
- `pydaw/ui/device_browser.py`: Instruments Tab auf echte Instrument-Liste umgestellt.
- `pydaw/ui/instrument_browser.py`: Neues Instrument-Tab (Suche + Add-to-Device).

### Plugin/Registry
- `pydaw/plugins/registry.py`: Instrument-Registry (Plugin-ID → Factory).

### Device Panel
- `pydaw/ui/device_panel.py`: Device-Chain (horizontal scroll), kein Auto-Sampler, Remove-Button je Device.
- Devices werden jetzt über Browser hinzugefügt.

### Pro Audio Sampler (Qt6)
- `pydaw/plugins/sampler/sampler_widget.py`: UI im Look&Feel des originalen Qt5 Samplers (Knobs, Bereiche, Waveform).
- `pydaw/plugins/sampler/sampler_engine.py`: Pull-based Engine (WAV → mono, Filter/FX/ADHSR, Preview-Noten).
- `pydaw/plugins/sampler/ui_widgets.py`: Knob + WaveformDisplay (WAV-only, keine externen Audio-Reader deps).
- `pydaw/plugins/sampler/dsp.py`: DSP Helpers (Biquad, DelayLine, etc.)

### MainWindow
- `pydaw/ui/main_window.py`: Browser erhält Callback → `DevicePanel.add_instrument()`; wechselt automatisch in Device-View.

## Test-Checkliste
- Start: Browser → Instruments → "Pro Audio Sampler" → Add → Device-View öffnet sich.
- WAV per Button oder Drag&Drop laden → Waveform sichtbar.
- Noten in PianoRoll/Notation hinzufügen → Preview triggert Sampler (wenn WAV geladen).
- Device entfernen (X) → Pull-Source wird deregistriert.

## Version
- `VERSION` und `pydaw/version.py` → **0.0.19.7.45**
