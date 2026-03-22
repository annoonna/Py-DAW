# 📝 SESSION LOG: 2026-03-16 — v0.0.20.515

**Entwickler:** Claude Opus 4.6
**Zeit:** 2026-03-16
**Task:** SmartDrop: Erster ECHTER atomarer Live-Pfad fuer leere Audio-Spur

## ZUSAMMENFASSUNG

Dies ist der **ERSTE ECHT MUTIERENDE SmartDrop-Pfad** in der gesamten Projektgeschichte.
Bisher war der gesamte Audio→Instrument-Morphing-Guard rein read-only (Preview/Validate/Plan).
Jetzt kann eine **leere Audio-Spur** erstmals atomar in eine **Instrument-Spur** umgewandelt werden.

## 3 ETAPPEN (alle in einem Rutsch)

### Etappe 1: Shadow-Commit-Rehearsal
- Neue Funktion `_build_shadow_commit_rehearsal()` in `smartdrop_morph_guard.py`
- Simuliert den kompletten Undo-Zyklus komplett read-only:
  1. Deep-Copy des Projekts
  2. track.kind-Aenderung auf der Kopie
  3. ProjectSnapshotEditCommand konstruieren
  4. do() gegen lokalen Recorder ausfuehren
  5. undo() gegen lokalen Recorder ausfuehren
  6. Round-Trip-Verifikation (before hat kind=audio, after hat kind=instrument)
- Beruehrt das Live-Projekt NIE

### Etappe 2: Erster atomarer Live-Pfad (Minimalfall)
- `build_audio_to_instrument_morph_plan()` setzt jetzt `can_apply=True` wenn:
  - track_kind == "audio"
  - Keine Audio-Clips, MIDI-Clips, FX, Note-FX
  - Shadow-Rehearsal bestanden
- `apply_audio_to_instrument_morph_plan()` fuehrt die echte Mutation durch:
  1. Before-Snapshot erfassen
  2. Auto-Undo unterdruecken (suppress_depth)
  3. `set_track_kind(track_id, "instrument")`
  4. After-Snapshot erfassen
  5. ProjectSnapshotEditCommand auf Undo-Stack pushen
  6. Auto-Undo-Baseline synchronisieren
  7. Bei JEDEM Fehler: sofortiger Rollback per Snapshot-Restore

### Etappe 3: Harte Absicherung
- Guard blockiert weiterhin ALLE nicht-leeren Audio-Spuren
- Undo/Redo funktioniert: Ctrl+Z stellt den Audio-Spur-Zustand wieder her
- Save/Reload geht ueber das bestehende Snapshot-System
- UI-Refresh: Arranger, Mixer, DevicePanel werden nach Morph aktualisiert
- MainWindow fuegt nach erfolgreichem Morph das Instrument via bestehende Pfade ein

## SICHERHEITSGARANTIEN
- Leere Audio-Spur: NUR track.kind wird geaendert (kein Routing, keine Clips)
- Nicht-leere Spuren: komplett BLOCKIERT (can_apply=False)
- Undo: Kompletter Projekt-Snapshot als ein Undo-Punkt
- Rollback: Bei jedem Fehler sofort per Snapshot-Restore
- Shadow-Rehearsal: Beweis dass do()/undo() funktionieren BEVOR die echte Mutation startet

## GEAENDERTE DATEIEN
- `pydaw/services/smartdrop_morph_guard.py` (+~170 Zeilen)
  - `_build_shadow_commit_rehearsal()` NEU
  - `_build_shadow_commit_rehearsal_summary()` NEU
  - `_build_apply_readiness_checks()` erweitert (shadow_commit_rehearsal Parameter)
  - `build_audio_to_instrument_morph_plan()` erweitert (can_apply/apply_mode Logik)
  - `validate_audio_to_instrument_morph_plan()` geaendert (bewahrt can_apply)
  - `apply_audio_to_instrument_morph_plan()` KOMPLETT NEU (echte Mutation)
- `pydaw/ui/main_window.py`
  - `_on_arranger_smartdrop_instrument_morph_guard()` erweitert (Instrument-Insert nach Morph)

## NICHTS KAPUTT GEMACHT
- Alle bestehenden SmartDrop-Pfade (neue Spur, bestehende Instrument-Spur, FX-Drop) unberuehrt
- Guard-Dialog fuer nicht-leere Spuren unveraendert
- Alle bestehenden Readiness-Checks beibehalten
- project_service.py unveraendert (nutzt bestehende set_track_kind + Undo-Infrastruktur)
