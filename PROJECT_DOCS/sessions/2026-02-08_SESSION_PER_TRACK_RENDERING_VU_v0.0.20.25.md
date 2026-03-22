# 📝 SESSION LOG — Per-Track Rendering + VU Metering (v0.0.20.25)

**Datum:** 2026-02-08  
**Kollege:** GPT-5.2 Thinking  
**Scope:** Hybrid Engine Phase 3 (Core)  
**Ziel:** Track-Params + Metering wirklich **pro Track** im Callback anwenden.

---

## Ausgangslage / Bug

Im Mixer war ein VU-Meter Widget vorhanden, aber:

- `HybridAudioCallback.get_track_meter(track_idx)` wurde im Callback nie aktualisiert
- `ArrangementState.render(frames)` rendert alles als **Master-Mix**, daher keine Track-Signale/Meter möglich
- Track-Index Mapping war nicht deterministisch (`enumerate()` vs. Bridge Registry)

Ergebnis: VU-Meter blieb meist bei 0.0 und/oder zeigte falsche Tracks.

---

## Umsetzung (v0.0.20.25)

### 1) ArrangementState: Per-Track Rendering
**File:** `pydaw/audio/arrangement_renderer.py`

- `PreparedClip` erweitert um `track_idx`
- `prepare_clips()` erzeugt deterministische `track_idx_map` aus Projekt-Reihenfolge
- `ArrangementState` bekommt:
  - `_track_clips` Map (track_idx → clips)
  - `_track_pos` Cursors (RT-friendly)
  - `get_active_tracks(frames, out=list)` (reused list)
  - `render_track(track_idx, frames, out=np.ndarray)` (kein Playhead-Advance)
  - `advance(frames)` (Playhead-Advance **einmal pro Block**, Loop reset)

### 2) HybridAudioCallback: per-track mix loop + meters
**File:** `pydaw/audio/hybrid_engine.py`

- Pre-alloc: `self._track_bufs = np.zeros((MAX_TRACKS, 8192, 2), float32)`
- Reused list: `self._active_tracks_buf`
- Per block:
  - tracks = st.get_active_tracks(frames, out=...)
  - pro Track:
    - `TrackParamState.get_track_gain()` (mute/solo/vol/pan)
    - `st.render_track()` in track scratch buffer
    - `TrackMeterRing.update_from_block()` (peaks)
    - apply vol/pan in-place + mix to master
  - `st.advance(frames)` einmal

### 3) Deterministisches Track-Index Mapping
- `HybridEngineBridge.set_track_index_map(mapping)` (neu)
- `MixerPanel.refresh()` synct mapping auf Projekt-Reihenfolge
- `AudioEngine._run_sounddevice_arrangement()` synct mapping vor prepare_clips()

---

## Status / Nächste Schritte

✅ Code kompiliert / strukturell korrekt.  
🚧 Bitte als nächstes unter realem Playback testen (sounddevice + JACK):

- Start playback → VU Meter sollte sich bewegen
- Solo/Mute should reflect live without re-prewarm
- Loop handling (playhead wrap) prüfen

**Offen:**
- GPU Waveform: echte Daten aus AsyncLoader (TODO v0.0.20.24)
- Runtime testing & Debugging (2h)

---

## Geänderte Dateien

- `pydaw/audio/arrangement_renderer.py`
- `pydaw/audio/hybrid_engine.py`
- `pydaw/audio/audio_engine.py`
- `pydaw/ui/mixer.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md` (aktualisiert)
