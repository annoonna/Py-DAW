# Session Log — v0.0.20.471

**Datum:** 2026-03-15
**Entwickler:** OpenAI GPT-5.4 Thinking
**Dauer:** ~20 min
**Version:** 0.0.20.470 → 0.0.20.471

## Task

**CLAP Preset-/Editor-Stabilität nach GUI-Fix lokal härten** — ohne DSP-/Routing-Umbau, nur den Reuse-Pfad für CLAP-Instrumente korrigieren.

## Problem-Analyse

1. Der native Surge-XT-Editor läuft jetzt sichtbar, aber bei späteren Refresh-/Rebuild-Zyklen wurden dennoch neue CLAP-Instrument-Engines erzeugt.
2. Root cause: der generische Instrument-Reuse-Check verglich `old_eng.path` mit dem kompletten `vst_ref`.
3. Bei CLAP ist `vst_ref` aber typischerweise `bundle_path::plugin_id`, während `ClapInstrumentEngine.path` nur den Bundle-Pfad enthält und `plugin_id_str` separat speichert.
4. Folge: CLAP wurde nie sauber wiederverwendet, obwohl dieselbe Instanz weiterlaufen sollte. Das kann dazu führen, dass Editor und Audio nicht mehr dieselbe Plugin-Instanz meinen.

## Fix

1. **CLAP-Reuse-Check getrennt nach Bundle-Pfad + Plugin-ID**
   - `audio_engine.py` trennt CLAP-Referenzen jetzt mit `split_plugin_reference()` in Pfad + Sub-Plugin-ID.
   - Ein vorhandener `ClapInstrumentEngine` wird wiederverwendet, wenn `engine.path` und `engine.plugin_id_str` dazu passen.

2. **Log-Ausgabe passend zum Engine-Typ**
   - Reuse-Meldungen zeigen für CLAP jetzt sauber `CLAP-INST`, damit spätere Diagnosen eindeutiger bleiben.

## Betroffene Dateien

- `pydaw/audio/audio_engine.py`

## Validierung

- `python -m py_compile pydaw/audio/audio_engine.py`

## Hinweis

- Der Schritt ist bewusst klein gehalten und ändert nur die Engine-Wiederverwendung.
- Kein Eingriff in CLAP-DSP, kein neues State-Format, kein Routing-Umbau.
