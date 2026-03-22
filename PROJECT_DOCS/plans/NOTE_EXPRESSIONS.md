# Note Expressions (MPE‑Style) — Plan & Datenmodell

Ziel: **Per‑Note Automationen** direkt auf dem MIDI‑Baustein, inspiriert von **Bitwig/Cubase**.

**Oberste Direktive:** *nichts kaputt machen*. Daher ist alles erstmal **additiv** und **opt‑in**.

---

## 1) Datenmodell (v0.0.20.196 foundation)

Wir speichern Expressions direkt am `MidiNote` Objekt.

### JSON‑safe Struktur

`MidiNote.expressions` ist ein Dictionary:

```python
expressions: dict[str, list[dict]]

# Beispiel:
note.expressions = {
  "velocity":  [ {"t": 0.0, "v": 0.8}, {"t": 1.0, "v": 0.6} ],
  "micropitch": [ {"t": 0.2, "v": -0.25}, {"t": 0.6, "v": 0.75} ],
}
```

**t (time):** normalisiert **0..1** innerhalb der Note (0 = Note‑Start, 1 = Note‑Ende).  
**v (value):** Parameter‑Wert.

- Für `velocity/chance/timbre/pressure/gain/pan`: bevorzugt normalisiert **0..1** (UI/Engine kann später mappen).
- Für `micropitch`: `v` wird als **Semitones** interpretiert (z.B. ‑1.0 .. +1.0), UI kann das später skalieren.

Warum **normalisierte Zeit**?
- Beim **Verschieben** der Note müssen Expression‑Punkte nicht verändert werden.
- Beim **Resizen** kann die UI entscheiden: „mit‑skalieren“ (default) oder „fixed time“.
- Das geplante **Expression‑Triangle** (Morph‑Handle) kann Time‑Scaling direkt auf `t` anwenden.

---

## 2) Undo/Redo + Clipboard

Damit Expressions nicht „verloren gehen“, wurden Snapshots erweitert:

- `snapshot_midi_notes()` speichert zusätzlich `accidental`, `tie_to_next`, `expressions`.
- Clipboard Copy/Paste in der Piano‑Roll nimmt diese Felder ebenfalls mit.

---

## 3) UI‑Integration (Nächste Iterationen)

### 3.1 NoteExpressionEngine (modular)

Neues Modul: `pydaw/ui/note_expression_engine.py`.

- `draw_expressions(painter, note_rects)` als Rendering‑Hook.
- Default: **enabled = False** (keine Regression).
- Später: Hit‑Testing, Menu‑Popup, Morph‑Drag.

### 3.2 Expression‑Triangle

Kleines Dreieck am Note‑Start:

- Klick → Quick‑Menu (Param wählen)
- Drag → Time‑Morph der Expression‑Kurve innerhalb der Note

✅ **Implementiert in v0.0.20.197 (opt‑in):**
- Hover über Note → Triangle erscheint dezent
- Klick auf Triangle → Param‑Quick‑Menu
- **Alt+Drag** auf Triangle → Time‑Morph (t‑Werte skaliert), Commit on Release
- Doppelklick auf Note → Focus‑Mode (andere Noten gedimmt), **ESC** beendet

### 3.3 Expression‑Lane (unter Piano‑Roll)

✅ **Implementiert in v0.0.20.197 (opt‑in):**

- Neues Widget: `pydaw/ui/note_expression_lane.py`
- Zeigt die aktive Expression‑Kurve für ein Target‑Note (Priorität: Focus > Select > Hover)
- Editing ist **nur in der Lane** aktiv → keine Regression für Move/Resize/Knife.
- Draw‑Editing: Linksklick+Ziehen → sparse Punkte; Undo Snapshot wird bei Release committed.

✅ **Erweitert in v0.0.20.198 (opt‑in):**

- Lane‑Tools: **Draw / Select / Erase** (Header‑Buttons in Piano‑Roll)
- Select‑Tool: Punkt anklicken → auswählen, Drag → bewegen (t/v). **Del/Backspace** löscht selektierten Punkt.
- Erase‑Tool: Linksklick+Ziehen löscht Punkte nahe am Cursor.
- RMB auf Punkt: Delete (Shortcut)
- Double‑Click: Draw=Add/Update, Select=Delete

### 3.4 Micropitch Rendering (Smooth)

`micropitch` wirkt „eckig“, wenn man nur Punkte verbindet.

✅ v0.0.20.197: Visualisierung nutzt **cubic Bezier** (Catmull‑Rom → `QPainterPath.cubicTo`) für ein
Bitwig‑ähnlich geschmeidiges Kurvenbild — ohne dass mehr Datenpunkte gespeichert werden müssen.

---

## 4) Parameter‑Keys (v0.0.20.196)

