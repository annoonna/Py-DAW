# FX Chains — Note-FX (MIDI) + Audio-FX (Audio)

Dieses Dokument erklärt **wo** Note-FX / Audio-FX im Code hängen, **warum** das so ist,
und **wie** man neue Effekte sauber erweitert (Team-Workflow).

---

## Note-FX (MIDI vor Instrument)

### Was?
Note-FX sind MIDI-Transformationen, die **vor** dem Instrument stattfinden.
Beispiele: Transpose, Velocity Scale, Humanize, Arpeggiator, Chord.

### Wo im Modell?
`pydaw/model/project.py` → `Track.note_fx_chain: list[dict]`

Beispiel (vereinfacht):
```python
track.note_fx_chain = [
  {"id": "nf1", "type": "transpose", "params": {"semitones": 12}},
]
```

### Wo wird es angewendet?
`pydaw/audio/arrangement_renderer.py` → `prepare_clips(...)`

- **Live MIDI Events (Sampler/Drum)**:  
  beim Erzeugen von `PreparedMidiEvent` wird `apply_note_fx_chain_to_pitch_velocity(...)` angewendet.

- **Offline MIDI Render (SF2)**:  
  `notes_fx = apply_note_fx_chain_to_notes(...)`  
  und **gerendert wird `notes_fx`**.

### Cache-Key
Offline Render WAVs müssen invalidiert werden, wenn Note-FX sich ändert.
Daher: `note_fx_chain_signature(...)` wird in `content_hash` eingemischt.

### Wie neue Note-FX hinzufügen?
`pydaw/audio/note_fx_chain.py`

1) Neue Device-Type in `NOTE_FX_REGISTRY` implementieren (pure MIDI-Transform)
2) Signatur stabil halten: `note_fx_chain_signature(chain)` muss Änderungen sehen
3) Optional: UI später in Device/Browser

---

## Audio-FX (post Instrument, pre-Fader)

### Was?
Audio-FX sind Audio-Prozessoren, die **nach** dem Instrument (Sampler/SF2) wirken,
aber **vor** Track-Fader/Pan/Mute/Solo.

Beispiele: Gain, Filter, EQ, Saturation, Reverb, Delay.

### Wo im Modell?
`pydaw/model/project.py` → `Track.audio_fx_chain: list[dict]`

Beispiel:
```python
track.audio_fx_chain = [
  {"id": "afx1", "type": "gain", "params": {"db": -6}},
  {"id": "afx2", "type": "lp1", "params": {"hz": 8000}},
]
```

### Wie läuft es in Echtzeit?
1) **Compile + Param-Setup (Main Thread):**
   - `pydaw/audio/audio_engine.py` → `AudioEngine.rebuild_fx_maps(project_snapshot)`
   - nutzt `ensure_track_fx_params(...)` + `build_track_fx_map(...)` aus `pydaw/audio/fx_chain.py`
   - pusht `track_id -> ChainFx` via `HybridEngineBridge.set_track_audio_fx_map(...)`

2) **Apply (Audio Thread):**
   - `pydaw/audio/hybrid_engine.py` → `HybridAudioCallback`
   - Arrangement Track Buffer: `fx.process_inplace(track_buf)`
   - Pull Sources: buffer → fx → metering → fader → mix

3) **Sounddevice Preview („silence mode“):**
   - `pydaw/audio/audio_engine.py` `_run_sounddevice_silence()` wendet ebenfalls FX an, wenn Track-ID bekannt ist.

### Wie neue Audio-FX hinzufügen?
`pydaw/audio/fx_chain.py`

**Schritt-für-Schritt:**
1) Neuen FX-Typ in `build_track_fx_map(...)` abfangen
2) `ChainFx.process_inplace(...)` soll **in-place** arbeiten (keine Allocations)
3) Parameter in `RTParamStore` anlegen:
   - `ensure_track_fx_params(project, rt_params)`
   - Keys: `afx:{track_id}:{device_id}:{param}`

**Wichtig (Realtime):**
- Keine Allokationen im Callback
- Keine Locks im Callback
- Arrays vor-allokieren (max_frames=8192)

---

## Debug / Troubleshooting

- Wenn Audio-FX nicht wirkt: prüfen ob `AudioEngine.rebuild_fx_maps()` aufgerufen wird (bind + start).
- Wenn Meter still: `direct_peaks` / `meter_ring` prüfen (Hybrid callback schreibt).
- Wenn SF2 Render falsch cached: `content_hash` muss Note-FX Signatur enthalten.
