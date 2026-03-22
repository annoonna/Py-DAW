# Changelog v0.0.20.158 — Audio Editor: Playhead Sync + Loop Draw + Lupe/Zoom + Zeiger=Select

## Ziel (User-Feedback)
Im Audio Editor fehlten trotz früherer Parity-Patches weiterhin die erwarteten DAW-Standards:
- **Keine rote Playhead-Linie** im Audio Editor während Playback
- **Loop-Region ließ sich nicht "einzeichnen"** (User war im Zeiger-Tool)
- **Keine "Lupe"/Zoom-Geste** wie in Bitwig (Beat-Ruler → Magnifier)
- **Zeiger konnte Audio-Events nicht selektieren/moven** → Copy/Paste/Duplicate fühlte sich "kaputt" an
- **Waveform-Tiling wirkte wie Stretch-to-fit** statt echter Loop-Wiederholung

## Implementiert (UI-safe, keine Breaking Changes)
### 1) Transport → Audio Editor Playhead (rot) läuft jetzt wirklich
- AudioEventEditor verbindet sich jetzt an `transport.playhead_changed`.
- Playhead wird **lokal im Clip** berechnet (Wrap nach Clip-Loop), damit die Linie im Editor korrekt läuft.
- Nach jedem `refresh()` wird die Playhead-Linie erneut angelegt (Scene rebuild safe).

### 2) Loop "einzeichnen" ohne Tool-Wechsel (Bitwig/Ableton Workflow)
- **Alt+Drag im Editor** setzt/zieht die Clip-Loop-Region direkt (auch im Zeiger).
- **Alt+Drag im Ruler** setzt die Loop-Region ebenfalls.
- Tool-Auswahl wurde klarer: **"Loop"** statt "Time" (intern weiterhin TIMESELECT).

### 3) "Lupe" / Zoom wie Bitwig
- Neues Tool: **Lupe** (ZOOM) im Tool-Dropdown.
  - Click+Drag **hoch/runter** zoomt horizontal (AnchorUnderMouse).
- Zusätzlich: Beat-Ruler unterstützt **Bitwig-Geste** (Drag vertikal = Zoom).

### 4) Zeiger verhält sich wie DAW-Pointer (Selektieren/Move von Audio-Events)
- EventBlockItems akzeptieren jetzt **ARROW oder POINTER**.
- Dadurch funktionieren im Zeiger-Tool auch:
  - Selektieren
  - Drag-Move
  - **Alt-Drag Duplicate**
  - Ctrl+C/V/D Workflows (Copy/Paste/Duplicate)

### 5) Waveform-Tiling korrekt: Beat→Zeit→Samples (kein Stretch-to-fit)
- Waveform-Mapping wurde auf **Beat→Sekunden→Samples** umgestellt:
  - nutzt Projekt-BPM + Clip `offset_seconds` + `stretch`
  - Loop-Region wrappt im Beat-Domain und zeigt echte Wiederholung

## Geänderte Dateien
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/services/transport_service.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`

