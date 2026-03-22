# Session v0.0.20.248 — LADSPA ABI Layout + Port Flags Fix

**Datum:** 2026-03-05
**Bearbeiter:** GPT-5.4 Thinking

## Anlass
User meldet reproduzierbaren SIGSEGV beim Arbeiten mit LADSPA-Devices. GDB-Backtrace zeigt Crash in `_ctypes`/`libffi` aus einem Qt-Button-Callback.

## Analyse
- In `pydaw/audio/ladspa_host.py` war `LADSPA_Descriptor` nicht ABI-kompatibel zu `ladspa.h`.
- Das Feld `ImplementationData` fehlte direkt vor `instantiate`.
- Dadurch wurden Callback-Pointer aus falschen Offsets gelesen — klassischer harter ctypes-Absturz.
- Zusätzlich waren die LADSPA Port-Flags falsch codiert, was Port-Klassifikation und Verdrahtung verfälschte.

## Änderungen
- `ImplementationData` in `LADSPA_Descriptor._fields_` eingefügt.
- Port-Konstanten auf offizielle LADSPA-Werte korrigiert.
- Kommentar ergänzt, damit das Struct künftig nicht wieder versehentlich ABI-inkompatibel wird.
- Versionsdateien auf `0.0.20.248` angehoben.

## Risiko
- Niedrig und gezielt: nur LADSPA-Host ABI/Bitmasks korrigiert.
- Keine Änderungen am übrigen DAW-Routing, UI-Layout oder Projektformat.

## Empfehlung an nächsten Kollegen
- Auf User-System mit problematischem LADSPA-Plugin erneut testen (`am_pitchshift_1433`, `allpass_1895`, `revdelay`).
- Falls noch einzelne Plugins crashen, als nächstes SAFE Schritt: LADSPA-Probe im Subprozess analog LV2 Safe-Mode.
