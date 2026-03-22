# CHANGELOG v0.0.20.636 — Multi-Track Recording (AP2 Phase 2B)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2B

## Was wurde gemacht

### Multi-Track Recording
- Mehrere Tracks können gleichzeitig Record-Armed und aufgenommen werden
- Jeder Track schreibt eine eigene WAV-Datei (24-bit, pro Track)
- JACK Backend: Separate Portpaare pro Input-Pair, automatisches Routing
- sounddevice/PipeWire: Multi-Channel Stream mit Demux im Callback
- Backward-kompatibel: Single-Track API funktioniert unverändert weiter

### Input-Routing pro Track
- Neues ComboBox "In 1/2", "In 3/4", etc. im Mixer-Strip
- Wählbar welches Stereo-Paar pro Track aufgenommen wird
- Hardware-Input-Erkennung bei Start (JACK Ports / sounddevice query)
- Model-Sync: `Track.input_pair` wird im Mixer-Strip angezeigt/gesetzt

### Buffer-Size Einstellungen
- Audio-Einstellungen Dialog: SpinBox → ComboBox mit Standard-DAW-Werten
  (64/128/256/512/1024/2048/4096) inkl. Latenz-Anzeige in ms
- Buffer-Size wird aus Settings in RecordingService übernommen
- Wird vor jedem Recording-Start neu aus Settings gelesen

### PDC Framework (Plugin Delay Compensation)
- Infrastruktur für Latenz-Kompensation bei Multi-Track Recording
- `set_track_pdc_latency()` / `get_track_pdc_latency()` API
- PDC-Offset wird beim WAV-Speichern als Sample-Trimming angewendet
- PDC-Beats-Korrektur für korrekte Clip-Platzierung im Arranger

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/services/recording_service.py | Komplett überarbeitet: Multi-Track, PDC, Buffer-Size, Input-Detection |
| pydaw/ui/mixer.py | Input-Routing ComboBox, Multi-Track Rec-Arm |
| pydaw/ui/main_window.py | Multi-Track Recording Toggle (alle armed Tracks) |
| pydaw/ui/audio_settings_dialog.py | Buffer-Size ComboBox statt SpinBox |
| pydaw/services/container.py | Buffer-Size aus Settings → RecordingService |
| pydaw/version.py | Version → 0.0.20.636 |
| VERSION | 0.0.20.636 |

## Was als nächstes zu tun ist
- AP2 Phase 2C — Punch In/Out: Region im Arranger, Crossfade an Grenzen
- Alternativ: AP2 Phase 2D — Comping / Take-Lanes

## Bekannte Probleme / Offene Fragen
- PDC-Werte werden noch nicht automatisch aus Plugin-Chains gelesen
  (Framework steht, aber FX-Chain müsste `get_latency()` pro Plugin liefern)
- Input-Detection bei JACK benötigt laufenden JACK-Server zum Scannen
- 24-bit WAV Packing (per-sample struct.pack) ist bei langen Recordings
  langsam — könnte mit numpy Vectorization beschleunigt werden
