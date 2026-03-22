# CHANGELOG v0.0.20.160 — Lasso-Selektion + Per-Event Reverse + Ctrl+J

**Datum:** 2026-02-28  
**Assignee:** Claude Opus 4.6 (Anthropic)  
**Priority:** 🔴 CRITICAL (User-Report: Reverse dreht alle Events, Lasso fehlt)  
**Status:** ✅ FERTIG  

---

## User-Report (Screenshots)

1. **Lasso fehlt:** Keine Möglichkeit, mehrere Audio-Events per Rubber-Band auszuwählen.
2. **Reverse Bug:** Wenn EIN Sample reversed wird, werden ALLE Events im Clip reversed.
3. **"Nur den ersten hören":** Gain/Pan/Pitch-Automation (Pencil) hat keinen Effekt auf Playback.

---

## Root-Cause-Analyse

### Bug 1: Reverse dreht ALLE Events
- **Ursache:** `Reverse` im Context-Menü setzte `clip.reversed` — ein **Clip-Level** Property.
- `AudioEvent` hatte kein eigenes `reversed`-Feld.
- **Fix:** Per-event `reversed` Attribut + Context-Menü toggelt nur selektierte Events.

### Bug 2: "Nur den ersten hören" bei Pitch/Gain/Pan
- **Ursache:** Die Pencil-Tool Automation (`clip.clip_automation`) wird im `ClipLauncherPlaybackService._mix_events_segment()` **nicht ausgelesen** — nur der statische Clip-Level Wert `v.pitch`.
- **Analyse:** Das ist ein **bekanntes TODO** — Clip-Automation-Playback fehlt noch. Gain/Pitch/Pan wirken Clip-weit auf ALLE Events gleichzeitig (korrekt für Clip-Level, aber User erwartet per-Event).
- **Status:** Dokumentiert als nächster Task.

---

## Implementiert (safe, nichts kaputt)

### 1. Lasso / Rubber-Band Selektion (Zeiger-Tool)
- **Was:** `QGraphicsView.DragMode.RubberBandDrag` für ARROW/POINTER/ZEIGER Tools.
- **Verhalten:** Klick auf leeren Bereich + Ziehen → Rubber-Band-Rechteck → alle EventBlockItems darin werden selektiert.
- **Ctrl+Click:** Weiterhin zum Hinzufügen zur Selektion.
- **Dateien:** `audio_event_editor.py` (WaveformCanvasView.set_tool)

### 2. Per-Event Reverse
- **Model:** `AudioEvent.reversed: bool = False` hinzugefügt (rückwärtskompatibel).
- **Context-Menü:** `Reverse` toggelt jetzt pro selektiertem Event (oder alle wenn keine Selektion).
- **Visual:** Orange Tint-Overlay pro reversed Event (als Child-Item am EventBlock).
- **Waveform:** Per-event reversed wird beim Waveform-Rendering berücksichtigt (XOR mit Clip-Level).
- **Playback:** `ClipLauncherPlaybackService._mix_events_segment()` dreht den Audio-Chunk per Event um.
- **Serialisierung:** Automatisch via `dataclasses.asdict()` / `AudioEvent(**dict)`.
- **Dateien:** `project.py`, `audio_event_editor.py`, `cliplauncher_playback.py`

### 3. Ctrl+J Shortcut (Consolidate / Zusammenführen)
- **Was:** Keyboard-Shortcut `Ctrl+J` ruft `consolidate_audio_events()` auf.
- **Vorher:** Nur über Context-Menü erreichbar.
- **Status-Bar:** Hilfetext um "Ctrl+J: Zusammenführen" erweitert.
- **Dateien:** `audio_event_editor.py` (handle_key_event)

### 4. Copy/Paste erhält per-event reversed
- Template-Kopie (`_collect_selected_event_templates`) enthält jetzt `reversed`-Feld.

---

## Dateien (GEÄNDERT)

| Datei | Änderung |
|-------|----------|
| `pydaw/model/project.py` | `AudioEvent.reversed: bool = False` |
| `pydaw/ui/audio_editor/audio_event_editor.py` | Lasso, Per-Event Reverse, Ctrl+J, Visual Tint, Templates |
| `pydaw/services/cliplauncher_playback.py` | Per-event reverse im Audio-Rendering |
| `VERSION` | 0.0.20.160 |
| `pydaw/version.py` | 0.0.20.160 |

---

## NICHT geändert (Nichts kaputt gemacht)
- ✅ Clip-Level `reversed` bleibt bestehen (Arrangement-Renderer nutzt es weiterhin)
- ✅ Alle bestehenden Shortcuts funktionieren weiterhin
- ✅ Context-Menü-Struktur unverändert
- ✅ Event-Drag/Move unverändert
- ✅ Serialisierung rückwärtskompatibel (alte Projekte ohne `reversed`-Feld → default False)

---

## Nächste Tasks (TODO)

- [ ] **Clip-Automation Playback:** `clip.clip_automation` im `_mix_events_segment()` auswerten (Pitch/Gain/Pan Envelope)
- [ ] **Per-Event Gain/Pan/Pitch:** Optional pro AudioEvent statt nur Clip-Level
- [ ] **Arrangement Renderer:** Per-event reverse auch für Arranger-Playback
