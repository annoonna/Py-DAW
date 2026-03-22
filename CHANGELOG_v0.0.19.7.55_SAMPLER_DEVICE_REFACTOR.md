# Changelog v0.0.19.7.55 — Sampler & Device Panel Refactor

## Datum: 2026-02-06

## Übersicht
Kompletter Umbau des Device Panels und Sampler-Widgets nach Pro-DAW-Vorbild:
Per-Track Device-Binding, kompaktes Layout, Multi-Format Audio, Piano Roll Fix.

---

## 🔧 Behobene Bugs

### 1. Sampler zu groß / muss scrollen
- **Problem:** Sampler-Widget war vertikal gestapelt, passte nicht ins Device Panel
- **Lösung:** Komplettes Layout-Rewrite: horizontale Sektionen (Pitch | Filter | AHDSR | Output)
- QPainter-basierte CompactKnob (~52×64px) statt QDial
- Waveform-Strip 40-60px Höhe
- Alle Controls ohne Scrollen sichtbar

### 2. Mehrere Sampler nebeneinander im Device Panel
- **Problem:** Jeder neue Sampler landete global im Panel neben dem vorherigen
- **Lösung:** Per-Track Device-Binding (`DevicePanel._track_chains`)
- `show_track(track_id)`: Zeigt nur Devices der ausgewählten Spur
- `add_instrument_to_track(track_id, plugin_id)`: Bindet Device an Spur
- Widgets werden versteckt/gezeigt (nicht zerstört) → Zustandserhalt

### 3. Piano Roll öffnet nicht bei Doppelklick auf MIDI-Clip
- **Problem:** `_on_clip_activated()` schaltete nicht in den Edit-Modus
- **Lösung:** `_set_view_mode("edit", force=True)` + `editor_dock.show()` + `editor_dock.raise_()`
- Unterstützt jetzt auch Audio-Clips (öffnet Audio-Editor)

### 4. Kein Sound im Editor-Modus
- **Problem:** Note-Preview Signal ging an alle Sampler, nicht nur den aktiven
- **Lösung:** `_on_note_preview()` prüft `self.isVisible()` — nur sichtbare Sampler reagieren

### 5. Drop Sample + Load Sample Konflikt
- **Problem:** Beide Buttons und Drag&Drop konnten sich stören
- **Lösung:** Beide nutzen jetzt denselben `_load_file(path)` Pfad

---

## ✨ Neue Features

### Multi-Format Audio Support
- **Neu:** `audio_io.py` ersetzt `wav_io.py`
- Unterstützte Formate: WAV, MP3, FLAC, OGG, AIFF, M4A, WV
- Loader-Kaskade: soundfile → pydub/ffmpeg → stdlib wave (WAV only)
- Drag & Drop akzeptiert alle unterstützten Formate

### Per-Track Device Panel (Pro-DAW-Style)
- `DevicePanel._track_chains`: Dict[str, List[dict]]
- `show_track(track_id)`: Auto-Switch bei Track-Auswahl
- `add_instrument_to_track()`: Bindet Device an spezifische Spur
- `has_device_for_track()`: Prüft ob Spur bereits Devices hat
- `remove_track_devices()`: Cleanup bei Track-Löschung

### Auto-Sampler für Instrument-Tracks
- Wenn ein Instrument-Track ohne SF2 und ohne Device ausgewählt wird,
  wird automatisch ein Pro Audio Sampler erstellt

### Kompakte QPainter Knobs
- Eigene `CompactKnob` Klasse (kein QDial)
- 52×64px, Arc-Darstellung, Drag-to-change, Mousewheel
- Akzentfarbe Magenta (#e060e0) passend zum Pro-DAW-Theme

---

## 📁 Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw/plugins/sampler/audio_io.py` | **NEU** — Multi-Format Audio Loader |
| `pydaw/plugins/sampler/ui_widgets.py` | Rewrite: CompactKnob + WaveformStrip |
| `pydaw/plugins/sampler/sampler_widget.py` | Rewrite: Kompaktes Pro-DAW-Layout |
| `pydaw/plugins/sampler/sampler_engine.py` | Import: audio_io statt wav_io |
| `pydaw/ui/device_panel.py` | Rewrite: Per-Track Device-Binding |
| `pydaw/ui/main_window.py` | Fix: Track-Selection, Clip-Activation, Instrument-Binding |
| `pydaw/ui/sample_browser.py` | Update: .wv/.aiff in AUDIO_EXTS |
| `pydaw/version.py` | → 0.0.19.7.55 |

---

## 🧪 Test-Anleitung

1. **Neues Projekt** → Projekt → Instrument-Track hinzufügen
2. **Device Panel prüfen:** Unten "Device" klicken → Sampler sollte automatisch erscheinen
3. **Kompaktes Layout:** Alle Knobs sichtbar ohne Scrollen
4. **Zweiten Track:** Nochmal Instrument-Track hinzufügen → zwischen Tracks wechseln
5. **Nur ein Sampler sichtbar:** Device Panel zeigt nur Devices der ausgewählten Spur
6. **Piano Roll:** Doppelklick auf MIDI-Clip → Piano Roll öffnet sich
7. **Audio laden:** "Load Sample" oder Drag & Drop von WAV/MP3/FLAC/OGG
8. **Sound-Test:** Noten im Piano Roll eingeben → Sampler spielt ab

---

## ⚠️ Bekannte Einschränkungen

- MP3/M4A/WV benötigen `soundfile` oder `pydub` + ffmpeg (WAV funktioniert immer)
- Track-Deletion räumt Devices noch nicht automatisch auf (manuell oder TODO)
- Sampler ist monophon (ein Sample gleichzeitig)
