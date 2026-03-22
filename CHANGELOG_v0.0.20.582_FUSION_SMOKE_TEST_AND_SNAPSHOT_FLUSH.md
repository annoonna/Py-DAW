# Changelog v0.0.20.582 — Fusion Regression Smoke-Test + Snapshot Flush

- Fusion nutzt fuer Projekt-/Preset-Snapshots jetzt einen gemeinsamen `_capture_state_snapshot()`-Pfad.
- Vor dem Snapshot werden noch offene Fusion-only MIDI-CC-Queue-Eintraege geflusht, damit der letzte coalescte Knob-Wert gespeichert wird.
- Neuer offscreen-faehiger Smoke-Test unter `pydaw/tools/fusion_smoke_test.py`.
- Neuer manueller Testplan unter `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md`.
