"""High-level file management.

This module binds together:
- project JSON persistence
- media import/export helpers for audio and MIDI
- *project packaging*: when saving, all referenced media is copied into a
  project-local "media/" folder and paths are stored *relative* to the project.

UI should call the public functions via a background worker to avoid GUI stalls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import shutil
import os

from pydaw.model.project import Project, MediaItem, Clip
from .project_io import save_project, load_project
from .audio_formats import import_audio, export_audio
from .midi_io import export_midi


@dataclass
class ProjectContext:
    project: Project
    path: Optional[Path] = None
    media_dir: Optional[Path] = None

    def resolve_media_dir(self) -> Path:
        if self.media_dir:
            return self.media_dir
        if self.path:
            return self.path.parent / "media"
        # fallback for unsaved projects (temporary)
        return Path.cwd() / "media"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _unique_dest(dest: Path) -> Path:
    """Return a non-existing path by adding _1/_2 suffixes if needed."""
    if not dest.exists():
        return dest
    stem = dest.stem
    suf = dest.suffix
    for i in range(1, 10_000):
        cand = dest.with_name(f"{stem}_{i}{suf}")
        if not cand.exists():
            return cand
    # extremely unlikely
    return dest.with_name(f"{stem}_{os.getpid()}{suf}")  # type: ignore[name-defined]


def _copy_into_media(src: Path, media_dir: Path) -> Path:
    media_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_dest(media_dir / src.name)
    if dest.resolve() != src.resolve():
        shutil.copy2(str(src), str(dest))
    return dest


def _relpath_from_root(root_dir: Path, abs_path: Path) -> str:
    try:
        return str(abs_path.resolve().relative_to(root_dir.resolve()))
    except Exception:
        # fallback: keep filename in media
        return str(Path("media") / abs_path.name)


def _package_project_media(ctx: ProjectContext, project_file: Path) -> None:
    """Copy all referenced media into <project_root>/media and store relative paths.

    This makes a project folder portable: moving the folder keeps links valid.
    Bitwig/Ableton-style: ALL assets (audio samples, SF2, instrument states) are packaged.
    """
    root_dir = project_file.parent
    media_dir = root_dir / "media"
    ctx.media_dir = media_dir

    # 1) Media items
    for item in list(ctx.project.media):
        p = Path(item.path)
        abs_p = p if p.is_absolute() else (root_dir / p)

        if abs_p.exists():
            if _is_within(abs_p, root_dir):
                # already inside project: store relative
                item.path = _relpath_from_root(root_dir, abs_p)
            else:
                # outside: copy into media
                copied = _copy_into_media(abs_p, media_dir)
                item.path = str(Path("media") / copied.name)
        else:
            # missing file: keep path but do not crash
            # (UI can surface warnings later)
            item.path = str(p)

    # 2) Clips: ensure audio clips reference the packaged media (if possible)
    media_by_id = {m.id: m for m in ctx.project.media}
    for clip in list(ctx.project.clips):
        if not getattr(clip, "media_id", None):
            continue
        mi = media_by_id.get(str(clip.media_id))
        if not mi:
            continue

        # For portability store relative clip.source_path as well
        if clip.kind in ("audio", "midi"):
            clip.source_path = str(mi.path)

    # 3) SF2 files: copy into media/ and make paths relative
    for track in list(ctx.project.tracks):
        sf2 = getattr(track, "sf2_path", None)
        if sf2:
            p = Path(sf2)
            abs_p = p if p.is_absolute() else (root_dir / p)
            if abs_p.exists():
                if _is_within(abs_p, root_dir):
                    track.sf2_path = _relpath_from_root(root_dir, abs_p)
                else:
                    copied = _copy_into_media(abs_p, media_dir)
                    track.sf2_path = str(Path("media") / copied.name)

    # 4) Instrument state: rewrite sample paths to be relative
    #    Handles: sampler, drum_machine, bach_orgel and future instruments
    for track in list(ctx.project.tracks):
        ist = getattr(track, "instrument_state", None)
        if not isinstance(ist, dict):
            continue

        # --- Sampler ---
        sampler_st = ist.get("sampler")
        if isinstance(sampler_st, dict):
            _package_instrument_sample_path(sampler_st, "sample_path", root_dir, media_dir)
            # Also handle engine.sample_name
            eng = sampler_st.get("engine")
            if isinstance(eng, dict):
                _package_instrument_sample_path(eng, "sample_name", root_dir, media_dir)

        # --- Drum Machine ---
        drum_st = ist.get("drum_machine")
        if isinstance(drum_st, dict):
            for slot in drum_st.get("slots", []):
                if isinstance(slot, dict):
                    _package_instrument_sample_path(slot, "sample_path", root_dir, media_dir)
                    # Nested sampler engine
                    nested_sampler = slot.get("sampler")
                    if isinstance(nested_sampler, dict):
                        _package_instrument_sample_path(nested_sampler, "sample_name", root_dir, media_dir)


def _package_instrument_sample_path(state_dict: dict, key: str, root_dir: Path, media_dir: Path) -> None:
    """Helper: copy a sample referenced by state_dict[key] into media/ and store relative path."""
    val = state_dict.get(key)
    if not val or not isinstance(val, str):
        return
    p = Path(val)
    abs_p = p if p.is_absolute() else (root_dir / p)
    if not abs_p.exists():
        return
    if _is_within(abs_p, root_dir):
        state_dict[key] = _relpath_from_root(root_dir, abs_p)
    else:
        copied = _copy_into_media(abs_p, media_dir)
        state_dict[key] = str(Path("media") / copied.name)


def _resolve_project_paths_after_load(project: Project, project_file: Path) -> None:
    """After loading, resolve relative media paths into absolute paths for runtime."""
    root_dir = project_file.parent

    # Media
    for m in project.media:
        p = Path(m.path)
        if not p.is_absolute():
            m.path = str((root_dir / p).resolve())

    # Clips
    media_by_id = {m.id: m for m in project.media}
    for c in project.clips:
        sp = getattr(c, "source_path", None)
        if sp:
            p = Path(sp)
            if not p.is_absolute():
                c.source_path = str((root_dir / p).resolve())
        if getattr(c, "media_id", None) and c.kind == "audio":
            mi = media_by_id.get(str(c.media_id))
            if mi:
                c.source_path = str(Path(mi.path))

    # SF2 paths on tracks
    for t in project.tracks:
        sf2 = getattr(t, "sf2_path", None)
        if sf2:
            p = Path(sf2)
            if not p.is_absolute():
                t.sf2_path = str((root_dir / p).resolve())

    # Instrument state sample paths
    _resolve_instrument_state_paths(project, root_dir)


def resolve_loaded_media_paths(project: Project, root_dir: Path) -> None:
    """v0.0.20.75: Public API to resolve media paths after loading a project/snapshot.
    
    Called by ProjectService when loading snapshots where the project_file path
    might differ from the actual root directory.
    """
    # Media
    for m in project.media:
        p = Path(m.path)
        if not p.is_absolute():
            m.path = str((root_dir / p).resolve())

    # Clips
    media_by_id = {m.id: m for m in project.media}
    for c in project.clips:
        sp = getattr(c, "source_path", None)
        if sp:
            p = Path(sp)
            if not p.is_absolute():
                c.source_path = str((root_dir / p).resolve())
        if getattr(c, "media_id", None) and c.kind == "audio":
            mi = media_by_id.get(str(c.media_id))
            if mi:
                c.source_path = str(Path(mi.path))

    # SF2 paths on tracks
    for t in project.tracks:
        sf2 = getattr(t, "sf2_path", None)
        if sf2:
            p = Path(sf2)
            if not p.is_absolute():
                t.sf2_path = str((root_dir / p).resolve())

    # Instrument state sample paths
    _resolve_instrument_state_paths(project, root_dir)


def _resolve_instrument_state_paths(project: Project, root_dir: Path) -> None:
    """Resolve relative sample paths inside track.instrument_state to absolute paths.

    v0.0.20.131: Bitwig/Ableton-style — all instrument samples are packaged
    into the project folder. After loading, relative paths must be resolved.
    """
    for track in project.tracks:
        ist = getattr(track, "instrument_state", None)
        if not isinstance(ist, dict):
            continue

        # --- Sampler ---
        sampler_st = ist.get("sampler")
        if isinstance(sampler_st, dict):
            _resolve_state_path(sampler_st, "sample_path", root_dir)
            eng = sampler_st.get("engine")
            if isinstance(eng, dict):
                _resolve_state_path(eng, "sample_name", root_dir)

        # --- Drum Machine ---
        drum_st = ist.get("drum_machine")
        if isinstance(drum_st, dict):
            for slot in drum_st.get("slots", []):
                if isinstance(slot, dict):
                    _resolve_state_path(slot, "sample_path", root_dir)
                    nested_sampler = slot.get("sampler")
                    if isinstance(nested_sampler, dict):
                        _resolve_state_path(nested_sampler, "sample_name", root_dir)


def _resolve_state_path(state_dict: dict, key: str, root_dir: Path) -> None:
    """Helper: resolve a relative path inside a state dict to absolute."""
    val = state_dict.get(key)
    if not val or not isinstance(val, str):
        return
    p = Path(val)
    if not p.is_absolute():
        resolved = (root_dir / p).resolve()
        state_dict[key] = str(resolved)


def new_project(name: str = "Neues Projekt") -> ProjectContext:
    p = Project(name=name)
    return ProjectContext(project=p, path=None, media_dir=None)


def open_project(path: Path) -> ProjectContext:
    proj = load_project(path)
    _resolve_project_paths_after_load(proj, path)
    ctx = ProjectContext(project=proj, path=path, media_dir=path.parent / "media")
    return ctx


def save_project_to(path: Path, ctx: ProjectContext) -> ProjectContext:
    """Save a project and package media into its folder."""
    # Ensure project has the current version string
    try:
        from pydaw.version import __version__  # local import
        ctx.project.version = str(__version__)
    except Exception:
        pass

    _package_project_media(ctx, path)
    saved_path = save_project(path, ctx.project)
    ctx.path = saved_path
    ctx.media_dir = saved_path.parent / "media"
    return ctx


def import_audio_to_project(audio_path: Path, ctx: ProjectContext) -> MediaItem:
    dest = import_audio(audio_path, ctx.resolve_media_dir())
    item = MediaItem(kind="audio", path=str(dest), label=dest.stem)
    ctx.project.media.append(item)
    return item


def import_midi_to_project(midi_path: Path, ctx: ProjectContext) -> MediaItem:
    # store a project-local copy
    ctx.resolve_media_dir().mkdir(parents=True, exist_ok=True)
    dest = ctx.resolve_media_dir() / midi_path.name
    if dest.resolve() != midi_path.resolve():
        dest.write_bytes(midi_path.read_bytes())
    item = MediaItem(kind="midi", path=str(dest), label=dest.stem)
    ctx.project.media.append(item)
    return item


def export_audio_from_file(input_audio: Path, output_path: Path) -> Path:
    return export_audio(input_audio, output_path)


def export_midi_data(data: dict, output_path: Path) -> Path:
    return export_midi(data, output_path)
