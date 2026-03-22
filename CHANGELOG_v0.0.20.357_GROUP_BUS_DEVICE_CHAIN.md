# CHANGELOG v0.0.20.357 — Echter Group-Bus mit eigener Device-Chain (Bitwig-Style)

## Überblick

Tracks können jetzt als echte Gruppenbusse zusammengefasst werden. Die Gruppenspur
hat eine eigene Audio-FX-Chain, durch die das summierte Audio aller Kind-Spuren
fließt, bevor es den Master-Bus erreicht. Genau wie in Bitwig Studio.

**Signal-Flow:**
```
Kick  → Kick FX  → Kick Vol/Pan ─┐
Snare → Snare FX → Snare Vol/Pan ─┤→ Group Bus → Group FX → Group Vol/Pan → Master
HiHat → HiHat FX → HiHat Vol/Pan ─┘
```

## Neu

### Datenmodell
- `group_tracks()` erstellt jetzt einen echten Track mit `kind="group"` und eigener `audio_fx_chain`
- Der Group-Track wird VOR den Kind-Spuren in die Tracklist eingefügt
- `ungroup_tracks()` entfernt den Group-Track wenn keine Kinder mehr übrig sind
- Alte Projekte mit organisatorischen Gruppen (`tgrp_`-IDs) funktionieren unverändert weiter

### Audio-Engine (hybrid_engine.py)
- Neues Group-Bus-Routing im Audio-Callback:
  1. Kind-Spuren werden gerendert, FX/Vol/Pan angewendet
  2. Statt direkt in den Master zu mischen, fließt das Audio in den Group-Bus-Buffer
  3. Der Group-Bus-Buffer wird durch die Gruppen-FX-Chain verarbeitet
  4. Group-Vol/Pan/Mute/Solo angewendet
  5. Erst dann in den Master gemischt
- Pull-Sources (Sampler/Drum/SF2) werden ebenfalls durch den Group-Bus geroutet
- VU-Metering und Direct-Peaks für den Group-Bus
- `set_group_bus_map()`: Neues API für atomares Routing-Update vom Main-Thread

### Audio-Engine (audio_engine.py)
- `rebuild_fx_maps()` berechnet und pusht das Group-Bus-Mapping an die HybridBridge
- Mapping: child_track_idx → group_track_idx (für Arrangement-Rendering)
- Mapping: child_track_id → group_track_idx (für Pull-Sources/Sampler)

### UI — Arranger
- Klick auf Gruppen-Header wählt jetzt den Group-Track aus
- DevicePanel zeigt die Device-Chain des Group-Tracks (eigene FX!)
- Effects die auf den Group-Header gedroppt werden, landen auf der Gruppen-FX-Chain
- Group-Tracks werden NICHT als eigene Track-Zeile angezeigt
- `_group_members()` schließt den Group-Track selbst aus der Member-Liste aus

## Geänderte Dateien
- `pydaw/services/project_service.py` — group_tracks/ungroup_tracks
- `pydaw/services/altproject_service.py` — group_tracks/ungroup_tracks (konsistent)
- `pydaw/audio/hybrid_engine.py` — Group-Bus-Rendering + Routing
- `pydaw/audio/audio_engine.py` — Group-Bus-Mapping-Berechnung
- `pydaw/ui/arranger.py` — Group-Header-Auswahl + Group-Track-Skip
- `pydaw/ui/arranger_canvas.py` — _lane_entries Group-Track-Skip
- `pydaw/model/project.py` — Default-Version
- `pydaw/version.py` — 0.0.20.357
- `VERSION` — 0.0.20.357

## Sicherheit / Nicht verändert
- Kein Eingriff in das Clip-System oder die Arrangement-Vorbereitung
- Kein Eingriff in MIDI-Routing, Note-FX oder Sampler-Dispatch
- Kein Eingriff in das Projektformat (Track-Dataclass bleibt unverändert)
- Master-FX-Chain wird weiterhin NACH dem Group-Bus angewendet (korrekte Hierarchie)
- Alte Projekte ohne Group-Tracks → exakt gleiches Audio-Verhalten wie vorher
- Audio-Callback: Alle Operationen sind lock-free und exception-safe

## Rückwärtskompatibilität
- Projekte mit alten `tgrp_`-Gruppen: Audio-Engine erkennt keine group_bus_map → kein Routing
- Neue Gruppen: Echte Group-Tracks → Group-Bus-Routing aktiv
- Migration: Bestehende Gruppen ungroupen (Ctrl+Shift+G) und neu groupen (Ctrl+G)
