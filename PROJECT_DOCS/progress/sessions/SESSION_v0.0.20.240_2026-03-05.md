# Session v0.0.20.240 (2026-03-05)

## Ziel
LV2 Audio-FX sind oft *DSP: ACTIVE*, aber klingen trocken/ohne hörbaren Effekt.

## Ursache (beobachtet)
Viele LV2 Plugins haben **mehr als 2 Audio Output Ports** (Dry-Tap/Monitor/Wet/Aux).
Wenn der Host die falsche Paarung zurückkopiert, bleibt der Sound praktisch unverändert.

## Änderungen (SAFE)
- LV2 Device UI: **Output Pair Selector** hinzugefügt (Auto + Out 0/1, 2/3, …).
- Runtime: Umschalten setzt nur die **Copy-Back Auswahl** im Lv2Fx (keine Re-Instantiation, keine GUI-Rebuilds).
- Persistenz: Auswahl wird als `__out_sel` im Device gespeichert.

## Dateien
- `pydaw/audio/lv2_host.py`
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/version.py`

## Test
- LV2 mit mehreren Outputs (z.B. Reverb/Delay/Wah/Flanger): Output-Paar durchklicken → Effekt sollte hörbar werden.
- Keine Crashes (keine run()-Calls im UI Thread).
