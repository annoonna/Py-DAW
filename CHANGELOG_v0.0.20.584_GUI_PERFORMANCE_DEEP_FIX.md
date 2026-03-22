# CHANGELOG v0.0.20.584 — GUI Performance Deep-Fix

**Datum:** 2026-03-18
**Entwickler:** Claude Opus 4.6
**Typ:** CRITICAL PERFORMANCE FIX
**Oberste Direktive:** Nichts kaputt machen ✅

## Problem
- GUI/UI hängt, Sound stottert
- Mausbewegung "hilft" temporär (pumpt Qt Event-Loop)
- Seit Fusion-Integration (v577+) verschlimmert

## Root Cause Analysis (5 Engpässe identifiziert, 4 gefixt)

### Ursache 1 — Signal-Kaskade (KRITISCHSTER FUND)
`FusionWidget._persist_instrument_state()` rief `project_updated.emit()` auf,
was **15+ UI-Panels** zum vollständigen Refresh zwang — bei JEDEM Knob-Dreh.
Kein anderes Plugin tat das.

### Ursache 2 — VU-Timer-Explosion
Jeder `_MixerStrip` hatte eigenen `QTimer(33ms)`. Bei 10 Tracks = 300
Callbacks/s, bei 20 = 600/s. Timer liefen auch bei unsichtbarem Mixer.

### Ursache 3 — 60fps-Timer-Überlast
Transport (16ms) + GL-Overlay (16ms) + diverse FX-Widgets = 120-180+
Timer-Callbacks/s nur für UI-Updates.

### Ursache 4 — Arranger Hover ohne Throttle
`mouseMoveEvent` rief `_clip_at_pos()` ZWEIMAL pro Pixel-Bewegung auf,
iterierte jedes Mal ALLE Clips. Bei 50 Clips = hunderte Iterationen/s.

### Ursache 5 — FusionEngine Lock-Contention (nicht gefixt, bereits v577-optimiert)
Bereits durch v577 Lock-Free-Pull erheblich verbessert. Verbleibendes
`_voice_params_dirty` Sync könnte granularer werden (Future Fix).

## Fixes (4 Dateien, 5 Änderungen)

### Fix 1: Signal-Kaskade eliminiert
**Datei:** `pydaw/plugins/fusion/fusion_widget.py`
- `_persist_instrument_state()` schreibt nur noch `trk.instrument_state`
- Kein `ps._emit_updated()` mehr → keine 15-Panel-Refresh-Kaskade
- Instrument-State ist im Track-Objekt gespeichert, UI braucht kein globales Refresh

### Fix 2: Zentraler VU-Meter-Timer
**Datei:** `pydaw/ui/mixer.py`
- Per-Strip `QTimer(33ms)` entfernt
- Ein einziger `QTimer` in `MixerPanel._tick_all_vu_meters()` iteriert alle Strips
- Timer stoppt bei `hideEvent()`, startet bei `showEvent()`
- Reduktion: N×30fps → 1×30fps

### Fix 3: Transport + GL-Overlay 60fps → 30fps
**Dateien:** `pydaw/services/transport_service.py`, `pydaw/ui/arranger_gl_overlay.py`
- Playhead-Timer: 16ms → 33ms (visuell identisch)
- GL-Overlay sync: 16ms → 33ms
- ~60 weniger Timer-Callbacks/Sekunde

### Fix 4: Arranger Hover-Throttling
**Datei:** `pydaw/ui/arranger_canvas.py`
- Zwei `_clip_at_pos()` Aufrufe zu einem verschmolzen
- 50ms Throttle auf Hover-Detection (max 20fps statt unbegrenzt)
- Clip-Iteration: ~1000/s → ~20/s

## Erwartete Wirkung
- **Timer-Callbacks/s:** ~400-600 → ~60-90 (85% Reduktion)
- **Panel-Refreshes pro Knob-Dreh:** 15+ → 0 (100% Reduktion)
- **Arranger Hover-Iterationen/s:** ~1000 → ~20 (98% Reduktion)
- GUI-Thread hat wieder genug Headroom für Audio-Callback-Scheduling
- "Mausbewegung hilft" Symptom sollte verschwinden

## Nicht angefasst (Oberste Direktive)
- Keine Änderung an Audio-Engine, Hybrid-Engine, DSP-Pfad
- Keine Änderung an Bach Orgel, AETERNA oder anderen Instrumenten
- Keine Änderung an MIDI-Learn, Automation, Project-Save
- Keine Änderung an Arranger Drag/Resize/Paint-Logik
- Fusion-Engine (pull/render) unverändert
