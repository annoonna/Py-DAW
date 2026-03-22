# CHANGELOG v0.0.20.0 — "Pro-DAW Core"

## 🔴 KRITISCHE NEUERUNGEN

### 1. Real-Time Parameter Store (`rt_params.py` — NEU)
- **Lock-freies Parameter-System** für DAW-taugliche Audio-Verarbeitung
- GUI-Thread schreibt Zielwerte (atomarer Float-Write unter GIL)
- Audio-Thread liest geglättete Werte (atomarer Float-Read, KEINE Locks)
- **Exponentielles Smoothing** (5ms Standard) verhindert Knackser/Klicks
- Per-Track-Parameter: Volume, Pan, Mute, Solo
- Master-Parameter: Volume, Pan
- Solo-Logik: `any_solo()` prüft globalen Solo-Status

### 2. DSP Engine Rewrite (`dsp_engine.py` — REWRITE)
- Integration von `RTParamStore` in den Render-Callback
- `advance()` wird pro Audio-Block aufgerufen → geglättete Parameter
- Master Volume/Pan aus RTParamStore (mit Legacy-Fallback)
- Zero-Allocation-Policy: Kein `new`, kein Lock im Callback
- Pre-allocated Mix-Buffer (8192×2 float32)
- Pre-cached Pull-Sources-Liste (kein Dict-Overhead)
- Soft Limiter (np.clip -1.0 bis 1.0)

### 3. Sampler Registry (`sampler_registry.py` — NEU)
- **Globaler Sampler-Instanz-Manager** für per-Track Instruments
- `register(track_id, engine, widget)` — Sampler an Track binden
- `trigger_note(track_id, pitch, velocity, duration_ms)` — Unified Note-Routing
- Piano Roll + Notation Editor routen beide über Registry
- Automatische Registrierung bei Track-Auswahl (Instrument-Tracks)
- Clean Lifecycle: `unregister()` bei Track-Löschung
- Modul-Level Singleton via `get_sampler_registry()`

### 4. Pro-DAW-Style Mixer (`mixer.py` — REWRITE)
- **Vertikale Fader-Strips** (92px breit) statt horizontaler Slider
- **VU-Meter** pro Strip (Stereo, Peak-Hold mit Decay)
- **Mute/Solo-Buttons** pro Track (checkable, farbcodiert)
- Volume-Fader: 0-127 Range, logarithmische dB-Anzeige (-∞ bis +X dB)
- Pan-Slider: Horizontal, -100 bis +100
- Automation-Mode Selector (off/read/write)
- **Alle Fader live via RTParamStore** — kein Stop/Play nötig!
- Track-Rename per Doppelklick
- Add/Remove Track Buttons mit Menü (Audio/Instrument/Bus)

### 5. Audio Engine RT-Integration (`audio_engine.py` — TARGETED EDITS)
- `self.rt_params = RTParamStore(default_smooth_ms=5.0)` in __init__
- Master-Params vorinitialisiert: `master:vol=0.8`, `master:pan=0.0`
- `set_master_volume/pan()` schreibt jetzt in BEIDE: atomic float + RTParamStore
- **Silence-Callback**: RTParamStore.advance() + smoothed reads
- **Arrangement-Callback**: RTParamStore.advance() + smoothed reads
- DSPJackEngine bekommt `rt_params=` im Konstruktor
- `running_changed` Signal hinzugefügt

### 6. Audio Editor — Non-Destructive Editing (TARGETED EDITS)
- **Reverse**: Toggle `clip.reversed` Flag (non-destructiv)
- **Mute Clip**: Toggle `clip.muted` Flag (non-destructiv)
- **Normalize**: Setzt `clip.gain = 1.0`
- **Gain +3dB**: Multipliziert gain × 1.4125 (max 4.0)
- **Gain -3dB**: Multipliziert gain × 0.7079 (min 0.01)
- Kontext-Menü erweitert: Split → Reverse/Mute/Normalize/Gain → Quantize/Transpose
- Alle Operationen über `project.update_audio_clip_params()` mit `reversed`/`muted`

### 7. Arranger — Grafik-Turbo (`arranger_canvas.py` — TARGETED EDITS)
- **QPixmap-Cache** für Clip-Visuals (`_clip_pixmap_cache`)
- Cache-Key: `{clip_id}:{width}:{height}:{vol}:{gain}:{kind}:{reversed}:{muted}`
- Clip wird einmal gerendert, dann als Pixmap geblittet
- Cache-Invalidierung bei `project_updated`
- Cache-Limit: 200 Einträge (LRU-artig)
- Muted Clips: Semi-transparentes Overlay
- Reversed Clips: "◄" Tag im Titel
- **Resultat**: Flüssiges Clip-Verschieben ohne Stutter

### 8. Model-Erweiterung (`model/project.py`)
- `Clip.reversed: bool = False` — Non-destructive Reverse
- `Clip.muted: bool = False` — Non-destructive Mute
- `ProjectService.update_audio_clip_params()` unterstützt jetzt `reversed=` und `muted=`

### 9. Main Window Wiring (`main_window.py`)
- MixerPanel bekommt `rt_params` vom AudioEngine
- SamplerRegistry-Integration in `_on_track_selected`
- `note_preview` Signal → `_on_note_preview_routed()` → SamplerRegistry
- Track-spezifisches Note-Routing (nur ausgewählter Track)
- Fallback: Broadcast an alle registrierten Sampler
- Track-Löschung: Sampler aus Registry entfernen

## DATEIEN

### NEU (3 Dateien)
| Datei | Zeilen | Beschreibung |
|-------|--------|--------------|
| `pydaw/audio/rt_params.py` | ~165 | Lock-free RT Parameter Store |
| `pydaw/audio/dsp_engine.py` | ~175 | DSP Engine mit RT-Smoothing |
| `pydaw/plugins/sampler/sampler_registry.py` | ~130 | Global Sampler Registry |

### REWRITE (1 Datei)
| Datei | Zeilen | Beschreibung |
|-------|--------|--------------|
| `pydaw/ui/mixer.py` | ~340 | Pro-DAW-Style Vertical Mixer |

### TARGETED EDITS (5 Dateien)
| Datei | Änderung |
|-------|----------|
| `pydaw/audio/audio_engine.py` | RTParamStore init, smoothed callbacks |
| `pydaw/ui/audio_editor/audio_event_editor.py` | Reverse/Mute/Normalize/Gain actions |
| `pydaw/ui/arranger_canvas.py` | QPixmap clip cache |
| `pydaw/model/project.py` | Clip.reversed/muted fields |
| `pydaw/services/project_service.py` | reversed/muted in update_audio_clip_params |
| `pydaw/ui/main_window.py` | RT params, sampler registry, note routing |

## ARCHITEKTUR

### Zero-Glitch Audio Path
```
GUI Thread → RTParamStore.set_param()     [atomic float write]
             ↓
Audio Thread → RTParamStore.advance()     [per-block smoothing]
             → RTParamStore.get_smooth()  [smoothed value, no locks]
```

### Sampler Routing
```
Piano Roll    → ProjectService.note_preview → MainWindow._on_note_preview_routed
Notation      → ProjectService.note_preview → MainWindow._on_note_preview_routed
                                              ↓
                                    SamplerRegistry.trigger_note(track_id)
                                              ↓
                                    ProSamplerEngine.trigger_note()
```

### Master Clock
```
Audio Callback → Transport._set_external_playhead_samples()
                 → Transport.current_beat
GUI Timer      → Transport.current_beat → Piano Roll cursor, Arranger playline
```
