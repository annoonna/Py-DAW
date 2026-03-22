# CHANGELOG v0.0.20.348 — Master-FX / Undo / Track-Menü-Hotfixes

## Neu / geändert

- **Master-Audio-FX** werden jetzt im Summenpfad tatsächlich verarbeitet und sind hörbar.
- **Globales Projekt-Undo/Redo** als sicherer Snapshot-Fallback ergänzt, damit deutlich mehr Projektaktionen rückgängig gemacht werden können.
- **Globale Undo/Redo-Shortcuts** ergänzt: `Ctrl+Z`, `Ctrl+Shift+Z`, `Ctrl+Y`.
- **Arranger-Track-Kontextmenü** erweitert/repariert: **Umbenennen**, **Track löschen**, **Instrument-/Audio-/Bus-Spur hinzufügen**.
- **Gruppenkopf einklappbar** im Arranger.
- **Track löschen** im Kontextmenü repariert (`delete_track` Alias).
- **Track-Umbenennen** verwendet jetzt einen sicheren Dialog statt instabiler Inline-Editierung.

## Sicherheit

- Keine Änderung an Routing-Architektur oder Bus-Struktur.
- Kein riskanter DSP-Core-Umbau; Master-FX nutzen den bestehenden Audio-FX-Weg.
- Globales Undo bleibt bewusst als sicherer Projektmodell-Fallback ausgeführt.
