# Session v0.0.20.580 — Fusion MIDI-CC UI Coalescing (~60 Hz)

**Datum:** 2026-03-17
**Entwickler:** OpenAI GPT-5.4 Thinking
**Task:** Fusion unter laufendem MIDI/CC weiter entlasten, ohne globale Widgets oder andere Instrumente anzufassen
**Prioritaet:** CRITICAL — User-Report: Fusion-Knobs frieren unter CC-Flut weiter ein, Bach Orgel bleibt fluessig

---

## Problem

Nach v0.0.20.579 war der teure Projekt-Persistenzpfad bereits entlastet, aber die Fusion-UI konnte unter echter Controller-Last noch immer zaeh werden.
Der Grund: Jeder einzelne eingehende MIDI-CC lief weiterhin direkt durch `CompactKnob.handle_midi_cc()` und damit durch Repaint + `valueChanged` + Engine-Update.

Bei einem Controller mit vielen schnellen CC-Ticks pro Sekunde fuehrte das in Fusion weiterhin zu sehr vielen UI-Updates hintereinander.

---

## Loesung (minimal, Fusion-only, risikoarm)

**Datei:** `pydaw/plugins/fusion/fusion_widget.py`

Es wurde nur Fusion angepasst:

- neuer Fusion-only `QTimer` (`16 ms`, single-shot) fuer gepufferte MIDI-CC-Flushes
- jeder Fusion-`CompactKnob` bekommt lokal einen kleinen Wrapper fuer `handle_midi_cc()`
- eingehende CC-Werte werden **pro Knob** gesammelt
- pro Frame wird nur der **letzte** Wert je Knob angewendet
- dynamische OSC/FLT/ENV-Extra-Knobs droppen beim Rebuild noch offene alte CC-Werte
- `shutdown()` flusht ausstehende CCs, bevor Pull-Source/Registry entfernt werden

---

## Warum das sicher ist

- **Keine** globale Aenderung an `CompactKnob`
- **Keine** Aenderung am AutomationManager-Dispatch fuer andere Instrumente
- **Keine** Aenderung an Bach Orgel / AETERNA / Sampler / Drum Machine
- **Keine** Aenderung an Audio-Engine oder DSP
- nur Fusion-Widgets bekommen lokal ein sanftes CC-Throttling

Damit bleibt das Risiko klein und auf das betroffene Instrument begrenzt.

---

## Erwartete Wirkung

- fluessigere Bedienung von Fusion-Knobs bei gemappten MIDI-Controllern
- deutlich weniger Repaints/GUI-Events pro Sekunde bei CC-Flut
- weiterhin direkter Eindruck, aber ohne jeden rohen Controller-Tick 1:1 zu visualisieren
- keine Verhaltensaenderung fuer andere Instrumente

---

## Validierung

### Statisch
- `python3 -m py_compile pydaw/plugins/fusion/fusion_widget.py` -> **OK**

### Fachliche Pruefung
- Coalescing bleibt lokal in `FusionWidget`
- dynamische Knob-Rebuilds loeschen offene Queue-Eintraege alter Widgets
- letzter pending CC geht beim `shutdown()` nicht verloren

---

## Naechster sicherer Schritt

Danach ist der sinnvollste naechste kleine Schritt **kein weiterer Blind-Hotfix**, sondern ein reproduzierbarer manueller Regression-Smoke-Test fuer:

1. MIDI Learn auf Fusion
2. mehrere schnelle CC-Drehungen
3. OSC/FLT/ENV-Wechsel waehrend Mapping aktiv ist
4. pruefen, ob Freeze, falsche Werte oder verlorene Mappings noch auftreten
