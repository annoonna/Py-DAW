# v0.0.20.351 — Arranger Maus-Reorder in TrackList

## Neu
- Linke Arranger-TrackList kann Spuren jetzt per **Maus-Drag** neu anordnen.
- Mehrfachauswahl wird als **Block** verschoben.
- Der bestehende **Cross-Project-Drag** bleibt erhalten und nutzt weiterhin das bekannte MIME-Format.

## Technik
- Neues internes MIME: `application/x-pydaw-tracklist-reorder`
- Neues `ArrangerTrackListWidget` fängt nur **same-widget** Drops mit diesem MIME ab.
- `ProjectService.move_tracks_block()` bewegt die ausgewählten Nicht-Master-Spuren als Block, ohne den Master zu verschieben.

## Sicherheit
- Kein Audio-/Routing-/Mixer-/DSP-Umbau.
- Kontextmenüs, Move-Buttons und Cross-Project-Drag bleiben parallel erhalten.
