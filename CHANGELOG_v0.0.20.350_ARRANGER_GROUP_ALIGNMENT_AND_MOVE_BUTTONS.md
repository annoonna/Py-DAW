# v0.0.20.350 — Arranger Group Alignment / Move Buttons / Group Block Move

## Neu / geändert
- ArrangerCanvas spiegelt jetzt den sichtbaren Gruppenaufbau der linken TrackList auch im ausgeklappten Zustand: **Gruppenkopf-Lane + alle Mitglieder-Lanes**.
- Dadurch werden **Instrument-, Audio- und Busspuren** in ausgeklappten Gruppen wieder sauber und vollständig untereinander dargestellt.
- Track- und Gruppenzeilen besitzen jetzt sichtbare **Move-Buttons** für `nach oben` / `nach unten`.
- ProjectService/AltProjectService können jetzt eine **ganze Gruppe als Block** verschieben.

## Safe-Grenze
- Kein Eingriff in Audio-Routing, Mixer-Core oder DSP.
- Reiner UI-/Projektordnungs-Schritt für Arranger und Gruppendarstellung.
