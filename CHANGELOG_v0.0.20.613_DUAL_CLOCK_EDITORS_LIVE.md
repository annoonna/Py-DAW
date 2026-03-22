# CHANGELOG v0.0.20.613 — Dual-Clock Phase C live + Phase E (Alle Editoren auf Adapter)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Typ:** Architektur-Aktivierung (Feature-Flag True, alle 3 Editoren verdrahtet)
**Vorgänger:** v0.0.20.612 (Phase A+B+C Vorbau+D)

---

## Überblick

Das Dual-Clock-System ist jetzt **aktiv**. Alle drei Editoren (Piano Roll,
Notation, Audio Editor) empfangen ihren Playhead über den
`EditorTimelineAdapter` statt direkt vom `TransportService`.

**Sicherheitsgarantie:** Im Arranger-Modus ist der Adapter ein reiner
Passthrough — der globale Beat wird 1:1 durchgereicht. Die Editoren
subtrahieren intern weiterhin `clip_start_beats`. Verhalten identisch.

Im Launcher-Modus berechnet der Adapter jetzt den lokalen Slot-Beat
über `LauncherSlotRuntimeState.compute_local_beat()`.

---

## Phase C live: Feature-Flag aktiviert + Adapter-Fix

- **`editor_dual_clock_enabled = True`** — Dual-Clock jetzt aktiv
- **Arranger-Modus = Passthrough** — `_compute_local_beat()` gibt
  `global_beat` unverändert zurück (keine doppelte Subtraktion, da
  PianoRollCanvas/AudioEditor/Notation intern bereits `clip_start_beats`
  subtrahieren)
- **PianoRollEditor** akzeptiert `editor_timeline` Parameter —
  wenn vorhanden, wird `editor_timeline.playhead_changed` statt
  `transport.playhead_changed` verbunden. Fallback auf Transport.

## Phase E: Audio Editor + Notation auf Adapter

- **NotationWidget** — `editor_timeline` Parameter, Adapter hat Vorrang
  für `_on_playhead_changed`. Click-to-Seek bleibt beim Transport.
- **AudioEventEditor** — `editor_timeline` Parameter, Adapter hat Vorrang
  für `_on_transport_playhead_changed`. `playing_changed` bleibt beim
  Transport (kein Adapter nötig für Play/Stop-Status).
- **EditorTabs** — `editor_timeline` Parameter, reicht ihn an alle drei
  Editoren weiter (PianoRoll, Notation, AudioEditor).
- **MainWindow** — `getattr(services, 'editor_timeline', None)` wird
  an EditorTabs übergeben.

---

## Sicherheitsanalyse

### Warum Arranger-Modus identisch ist:

```
VORHER:  Transport → global_beat → PianoRollCanvas → local = global - clip_start
NACHHER: Transport → Adapter(passthrough) → global_beat → PianoRollCanvas → local = global - clip_start
```

Exakt gleiche Berechnung, nur ein transparenter Zwischenschritt.

### Warum Launcher-Modus jetzt korrekt ist:

```
Launcher-Clip hat start_beats = 0 (immer)
Adapter sendet: local = loop_start + (global - voice_start) % span
PianoRollCanvas: local = adapter_beat - 0 = adapter_beat ✓
```

### Fallback-Sicherheit:

Wenn `editor_timeline` None ist (z.B. Import-Fehler), verbinden sich
alle Editoren direkt mit dem Transport — exakt wie vor v0.0.20.612.

---

## Geänderte Dateien

| Datei | Typ | Änderung |
|---|---|---|
| `pydaw/services/editor_timeline_adapter.py` | GEÄNDERT | Arranger=Passthrough, Flag=True |
| `pydaw/ui/pianoroll_editor.py` | GEÄNDERT | `editor_timeline` Param + Adapter-Wiring |
| `pydaw/ui/notation/notation_view.py` | GEÄNDERT | `editor_timeline` Param + Adapter-Wiring |
| `pydaw/ui/audio_editor/audio_event_editor.py` | GEÄNDERT | `editor_timeline` Param + Adapter-Wiring |
| `pydaw/ui/editor_tabs.py` | GEÄNDERT | `editor_timeline` Param → alle 3 Editoren |
| `pydaw/ui/main_window.py` | GEÄNDERT | `editor_timeline` an EditorTabs |

---

## Nächste Schritte

- [ ] AVAILABLE: **Phase F: Alte Direktverdrahtung entfernen** — Wenn C+E stabil
  getestet sind, können die Fallback-Transport-Connections entfernt werden.
- [ ] AVAILABLE: **AudioEditor._local_playhead_beats Adapter-Integration** —
  Aktuell liest der AudioEditor bei Audio-Clips noch `transport.current_beat`
  direkt. Für volle Launcher-Unterstützung sollte auch dieser Pfad den
  Adapter nutzen.
- [ ] AVAILABLE: **Launcher-Playhead-Anzeige im Slot** — Der Slot-Button
  könnte die lokale Position aus dem Adapter statt eigener Berechnung zeigen.
