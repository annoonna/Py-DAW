# CHANGELOG v0.0.20.672 — Phase R5: Sample Playback Engine

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R5A + R5B

## Was wurde gemacht

### R5A — Audio File I/O: `sample/mod.rs` (~250 Zeilen)

1. **`SampleData`** — Immutable audio sample struct
   - `Arc<Vec<f32>>` für zero-copy sharing zwischen Voices/Threads
   - Felder: channels, sample_rate, frames, root_note, fine_tune, name
   - `get_sample()`, `get_frame()` — inline, bounds-checked
   - `pitch_ratio(midi_note)` — Semitone-basiert (2^(Δ/12))
   - `playback_rate(midi_note, engine_sr)` — inkl. Sample-Rate-Konversion
   - `duration_secs()`

2. **WAV Loader** — `load_wav(path) -> Result<SampleData>`
   - PCM 8/16/24/32-bit Integer + 32-bit Float via `hound` Crate
   - `load_wav_with_root()` für Custom Root Note
   - Dependency: `hound = "3.5"` in Cargo.toml

3. **Konversions-Utilities**
   - `mono_to_stereo()` — Mono → Stereo Duplikation
   - `downmix_to_stereo()` — N-Channel → Stereo (L=Ch0, R=Ch1)
   - `resample_linear()` — Linear-Interpolation Resampling src→dst SR

4. **8 Unit-Tests** — from_raw, get_frame, mono→stereo, pitch_ratio, playback_rate, resample, duration

### R5B — Voice + Playback: `sample/voice.rs` (~300 Zeilen)

5. **`SampleVoice`** — Einzelne spielende Sample-Instanz
   - States: Idle → Playing → Releasing → Idle
   - `note_on(sample, note, velocity, engine_sr, time)` — Startet Playback
   - `note_off()` → Release-Phase, `kill()` → sofortiger Stop
   - ADSR Envelope aus R1 (`AdsrEnvelope`)
   - Velocity → Volume Mapping

6. **Cubic Interpolation** für Pitch-Shifting
   - Nutzt `interpolate_cubic()` aus `dsp/interpolation.rs`
   - 4-Punkt Hermite für Haupt-Bereich, Linear-Fallback am Sample-Ende

7. **Loop-Modi**
   - `LoopMode::None` — Play once, auto-release at end
   - `LoopMode::Forward` — Wrap von loop_end → loop_start
   - `LoopMode::PingPong` — Direction-Flip an Loop-Grenzen

8. **5 Unit-Tests** — lifecycle, render, pitch_shift, forward_loop, velocity

### R5B — Voice Pool: `sample/voice_pool.rs` (~210 Zeilen)

9. **`VoicePool`** — Pre-allokierter Voice-Pool
   - Max 256 Voices, alle bei Erstellung allokiert
   - `note_on()` → freie Voice finden oder stehlen
   - `note_off(note)` → alle Voices mit diesem Note releasen
   - `all_notes_off()` / `all_sound_off()` (Panic Button)
   - `render()` — Alle aktiven Voices additiv in Output-Buffer

10. **Voice-Stealing Strategien** (`StealMode`)
    - `Oldest` — Voice mit niedrigstem start_time
    - `Quietest` — Voice mit niedrigstem Envelope-Level
    - `SameNote` — Re-Trigger (gleiche Note bevorzugt, Fallback: Oldest)

11. **5 Unit-Tests** — note_on/off, stealing, same_note, render, all_notes_off

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw_engine/src/sample/mod.rs` | **NEU** — SampleData, WAV Loader, Utilities |
| `pydaw_engine/src/sample/voice.rs` | **NEU** — SampleVoice, LoopMode, Cubic Interp |
| `pydaw_engine/src/sample/voice_pool.rs` | **NEU** — VoicePool, StealMode |
| `pydaw_engine/src/main.rs` | `mod sample;` hinzugefügt |
| `pydaw_engine/Cargo.toml` | `hound = "3.5"` Dependency |
| `VERSION` | 671 → 672 |
| `pydaw/version.py` | 671 → 672 |

## Statistik
- **3 neue Rust-Dateien**, ~760 Zeilen
- **18 neue Unit-Tests** (8 + 5 + 5)
- **Gesamt Rust-Engine:** ~8.400+ Zeilen

## Was als nächstes zu tun ist
- **Phase R6A** — ProSampler: AudioNode Impl, Single-Sample Mode, MIDI Input
- **Phase R6B** — MultiSample: Zone Mapping, Round-Robin, Velocity Layers
