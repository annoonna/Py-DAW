"""Sampler/Drums Offline MIDI→WAV Renderer (v0.0.20.47).

Renders MIDI clips to WAV using ProSamplerEngine/DrumMachineEngine.
Similar to FluidSynth rendering but uses internal engines.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import List, Any, Optional
from dataclasses import dataclass

try:
    import numpy as np
except Exception:
    np = None


@dataclass
class SamplerRenderKey:
    """Cache key for sampler rendering."""
    clip_id: str
    track_id: str
    plugin_type: str  # "sampler" | "drum_machine"
    bpm: float
    samplerate: int
    clip_length_beats: float
    content_hash: str  # Hash of MIDI notes + sample paths
    
    def to_filename(self) -> str:
        """Generate cache filename."""
        h = hashlib.sha256()
        h.update(f"{self.clip_id}:{self.track_id}:{self.plugin_type}".encode())
        h.update(f":{self.bpm}:{self.samplerate}:{self.clip_length_beats}".encode())
        h.update(f":{self.content_hash}".encode())
        return f"sampler_{h.hexdigest()[:16]}.wav"


def _cache_dir() -> Path:
    """Get cache directory for rendered samples."""
    import os
    cache_root = Path(os.environ.get("XDG_CACHE_HOME") or 
                     Path.home() / ".cache")
    cache_dir = cache_root / "ChronoScaleStudio" / "sampler_render"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def render_sampler_midi(
    *,
    engine: Any,  # ProSamplerEngine instance
    midi_notes: List[Any],
    bpm: float,
    clip_length_beats: float,
    samplerate: int = 48000,
) -> Optional[np.ndarray]:
    """Render MIDI notes with Sampler engine to numpy array.
    
    Args:
        engine: ProSamplerEngine instance with loaded sample
        midi_notes: List of note objects with pitch, start_beats, length_beats, velocity
        bpm: Project BPM
        clip_length_beats: Clip length in beats
        samplerate: Target samplerate
        
    Returns:
        numpy array (frames, 2) float32 or None on failure
    """
    if np is None or engine is None:
        return None
    
    try:
        # Calculate total frames needed
        beats_per_second = bpm / 60.0
        clip_duration_sec = clip_length_beats / beats_per_second
        total_frames = int(clip_duration_sec * samplerate)
        
        if total_frames <= 0:
            return None
        
        # Allocate output buffer
        output = np.zeros((total_frames, 2), dtype=np.float32)
        
        # Sort notes by start time
        sorted_notes = sorted(
            midi_notes,
            key=lambda n: float(getattr(n, "start_beats", 0.0))
        )
        
        # Render each note
        for note in sorted_notes:
            try:
                pitch = int(getattr(note, "pitch", 60))
                start_beats = float(getattr(note, "start_beats", 0.0))
                length_beats = float(getattr(note, "length_beats", 0.0))
                velocity = int(getattr(note, "velocity", 100))
                
                # Convert beats to frames
                start_frame = int(start_beats / beats_per_second * samplerate)
                note_duration_sec = length_beats / beats_per_second
                
                # Trigger note in engine
                engine.trigger_note(pitch, velocity, int(note_duration_sec * 1000))
                
                # Pull audio from engine
                frames_remaining = total_frames - start_frame
                if frames_remaining > 0:
                    # Pull in chunks to avoid huge allocations
                    chunk_size = 4096
                    offset = start_frame
                    
                    while frames_remaining > 0 and offset < total_frames:
                        chunk_frames = min(chunk_size, frames_remaining)
                        chunk = engine.pull(chunk_frames, samplerate)
                        
                        if chunk is not None and chunk.shape[0] > 0:
                            # Add to output buffer
                            end = min(offset + chunk.shape[0], total_frames)
                            output[offset:end] += chunk[:end-offset, :2]
                            offset = end
                            frames_remaining -= chunk.shape[0]
                        else:
                            break
                            
            except Exception:
                continue
        
        return output
        
    except Exception:
        return None


def render_drums_midi(
    *,
    engine: Any,  # DrumMachineEngine instance
    midi_notes: List[Any],
    bpm: float,
    clip_length_beats: float,
    samplerate: int = 48000,
) -> Optional[np.ndarray]:
    """Render MIDI notes with Drum Machine engine to numpy array.
    
    Similar to render_sampler_midi but uses DrumMachineEngine.
    """
    # Drums use the same rendering strategy as sampler
    # The engine.trigger_note() API is compatible
    return render_sampler_midi(
        engine=engine,
        midi_notes=midi_notes,
        bpm=bpm,
        clip_length_beats=clip_length_beats,
        samplerate=samplerate,
    )


def ensure_sampler_rendered_wav(
    *,
    key: SamplerRenderKey,
    engine: Any,
    midi_notes: List[Any],
) -> Optional[Path]:
    """Ensure WAV file exists for sampler/drums MIDI clip.
    
    Returns cached WAV path or renders new one.
    Similar to ensure_rendered_wav for FluidSynth.
    """
    if np is None:
        return None
    
    try:
        # Check cache
        cache_path = _cache_dir() / key.to_filename()
        if cache_path.exists() and cache_path.stat().st_size > 44:
            return cache_path
        
        # Render audio
        if key.plugin_type == "sampler":
            audio = render_sampler_midi(
                engine=engine,
                midi_notes=midi_notes,
                bpm=key.bpm,
                clip_length_beats=key.clip_length_beats,
                samplerate=key.samplerate,
            )
        elif key.plugin_type == "drum_machine":
            audio = render_drums_midi(
                engine=engine,
                midi_notes=midi_notes,
                bpm=key.bpm,
                clip_length_beats=key.clip_length_beats,
                samplerate=key.samplerate,
            )
        else:
            return None
        
        if audio is None or audio.shape[0] == 0:
            return None
        
        # Write WAV file
        try:
            import soundfile as sf
            sf.write(str(cache_path), audio, int(key.samplerate), format='WAV')
        except Exception:
            return None
        
        # Verify file
        if cache_path.exists() and cache_path.stat().st_size > 44:
            return cache_path
        
        return None
        
    except Exception:
        return None
