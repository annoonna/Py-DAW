# Session: JACK Hybrid Per-Track Faders + VU Meter Fix — v0.0.20.39

**Datum:** 2026-02-08  
**Ziel:** Mixer-Fader + VU Meter müssen **in Echtzeit** während Loop/Playback reagieren (kein Stop/Play mehr nötig).

---

## Ausgangsproblem (User Report)
- Im Loop/Live-Playback reagiert **nur Master** sofort.
- Track-Fader (Instrument/Audio/Busses) greifen erst nach Stop → Play.
- VU Meter bewegen sich nicht bzw. nur unzuverlässig.

## Root Cause
JACK-Backend nutzt den Hybrid-Renderpfad:
- `AudioEngine._start_arrangement_playback()` setzt bei JACK `jack_service.set_render_callback(hybrid_cb.render_for_jack)`.
- `HybridAudioCallback.render_for_jack()` hat **nur** `st.render(frames)` genutzt (legacy full-mix) →
  **keine per-track Param-Anwendung (Vol/Pan/Mute/Solo)** und **keine TrackMeterRing Updates**.

Zusätzlich war in JACK der deterministische Track-Index-Mapping-Call nicht garantiert.
Wenn Bridge/UI und ArrangementState unterschiedliche Track-Indices nutzen → Master wirkt, Tracks nicht.

## Fix (v0.0.20.39)
### 1) Per-Track Pipeline in JACK aktivieren
`HybridAudioCallback.render_for_jack()` wurde auf die gleiche Pipeline wie `_process()` umgestellt:
- Drain ParamRingBuffer → `TrackParamState` (pro Block)
- Pro aktivem Track: `render_track()` → apply vol/pan → update TrackMeterRing → sum into master
- `st.advance(frames)` nur **einmal pro Block**
- Master vol/pan smoothing, soft limiter
- Master meter ring write

### 2) Deterministisches Track-Index-Mapping auch bei JACK
In `audio_engine.py` im JACK-Arrange-Prepare:
- `self._hybrid_bridge.set_track_index_map({track.id: idx ...})` basierend auf dem Project-Snapshot
- Dadurch ist die UI/Bridge-Indizierung garantiert kompatibel zu `ArrangementState`.

## Geänderte Dateien
- `pydaw/audio/hybrid_engine.py`
- `pydaw/audio/audio_engine.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Testplan (schnell)
1. Start mit JACK (PipeWire-JACK), Arrangement mit mehreren Tracks.
2. Play + Loop aktiv.
3. Während Playback:
   - Track-Fader bewegen → **Audio muss sofort reagieren** (ohne Stop/Play)
   - Track Mute/Solo togglen → sofort
   - Master-Fader weiterhin live
4. VU Meter:
   - Master + Track Meter müssen sichtbar ausschlagen.

