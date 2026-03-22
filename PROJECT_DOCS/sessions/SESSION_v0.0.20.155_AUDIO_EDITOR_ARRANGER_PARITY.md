# Session: v0.0.20.155 — Audio Editor: Arranger-Parity (Ruler, Playhead, Loop, Zoom, Clipboard, Ctrl+Drag)

**Datum:** 2026-02-28
**Assignee:** Claude Opus 4.6 (Anthropic)
**Priority:** 🔴 HIGH (Core DAW UX)
**Status:** ✅ FERTIG

---

## Problem (User-Report)

Der Audio Editor hatte im Vergleich zum Arranger massive Feature-Lücken:
- **Ruler:** Nur einfache Bar-Nummern, keine Interaktion
- **Playhead:** Komplett fehlend (keine rote Linie, nicht draggbar)
- **Loop-Region:** Nicht sichtbar im Editor
- **Zoom:** Keine Lupe / Ctrl+Wheel Zoom im Ruler
- **Kontextmenü:** Fehlende Clipboard-Operationen (Copy/Cut/Paste/Delete/Select All/Duplicate)
- **Ctrl+Drag Copy:** Events konnten nicht per Ctrl+Maus auf andere Positionen kopiert werden
- **Tastenkombinationen:** Nicht alle funktionsfähig
- **Cursor-Linie:** Keine Paste-Position angezeigt

**User-Anforderung:** "Es muss alles wie bei Ableton und Bitwig funktionieren zu 120%"

---

## Lösung (safe, nichts kaputt gemacht)

### 1. AudioEditorRuler — Komplett überarbeitet (Zeile 221-450)

**Neue Signale:**
- `seek_requested = pyqtSignal(float)` — emittiert Beat-Position bei Klick/Drag

**Neue Methoden:**
- `_beat_from_x(x_widget)` — Widget-Pixel → Beat-Position (mit View-Transform)
- `mousePressEvent()` — Click-to-Seek (Playhead springt zu Bar)
- `mouseMoveEvent()` — Drag-to-Seek (Playhead folgt Maus bei LMB)
- `mouseReleaseEvent()` — Drag beenden
- `wheelEvent()` — Ctrl+Wheel = horizontaler Zoom
- `mouseDoubleClickEvent()` — Doppelklick = Zoom-to-Fit

**Paint erweitert:**
- Playhead-Linie (rot, 2px) + Dreieck-Marker oben
- Loop-Region (grüne Shading + "LOOP" Label)
- Cursor-Linie (blau gestrichelt, Paste-Position)

**Dimensionen:** Höhe 22px → 28px (bessere Klickbarkeit)

### 2. Playhead + Cursor im AudioEventEditor

**Neue State-Variablen:**
```python
self._playhead_beat: float = 0.0
self._playhead_line: QGraphicsLineItem | None = None
self._cursor_beat: float = 0.0
self._has_cursor: bool = False
self._cursor_line: QGraphicsLineItem | None = None
```

**Neue Methoden:**
- `set_playhead_beat(beat)` — Lightweight: nur Line-Item verschieben, kein Full-Refresh
- `set_cursor_beat(beat)` — Paste-Cursor setzen + sichtbar machen
- `_on_ruler_seek(beat)` — Ruler-Click → Playhead + Cursor + Transport

**Rendering in `refresh()`:**
- Playhead-Linie: `QGraphicsLineItem` (rot, 2px, ZValue=60)
- Cursor-Linie: `QGraphicsLineItem` (blau gestrichelt, ZValue=59)

### 3. Kontextmenü — Clipboard-Operationen

**Neue Menü-Einträge (oben im Kontextmenü):**
- Copy (Ctrl+C) — enabled wenn Selection
- Cut (Ctrl+X) — enabled wenn Selection
- Paste (Ctrl+V) — enabled wenn Clipboard
- Delete (Del) — enabled wenn Selection
- Select All (Ctrl+A)
- Duplicate (Ctrl+D) — enabled wenn Selection

**Action-Handler (`_on_context_action`):**
Wiederverwendung bestehender Keyboard-Handler via simulierte QKeyEvents (DRY-Prinzip).

### 4. Ctrl+Drag Copy

**Implementierung:**
- `mousePressEvent` im EventBlockItem: `ctrl = bool(mods & ControlModifier)`
- `_begin_group_drag()`: `self._pending_dup_on_drag = bool(ctrl)`
- `_update_group_drag()`: Bei Ctrl+Drag + 4px Threshold → `_begin_duplicate_drag()`
- Dupliziert Events im Modell + erstellt neue Graphics-Items
- Nahtlose Drag-Fortsetzung mit duplizierten Items

### 5. Signal-Wiring

```python
self.ruler.seek_requested.connect(self._on_ruler_seek)
self.view.context_action_selected.connect(self._on_context_action)
```

---

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw/ui/audio_editor/audio_event_editor.py` | +310 Zeilen: Ruler, Playhead, Cursor, Kontextmenü, Ctrl+Drag |
| `VERSION` | 0.0.20.154 → 0.0.20.155 |
| `pydaw/version.py` | __version__ = "0.0.20.155" |
| `pydaw/model/project.py` | version = '0.0.20.155' |

---

## Feature-Checkliste

- [x] Ruler: Bar-Nummern (1-basiert, wie Arranger)
- [x] Ruler: Playhead (rote Linie + Dreieck)
- [x] Ruler: Loop-Region (grüne Shading + Edges + "LOOP" Label)
- [x] Ruler: Cursor-Linie (blau gestrichelt, Paste-Position)
- [x] Ruler: Click-to-Seek (Playhead + Cursor springen zu Bar)
- [x] Ruler: Drag-to-Seek (Playhead folgt Maus)
- [x] Ruler: Ctrl+Wheel Zoom (horizontal)
- [x] Ruler: Doppelklick = Zoom-to-Fit
- [x] Kontextmenü: Copy/Cut/Paste/Delete/Select All/Duplicate
- [x] Keyboard: Ctrl+C/X/V/Del/A/D (via Kontextmenü + direkt)
- [x] Ctrl+Drag Copy (Events per Ctrl+Maus duplizieren + verschieben)
- [x] Playhead-Update: `set_playhead_beat()` für Transport-Timer
- [x] Cursor-Update: `set_cursor_beat()` für Paste-Ziel

---

## Kompatibilität

- ✅ Keine Breaking Changes
- ✅ Alle bestehenden Features unverändert
- ✅ Keyboard-Shortcuts bleiben identisch
- ✅ Projekt-Datenmodell unverändert
- ✅ Transport-Integration optional (funktioniert auch ohne)
- ✅ Python-Syntax verifiziert (ast.parse OK)

---

## Nächste Schritte (für Kollegen)

- [ ] AVAILABLE — Audio Editor: Waveform-Darstellung verbessern (Peak-Normalisierung, Farb-Gradient)
- [ ] AVAILABLE — Audio Editor: Snap-to-Grid visuelles Feedback (Gridlines bei Drag)
- [ ] AVAILABLE — Audio Editor: Time-Stretch Handle (Event-Enden ziehen = Stretch)
- [ ] AVAILABLE — Audio Editor: Multi-Track Overlay (mehrere Clips überlagert anzeigen)
