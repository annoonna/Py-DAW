# CHANGELOG v0.0.20.612 — Dual-Clock Architektur: Phase A + B + C Vorbau

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Typ:** Architektur-Vorbau (rein additiv, kein Verhaltenswechsel)
**Design-Referenz:** DUAL_CLOCK_CLIP_LAUNCHER_ARRANGER_DESIGN.md

---

## Überblick

Implementierung der ersten drei Phasen der Dual-Clock-Architektur zur
Entkopplung von Clip-Launcher-Looping und Arranger-Timeline. Alle Änderungen
sind **rein additiv** — bestehende Pfade laufen weiterhin exakt wie vorher.

Feature-Flag `editor_dual_clock_enabled` ist **False** als Default.

---

## Phase A: Neue Datenobjekte (editor_focus.py)

- **`EditorFocusContext`** (frozen dataclass) — Beschreibt vollständig was
  editiert wird und in welchem Kontext:
  - `source`: "arranger" oder "launcher"
  - `clip_id`, `slot_key`, `scene_index`, `track_id`
  - `arranger_clip_start_beats`, `clip_length_beats`
  - `loop_start_beats`, `loop_end_beats`
  - `pinned_to_slot` (Follow-Action-Schutz)
  - Properties: `is_launcher`, `is_arranger`, `loop_span`

- **`LauncherSlotRuntimeState`** (dataclass) — GUI-sicherer Snapshot des
  aktiven Playback-Zustands eines Slots:
  - `slot_key`, `clip_id`, `is_playing`, `is_queued`
  - `voice_start_beat`, `local_beat`
  - `loop_start_beats`, `loop_end_beats`, `loop_count`
  - `track_id`
  - Methode: `compute_local_beat(global_beat)` — die zentrale Formel:
    `local = loop_start + (global_beat - voice_start_beat) % loop_span`

## Phase B: Runtime-Snapshot-Bridge (cliplauncher_playback.py)

- **`get_runtime_snapshot(slot_key)`** — Erzeugt unter Lock einen
  `LauncherSlotRuntimeState` aus der aktiven `_Voice`. Berechnet
  `local_beat` und `loop_count` aus dem aktuellen Transport-Beat.
  Keine Qt-Signale aus dem Audio-Thread.

- **`get_all_runtime_snapshots()`** — Erzeugt Snapshots für alle
  aktiven Voices (für spätere Multi-Slot-Anzeige).

## Phase C Vorbau: EditorTimelineAdapter (editor_timeline_adapter.py)

- **`EditorTimelineAdapter`** (QObject) — Zentrale Zeitumrechnung:
  - `playhead_changed(float)` Signal — lokaler Beat für Editoren
  - `focus_changed(EditorFocusContext)` Signal
  - `set_focus(ctx)` — Startet/Stoppt Snapshot-Polling je nach Fokus
  - Feature-Flag: `editor_dual_clock_enabled = False`
  - Umrechnungslogik:
    - Arranger: `local = global_beat - clip.start_beats`
    - Launcher (Slot spielt): `local = snap.compute_local_beat(global_beat)`
    - Launcher (Slot gestoppt): letzte Position beibehalten
  - 30 Hz Snapshot-Polling-Timer (nur bei Launcher-Fokus aktiv)

## ClipContextService Erweiterung (clip_context_service.py)

- **`editor_focus_changed`** Signal (object) — Neues Signal für
  reicheren Kontext (parallel zu bestehendem `active_slot_changed`)
- **`set_editor_focus(ctx)`** — Setzt und broadcastet EditorFocusContext
- **`get_editor_focus()`** — Getter
- **`build_arranger_focus(clip_id)`** — Factory für Arranger-Kontext
- **`build_launcher_focus(clip_id, slot_key, scene_index, track_id)`**
  — Factory für Launcher-Kontext

## ServiceContainer Erweiterung (container.py)

- **`editor_timeline`** Feld (Optional) — EditorTimelineAdapter
- Erstellung in `create_default()` mit Wiring:
  `clip_context.editor_focus_changed → editor_timeline.set_focus`
- Sauberes Shutdown in `shutdown()`

## Phase D: Clip Launcher + Arranger senden echten Fokus

- **`ClipLauncherPanel._emit_launcher_focus(slot_key, clip_id)`** —
  Neue Helper-Methode baut `EditorFocusContext` via
  `clip_context.build_launcher_focus()` und sendet ihn via
  `clip_context.set_editor_focus()`. Aufgerufen bei:
  - Slot-Klick (Selektion)
  - `_launch()` (Play-Button)

- **`MainWindow._on_clip_activated(clip_id)`** erweitert —
  Baut automatisch `EditorFocusContext` via `build_arranger_focus()`
  wenn der Fokus nicht bereits vom Launcher gesetzt wurde.
  Prüft: `existing.is_launcher and existing.clip_id == clip_id` →
  überspringt, damit Launcher-Fokus nicht von Arranger-Fokus
  überschrieben wird.

---

## Sicherheit

- ✅ **Kein Editor-Rendering geändert** (PianoRoll, Notation, AudioEditor Playhead-Zeichnung identisch)
- ✅ **Kein Audio-Thread-Code geändert** (nur Snapshot unter Lock)
- ✅ **Kein bestehendes Signal umverdrahtet**
- ✅ **Feature-Flag Default: False** — alte Pfade 1:1 aktiv
- ✅ **Syntax-Check bestanden** (alle 7 Dateien)
- ✅ **Logik-Tests bestanden** (EditorFocusContext, compute_local_beat)
- ✅ **Oberste Direktive eingehalten: Nichts kaputt gemacht**

---

## Geänderte Dateien

| Datei | Typ | Zeilen |
|---|---|---|
| `pydaw/services/editor_focus.py` | NEU | ~120 |
| `pydaw/services/editor_timeline_adapter.py` | NEU | ~180 |
| `pydaw/services/clip_context_service.py` | ERWEITERT | +~110 |
| `pydaw/services/cliplauncher_playback.py` | ERWEITERT | +~65 |
| `pydaw/services/container.py` | ERWEITERT | +~15 |
| `pydaw/ui/clip_launcher.py` | ERWEITERT | +~35 |
| `pydaw/ui/main_window.py` | ERWEITERT | +~12 |

---

## Nächste sichere Schritte (Phase D–F)

- [ ] AVAILABLE: **Phase D: Clip Launcher sendet echten Fokus** —
  `_slot_clicked()` / `_launch()` sollen `build_launcher_focus()` aufrufen
  und `set_editor_focus()` statt nur `clip_activated`.
- [ ] AVAILABLE: **Phase C live: Piano Roll hinter Adapter** —
  `editor_dual_clock_enabled = True` setzen, PianoRoll auf
  `editor_timeline.playhead_changed` umhängen (Feature-Flag).
- [ ] AVAILABLE: **Phase E: Audio Editor + Notation nachziehen** —
  Gleiche Adapter-Logik in allen Editoren.
- [ ] AVAILABLE: **Phase F: Alte Direktverdrahtung abbauen** —
  Erst wenn C–E stabil sind.
