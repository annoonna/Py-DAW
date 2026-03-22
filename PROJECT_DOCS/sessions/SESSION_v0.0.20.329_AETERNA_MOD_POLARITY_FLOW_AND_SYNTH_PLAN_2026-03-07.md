# SESSION LOG — v0.0.20.329 — AETERNA Mod-Polarität + Flow + Synth-Plan

Datum: 2026-03-07
Autor: GPT-5

## Kontext
Ziel war der nächste sichere lokale AETERNA-Schritt nach dem Mod-Rack:
1. sichtbare **Amount-/Polaritätsanzeige** für die realen Web-A/B-Slots
2. kleine lokale **Signalfluss-Linienansicht**
3. ehrliche Klärung, was von der großen gewünschten Synth-Liste bereits real vorhanden ist und was noch geplant werden muss

## Umsetzung
- In `aeterna_engine.py` wurden die lokalen Web-Slots um `mod1_polarity` / `mod2_polarity` erweitert.
- Polarität wirkt nur lokal in AETERNA auf die beiden vorhandenen Mod-Slots.
- In `aeterna_widget.py` wurden ergänzt:
  - Polaritätsbuttons **+ / −** für Web A und Web B
  - Mod-Rack-Slot-Zusammenfassung mit **Balkenanzeige**
  - kleine **FLOW**-Karte mit dynamischer Darstellung `Quelle → Web A/B → Ziel`
  - Restore/Save-Handling für die neue Polarität
- Zusätzlich wurde in der Arbeitsplanung ein sicherer mehrstufiger Ausbauplan für die große gewünschte Synth-Erweiterung festgehalten.

## Wichtig
Die große Liste aus der User-Anfrage ist **noch nicht** komplett real implementiert:
- nicht vollständig vorhanden: eigene neue AEG/FEG-ADSR, echter Filterblock mit mehreren Typen, Unison-Voices, Sub-Oszillator, Pulse Width, Glide, Feedback/Pre-Filter-Drive, Noise-Generator, komplette Pitch-/Retrig-/Pan-Sektion
- vorhanden sind aktuell:
  - bestehende AETERNA-Klangknobs
  - Web A/B mit Amount
  - Mod-Quellen LFO1/LFO2/MSEG/Chaos/ENV/VEL
  - Drag-&-Drop-Zuweisung
  - einklappbare Bereiche
  - jetzt zusätzlich **Polarität und Flow-Karte**

## Warum dieser Schritt sicher ist
- nur lokale Dateien in AETERNA + Versions-/Doku-Dateien geändert
- kein Eingriff in Arranger-Core, Playback-Core, Mixer oder Transport
- kein globales Projektmodell geändert

## Nächste sichere Optionen
- **SYNTH PANEL Stage 1**: lokale UI-Gruppierung vorhandener stabiler AETERNA-Parameter in eine besser lesbare Synth-Oberfläche
- **SYNTH PANEL Stage 2**: erster kleiner echter neuer Filterblock (Cutoff/Reso/Type) als isolierter AETERNA-Schritt
- **Targets kompakter gruppieren** im Mod-Rack
