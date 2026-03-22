# Py_DAW v0.0.20.153 – Audio Editor: Bar-Ruler + DAW Shortcuts

## Ziel
Wenn der Clip Launcher aktiv ist und unten der Audio-Editor offen ist, fehlt bisher die "Bar"-Anzeige wie im Arranger (Bitwig/Ableton). Außerdem sollen Standard-Shortcuts (Strg+C/V/X, Entf, Strg+D) im Audio-Editor genauso funktionieren wie im Arranger.

## Änderungen
### 1) Bar/Beat-Ruler im AudioEventEditor (UI-only)
- Neuer `AudioEditorRuler` über dem Audio-Editor View.
- Zeichnet Bar-Zahlen (1-based) + Beat-Ticks.
- Bleibt korrekt ausgerichtet bei Zoom/Scroll (QGraphicsView mapping scene→viewport).

### 2) DAW-Shortcuts im Audio-Editor
- `Strg+C` kopiert ausgewählte AudioEvents (Clipboard als Templates, nicht nur IDs).
- `Strg+X` schneidet aus (kopiert + löscht).
- `Strg+V` fügt an Cursor/Transport-Position ein.
  - `Strg+Shift+V` fügt ohne Snap ein.
- `Entf/Backspace` löscht Auswahl.
- `Strg+D` dupliziert Auswahl nach rechts (Group-Span).
- `Strg+A` selektiert alle AudioEvents.
- `Esc` hebt Auswahl auf.

### 3) Maus: Strg+Ziehen = Duplicate-Drag (AudioEvents)
- Alt=Duplicate Drag war vorbereitet, aber nicht zuverlässig verdrahtet.
- Jetzt:
  - `Alt+Drag` dupliziert und zieht die Duplikate.
  - `Strg+Drag` (wie gewünscht) dupliziert beim tatsächlichen Drag-Start.

### 4) ProjectService Erweiterungen (minimal & sicher)
- `delete_audio_events(clip_id, event_ids)`
- `add_audio_events_from_templates(clip_id, templates, delta_beats)`

## Sicherheit / "Nichts kaputt machen"
- Keine Audio-Engine Änderungen.
- Änderungen sind UI- und ProjectService-Level, mit try/except-Schutz in Qt Overrides.

