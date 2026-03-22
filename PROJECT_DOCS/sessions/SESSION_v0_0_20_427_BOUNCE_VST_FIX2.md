# Session: v0.0.20.427 — Bounce in Place: VST Offline Fix #2

**Datum:** 2026-03-12
**Entwickler:** Claude Opus 4.6
**Aufgabe:** Bounce in Place erzeugt weiterhin stille WAV trotz VST-Engine-Code aus v426

## Problem-Analyse

v426 hat den korrekten Rahmen geschaffen (VST-Engine-Erstellung + MIDI-Rendering),
aber die VST-Plugins "schlafen" während des Offline-Bouncens. Drei Ursachen identifiziert:

### 1. Kein Suspend/Resume nach State-Restore
Viele VST2-Plugins (Dexed, Helm, Obxd) benötigen nach `set_chunk()` (State-Wiederherstellung)
einen expliziten Suspend→Resume Zyklus:
```
effMainsChanged(0)  → Plugin geht in Standby
effMainsChanged(1)  → Plugin wird re-aktiviert mit neuem State
effStartProcess     → Plugin beginnt Audio-Verarbeitung
```
Ohne diesen Schritt bleibt das Plugin im Bypass/Init-Modus.

### 2. Keine Warmup-Phase
VST-Instrumente laden intern Samples, initialisieren Oszillatoren und Filter-Buffer.
Wenn sofort MIDI-Noten geschickt werden, kann das Plugin noch "kalt" sein.
Fix: 200ms Leer-Audio (Null-Buffer) durch das Plugin pumpen vor dem ersten MIDI-Event.

### 3. Instrument-Erkennung zu strikt
`__ext_is_instrument` wird zwar zur Laufzeit gesetzt, aber nicht immer ins Projekt-JSON
geschrieben. Die Fallback-Erkennung via `is_vst2_instrument()` spawnt einen Subprocess
und kann ebenfalls fehlschlagen. Lösung: Wenn wir MIDI-Clips bouncen und kein internes
Engine verfügbar ist, ist jedes `ext.vst` Device per Definition das Instrument.

### 4. Stille Exception-Verschluckung
Alle `except Exception: pass` im Bounce-Pfad haben potentielle Fehler unsichtbar gemacht.
Jetzt: Jede Exception wird mit Traceback nach stderr geloggt.

## Änderungen

### `_create_vst_instrument_engine_offline()` — komplett überarbeitet:
- Diagnose-Logs für jeden Schritt (Device-Scan, Engine-Status, Fehler)
- Relaxierte Instrument-Erkennung (Fallback: assume instrument)
- **NEU:** Suspend/Resume nach Engine-Erstellung für VST2
- **NEU:** 200ms Warmup-Phase (leere pull()-Aufrufe)
- Exception-Logging statt `pass`

### `_render_vst_notes_offline()` — überarbeitet:
- MIDI-Event-Logging (Anzahl, erstes Event)
- Peak-Level-Tracking pro Block
- Finale Diagnose: `AUDIO OK` oder `SILENT!`
- Sauberer Tail (1 Sekunde nach all_notes_off)

### `_render_track_subset_offline()` — Calling Code:
- Diagnose-Logs: welche Engine, wie viele Clips, Fehler
- Exception-Logging statt stilles Verschlucken

### `_render_tracks_selection_to_wav()` — WAV Writer:
- Peak-Level des finalen Mix wird geloggt

## Geänderte Dateien
- `pydaw/services/project_service.py` (3 Methoden überarbeitet, 1 erweitert)

## Nichts kaputt gemacht
- Kein Eingriff in Audio-Engine oder Real-Time-Pfad
- Kein Eingriff in VST2/VST3-Host-Code
- Kein Eingriff in UI-Code

## Erwartete Terminal-Ausgabe beim Bounce

```
[BOUNCE-OFFLINE] No internal engine (plugin_type=''), trying VST...
[BOUNCE-OFFLINE] Scanning 1 devices for VST instrument on track=abc123
[BOUNCE-OFFLINE] Device[0]: pid=ext.vst2:/usr/lib/vst/Dexed.so ref=/usr/lib/vst/Dexed.so name=Dexed
[BOUNCE-OFFLINE] Assuming instrument (fallback): /usr/lib/vst/Dexed.so
[BOUNCE-OFFLINE] Creating Vst2InstrumentEngine: /usr/lib/vst/Dexed.so sr=48000
[VST2-INST] Loaded instrument: Dexed (/usr/lib/vst/Dexed.so) | params=24
[BOUNCE-OFFLINE] Engine OK! Applying post-load fixes...
[BOUNCE-OFFLINE] VST2 suspend/resume cycle done
[BOUNCE-OFFLINE] Warmup done: 9600 frames (200ms)
[BOUNCE-OFFLINE] Rendering 8 MIDI clips, is_vst=True
[BOUNCE-OFFLINE] Clip: start=0.0 len=4.0 notes=3
[BOUNCE-RENDER] 3 note_on events, total_frames=96000, bpm=120.0, clip_len=4.0 beats, sr=48000
[BOUNCE-RENDER] First note_on: frame=0 pitch=60 vel=100
[BOUNCE-RENDER] Done: 188 blocks, peak=0.342156, AUDIO OK
...
[BOUNCE-WAV] Final mix: frames=768000, peak=0.342156, AUDIO OK
```

Falls die Ausgabe `SILENT!` zeigt, liegt das Problem tiefer im VST-Plugin selbst.
