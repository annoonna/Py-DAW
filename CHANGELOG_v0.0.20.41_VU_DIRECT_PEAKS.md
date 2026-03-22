# CHANGELOG v0.0.20.41 — Direct Peak VU Metering Fix

**Date:** 2026-02-09  
**Author:** Claude Opus 4.6  
**Priority:** 🔴 HIGH (User-reported bug)

## Problem

VU meters in the mixer did not deflect during playback. The metering data pipeline
had too many layers of indirection with silent `except Exception: pass` at every
step, causing data to silently vanish:

```
AudioCallback → TrackMeterRing → HybridAudioCallback → HybridEngineBridge → MixerStrip
```

If any step in this 4-layer chain threw an exception, the meter got `(0.0, 0.0)`.

## Root Cause

Multiple possible failure points:
1. `_HYBRID_AVAILABLE` could be `False` (import failure) → `_hybrid_bridge = None`
2. HybridAudioCallback could fall to legacy `render()` path (no per-track metering)
3. Track index mapping could mismatch between `prepare_clips` and mixer strips
4. `TrackMeterRing.read_and_decay()` applied double-decay (audio + GUI side)
5. All failures were silently caught by `except Exception: pass`

## Solution: Direct Peak Storage

Added a simple, direct metering path that bypasses the entire HybridBridge chain:

### New: `AudioEngine._direct_peaks` dict

- Written directly from the audio callback (both legacy and hybrid paths)
- Read directly by the mixer's `_update_vu_meter()` 
- Only ONE layer between audio thread and GUI — a Python dict (atomic reads)

### Data Flow (New)

```
Audio Callback → AudioEngine._direct_peaks[track_id] = (peak_l, peak_r)
                                    ↓
Mixer Timer → AudioEngine.read_direct_track_peak(track_id) → VUMeterWidget
```

### Files Changed

**pydaw/audio/audio_engine.py:**
- Added `_direct_peaks` dict and `_direct_peaks_decay` on AudioEngine
- Added `read_direct_track_peak()` method
- Updated `read_master_peak()` to check direct peaks first
- Updated `read_track_peak()` to check direct peaks first
- Legacy callback now writes per-track + master peaks to `_direct_peaks`
- Hybrid callback wiring passes `_direct_peaks` ref to callback

**pydaw/audio/hybrid_engine.py:**
- Added `_direct_peaks_ref` and `_track_index_to_id` on HybridAudioCallback
- `set_track_index_map()` now builds reverse map (idx→track_id)
- `__call__()` writes per-track + master peaks via `_direct_peaks_ref`
- `render_for_jack()` writes per-track + master peaks via `_direct_peaks_ref`

**pydaw/ui/mixer.py:**
- `_update_vu_meter()` now tries `AudioEngine.read_direct_track_peak()` FIRST
- Falls back to existing HybridBridge chain if direct peaks unavailable

**pydaw/version.py, VERSION:** → 0.0.20.41

## Backward Compatibility

✅ All existing metering paths preserved as fallbacks  
✅ No API changes — purely additive  
✅ Works with JACK, sounddevice, and hybrid callback paths  
