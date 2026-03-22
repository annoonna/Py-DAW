# Session: v0.0.20.428 — Bounce in Place: Best-Practice Fix

**Datum:** 2026-03-12
**Entwickler:** Claude Opus 4.6

## Wie machen es Bitwig, Ableton, Cubase?

Alle drei DAWs erstellen KEINE neue Plugin-Instanz für Bounce-in-Place.
Sie nutzen die **bereits laufende, geladene Instanz** aus der Audio-Engine:

- Plugin ist schon initialisiert und hat den korrekten State
- Oszillatoren, Filter, Buffer sind "warm"
- Kein State-Transfer-Problem (set_chunk, __ext_state_b64)
- Garantiert identischer Sound wie beim Live-Playback
- Während Bounce ist Transport gestoppt → Audio-Callback idle → sicher

## Was v426/v427 falsch gemacht haben

Beide Versionen haben eine NEUE Plugin-Instanz erstellt:
```
Projekt-JSON → __ext_state_b64 → set_chunk() → NEUES Plugin → ???
```

Problem: Viele VST2-Plugins (besonders ctypes-geladene .so) verhalten sich
nach `set_chunk()` nicht identisch zur laufenden Instanz. Trotz
Suspend/Resume und Warmup bleibt der Sound oft stumm.

## v428 Lösung: Borrow Running Engine

```
Audio-Engine._vst_instrument_engines[track_id] → LAUFENDE Instanz → Bounce
```

### Approach 1: Borrow (Best Practice)
1. ProjectService hat jetzt `_audio_engine_ref` (gesetzt in container.py)
2. Laufende VST-Engine wird direkt aus `audio_engine._vst_instrument_engines` geholt
3. Markiert mit `_borrowed = True` → kein shutdown() nach Bounce
4. Nach Render: all_notes_off() + Flush-Blocks

### Approach 2: Offline Fallback
Falls keine laufende Engine verfügbar (z.B. frisch geladenes Projekt):
- Neue Instanz mit restored State (wie v427)
- Suspend/Resume + Warmup
- Markiert mit `_borrowed = False` → normales shutdown()

### Fix: Relaxierte kind-Prüfung
Das Guard `kind == 'instrument'` hat den gesamten MIDI-Render-Block übersprungen,
wenn ein Track nicht explizit als Instrument-Track markiert war.
Jetzt: `kind == 'instrument' OR _track_has_vst_device(track)`

## Geänderte Dateien
- `pydaw/services/container.py` — audio_engine_ref Brücke
- `pydaw/services/project_service.py` — 3 Methoden geändert, 1 neue

## Erwartete Log-Ausgabe (Terminal)
```
[BOUNCE] Track has 8 MIDI clips to render (kind='instrument', plugin_type='')
[BOUNCE] No internal engine (plugin_type='', kind='instrument'), trying VST...
[BOUNCE] ★ Borrowed RUNNING VST engine for track=abc123 (plugin=/usr/lib/vst/Dexed.so)
[BOUNCE] Rendering 8 MIDI clips, is_vst=True, borrowed=True
[BOUNCE] Clip: start=0.0 rel=0.0 len=4.0 notes=3
[BOUNCE-RENDER] 3 note_on events, total_frames=96000, ...
[BOUNCE-RENDER] Done: 188 blocks, peak=0.342156, AUDIO OK
...
[BOUNCE-WAV] Final mix: frames=768000, peak=0.342156, AUDIO OK
```
