# Session v0.0.20.262 — FX Automation UI RT Sync

Datum: 2026-03-06

## Kontext
User-Report nach v0.0.20.261: Audio-FX-Automation ist jetzt hörbar korrekt, aber die sichtbaren Slider/Regler bewegen sich im Device/Slot-FX-UI nicht mit.

## Safe-Fix
- UI-only Fallback-Synchronisierung über `RTParamStore` ergänzt
- betroffen: `AudioChainContainerWidget`, `LadspaAudioFxWidget`
- bestehende Automations-Qt-Signale bleiben unverändert aktiv

## Technische Umsetzung
- je Widget leichter `QTimer` (50 ms)
- liest nur sichtbare RT-Zielwerte und blockt Widget-Signale beim Setzen
- kein Eingriff in Playback, DSP, Persistenz oder Plugin-Instanziierung

## Geänderte Dateien
- `pydaw/ui/fx_device_widgets.py`
- `VERSION`
- `pydaw/version.py`

## Validierung
- `python3 -m py_compile pydaw/ui/fx_device_widgets.py`
