# Session v0.0.20.581 — Fusion Scrawl State Save/Load Fix

**Datum:** 2026-03-17  
**Entwickler:** OpenAI GPT-5.4 Thinking

## Problem

Im Fusion-Scrawl-Oszillator wurde die gezeichnete Wellenform nach dem Projektladen nicht identisch wiederhergestellt. Der Screenshot-Vergleich zeigte klar: Knob-State war da, aber die eigentliche gezeichnete Welle wich nach dem Laden sichtbar ab.

## Ursache

`FusionWidget` speicherte bisher nur Modul-Typen und Knob-Werte. Der erweiterte Oszillator-Zustand fuer Scrawl (`points` + `smooth`) sowie der optionale Wavetable-Dateipfad lebten nur im Engine-/Editor-RAM und wurden beim Projekt-/Preset-State nicht mitgeschrieben. Zusaetzlich triggerte der Scrawl-Editor nach Zeichen-Aenderungen keinen Projekt-Persist.

## Umsetzung

### 1. Erweiterte Fusion-State-Persistenz
- Projekt-/Preset-State enthaelt jetzt zusaetzlich:
  - `scrawl_points`
  - `scrawl_smooth`
  - `wt_file_path`

### 2. Persist-Trigger fuer Scrawl-Edits
- `_on_scrawl_points_changed()` wendet die neue Welle weiter sofort auf Engine/Voices an
- danach wird der vorhandene Fusion-only Debounce-Persist angestossen

### 3. Sichere Restore-/Display-Synchronisation
- neuer Helper `_apply_scrawl_state(...)` spiegelt den geladenen Zustand in:
  - Engine-Shared-State
  - aktive Voices
  - Scrawl-Editor
- `_sync_scrawl_display()` bevorzugt jetzt bewusst den Engine-State statt bei leeren Voices auf die Default-Welle zurueckzufallen

## Geänderte Datei

- `pydaw/plugins/fusion/fusion_widget.py`

## Validierung

- `python3 -m py_compile pydaw/plugins/fusion/fusion_widget.py` ✅

## Ergebnis

Fusion speichert den Scrawl-Zusatzstate jetzt ueber denselben sicheren Projekt-/Preset-Pfad wie die restlichen Parameter. Die Editor-Welle sollte nach dem Laden nicht mehr auf eine andere Default-/Voice-Ansicht zurueckfallen.
