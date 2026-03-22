# 🔧 HYBRID ENGINE PHASE 3 - IMPLEMENTATION GUIDE

**Status:** 🚧 IN PROGRESS (Teilweise dokumentiert)  
**Geschätzter Aufwand:** 6-8h für vollständige Implementierung  
**Priority:** 🟡 MEDIUM

---

## 📊 ÜBERSICHT

Die Hybrid Engine Phase 3 erweitert das bestehende System um:
1. **Per-Track Audio Rendering** - Individuelles Vol/Pan pro Track
2. **VU-Metering** - Real-time Level-Anzeige
3. **StretchPool Integration** - Automatisches Re-Stretch bei BPM-Change
4. **GPU Waveform** - Echte Audio-Daten statt Mock

---

## ✅ WAS BEREITS FUNKTIONIERT (v0.0.20.14)

Die Foundation ist solid:
- ✅ `ParamRingBuffer` - Lock-Free Parameter Updates
- ✅ `TrackParamState` - Per-Track Vol/Pan/Mute/Solo Cache
- ✅ `TrackMeterRing` - Lightweight Metering Ring
- ✅ `HybridAudioCallback` - Zero-Lock Audio Callback
- ✅ `Hybrid Engine Phase 3` auf Pro-DAW-Niveau heben.

Der Workflow ist:
1. Clip-Arranger ist bereits finalisiert (v0.0.20.19) ✅
2. Hybrid Engine Phase 1 + 2 sind fertig (v0.0.20.13/14) ✅
3. Phase 3 braucht noch ~6-8h Arbeit

---

## 🎯 TASK 1: Per-Track Rendering (4-6h)

### Ziel:
Jeder Track wird separat gerendert mit eigenem Vol/Pan, dann gemischt.

### Current Implementation:
```python
# pydaw/audio/hybrid_engine.py:226
if st is not None:
    buf = st.render(frames)  # Rendert ALLE Tracks gemischt
    mix[:buf.shape[0]] += buf[:frames]
```

### Target Implementation:
```python
# Neu: Per-Track Rendering Loop
if st is not None and hasattr(st, 'render_per_track'):
    tracks = st.get_active_tracks()
    ts = self._track_state
    
    for track_idx in tracks:
        # 1. Render Track
        track_buf = st.render_track(track_idx, frames)
        if track_buf is None:
            continue
        
        # 2. Get Track Parameters (smoothed)
        vol = ts.get_vol_smooth(track_idx)
        pan = ts.get_pan_smooth(track_idx)
        muted = ts.is_muted(track_idx)
        solo_active = ts.any_solo()
        
        # 3. Mute/Solo Logic
        if muted or (solo_active and not ts.is_solo(track_idx)):
            continue
        
        # 4. Apply Vol/Pan
        gl, gr = _pan_gains(vol, pan)
        track_buf[:, 0] *= gl
        track_buf[:, 1] *= gr
        
        # 5. VU Metering
        meter = self.get_track_meter(track_idx)
        meter.update_from_block(track_buf, gl, gr)
        
        # 6. Mix into Master
        mix[:frames] += track_buf[:frames]
else:
    # Fallback: Old rendering
    buf = st.render(frames)
    mix[:buf.shape[0]] += buf[:frames]
```

### Required Changes:

#### 1.1 ArrangementState Extension
**File:** `pydaw/audio/arrangement_renderer.py`

```python
class ArrangementState:
    # ... existing code
    
    def __init__(self, ...):
        # ... existing
        self._track_clips: Dict[int, List[AudioClip]] = {}  # NEU
    
    def set_tracks(self, tracks: List[Track]):
        """Update track → clips mapping."""
        self._track_clips.clear()
        for track in tracks:
            track_idx = track.index  # Assuming Track has index
            clips = [c for c in self.clips if c.track_id == track.id]
            self._track_clips[track_idx] = clips
    
    def get_active_tracks(self) -> List[int]:
        """Return list of track indices with clips."""
        return list(self._track_clips.keys())
    
    def render_track(self, track_idx: int, frames: int) -> np.ndarray:
        """Render single track's audio."""
        # Similar to render(), but only for clips in this track
        clips = self._track_clips.get(track_idx, [])
        if not clips:
            return np.zeros((frames, 2), dtype=np.float32)
        
        out = np.zeros((frames, 2), dtype=np.float32)
        ph = self.playhead
        
        for clip in clips:
            # ... render logic (same as current render())
            pass
        
        return out
```

#### 1.2 Track Index Registry Update
**File:** `pydaw/audio/audio_engine.py`

```python
# In bind_transport() oder ähnlich:
def _update_track_indices(self):
    """Update HybridCallback's track index map."""
    tracks = self.project.ctx.project.tracks
    mapping = {t.id: idx for idx, t in enumerate(tracks) if t.kind != 'master'}
    
    if hasattr(self._hybrid_callback, 'set_track_index_map'):
        self._hybrid_callback.set_track_index_map(mapping)
```