- `velocity`
- `chance`
- `timbre`
- `pressure`
- `gain`
- `pan`
- `micropitch`

---

## 5) Debug/Toggles

Preferences (QSettings):

- `ui/pianoroll_note_expressions_enabled` (default False)
- `ui/pianoroll_note_expressions_param` (default "velocity")

Damit kann man das Overlay später schnell aktivieren, ohne UI‑Umbau.

## v0.0.20.199 — Lane Pro Tools
- SHIFT axis-lock constraints while dragging points (Select tool)
- Lasso selection (Select tool, drag empty area)
- Per-segment curve types: `MidiNote.expression_curve_types[param]` (linear/smooth)
- Toggle curve type: `C` (after selected point) + RMB on curve
- Quantize selected points: `Q` (to current grid)
- Thin selected points: `T`


## v0.0.20.200 — Lane UX: Segment Badges + Context Menu + Value Snapping (Alt=free)
### Segment Badges (Affordances)
- Jeder Segment-Abschnitt zwischen zwei Punkten bekommt ein kleines Badge:
  - **L** = Linear
  - **S** = Smooth
- Hover hebt das Badge hervor.
- **Left-Click auf Badge** toggelt den Segment-Typ (linear ↔ smooth).

### Context Menu (statt nur Hotkeys)
- **RMB auf Segment/Badge**: Context-Menu
  - Toggle Linear/Smooth
  - Set Linear
  - Set Smooth
  - Insert Point Here
- **RMB auf Punkt**: Quick-Delete bleibt (wie zuvor), **Ctrl+RMB** öffnet das Point-Menü.
- **RMB leerer Bereich**: Quantize/Thin/Clear Selection (falls Selection vorhanden)

### Value Snapping (per Param)
- Standard **AN** (Lane-only):
  - velocity/chance/timbre/pressure/gain/pan: **Step 0.01**
  - micropitch: **Step 0.05 semitones**
- **ALT halten** = frei (kein Snapping)
- Preference:
  - `ui/pianoroll_expr_value_snap` (default True)
- UI:
  - Header Button **V-Snap** toggelt diese Preference.

## v0.0.20.201 — Lane UX Polish: Badge Icons + Tooltips + Legend
- Segment-Badges zeigen **Icons**:
  - Linear = kleine Linie
  - Smooth = kleine Kurve (Bezier)
- Hover über Badge zeigt Tooltip (Segment-Typ + Actions)
- Kleine Legend oben rechts erklärt die Icons (klarer / Bitwig-Style)


## v0.0.20.206 — Playback Mapping (hörbar machen)

### Warum war vorher „nichts hörbar“?
Der SF2/FluidSynth Render benutzt einen WAV-Cache. Der Cache-Key hat **Expressions ignoriert** und in Teilen sogar die falschen Keys (`start` statt `start_beats`) gehasht.
→ Ergebnis: Das System hat alte WAVs wiederverwendet, obwohl du Velocity/Chance/Timbre/Pressure geändert hast.

### Was wird jetzt beim Abspielen angewendet (safe, Note-On only)
- **Velocity**: Wenn `expressions['velocity']` vorhanden ist, wird der Wert bei `t=0.0` als Note-On Velocity benutzt.
- **Chance**: Wenn `expressions['chance']` vorhanden ist, wird bei `t=0.0` deterministisch entschieden, ob die Note gespielt wird.
- **Timbre**: Wenn `expressions['timbre']` vorhanden ist, wird bei `t=0.0` **CC74** vor dem Note-On gesendet.
- **Pressure**: Wenn `expressions['pressure']` vorhanden ist, wird bei `t=0.0` **Poly Aftertouch (polytouch)** vor dem Note-On gesendet.

> Hinweis: Micropitch/MPE ist bewusst noch nicht Teil des Playback-Mappings (riskant → später als eigener MPE-Mode).

### Deterministische Chance
Chance nutzt eine deterministische Hash-Funktion (clip_id + beat + pitch), damit:
- Projekte bei jedem Abspielen/Rerender gleich klingen
- Render-Cache stabil bleibt

### Advanced Toggles (QSettings)
Diese Keys sind optional (defaults sind True). Sie sind „advanced“, weil noch kein UI-Menü dafür existiert.
- `audio/note_expr_apply_velocity` (True)
- `audio/note_expr_apply_chance` (True)
- `audio/note_expr_send_cc74` (True)
- `audio/note_expr_send_pressure` (True)

### Code
- Expression Eval: `pydaw/audio/note_expression_eval.py`
- SF2 Render: `pydaw/audio/midi_render.py`
- Arranger Hash + Tie-Coerce: `pydaw/audio/arrangement_renderer.py`
- Live-MIDI Fallback: `pydaw/audio/audio_engine.py`
