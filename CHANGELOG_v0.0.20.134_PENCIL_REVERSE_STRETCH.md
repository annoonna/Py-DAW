# CHANGELOG v0.0.20.134 — Pencil Tool, Reverse Fix, Stretch Display

## 🎯 Drei kritische Features

### 1. Pencil-Tool für Clip-Automation (NEU)
- **Pencil-Werkzeug** im Audio-Editor → Automationslinien direkt auf den Clip zeichnen
- **Parameter-Auswahl**: Gain / Pan / Pitch / Formant (Dropdown neben Werkzeug)
- **Klick** = Breakpoint setzen, **Ziehen** = kontinuierlich zeichnen (Grid-Snap)
- **Rechtsklick** im Pencil-Modus = Breakpoint löschen
- **Farbcodierung**: Gain=Grün, Pan=Gelb, Pitch=Blau, Formant=Magenta
- **Breakpoint-Dots** + verbindende Linien (Z-Order über Waveform)
- Kontextmenü: Clear Gain/Pan/Pitch/All Clip Automation
- **Model**: `clip_automation` Dict im Clip-Dataclass (rückwärtskompatibel)
- **Service**: add_clip_automation_point(), remove_clip_automation_point(), clear_clip_automation()

### 2. Reverse Fix — Arranger + Playback (BUGFIX)
- **Arranger**: Waveform wird jetzt tatsächlich umgedreht angezeigt (data[::-1])
- **Arranger**: Oranger Tint-Overlay bei reversed Clips (wie Bitwig)
- **Audio Engine**: `data = data[::-1].copy()` in prepare_clips() wenn clip.reversed=True
- **Vorher**: Reverse war nur im Model, aber weder visuell noch akustisch wirksam

### 3. Stretch Display im Arranger
- Stretch-Faktor wird jetzt im Clip-Label angezeigt: "×1.50" etc.
- Stretch-Wert im Pixmap-Cache-Key (invalidiertcCache bei Änderung)
- Time-Stretch Engine war bereits vorhanden (phase vocoder + Essentia)

## Dateien geändert
- `pydaw/model/project.py`: +clip_automation Feld, Version 134
- `pydaw/services/project_service.py`: +3 Methoden (clip automation CRUD)
- `pydaw/ui/audio_editor/audio_event_editor.py`: +Pencil tool, +automation rendering, +signals
- `pydaw/audio/arrangement_renderer.py`: +Reverse audio data flip
- `pydaw/ui/arranger_canvas.py`: +Reverse waveform flip, +reverse tint, +stretch label
- `pydaw/version.py`, `VERSION`: 0.0.20.133 → 0.0.20.134

## Kompatibilität
- 100% rückwärtskompatibel (clip_automation defaults to {})
- Keine bestehende Funktionalität verändert
