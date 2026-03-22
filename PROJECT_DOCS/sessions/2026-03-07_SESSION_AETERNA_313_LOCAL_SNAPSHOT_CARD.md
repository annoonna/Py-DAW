# Session — v0.0.20.313 — AETERNA lokale Snapshot-Karte

Datum: 2026-03-07

## Ziel
Kleiner sicherer lokaler AETERNA-Schritt: schnelle Snapshot-Wege für **Klang / Formel / Web** direkt im Widget, ohne Eingriff in DAW-Core oder andere Editoren.

## Umgesetzt
- neue lokale Snapshot-Sektion mit drei Slots **A / B / C**
- je Slot **Store** und **Recall**
- Snapshot speichert nur lokale AETERNA-Zustände:
  - Preset
  - Mode / Formeltext
  - Formel-Hilfsstatus
  - Web-Vorlage / Intensität
  - Web A/B Source/Target
  - wichtige Klang- und Rate-Knobs
- Snapshot-Slots werden mit dem Instrument-State gespeichert und beim Wiederladen des Projekts restauriert

## Sicherheit
- nur `pydaw/plugins/aeterna/aeterna_widget.py` geändert
- keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core

## Nächster sicherer Schritt
Lokale Snapshot-Hinweise noch kompakter lesbar machen oder Preset-/Snapshot-Kombis als Schnellaufruf ergänzen.
