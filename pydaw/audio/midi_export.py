"""MIDI Export functionality for PyDAW.

Export MIDI clips, tracks, or entire projects to .mid files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

try:
    import mido  # type: ignore
except Exception:
    mido = None


def export_midi_clip(
    clip: Any,
    midi_notes: List[Any],
    output_path: Path,
    bpm: float = 120.0,
) -> bool:
    """Export a single MIDI clip to a .mid file.
    
    Args:
        clip: The clip object with start_beats, length_beats
        midi_notes: List of note objects with pitch, start_beats, length_beats, velocity
        output_path: Output file path
        bpm: Tempo in BPM
        
    Returns:
        True if successful, False otherwise
    """
    if mido is None:
        return False
    
    try:
        # Create MIDI file
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        
        # Set tempo
        tempo = mido.bpm2tempo(float(bpm))
        track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
        
        # Track name
        clip_name = getattr(clip, 'name', 'MIDI Clip')
        track.append(mido.MetaMessage('track_name', name=str(clip_name), time=0))
        
        # Convert notes
        def beat_to_ticks(b: float) -> int:
            return int(round(b * 480))
        
        events = []
        for n in midi_notes or []:
            try:
                pitch = int(getattr(n, 'pitch'))
                start_b = float(getattr(n, 'start_beats'))
                length_b = float(getattr(n, 'length_beats'))
                vel = int(getattr(n, 'velocity', 96))
            except Exception:
                continue
            
            events.append((start_b, True, pitch, vel))
            events.append((start_b + length_b, False, pitch, 0))
        
        # Sort by time
        events.sort(key=lambda e: (e[0], 0 if not e[1] else 1))
        
        # Write events
        last_tick = 0
        for beat, is_on, pitch, vel in events:
            tick = beat_to_ticks(beat)
            delta = max(0, tick - last_tick)
            last_tick = tick
            
            if is_on:
                track.append(mido.Message('note_on', channel=0, note=pitch, velocity=vel, time=delta))
            else:
                track.append(mido.Message('note_off', channel=0, note=pitch, velocity=0, time=delta))
        
        # End of track
        clip_length = float(getattr(clip, 'length_beats', 4.0))
        final_tick = beat_to_ticks(clip_length)
        track.append(mido.MetaMessage('end_of_track', time=max(0, final_tick - last_tick)))
        
        # Save
        mid.save(str(output_path))
        return True
        
    except Exception as e:
        print(f"MIDI export failed: {e}")
        return False


def export_midi_track(
    track: Any,
    clips: List[Any],
    midi_notes_map: dict,
    output_path: Path,
    bpm: float = 120.0,
) -> bool:
    """Export all MIDI clips from a track to a single .mid file.
    
    Args:
        track: Track object
        clips: All clips in the project
        midi_notes_map: Mapping of clip_id -> notes
        output_path: Output file path
        bpm: Tempo in BPM
        
    Returns:
        True if successful, False otherwise
    """
    if mido is None:
        return False
    
    # Get all MIDI clips for this track
    track_clips = [c for c in clips if getattr(c, 'track_id', '') == track.id and getattr(c, 'kind', '') == 'midi']
    
    if not track_clips:
        return False
    
    try:
        # Create MIDI file
        mid = mido.MidiFile(ticks_per_beat=480)
        track_midi = mido.MidiTrack()
        mid.tracks.append(track_midi)
        
        # Set tempo
        tempo = mido.bpm2tempo(float(bpm))
        track_midi.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
        
        # Track name
        track_name = getattr(track, 'name', 'Track')
        track_midi.append(mido.MetaMessage('track_name', name=str(track_name), time=0))
        
        # Collect all notes from all clips
        def beat_to_ticks(b: float) -> int:
            return int(round(b * 480))
        
        all_events = []
        
        for clip in track_clips:
            clip_start = float(getattr(clip, 'start_beats', 0.0))
            notes = midi_notes_map.get(clip.id, [])
            
            for n in notes:
                try:
                    pitch = int(getattr(n, 'pitch'))
                    note_start_b = float(getattr(n, 'start_beats'))
                    length_b = float(getattr(n, 'length_beats'))
                    vel = int(getattr(n, 'velocity', 96))
                except Exception:
                    continue
                
                # Absolute timeline position
                abs_start = clip_start + note_start_b
                abs_end = abs_start + length_b
                
                all_events.append((abs_start, True, pitch, vel))
                all_events.append((abs_end, False, pitch, 0))
        
        # Sort by time
        all_events.sort(key=lambda e: (e[0], 0 if not e[1] else 1))
        
        # Write events
        last_tick = 0
        for beat, is_on, pitch, vel in all_events:
            tick = beat_to_ticks(beat)
            delta = max(0, tick - last_tick)
            last_tick = tick
            
            if is_on:
                track_midi.append(mido.Message('note_on', channel=0, note=pitch, velocity=vel, time=delta))
            else:
                track_midi.append(mido.Message('note_off', channel=0, note=pitch, velocity=0, time=delta))
        
        # End of track
        if all_events:
            final_beat = max(e[0] for e in all_events) + 1.0
        else:
            final_beat = 4.0
        
        final_tick = beat_to_ticks(final_beat)
        track_midi.append(mido.MetaMessage('end_of_track', time=max(0, final_tick - last_tick)))
        
        # Save
        mid.save(str(output_path))
        return True
        
    except Exception as e:
        print(f"MIDI track export failed: {e}")
        return False
