# SESSION v0.0.20.338 — AETERNA LIVE ARP SAFE BRIDGE

Datum: 2026-03-07

## Gemacht

- AETERNA **Arp A** um einen sicheren **ARP Live**-Schalter erweitert.
- Statt einen neuen riskanten Live-Arp im Playback-Core zu bauen, wird jetzt lokal auf der aktuellen AETERNA-Spur ein vorhandenes **Track Note-FX Arp** gepflegt.
- Das AETERNA-Widget erzeugt/findet dafür ein eigenes Note-FX-Arp mit Marker `aeterna_owner=arp_a` und schaltet es per UI **an/aus**.
- Die bereits vorhandenen **16-Step-Daten** werden jetzt auch im bestehenden `chrono.note_fx.arp` berücksichtigt:
  - Pattern/Mode
  - Rate + Straight/Dotted/Triplets
  - Shuffle + Shuffle Steps
  - pro Step: Transpose / Skip / Velocity / Gate
- AETERNA-Arp-UI klarer getrennt in **ARP Live** und **ARP → MIDI**.
- Lokale Readability leicht erhöht (Card-/Hint-Schriften, Controls).

## Nicht angefasst

- Arranger
- Clip Launcher
- Audio Editor
- Mixer
- Transport
- globaler Playback-Core
- andere Instrumente

## Technischer Hinweis

Der sichere Weg war hier, die vorhandene **Track.note_fx_chain** zu nutzen, statt einen neuen Echtzeit-Arpeggiator direkt in den Instrument-Pull-Pfad einzubauen. Dadurch bleibt die Änderung rückwärtskompatibel und lokal beherrschbar.
