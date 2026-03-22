# SESSION LOG — v0.0.20.330 — AETERNA Synth Panel Stage 1

Datum: 2026-03-07
Autor: GPT-5

## Kontext
Ziel war der nächste sichere lokale AETERNA-Schritt nach Mod-Rack-Polarität/Flow:
1. die bereits vorhandenen stabilen AETERNA-Parameter lesbarer als Synth-Oberfläche gruppieren
2. die Grenze zur großen Wunschliste ehrlich sichtbar machen
3. noch keinen riskanten Vollumbau von Filter/ADSR/Unison/Sub/Noise in die Audio-Engine erzwingen

## Umsetzung
- In `pydaw/plugins/aeterna/aeterna_widget.py` wurde ein neuer Bereich **AETERNA SYNTH PANEL (STAGE 1 SAFE)** ergänzt.
- Der Bereich gruppiert die bereits vorhandenen stabilen Parameter in:
  - **Core Voice**
  - **Space / Motion**
  - **Mod / Web**
- Kleine Navigations-Buttons öffnen direkt die bereits vorhandenen AETERNA-Bereiche `ENGINE`, `MORPHOGENETIC CONTROLS`, `THE WEB (LOCAL SAFE)` und `MOD RACK / FLOW (LOCAL SAFE)`.
- Eine neue kompakte Kurzansicht zeigt die aktuellen Werte der stabilen Parameter sowie **Web A / Web B** in lesbarer Form.
- Zusätzlich wurden bewusst **deaktivierte UI-Preview-Felder** ergänzt:
  - Filter Type
  - Envelope
  - Layer
  - Unison / Sub / Noise
- Diese Vorschau reserviert nur sicher den UI-Platz und dokumentiert die Richtung; sie hat noch **keine Audio-Wirkung**.

## Warum dieser Schritt sicher ist
- nur lokaler AETERNA-Widget-Code geändert
- keine Änderungen an globalem Playback-Core, Mixer, Arranger, Transport oder Projektmodell
- keine neuen Audio-Parameter im globalen Automations-/Projektkern eingeführt
- Save/Load bleibt unverändert kompatibel, da nur bestehende Zustände gelesen/visualisiert werden

## Nicht umgesetzt in diesem Schritt
- keine vollständige neue AEG/FEG-ADSR-Engine
- kein neuer Filterblock mit Audio-Wirkung
- kein Unison-/Sub-/Noise-/Glide-/Drive-/Feedback-Audiopfad
- keine riskante Vollangleichung an Hive/Surge in einem Schritt

## Nächste sichere Schritte
- erster kleiner echter **Filter-Block** nur in AETERNA (**Cutoff / Resonance / Type**)
- Mod-Rack-Ziele kompakter gruppieren
- Preview-Familien lokal noch deutlicher als „noch nicht audioaktiv“ ausweisen
