# CHANGELOG v0.0.20.471 — CLAP Instrument Engine Reuse Fix

## Problem
Nach dem sichtbaren CLAP-GUI-Fix konnte es weiterhin passieren, dass bei harmlosen Refresh-/Rebuild-Zyklen eine zweite CLAP-Instrument-Engine für dieselbe Spur erzeugt wurde.

## Ursache
Der generische Reuse-Check verglich `old_eng.path` mit dem kompletten `vst_ref`. Bei CLAP ist `vst_ref` jedoch oft `bundle_path::plugin_id`, während `ClapInstrumentEngine` Pfad und Plugin-ID getrennt speichert.

## Fix
- CLAP-Referenz wird jetzt mit `split_plugin_reference()` getrennt
- Reuse prüft `engine.path` **und** `engine.plugin_id_str`
- Reuse-Logging für CLAP zeigt jetzt `CLAP-INST`

## Datei
- `pydaw/audio/audio_engine.py`