#### 1.3 Testing:
```bash
python3 -c "
from pydaw.audio.hybrid_engine import HybridAudioCallback
from pydaw.audio.ring_buffer import ParamRingBuffer

# Create callback
ring = ParamRingBuffer()
cb = HybridAudioCallback(ring, sr=48000)

# Test per-track metering
for i in range(4):
    meter = cb.get_track_meter(i)
    print(f'Track {i}: {meter.peak_l:.3f} / {meter.peak_r:.3f}')
"
```

---

## 🎯 TASK 2: VU-Metering UI (1-2h)

### Ziel:
Mixer zeigt Live-Meter für jeden Track.

### Implementation:
**File:** `pydaw/ui/mixer.py`

```python
class TrackStrip(QWidget):
    def __init__(self, track, hybrid_callback, ...):
        # ... existing
        
        # VU Meter Widget
        self.vu_meter = VUMeterWidget()
        layout.addWidget(self.vu_meter)
        
        # Timer for updates
        self._meter_timer = QTimer()
        self._meter_timer.timeout.connect(self._update_meter)
        self._meter_timer.start(50)  # 20 FPS
        
        self._hybrid_callback = hybrid_callback
        self._track_idx = track_idx
    
    def _update_meter(self):
        """Read meter from HybridCallback (lock-free!)."""
        if self._hybrid_callback is None:
            return
        
        meter = self._hybrid_callback.get_track_meter(self._track_idx)
        l, r = meter.read_and_decay()
        
        # Update UI
        self.vu_meter.set_levels(l, r)
```

**New Widget:** `pydaw/ui/widgets/vu_meter.py`

```python
class VUMeterWidget(QWidget):
    """Simple VU Meter with peak hold."""
    
    def __init__(self):
        super().__init__()
        self.setFixedWidth(30)
        self.setMinimumHeight(100)
        
        self._level_l = 0.0
        self._level_r = 0.0
        self._peak_hold_l = 0.0
        self._peak_hold_r = 0.0
    
    def set_levels(self, l: float, r: float):
        self._level_l = max(0.0, min(1.0, l))
        self._level_r = max(0.0, min(1.0, r))
        
        # Peak hold
        if l > self._peak_hold_l:
            self._peak_hold_l = l
        if r > self._peak_hold_r:
            self._peak_hold_r = r
        
        self.update()
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw meter bars
        # Green: 0-0.7, Yellow: 0.7-0.9, Red: 0.9-1.0
        # ...
```

---

## 🎯 TASK 3: StretchPool Integration (2h)

### Ziel:
Bei BPM-Change werden Clips automatisch im Hintergrund ge-stretched.

### Implementation:
**File:** `pydaw/services/prewarm_service.py`

```python
# Add at top:
try:
    from pydaw.audio.essentia_pool import get_essentia_pool
    ESSENTIA_AVAILABLE = True
except Exception:
    ESSENTIA_AVAILABLE = False

class PrewarmService:
    def __init__(self, ...):
        # ... existing
        self._essentia_pool = get_essentia_pool() if ESSENTIA_AVAILABLE else None
    
    def _do_prewarm(self, ...):
        # ... existing decode logic
        
        # When stretch is needed:
        if needs_stretch and self._essentia_pool:
            # Submit to pool instead of blocking
            job_id = self._essentia_pool.submit_stretch(
                audio_data=decoded,
                rate=stretch_rate,
                priority=1  # High priority
            )
            
            # Poll or wait (non-blocking)
            stretched = self._essentia_pool.get_result(
                job_id, timeout=3.0, fallback=decoded
            )
            
            # Cache
            cache.put_stretched(key, stretched, ...)
        else:
            # Fallback: synchronous stretch
            stretched = stretch_audio(decoded, stretch_rate)
```

**File:** `pydaw/audio/essentia_pool.py` (UPDATE)

```python
# Add priority parameter to submit_stretch:
def submit_stretch(self, audio_data, rate, priority=0):
    """Submit stretch job with priority (higher = more urgent)."""
    # Put in priority queue
    heapq.heappush(self._queue, (-priority, job_id, (audio_data, rate)))
    return job_id
```

---

## 🎯 TASK 4: GPU Waveform Echte Daten (1h)

### Ziel:
Waveform-Renderer nutzt echte Peak-Daten statt Mock.

### Implementation:
**File:** `pydaw/ui/gpu_waveform_renderer.py`

```python
class WaveformGLRenderer(QOpenGLWidget):
    # ... existing
    
    def set_clip_data(self, clip):
        """Load real waveform data from AsyncLoader."""
        if not clip or not hasattr(clip, 'source_path'):
            return
        
        from pydaw.audio.async_loader import get_async_loader
        loader = get_async_loader()
        
        # Get peaks asynchronously
        peaks = loader.get_peaks(
            clip.source_path,
            block_size=512,  # One peak per 512 samples
            callback=self._on_peaks_loaded
        )
    
    def _on_peaks_loaded(self, peaks):
        """Called when peaks are ready."""
        if peaks is None or len(peaks) == 0:
            return
        
        # Upload to VBO
        self._upload_peaks_to_vbo(peaks)
        self.update()  # Trigger repaint
    
    def _upload_peaks_to_vbo(self, peaks):
        """Upload peak data to OpenGL VBO."""
        if not self._vbo_initialized:
            return
        
        # Convert peaks to vertex data
        vertices = self._peaks_to_vertices(peaks)
        
        # Upload
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_DYNAMIC_DRAW)
```

