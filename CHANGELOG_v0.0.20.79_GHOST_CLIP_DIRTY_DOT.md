# CHANGELOG v0.0.20.79 — Ghost-Clip Feedback + Dirty-Indicator Dot

**Datum:** 2026-02-15
**Entwickler:** Claude Opus 4.6

## Neue Features

### Ghost-Clip Overlay im Arranger Canvas
Beim Drag über den Arranger Canvas wird ein halbtransparenter Clip-Preview an der
Cursor-Position angezeigt. Der Ghost snapped an die aktuelle Grid-Division und die
Track-Lane unter dem Cursor.

**Farbcodierung:**
- **Blau** (rgba 80,160,255): Cross-Project Drag (Tracks/Clips aus anderem Tab)
- **Grün** (rgba 120,200,120): MIDI-Datei-Drop (.mid/.midi)
- **Amber** (rgba 200,160,80): Audio-Datei-Drop (.wav/.mp3 etc.)

**Label:** Zeigt Typ + Details an:
- Cross-Project: "↗ 2 Tracks" / "↗ 3 Clips"
- Audio: "🔊 drums.wav"
- MIDI: "🎵 melody.mid"

**Technisch:**
- `_drag_ghost_pos` (QPointF): aktuelle Cursor-Position
- `_drag_ghost_kind` (str): "cross-project" | "audio" | "midi" | ""
- `_drag_ghost_label` (str): anzuzeigende Bezeichnung
- Ghost wird in `paintEvent` nach Lasso-Rect gerendert
- `dragLeaveEvent` (NEU): löscht Ghost wenn Drag den Canvas verlässt
- Ghost wird am Anfang von `dropEvent` gelöscht

### Dirty-Indicator als Farbiger Punkt
Tabs mit ungespeicherten Änderungen zeigen jetzt einen orangefarbigen Punkt (QIcon)
links neben dem Tab-Text, statt des bisherigen "• " Unicode-Prefix.

**Vorteile:**
- Funktioniert auch wenn Tab-Text elidiert (abgeschnitten) wird
- Visuell auffälliger als Text-Prefix
- Konsistentes Erscheinungsbild unabhängig von Font-Rendering

**Technisch:**
- `_get_dirty_icon()`: Erzeugt 12×12 QPixmap mit 8px orange Kreis (antialiased)
- `_get_clean_icon()`: Erzeugt 12×12 transparenten QPixmap
- Icons werden als Klassenattribute gecached (nur 1x erzeugt)
- `setTabIcon()` statt Text-Manipulation in allen 4 Handlern

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/ui/arranger_canvas.py` | Ghost-clip state + dragEnter/Move/Leave/drop/paint |
| `pydaw/ui/project_tab_bar.py` | Dirty-dot icon + QIcon imports + cache |
| `pydaw/version.py` | 0.0.20.79 |
| `pydaw/model/project.py` | Version-String |
| `VERSION` | 0.0.20.79 |

## Keine Breaking Changes
- Ghost-Overlay ist rein visuell (keine Änderung an Drag&Drop-Logik)
- Icon-Approach ist backward-kompatibel (Tab-Text bleibt identisch)
