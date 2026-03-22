# Session-Log: v0.0.20.356 — Collapsed-Group Drag Bugfix

**Datum**: 2026-03-08
**Bearbeiter**: Claude Opus 4.6
**Aufgabe**: Kritische Bugs bei eingeklappten Gruppen-Tracks analysieren und beheben
**Ausgangsversion**: 0.0.20.355
**Ergebnisversion**: 0.0.20.356

## Analyse

### Bug-Report vom User
1. Bei gruppierten Audio-Tracks spielen ALLE Instrumente, auch wenn nur Kick von Bar 1-4 laufen soll
2. Beim Umordnen von Clips in eingeklappter Gruppe hört man trotzdem alle Instrumente
3. Bei eingeklappter Gruppe zeigt sich "o-hi" wo "kick" stehen sollte

### Tiefenanalyse

**Root Cause identifiziert in `arranger_canvas.py`:**

Die `_lane_entries()` Methode erstellt bei eingeklappter Gruppe EINEN Eintrag mit
`members: [alle]` aber `track: members[0]`. Drei Folgeprobleme:

1. `_lane_index_for_track_id()` mappt ALLE Member-Clips auf denselben Lane-Index
2. `_tracks()` liefert nur `members[0]` → Drag-Code nutzt diesen für track_id Zuordnung
3. `_track_at_y()` gibt für die collapsed Row immer `members[0]` zurück

**Konsequenz:** Bei JEDEM Drag (horizontal oder vertikal) werden ALLE Clips auf
den ersten Member-Track umgehängt → Data Corruption → alle Instrumente spielen zusammen.

**Audio-Engine selbst ist korrekt** — der Bug liegt rein in der UI-Drag-Logik.

### Betroffene Code-Pfade
- Single-Clip-Drag: `mouseReleaseEvent` → `_drag_move` → `move_clip_track()`
- Multi-Clip-Drag: `mouseReleaseEvent` → `_drag_move_multi` → `move_clip_track()`
- Copy-Drag: `mouseReleaseEvent` → `_drag_copy_preview` → `track_id = tracks[nt].id`

## Implementierung

### Neuer Code
- `_is_same_collapsed_group(track_id_a, track_id_b)`: Prüft ob beide Tracks zur
  selben aktuell eingeklappten Gruppe gehören

### Guards eingefügt
- Single-Drag: Guard vor `move_clip_track()`
- Multi-Drag: Guard vor `move_clip_track()`
- Copy-Drag: Fallback auf Original-Track-ID

### Visuelle Verbesserungen
- Track-Lookup-Fallback auf `project.tracks` wenn `_tracks()` den Track nicht findet
- Spur-Name-Prefix (🔹kick: ...) bei eingeklappter Gruppe im Clip-Label
- Cache-Key um Collapsed-State erweitert

## Sicherheit
- ✅ Kein Eingriff in Audio-Engine
- ✅ Kein Eingriff in DSP/Routing/Mixer
- ✅ Kein Eingriff in Projektformat/Serialisierung
- ✅ Rein defensive Guards + visueller Fix
- ✅ Expand/Collapse-Funktionalität unverändert

## Nächste Schritte
- [ ] Sub-Lanes für eingeklappte Gruppen (statt Überlappung)
- [ ] Echte Group-Bus Device-Chain (Routing-/Mixer-Schritt)
