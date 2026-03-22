"""Project domain model (v0.0.9).

v0.0.5: MIDI notes per clip (Piano Roll).
v0.0.7: Clip Launcher mapping slot_key -> clip_id.
v0.0.8: Clip Launcher settings (quantize/mode).
v0.0.9: Audio clip params (gain/pan/pitch + per-clip loop/slices) for AudioEventEditor.

Persistence: JSON via dataclasses.asdict in file_manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from .midi import MidiNote


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class MediaItem:
    kind: str  # "audio" | "midi"
    path: str
    label: str = ""
    id: str = field(default_factory=lambda: new_id("media"))


# v0.0.20.639: Comp Region — defines which take provides audio for a beat range
@dataclass
class CompRegion:
    """A region in a comp that references a specific take clip.

    Used by the Comp-Tool to define which take is active for which beat range.
    Multiple CompRegions on a track form the complete comp.
    """
    start_beat: float = 0.0
    end_beat: float = 4.0
    source_clip_id: str = ""  # clip.id of the take to use
    crossfade_beats: float = 0.0  # crossfade at boundaries


# v0.0.20.641: Warp Marker (AP3 Phase 3A)
@dataclass
class WarpMarker:
    """A warp marker that maps a position in the source audio to a position
    in the output timeline. Moving dst_beat while keeping src_beat fixed
    causes elastic time-stretching of the audio between adjacent markers.

    src_beat: Position in the original audio (source space, in beats).
    dst_beat: Position in the output timeline (destination space, in beats).
    When src_beat == dst_beat → no stretching at this point.
    When dst_beat > src_beat → audio is stretched (slowed down).
    When dst_beat < src_beat → audio is compressed (sped up).
    """
    src_beat: float = 0.0
    dst_beat: float = 0.0
    is_anchor: bool = False  # anchor markers can't be moved (start/end)


@dataclass
class Track:
    id: str = field(default_factory=lambda: new_id("trk"))
    kind: str = "audio"  # "audio" | "instrument" | "bus" | "master" | "fx" | "group"
    name: str = "Track"
    muted: bool = False
    solo: bool = False
    automation_mode: str = "off"  # off|read|write
    volume: float = 0.8
    pan: float = 0.0
    record_arm: bool = False

    # Audio I/O routing (JACK-first): choose which stereo input pair is used for
    # monitoring/recording (1..N). Output pair is reserved for future submix/bus routing.
    input_pair: int = 1
    output_pair: int = 1
    monitor: bool = False

    # v0.0.20.608: MIDI Input Routing (Bitwig-Style)
    # Determines which MIDI source feeds this track for monitoring & recording.
    # Values: "No input" | "All ins" | "Computer Keyboard" | specific port name | "track:<track_id>"
    # Default "" means auto: instrument/drum tracks → "All ins", audio/fx/master → "No input".
    midi_input: str = ""

    # v0.0.20.609: MIDI Channel Filter (Bitwig-Style)
    # Which MIDI channels this track accepts. -1 = Omni (all channels), 0-15 = specific channel.
    midi_channel_filter: int = -1

    # v0.0.20.518: Send-FX routing (Bitwig-Style)
    # Each entry: {"target_track_id": "trk_...", "amount": 0.5, "pre_fader": False}
    # amount: 0.0=off .. 1.0=full send. pre_fader: send before or after track fader.
    sends: list = field(default_factory=list)

    # v0.0.20.46: Plugin-based instrument routing (Pro-DAW-Style!)
    # This determines which instrument engine processes MIDI clips on this track
    # Options: "sampler", "drum_machine", "sf2", None (no instrument)
    # If None but sf2_path is set: auto-detected as "sf2" for backwards compatibility
    plugin_type: Optional[str] = None
    # v0.0.20.80: Instrument Power/Bypass — when False, the instrument is bypassed
    # (no MIDI dispatch, no SF2 render, no pull-source audio). Track stays visible.
    instrument_enabled: bool = True
    # Instrument-spezifischer Persistenz-Speicher (Sampler/Drum/etc.)
    # Wird automatisch in der Projektdatei gespeichert (dataclass -> asdict).
    instrument_state: Dict[str, Any] = field(default_factory=dict)

    # Phase 3: SF2 instrument state (kept for backwards compatibility)
    # When plugin_type="sf2" or plugin_type=None with sf2_path set, these are used
    sf2_path: Optional[str] = None
    sf2_bank: int = 0
    sf2_preset: int = 0
    midi_channel: int = 0

    # v0.0.20.56: Device Chains (Engine-First)
    # Note-FX Chain: MIDI/Notenbearbeitung vor dem Instrument
    note_fx_chain: dict = field(default_factory=lambda: {"devices": []})

    # Audio-FX Chain: serielle Effekte nach dem Instrument (mit Dry/Wet + Wet Gain)
    audio_fx_chain: dict = field(default_factory=lambda: {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []})

    # v0.0.20.254: Safe organisational track grouping (UI/project-level only).
    # This is intentionally NOT audio bus routing yet; it is used for
    # selection/organisation without touching the engine.
    track_group_id: str = ""
    track_group_name: str = ""

    # v0.0.20.639: Take-Lanes / Comping (AP2 Phase 2D)
    take_lanes_visible: bool = False  # show take lanes below this track in arranger
    take_lanes_height: int = 40       # pixel height per take lane (compact)
    # v0.0.20.640: Comp regions — which take plays which beat range
    comp_regions: List[Dict[str, Any]] = field(default_factory=list)

    # v0.0.20.641: Sidechain Routing (AP5 Phase 5B)
    # Which track feeds the sidechain input for FX plugins on this track.
    # "" or None = no sidechain. Value is a track_id (e.g. "trk_abc123").
    # Used by compressor/gate/ducker plugins that need a key signal.
    sidechain_source_id: str = ""

    # v0.0.20.641: Channel Configuration (AP5 Phase 5C)
    # "stereo" (default) | "mono" — determines track width for rendering.
    # Mono tracks: single channel → panned to stereo at output.
    channel_config: str = "stereo"

    # v0.0.20.641: Output Routing (AP5 Phase 5C)
    # Where this track's audio goes after fader. "" = Master bus (default).
    # Can be set to a group/bus track_id for submix routing.
    # Master track ignores this field.
    output_target_id: str = ""

    # v0.0.20.650: Multi-Output Plugin Routing (AP5 Phase 5C)
    # For plugins with multiple stereo outputs (e.g. drum samplers, multi-timbral synths).
    # Maps plugin output index (0-based) to a target track_id.
    # Output 0 always goes to this track's own mixer strip (implicit).
    # Example: {1: "trk_abc", 2: "trk_def"} → output pair 1 → trk_abc, pair 2 → trk_def
    # Empty dict = single-output mode (default).
    plugin_output_routing: Dict[int, str] = field(default_factory=dict)
    # How many stereo output pairs the plugin provides (0 = auto-detect, 1 = mono/stereo)
    plugin_output_count: int = 0

    # v0.0.20.650: MPE (MIDI Polyphonic Expression) Config (AP6 Phase 6B)
    # Stored as dict for JSON serialization. Use MPEConfig.from_dict() / .to_dict().
    # Keys: mpe_enabled, lower_zone, upper_zone (see audio/mpe_support.py)
    mpe_config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AudioEvent:
    """Non-destructive segment inside an audio clip.

    Timeline inside the clip is expressed in beats (quarter-note beats).
    - start_beats: position inside clip content (0..clip.length_beats)
    - length_beats: duration of this segment
    - source_offset_beats: offset inside the underlying source (beats) relative to clip offset
      (placeholder until we add sample-accurate seconds based editing).
    """
    id: str = field(default_factory=lambda: new_id("aev"))
    start_beats: float = 0.0
    length_beats: float = 0.0
    source_offset_beats: float = 0.0
    reversed: bool = False  # per-event non-destructive reverse (v0.0.20.160)


@dataclass
class Clip:
    id: str = field(default_factory=lambda: new_id("clip"))
    kind: str = "audio"  # "audio" | "midi"
    track_id: str = ""
    start_beats: float = 0.0
    length_beats: float = 4.0
    # content offset inside source (for left trim/extend)
    offset_beats: float = 0.0
    offset_seconds: float = 0.0
    label: str = "Clip"
    media_id: Optional[str] = None
    source_path: Optional[str] = None

    # Optional: if the clip's source tempo is known (e.g. parsed from the
    # filename "*_150bpm.wav"), playback can be time-scaled to match the project BPM.
    source_bpm: Optional[float] = None
    # Optional: used for simple grouping (move/edit multiple clips together)
    group_id: str = ""

    # --- Audio Clip non-destructive params (used by AudioEventEditor / Launcher)
    gain: float = 1.0          # linear (1.0 = unity)
    pan: float = 0.0           # -1.0 (L) .. 0.0 .. +1.0 (R)
    pitch: float = 0.0         # semitones
    formant: float = 0.0       # semitones (placeholder)
    stretch: float = 1.0       # time-stretch factor (1.0 = original)
    # v0.0.20.641: Stretch algorithm mode (AP3 Phase 3B)
    # "tones" = phase vocoder / Essentia (default, melodic material)
    # "beats" = slice-based (drums/percussion, preserves transients)
    # "texture" = granular (ambient/pads, smeared)
    # "repitch" = simple resampling (changes pitch, no stretch)
    # "complex" = highest quality phase vocoder (CPU-intensive)
    stretch_mode: str = "tones"
    reversed: bool = False     # non-destructive reverse playback
    muted: bool = False        # non-destructive clip mute
    fade_in_beats: float = 0.0   # fade-in length in beats (0 = no fade)
    fade_out_beats: float = 0.0  # fade-out length in beats (0 = no fade)

    # Per-clip loop region in beats (relative to clip start inside its content)
    # If loop_end_beats <= loop_start_beats -> treated as "full clip length"
    loop_start_beats: float = 0.0
    loop_end_beats: float = 0.0

    # Non-destructive slice markers (beats relative to clip content start)
    audio_slices: List[float] = field(default_factory=list)
    # Optional transient/onset markers (beats relative to clip content start)
    onsets: List[float] = field(default_factory=list)

    # Phase 2: non-destructive events inside the audio clip (derived from slices if missing)
    audio_events: List[AudioEvent] = field(default_factory=list)

    # Per-clip automation envelopes (Bitwig/Ableton style)
    # Dict of param_name -> list of breakpoints [{"beat": float, "value": float}, ...]
    # param_name: "gain", "pan", "pitch", "formant"
    # value: 0.0..1.0 normalized (mapped to param range by editor)
    clip_automation: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)

    # Warp/Stretch markers: list of beat positions (float)
    # Used by audio editor to define custom warp points for time-stretching
    stretch_markers: List[dict] = field(default_factory=list)

    # Render/Bounce metadata (forward-compatible, non-destructive history)
    # Used by Consolidate/Bounce to store source references + flags + ranges.
    render_meta: Dict[str, Any] = field(default_factory=dict)

    # Clip exists only in Clip-Launcher (not shown on Arranger timeline)
    launcher_only: bool = False

    # v0.0.20.639: Take-Lanes / Comping (AP2 Phase 2D)
    # All clips sharing the same take_group_id are alternative recordings
    # of the same region. take_index orders them (0=first, 1=second, ...).
    # is_comp_active=True means this take (or a region of it) is used in the comp.
    take_group_id: str = ""     # "" = not part of a take group
    take_index: int = 0         # ordering within the take group
    is_comp_active: bool = True # True = this take is the "active" one for playback

    # --- Bitwig-Style per-Clip Launcher Properties (v0.0.20.147) ---
    # Per-clip start quantize: "Project" (use global), "Off", "1 Bar", "1 Beat",
    # "1/2", "1/4", "1/8", "1/16"
    launcher_start_quantize: str = "Project"
    # ALT start quantize (Bitwig: held with modifier key)
    launcher_alt_start_quantize: str = "Project"
    # Playback mode: "Trigger ab Start", "Legato vom Clip", "Legato vom Projekt"
    launcher_playback_mode: str = "Trigger ab Start"
    # ALT playback mode
    launcher_alt_playback_mode: str = "Trigger ab Start"
    # Release action: "Fortsetzen", "Stopp", "Zurück", "Nächste Aktion"
    launcher_release_action: str = "Stopp"
    # ALT release action
    launcher_alt_release_action: str = "Stopp"
    # Q auf Loop (quantize on loop boundary): True/False
    launcher_q_on_loop: bool = True
    # Nächste Aktion (Next Action): "Stopp", "Nächsten abspielen", "Vorherigen abspielen",
    # "Ersten abspielen", "Letzten abspielen", "Zufälligen abspielen", "Anderen abspielen",
    # "Round-robin", "Zum Arrangement zurückkehren"
    launcher_next_action: str = "Stopp"
    # v0.0.20.604: Follow Action B + Probability (Ableton-style dual actions)
    launcher_next_action_b: str = "Stopp"
    launcher_next_action_probability: int = 100  # % chance for action A (0-100)
    launcher_next_action_count: int = 1
    # Shuffle amount (0.0 - 1.0)
    launcher_shuffle: float = 0.0
    # Accent strength (0.0 - 1.0)
    launcher_accent: float = 0.0
    # Seed / start value: "Random" or fixed int
    launcher_seed: str = "Random"
    # Clip color index (0-15, maps to color palette)
    launcher_color: int = 0
    # v0.0.20.604: Crossfade ms for legato transitions
    launcher_crossfade_ms: float = 10.0
    # v0.0.20.604: Record mode (Overdub / Replace)
    launcher_record_mode: str = "Overdub"
    # v0.0.20.604: Record quantize (Off / 1/16 / 1/8 / 1/4 / 1 Bar)
    launcher_record_quantize: str = "Off"
    # v0.0.20.604: Alt-clips for variations (list of clip IDs)
    launcher_alt_clips: List[str] = field(default_factory=list)


@dataclass
class Project:
    # Keep this in sync with VERSION / pydaw.version.__version__ for new projects.
    version: str = '0.0.20.583'
    name: str = "Neues Projekt"
    created_utc: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))
    modified_utc: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    sample_rate: int = 48000
    bpm: float = 120.0
    time_signature: str = "4/4"
    snap_division: str = "1/16"
    # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
    punch_enabled: bool = False
    punch_in_beat: float = 4.0
    punch_out_beat: float = 16.0
    pre_roll_bars: int = 0
    post_roll_bars: int = 0
    automation_lanes: dict = None  # legacy/simple lanes
    # v0.0.20.175: Enhanced AutomationManager persistence (parameter_id -> lane dict)
    automation_manager_lanes: Dict[str, Any] = field(default_factory=dict)
    # v0.0.20.349: Arranger/UI state for collapsed organisational groups.
    arranger_collapsed_group_ids: List[str] = field(default_factory=list)
    midi_mappings: list = None  # placeholder: list of mappings

    media: List[MediaItem] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    clips: List[Clip] = field(default_factory=list)

    # clip_id -> notes
    midi_notes: Dict[str, List[MidiNote]] = field(default_factory=dict)

    # slot_key -> clip_id
    clip_launcher: Dict[str, str] = field(default_factory=dict)
    # v0.0.20.599: Scene names for Clip Launcher (scene_index str -> name)
    launcher_scene_names: Dict[str, str] = field(default_factory=dict)
    # v0.0.20.604: Scene colors (scene_index str -> color index 0-11)
    # v0.0.20.604: Scene colors (scene_index str -> color_index int)
    launcher_scene_colors: Dict[str, int] = field(default_factory=dict)
    # v0.0.20.604: MIDI Controller Mapping (list of {cc, channel, action, target} dicts)
    launcher_midi_mapping: List[Dict[str, Any]] = field(default_factory=list)
    # v0.0.20.604: Audio recording settings
    launcher_audio_input: str = "Default"  # audio input device/channel
    launcher_punch_in: bool = False
    launcher_punch_out: bool = False
    launcher_monitoring: bool = True  # input monitoring during recording
    # v0.0.20.604: Scene crossfade (ms, 0=instant)
    launcher_scene_crossfade_ms: float = 0.0

    # Clip Launcher settings (placeholder)
    launcher_quantize: str = "1 Bar"  # Off | 1 Beat | 1 Bar
    launcher_mode: str = "Trigger"    # Trigger | Toggle | Gate

    # Ghost Notes / Layered Editing state (persisted)
    # JSON-safe dict produced by LayerManager.to_dict()
    ghost_layers: Dict[str, Any] = field(default_factory=dict)
    # Notation marks / annotations (sticky notes, rests, ornaments, ties, etc.)
    # Stored as list of JSON-safe dicts. Rendering/editor can interpret these.
    notation_marks: List[Dict[str, Any]] = field(default_factory=list)


    def __post_init__(self) -> None:
        if not self.tracks:
            self.tracks = [Track(kind="master", name="Master")]

    

    def tracks_by_id(self) -> Dict[str, Track]:
        """Convenience: map track_id -> Track.

        Used across UI/Engine to avoid repeated linear scans.
        """
        return {str(getattr(t, 'id', '')): t for t in (self.tracks or []) if str(getattr(t, 'id', ''))}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Project":
        # Robust loader: ignore unknown keys (forward-compatible) and convert nested dataclasses.
        from dataclasses import fields as _dc_fields

        media = [MediaItem(**m) for m in d.get("media", []) if isinstance(m, dict)]

        # Filter Track keys
        track_keys = {f.name for f in _dc_fields(Track)}
        tracks = []
        for td in d.get("tracks", []) or []:
            if not isinstance(td, dict):
                continue
            td2 = {k: v for k, v in td.items() if k in track_keys}
            tracks.append(Track(**td2))

        # Convert Clip + AudioEvents
        clip_keys = {f.name for f in _dc_fields(Clip)}
        clips = []
        for cd in d.get("clips", []) or []:
            if not isinstance(cd, dict):
                continue
            # audio_events may be list[dict]
            evs = cd.get("audio_events", None)
            if isinstance(evs, list):
                conv = []
                for e in evs:
                    if isinstance(e, dict):
                        try:
                            conv.append(AudioEvent(**e))
                        except Exception:
                            # best-effort: ignore malformed
                            continue
                cd = dict(cd)
                cd["audio_events"] = conv
            cd2 = {k: v for k, v in cd.items() if k in clip_keys}
            clips.append(Clip(**cd2))

        midi_notes: Dict[str, List[MidiNote]] = {}
        # Robust loader: filter unknown MidiNote keys (forward compatible)
        note_keys = {f.name for f in _dc_fields(MidiNote)}
        raw_notes = d.get("midi_notes", {}) or {}
        if isinstance(raw_notes, dict):
            for clip_id, notes in raw_notes.items():
                nl: List[MidiNote] = []
                if isinstance(notes, list):
                    for n in notes:
                        if isinstance(n, dict):
                            try:
                                n2 = {k: v for k, v in n.items() if k in note_keys}
                                nl.append(MidiNote(**n2).clamp())
                            except Exception:
                                continue
                midi_notes[str(clip_id)] = nl

        clip_launcher: Dict[str, str] = {}
        raw_cl = d.get("clip_launcher", {}) or {}
        if isinstance(raw_cl, dict):
            clip_launcher = {str(k): str(v) for k, v in raw_cl.items() if v}

        lq = str(d.get("launcher_quantize", "1 Bar"))
        lm = str(d.get("launcher_mode", "Trigger"))

        obj = cls(
            version=str(d.get("version", "0.0.19.7.52")),
            name=str(d.get("name", "Projekt")),
            created_utc=str(d.get("created_utc", "")),
            modified_utc=str(d.get("modified_utc", "")),
            sample_rate=int(d.get("sample_rate", 48000)),
            bpm=float(d.get("bpm", 120.0)),
            time_signature=str(d.get("time_signature", "4/4")),
            snap_division=str(d.get("snap_division", "1/16")),
            punch_enabled=bool(d.get("punch_enabled", False)),
            punch_in_beat=float(d.get("punch_in_beat", 4.0)),
            punch_out_beat=float(d.get("punch_out_beat", 16.0)),
            pre_roll_bars=int(d.get("pre_roll_bars", 0)),
            post_roll_bars=int(d.get("post_roll_bars", 0)),
            automation_lanes=dict(d.get("automation_lanes", {})) if d.get("automation_lanes") is not None else {},
            automation_manager_lanes=dict(d.get("automation_manager_lanes", {})) if isinstance(d.get("automation_manager_lanes", {}), dict) else {},
            arranger_collapsed_group_ids=[str(x) for x in (d.get("arranger_collapsed_group_ids", []) or []) if str(x)],
            midi_mappings=list(d.get("midi_mappings", [])) if d.get("midi_mappings") is not None else [],
            media=media,
            tracks=tracks,
            clips=clips,
            midi_notes=midi_notes,
            clip_launcher=clip_launcher,
            launcher_scene_names={str(k): str(v) for k, v in (d.get("launcher_scene_names", {}) or {}).items()} if isinstance(d.get("launcher_scene_names", {}), dict) else {},
            launcher_scene_colors={str(k): int(v) for k, v in (d.get("launcher_scene_colors", {}) or {}).items()} if isinstance(d.get("launcher_scene_colors", {}), dict) else {},
            launcher_quantize=lq,
            launcher_mode=lm,
            ghost_layers=dict(d.get("ghost_layers", {})) if isinstance(d.get("ghost_layers", {}), dict) else {},
            notation_marks=[m for m in (d.get("notation_marks", []) or []) if isinstance(m, dict)],
        )
        if not obj.tracks:
            obj.tracks = [Track(kind="master", name="Master")]
        return obj
