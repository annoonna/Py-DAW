# CHANGELOG v0.0.20.356 — Kritischer Bugfix: Collapsed-Group Clip-Track-Zuordnung

## Fehlerbeschreibung

Beim Gruppieren von Audio-Tracks (z.B. Drums: kick, snare, closed hi, open hi) und
anschließendem Einklappen der Gruppe traten drei zusammenhängende Bugs auf:

1. **Clip-Track-Korruption bei Drag (KRITISCH)**: Jeder horizontale Drag-Vorgang
   innerhalb einer eingeklappten Gruppe hat ALLE Clips auf den ersten Member-Track
   (z.B. kick) umgehängt. Ursache: `_tracks()` lieferte nur `members[0]` für
   collapsed Groups, und die Drag-Commit-Logik nutzte diesen Index zum Umhängen.

2. **Falsche Audio-Wiedergabe**: Als Folge von Bug 1 spielten nach einem Drag
   alle gruppierten Instrumente gleichzeitig, weil ihre Clips dem gleichen Track
   zugeordnet waren.

3. **Visuelle Verwirrung**: In der eingeklappten Ansicht überlagerten sich alle
   Clips aller Member-Tracks auf einer Zeile. Der zuletzt gemalte Clip (z.B. open hi)
   verdeckte die anderen (z.B. kick) → User sah "o-hi wo kick sein sollte".

## Fixes

### Fix 1: `_is_same_collapsed_group()` Helper (NEU)
- Neue Methode in `arranger_canvas.py` prüft, ob zwei Track-IDs zur selben
  aktuell eingeklappten Gruppe gehören.
- Wird von allen drei Drag-Codepfaden verwendet.

### Fix 2: Single-Clip-Drag geschützt
- `mouseReleaseEvent` → `_drag_move` Pfad: `move_clip_track()` wird übersprungen,
  wenn Quell- und Ziel-Track in derselben collapsed Group liegen.

### Fix 3: Multi-Clip-Drag geschützt
- `_drag_move_multi` Pfad: Gleicher Guard wie Fix 2.

### Fix 4: Copy-Drag geschützt
- `_drag_copy_preview` Pfad: Bei Kopie innerhalb einer collapsed Group wird die
  Original-Track-ID beibehalten (nicht `members[0]`).

### Fix 5: Track-Lookup Fallback
- Clip-Rendering: Wenn `trk` in der reduzierten `_tracks()`-Liste nicht gefunden
  wird (= Clip gehört zu einem Non-First-Member einer collapsed Group), wird auf
  die vollständige `project.tracks`-Liste zurückgegriffen. Damit stimmt Volume-Anzeige.

### Fix 6: Spur-Name-Prefix bei eingeklappter Gruppe
- Clips auf einer eingeklappten Gruppen-Zeile zeigen jetzt den Track-Namen als
  Prefix: `🔹kick: 000_Kick Thick...` / `🔹open hi: 053_O_Hat...`
- Damit kann der User sofort erkennen, welcher Clip zu welchem Member-Track gehört.

## Technisch

### Geänderte Dateien
- `pydaw/ui/arranger_canvas.py`
  - `_is_same_collapsed_group()` (NEU, ~30 Zeilen)
  - `mouseReleaseEvent` → drei Drag-Commit-Guards
  - `paintEvent` → Track-Lookup-Fallback + Label-Prefix
  - Cache-Key erweitert um Collapsed-State
- `pydaw/version.py` → 0.0.20.356
- `pydaw/model/project.py` → Default-Version 0.0.20.356
- `VERSION` → 0.0.20.356

### Sicherheit
- Kein Eingriff in Audio-Engine, DSP, Routing, Mixer oder Playback-Core.
- Keine Änderung an Datenmodell, Projektformat oder Serialisierung.
- Rein defensive Guards in der UI-Drag-Logik + visueller Fix.
- Bestehende expand/collapse-Funktionalität unverändert.
- Keine neuen Dependencies.

## Reproduktion (vorher)
1. Tracks gruppieren (Ctrl+G)
2. Gruppe einklappen
3. Einen Clip horizontal verschieben → ALLE Clips werden auf `members[0]` umgehängt
4. Abspielen → Alle Instrumente spielen gleichzeitig

## Verifikation (nachher)
1. Tracks gruppieren + einklappen
2. Clip horizontal verschieben → Track-Zuordnung bleibt erhalten
3. Abspielen → Jedes Instrument spielt nur seine eigenen Clips
4. Clip-Labels zeigen Track-Name-Prefix für bessere Übersicht
