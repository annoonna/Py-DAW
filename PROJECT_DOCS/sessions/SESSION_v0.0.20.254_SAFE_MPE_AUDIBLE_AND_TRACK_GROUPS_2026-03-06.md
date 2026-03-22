# Session v0.0.20.254 — Safe MPE hörbarer + Spurgruppen

## Ziel
- Micropitch/MPE hörbarer machen, ohne riskanten Playback-Umbau.
- Ausgewählte Instrument-/Audio-Spuren organisatorisch gruppierbar machen.

## Umgesetzt
- Realtime-Micropitch nutzt jetzt einen robusten frühen Startwert (0/5/10% Attack-Fenster gemittelt).
- SF2 Offline-Render setzt zusätzliche Pitchwheel-Punkte entlang der Micropitch-Kurve.
- Neue Track-Felder `track_group_id` / `track_group_name`.
- `ProjectService.group_tracks()` / `ungroup_tracks()` ergänzt.
- Arranger-Trackliste: `Ctrl+G` gruppiert Auswahl, `Ctrl+Shift+G` hebt auf.
- Gruppen werden als Badge in der Trackliste angezeigt.

## Sicherheitsrahmen
- Kein Umbau an Audio-Bus-Routing.
- Kein riskanter globaler MPE-Live-Bend-Stream für alle Engines.
- Nur additive, eng begrenzte Änderungen.
