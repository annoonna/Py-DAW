#!/usr/bin/env python3
"""
Fix Old Projects - Convert Horizontal Clips to Vertical Layout

This script fixes projects created BEFORE v0.0.19.5.1.43 where duplicate clips
were placed horizontally (side-by-side) instead of vertically (in new tracks).

Usage:
    python3 fix_old_project.py path/to/project.pydaw.json

What it does:
    1. Detects clips that are horizontal (same track, different start_beats)
    2. Creates new tracks for each horizontal clip
    3. Moves clips to new tracks (vertical layout)
    4. Preserves MIDI notes and clip properties
    5. Saves backup before modifying

Author: Claude-Sonnet-4.5
Date: 2026-02-03
Version: v0.0.19.5.1.43
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import uuid

def fix_project(project_path: Path):
    """Fix old project by converting horizontal clips to vertical layout."""
    
    if not project_path.exists():
        print(f"ERROR: Project file not found: {project_path}")
        return False
    
    # Load project
    try:
        with open(project_path, 'r', encoding='utf-8') as f:
            project = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not load project: {e}")
        return False
    
    # Create backup
    backup_path = project_path.with_suffix('.pydaw.json.backup')
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(project, f, indent=2)
        print(f"✅ Backup created: {backup_path}")
    except Exception as e:
        print(f"ERROR: Could not create backup: {e}")
        return False
    
    # Group clips by track
    clips_by_track = defaultdict(list)
    for clip in project.get('clips', []):
        clips_by_track[clip['track_id']].append(clip)
    
    # Find tracks with multiple clips (potential horizontal layout)
    tracks_to_fix = {}
    for track_id, clips in clips_by_track.items():
        if len(clips) > 1:
            # Sort by start_beats
            clips_sorted = sorted(clips, key=lambda c: c['start_beats'])
            tracks_to_fix[track_id] = clips_sorted
    
    if not tracks_to_fix:
        print("✅ No horizontal clips found - project is already OK!")
        return True
    
    print(f"\n🔍 Found {len(tracks_to_fix)} tracks with multiple clips:")
    for track_id, clips in tracks_to_fix.items():
        print(f"   Track {track_id}: {len(clips)} clips")
    
    # Ask for confirmation
    response = input("\n⚠️  Convert to vertical layout? (y/n): ")
    if response.lower() != 'y':
        print("Aborted.")
        return False
    
    # Fix: Create new tracks and move clips
    new_tracks = []
    tracks_list = project.get('tracks', [])
    master_track = next((t for t in tracks_list if t.get('kind') == 'master'), None)
    other_tracks = [t for t in tracks_list if t.get('kind') != 'master']
    
    for track_id, clips in tracks_to_fix.items():
        # Keep first clip in original track
        first_clip = clips[0]
        print(f"\n✅ Track {track_id}: Keeping first clip at {first_clip['start_beats']}")
        
        # Create new tracks for remaining clips
        orig_track = next((t for t in other_tracks if t['id'] == track_id), None)
        if not orig_track:
            continue
        
        orig_idx = other_tracks.index(orig_track)
        
        for i, clip in enumerate(clips[1:], start=1):
            # Create new track
            new_track_id = str(uuid.uuid4())
            new_track = {
                'id': new_track_id,
                'kind': orig_track['kind'],
                'name': f"{orig_track['name']} (Fixed {i})",
                'volume': orig_track.get('volume', 1.0),
                'pan': orig_track.get('pan', 0.0),
                'mute': orig_track.get('mute', False),
                'solo': orig_track.get('solo', False),
            }
            
            # Insert after original track
            other_tracks.insert(orig_idx + i, new_track)
            new_tracks.append(new_track)
            
            # Move clip to new track (keep same start_beats = vertical!)
            clip['track_id'] = new_track_id
            print(f"   → Moved clip (was at {clip['start_beats']}) to new track {new_track_id}")
    
    # Rebuild tracks list
    if master_track:
        project['tracks'] = other_tracks + [master_track]
    else:
        project['tracks'] = other_tracks
    
    # Save fixed project
    try:
        with open(project_path, 'w', encoding='utf-8') as f:
            json.dump(project, f, indent=2)
        print(f"\n✅ Project fixed! Created {len(new_tracks)} new tracks.")
        print(f"   Backup: {backup_path}")
        print(f"   Fixed:  {project_path}")
    except Exception as e:
        print(f"ERROR: Could not save project: {e}")
        # Restore from backup
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup = json.load(f)
            with open(project_path, 'w', encoding='utf-8') as f:
                json.dump(backup, f, indent=2)
            print("Restored from backup.")
        except Exception:
            pass
        return False
    
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 fix_old_project.py path/to/project.pydaw.json")
        sys.exit(1)
    
    project_path = Path(sys.argv[1])
    success = fix_project(project_path)
    sys.exit(0 if success else 1)