**Integration with AsyncLoader:**
**File:** `pydaw/audio/async_loader.py`

```python
class AsyncSampleLoader:
    # ... existing
    
    def get_peaks(self, path, block_size=512, callback=None):
        """Get peak data for waveform rendering."""
        # Check cache first
        cache_key = f"peaks:{path}:{block_size}"
        if cache_key in self._peaks_cache:
            result = self._peaks_cache[cache_key]
            if callback:
                callback(result)
            return result
        
        # Submit job
        def _job():
            peaks = self._compute_peaks(path, block_size)
            self._peaks_cache[cache_key] = peaks
            if callback:
                callback(peaks)
            return peaks
        
        self._pool.submit(_job)
        return None  # Async
    
    def _compute_peaks(self, path, block_size):
        """Compute peak values for waveform."""
        import soundfile as sf
        import numpy as np
        
        with sf.SoundFile(path) as f:
            data = f.read()
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            
            # Compute peaks
            n_blocks = (len(data) + block_size - 1) // block_size
            peaks = np.zeros(n_blocks, dtype=np.float32)
            
            for i in range(n_blocks):
                start = i * block_size
                end = min((i + 1) * block_size, len(data))
                block = data[start:end]
                peaks[i] = np.max(np.abs(block))
            
            return peaks
```

---

## 🧪 TESTING CHECKLIST

### Per-Track Rendering:
- [ ] Create project with 4 tracks
- [ ] Each track: different Vol/Pan settings
- [ ] Play: Verify stereo image correct
- [ ] Mute Track 2: Verify silence
- [ ] Solo Track 3: Verify only Track 3 audible

### VU-Metering:
- [ ] Play audio: VU meters move
- [ ] Loud audio: Peak reaches near 1.0
- [ ] Silent audio: Meters decay to 0
- [ ] Change track volume: Meter reflects change

### StretchPool:
- [ ] Change BPM: Prewarm starts
- [ ] Play after BPM change: No lag
- [ ] Check logs: Essentia pool used
- [ ] Fallback: Works without Essentia

### GPU Waveform:
- [ ] Load audio clip: Waveform renders
- [ ] Zoom in/out: Waveform updates
- [ ] Compare to old mock: Real data visible
- [ ] Performance: No lag with 10+ clips

---

## 📁 FILES TO MODIFY

### Core Engine:
1. `pydaw/audio/hybrid_engine.py` - Per-Track Rendering Loop
2. `pydaw/audio/arrangement_renderer.py` - Track-wise render methods
3. `pydaw/audio/audio_engine.py` - Track index registry

### Services:
4. `pydaw/services/prewarm_service.py` - StretchPool integration
5. `pydaw/audio/essentia_pool.py` - Priority queue

### UI:
6. `pydaw/ui/mixer.py` - VU meter updates
7. `pydaw/ui/widgets/vu_meter.py` - NEW: VU meter widget
8. `pydaw/ui/gpu_waveform_renderer.py` - Real peak data
9. `pydaw/audio/async_loader.py` - Peak computation

---

## ⏱️ TIME ESTIMATES

| Task | Estimate | Difficulty |
|------|----------|------------|
| Per-Track Rendering | 4-6h | 🔴 HIGH |
| VU-Metering UI | 1-2h | 🟡 MED |
| StretchPool Integration | 2h | 🟡 MED |
| GPU Waveform Data | 1h | 🟢 LOW |
| Testing & Debugging | 2h | 🟡 MED |
| **TOTAL** | **10-13h** | |

---

## 🚀 RECOMMENDED APPROACH

### Day 1 (4h):
- Morning: Per-Track Rendering (Core Logic)
- Afternoon: ArrangementState.render_track()

### Day 2 (4h):
- Morning: VU-Metering UI + Testing
- Afternoon: StretchPool Integration

### Day 3 (2h):
- Morning: GPU Waveform + Final Testing
- Documentation + Handoff

---

## 📝 NOTES FOR NEXT DEVELOPER

1. **Don't rush Per-Track Rendering** - It's the core feature, needs careful testing
2. **VU Metering is Quick Win** - Can be done first for visible progress
3. **StretchPool is Optional** - Fallback works without Essentia
4. **GPU Waveform is Polish** - Can be done last

**WICHTIG:**
- Testen Sie jeden Schritt einzeln!
- Commit nach jedem funktionierenden Feature
- Dokumentieren Sie Probleme im Session-Log

---

**Viel Erfolg!** 🚀
