# Session v0.0.20.582 — Fusion Regression Smoke-Test + Snapshot Flush

**Datum:** 2026-03-17
**Entwickler:** OpenAI GPT-5.4 Thinking

## Kontext
Nach den Hotfixes fuer Fusion (Realtime-Sync, debounced Persist, MIDI-CC Coalescing, Scrawl Recall) war der naechste sichere Schritt nicht sofort LFO/FX, sondern zuerst eine reproduzierbare Regression-Absicherung. Gleichzeitig sollte ein kleiner Snapshot-Randfall geschlossen werden: ein gespeicherter State darf nicht den letzten coalescten MIDI-CC-Wert verlieren.

## Erledigt
- `pydaw/plugins/fusion/fusion_widget.py`
  - neuer Helper `_capture_state_snapshot()`
  - offene Fusion-only MIDI-CC Queue wird vor State-Snapshots geflusht
  - `Preset Save` und Projekt-Persistenz nutzen jetzt denselben Snapshot-Pfad
- `pydaw/tools/fusion_smoke_test.py`
  - neuer offscreen-faehiger Regression-Harness
  - Tests: queued MIDI-CC Snapshot, Modulwechsel, Scrawl Roundtrip, Wavetable Roundtrip
  - klare `[SKIP]`-Meldung, wenn `PyQt6` in der Laufumgebung fehlt
- `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md`
  - manueller Testplan fuer echte GUI/MIDI-Interaktion

## Validierung
- Syntax: `python3 -m py_compile pydaw/plugins/fusion/fusion_widget.py pydaw/tools/fusion_smoke_test.py`
- Qt-Runtime im Container nicht voll pruefbar (`PyQt6` nicht installiert)

## Naechste sichere Schritte
1. Smoke-Test im echten PyQt6-User-Setup laufen lassen
2. Dann Fusion LFO Modulation bauen
3. Danach Unison/Detune auf Engine-Ebene
4. Danach Fusion FX-Sektion
