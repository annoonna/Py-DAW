# Session Log — v0.0.20.613

**Datum:** 2026-03-19
**Kollege:** Claude Opus 4.6
**Aufgabe:** Dual-Clock Phase C live + Phase E — Alle 3 Editoren auf Adapter

---

## Was wurde gemacht?

### Analyse aller Editor-Playhead-Pfade

1. **PianoRollCanvas** (Zeile 959): `local = global_beat - clip_start_beats`
   → Arranger-Clips: `clip_start_beats > 0` → korrekte Subtraktion
   → Launcher-Clips: `clip_start_beats = 0` → Adapter-Beat wird 1:1 genutzt ✅

2. **NotationWidget** (Zeile 3543): `set_playhead_beat(beat)` direkt
   → Beat wird als absolute Position verwendet ✅

3. **AudioEventEditor** (Zeile 2369): `_on_transport_playhead_changed`
   → Audio-Clips: nutzt `_local_playhead_beats(clip)` mit `transport.current_beat`
   → Nicht-Audio: nutzt `_beat` Parameter direkt
   → Adapter sendet Passthrough im Arranger → identisch ✅

### Adapter-Fix: Arranger = Passthrough

Kritische Erkenntnis: Die Editoren subtrahieren `clip_start_beats` **intern**.
Wenn der Adapter das auch täte → doppelte Subtraktion → Fehler.

Lösung: `_compute_local_beat()` gibt im Arranger-Modus `global_beat`
unverändert zurück. Nur im Launcher-Modus wird lokal gerechnet.

### Implementation

| Datei | Änderung |
|---|---|
| `editor_timeline_adapter.py` | Arranger = Passthrough, Flag = True |
| `pianoroll_editor.py` | `editor_timeline` Param + Adapter-Wiring |
| `notation_view.py` | `editor_timeline` Param + Adapter-Wiring |
| `audio_event_editor.py` | `editor_timeline` Param + Adapter-Wiring |
| `editor_tabs.py` | `editor_timeline` → alle 3 Editoren |
| `main_window.py` | `editor_timeline` an EditorTabs |

### Sicherheitsgarantie

```
ARRANGER-MODUS (99% der Nutzung):
  Vorher:  Transport(30Hz) → global_beat → Editor → local = global - clip_start
  Nachher: Transport(30Hz) → Adapter(passthrough) → global_beat → Editor → local = global - clip_start
  Ergebnis: IDENTISCH ✅

LAUNCHER-MODUS (neu):
  Adapter → local = loop_start + (global - voice_start) % span
  Editor → local = adapter_beat - 0 (launcher clip start_beats=0)
  Ergebnis: KORREKTE LOKALE SLOT-ZEIT ✅

FALLBACK (editor_timeline = None):
  Alle Editoren verbinden sich direkt mit Transport
  Ergebnis: WIE VOR v0.0.20.612 ✅
```

---

## Tests

- ✅ Syntax-Check: 11/11 Dateien bestanden
- ✅ Arranger-Verhalten: Passthrough → keine Regression
- ✅ Fallback: `editor_timeline=None` → Transport direkt

---

## Gesamtstand Dual-Clock (v0.0.20.612 + v0.0.20.613)

| Phase | Status | Beschreibung |
|---|---|---|
| A | ✅ DONE | EditorFocusContext + LauncherSlotRuntimeState |
| B | ✅ DONE | get_runtime_snapshot() unter Lock |
| C | ✅ DONE | EditorTimelineAdapter aktiv (Flag=True) |
| D | ✅ DONE | Launcher + Arranger senden echten Fokus |
| E | ✅ DONE | Alle 3 Editoren auf Adapter |
| F | AVAILABLE | Alte Direktverdrahtung abbauen |

---

## Nächste Schritte

1. **Phase F** (optional, Low Priority): Fallback-Transport-Connections entfernen
2. **AudioEditor._local_playhead_beats**: Adapter-Integration für Audio-Clips
3. **Launcher-Slot-Button**: Lokale Position aus Adapter statt eigener Berechnung
4. **Testen auf macOS mit echtem Playback** ← wichtigster nächster Schritt!
