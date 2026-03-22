# Session v0.0.20.579 — Fusion GUI Hotfix: debounced State Persist

**Datum:** 2026-03-17
**Entwickler:** OpenAI GPT-5.4 Thinking
**Task:** Fusion-UI bei MIDI-CC-Flut flüssiger machen, ohne globale Systeme anzufassen
**Prioritaet:** CRITICAL — User-Report: Fusion-Knobs frieren bei laufendem MIDI/CC ein, Bach Orgel bleibt fluessig

---

## Problem

Nach v0.0.20.578 war Fusion stabiler und rangekorrekt, aber die UI war unter echter MIDI-CC-Last noch immer zaeh.
Der entscheidende Unterschied zu Bach Orgel war im Widget-Pfad:

- `FusionWidget._on_knob_changed()` setzte **bei jedem Tick** den Engine-Parameter
- und schrieb danach **sofort** den kompletten Instrument-State zurueck ins Projekt
- inkl. `project_updated` Signal

Bei schnell eintreffenden Controller-CCs fuehrte das zu einer Kette aus:

`MIDI CC -> Knob repaint -> engine.set_param() -> kompletter knob-state snapshot -> project_updated`

Das ist fuer Fusion teurer als bei den einfacheren Instrumenten, weil Fusion mehr UI-Zustand und mehr dynamische Module verwaltet.

---

## Loesung (minimal, Fusion-only, risikoarm)

**Datei:** `pydaw/plugins/fusion/fusion_widget.py`

Es wurde **nur Fusion** angepasst:

- neuer `QTimer` als **single-shot debounce** (`120 ms`)
- `_on_knob_changed()` speichert den Projektzustand nicht mehr sofort
- stattdessen: `_schedule_persist_instrument_state()`
- Engine-Parameter werden weiterhin **sofort** gesetzt
- nur der teure Projekt-/UI-Refresh-Pfad wird zusammengefasst
- `shutdown()` flusht einen evtl. noch offenen Persist-Timer sauber vor dem Entfernen des Pull-Source

---

## Warum das sicher ist

- **Keine** Aenderung an `CompactKnob` global
- **Keine** Aenderung am MIDI-Routing fuer andere Instrumente
- **Keine** Aenderung an Bach Orgel / AETERNA / Sampler / Drum Machine
- **Keine** Aenderung an Audio-Engine, AutomationManager oder SamplerRegistry
- Nur der Fusion-Widget-Refresh/Persist-Pfad wurde entlastet

Engine-Werte reagieren weiterhin sofort; nur der Projektzustand wird gesammelt geschrieben.

---

## Erwartete Wirkung

- Deutlich weniger GUI-Haenger bei gemappten Fusion-Knobs
- Weniger `project_updated`-Sturm bei CC-Flut
- Besseres Gefuehl beim Drehen von MIDI-Controllern auf Fusion
- Kein globales Risiko fuer andere Devices

---

## Validierung

### Statisch
- `python3 -m py_compile pydaw/plugins/fusion/fusion_widget.py` -> **OK**

### Fachliche Pruefung
- Engine-Update bleibt sofort
- Persistenz bleibt erhalten
- letzter offener Persist wird in `shutdown()` nicht verloren

---

## Naechster sicherer Schritt (falls noch noetig)

Wenn Fusion trotz dieses Hotfixes noch zaeh bleibt, waere der **naechste** kleine und sichere Schritt:

1. nur fuer Fusion MIDI-CC-UI-Updates auf ~60 Hz coalescen
2. **nicht** global in `CompactKnob` eingreifen
3. erst danach weiter an tieferen Engine-Themen arbeiten
