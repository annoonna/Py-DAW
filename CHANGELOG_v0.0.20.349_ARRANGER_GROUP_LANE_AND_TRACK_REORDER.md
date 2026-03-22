# v0.0.20.349 — Arranger Group-Lane / Fold-State / Track-Reorder

## Neu / geändert
- Projektmodell um `arranger_collapsed_group_ids` erweitert.
- TrackList synchronisiert Fold-State jetzt mit dem Projektmodell.
- ArrangerCanvas reduziert eingeklappte Gruppen auf eine gemeinsame sichtbare Lane.
- Track-Kontextmenü bietet jetzt `Spur nach oben` / `Spur nach unten`.
- Gruppenkopf- und Track-Menüs können neue Instrument-/Audio-/Busspuren direkt in die aktive Gruppe einfügen.

## Safe-Grenze
- Keine Änderung an Audio-Routing, Mixer-Core oder DSP.
- Gruppen-Lane ist eine organisatorische/visuelle Ansicht, kein neuer Gruppenbus.
