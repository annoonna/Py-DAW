# Session v0.0.20.350 — Arranger Group Alignment / Move Buttons

Datum: 2026-03-08
Bearbeiter: GPT-5

## Ziel
- Ausgeklappte Gruppen im Arranger wieder synchron zur linken TrackList darstellen.
- Direkt sichtbares Verschieben von Spuren/Gruppen im Arranger ergänzen.

## Umsetzung
- `ArrangerCanvas._lane_entries()` so angepasst, dass ausgeklappte Gruppen jetzt wie links als **Gruppenkopf + Mitglieder** aufgebaut werden.
- Canvas-Lane-Zeichnung entsprechend ergänzt.
- New-clip-Ghost auf Lane-Index statt Track-Liste umgestellt, damit die Vertikalposition mit Gruppenkopf-Lanes stimmt.
- In `TrackList` sichtbare Move-Buttons für Spuren und Gruppen ergänzt.
- In `ProjectService` und `AltProjectService` Block-Move für Gruppen ergänzt.

## Safe-Grenze
- Kein Eingriff in Playback, Mixer, Routing oder DSP.
- Reiner UI-/Projektordnungs-Schritt.
