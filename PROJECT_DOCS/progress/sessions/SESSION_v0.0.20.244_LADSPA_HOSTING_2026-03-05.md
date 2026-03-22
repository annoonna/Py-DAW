# Session v0.0.20.244 — LADSPA Live-Hosting (2026-03-05)

## Ziel
LADSPA Plugins sind im Browser sichtbar (187 Stück), zeigen aber nur "(no UI yet)".
Ziel: Live Audio-Processing + Parameter-UI für LADSPA.

## Ansatz
LADSPA ist ein einfaches C-API (simpler als LV2):
- Jede .so exportiert `ladspa_descriptor(index)` → `LADSPA_Descriptor*`
- Ports sind AUDIO|CONTROL × INPUT|OUTPUT (einfache Bitmask)
- Kein TTL, kein RDF — alles in der C-Struct

Implementierung via `ctypes` (stdlib) — kein extra C-Compiler nötig.

## Neue Dateien
- `pydaw/audio/ladspa_host.py` — Komplettes LADSPA Hosting

## Geänderte Dateien
- `pydaw/audio/fx_chain.py` — LADSPA/DSSI in _compile_devices + ensure_track_fx_params
- `pydaw/ui/fx_device_widgets.py` — LadspaAudioFxWidget + make_audio_fx_widget Routing

## Architektur
```
Browser → "Add to Device" → plugin_id = "ext.ladspa:/usr/lib/ladspa/foo.so"
                                ↓
fx_chain.py → ChainFx._compile_devices → LadspaFx(path, index, ...)
                                ↓
ladspa_host.py → ctypes.CDLL(path) → ladspa_descriptor(idx)
              → instantiate(desc, sr) → connect_port() × N → activate()
                                ↓
Audio Thread → LadspaFx.process_inplace(buf, frames, sr)
            → update controls from RT store → run(handle, frames) → copy back
                                ↓
UI → LadspaAudioFxWidget → Slider/SpinBox pro Control-Port
  → _set_value → rt_params.set_param() + persist to device params
```

## Test
1. LADSPA Plugin laden (z.B. adsr_1653, compressor, delay)
2. Parameter-Slider sollten erscheinen
3. Audio abspielen → Effekt sollte hörbar sein
4. Konsole: `[LADSPA] /usr/lib/ladspa/foo.so#0: ok=True ain=2 aout=2 ctl_in=N`
