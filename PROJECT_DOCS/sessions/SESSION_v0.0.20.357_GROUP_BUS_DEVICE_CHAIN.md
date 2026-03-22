# Session-Log: v0.0.20.357 — Echter Group-Bus mit eigener Device-Chain

**Datum**: 2026-03-08
**Bearbeiter**: Claude Opus 4.6
**Aufgabe**: Echte Gruppenspur mit eigener Device-Chain implementieren (Bitwig-Style)
**Ausgangsversion**: 0.0.20.356
**Ergebnisversion**: 0.0.20.357

## Problem-Beschreibung
Effects die auf eine Gruppe gelegt werden sollen, landeten immer auf der kick-Spur,
weil die Gruppierung bisher rein organisatorisch war — es gab keinen echten Group-Track
mit eigener Device-Chain im Datenmodell.

## Architektur-Entscheidungen

### Warum ein echter Track mit kind="group"?
- Das Track-Datenmodell hat bereits `audio_fx_chain` — keine Schema-Änderung nötig
- build_track_fx_map() kompiliert FX-Chains für ALLE Tracks → Group-FX funktioniert automatisch
- DevicePanel zeigt die Chain für den ausgewählten Track → funktioniert automatisch
- TrackParamState hat Vol/Pan/Mute/Solo für alle track_idx → Group-Fader funktioniert automatisch

### Signal-Flow im Audio-Callback
1. Arrangment-Rendering: Kind-Clips gerendert → Kind-FX → Kind-Vol/Pan → Group-Buffer
2. Pull-Sources (Sampler): Kind-Audio → Kind-FX → Kind-Vol/Pan → Group-Buffer  
3. Group-Bus: Group-FX → Group-Vol/Pan → Group-Metering → Master-Mix
4. Master: Master-FX → Master-Vol/Pan → Output

### Rückwärtskompatibilität
- Alte Gruppen (`tgrp_` IDs) haben keinen Group-Track → kein Routing → Audio unverändert
- Neue Gruppen → echte Group-Tracks → Routing aktiv
- Migration: Ungroup + Re-Group

## Geänderte Dateien (8 Dateien)

### project_service.py + altproject_service.py
- `group_tracks()`: Erstellt Track(kind="group") vor den Kindspuren
- `ungroup_tracks()`: Entfernt den Group-Track wenn leer

### hybrid_engine.py
- Neue Slots: `_group_bus_map`, `_group_track_idxs`, `_group_bus_id_map`
- `set_group_bus_map()`: Atomares Update der Routing-Maps
- Rendering-Loop: Zwei-Pass-Algorithmus (1. Kinder→Group-Buffer, 2. Group→Master)
- Pull-Sources: Selbe Routing-Logik für Sampler/Drum/SF2

### audio_engine.py
- `rebuild_fx_maps()`: Berechnet Group-Bus-Mapping aus Projektdaten

### arranger.py
- `_on_sel()`: Group-Header → Group-Track-ID emittieren
- `selected_track_id()`: Gibt Group-Track-ID für Header zurück
- `refresh()`: Tracks mit kind="group" überspringen
- `_group_members()`: Group-Track aus Member-Liste ausschließen

### arranger_canvas.py
- `_lane_entries()`: Tracks mit kind="group" überspringen

## Tests
- ✅ Syntax-Check aller 8 geänderten Dateien bestanden
- ✅ Alte Projekte ohne Group-Tracks: Kein Routing (safe)
- ✅ Neues Grouping: Group-Track erstellt, Kind-Zuordnung korrekt
- ✅ Audio-Callback: Lock-free, exception-safe, zero-alloc

## Nächste Schritte
- [ ] Group-Fader im Mixer-View anzeigen
- [ ] Group-Track im Mixer als Bus-Kanal visualisieren
- [ ] Group Mute/Solo Verhalten (Bitwig: Group-Mute stummschaltet alle Kinder)
