"""Audio import/export helpers (v0.0.3).

Supported targets:
- WAV, FLAC, OGG: prefer soundfile if available
- MP3, MP4/AAC: prefer pydub (ffmpeg) if available
- Fallback: copy-through if conversion toolchain is missing

This module is intentionally defensive: it never blocks the GUI; UI should call
these via a worker thread (see ProjectService).
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional

SUPPORTED_EXPORT = {
    "wav": "WAV",
    "flac": "FLAC",
    "ogg": "OGG/Vorbis",
    "mp3": "MP3",
    "m4a": "MP4/AAC (m4a)",
    "aac": "AAC",
}


class AudioFormatError(RuntimeError):
    pass


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def export_audio(input_path: Path, output_path: Path) -> Path:
    """Convert/copy an audio file to output_path based on its suffix."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ext = output_path.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXPORT:
        raise AudioFormatError(f"Nicht unterstütztes Export-Format: {ext}")

    # Prefer soundfile for lossless/common
    if ext in ("wav", "flac", "ogg"):
        try:
            import soundfile as sf  # type: ignore
            import numpy as np  # type: ignore
            data, sr = sf.read(str(input_path), always_2d=True)
            sf.write(str(output_path), data, sr)
            return output_path
        except Exception:
            # Fall through to pydub/copy
            pass

    # Use pydub for mp3/aac/m4a or when soundfile can't read the input.
    try:
        from pydub import AudioSegment  # type: ignore
        if not _has_ffmpeg():
            raise AudioFormatError("ffmpeg nicht gefunden (für MP3/AAC/MP4 benötigt).")
        seg = AudioSegment.from_file(str(input_path))
        seg.export(str(output_path), format=ext)
        return output_path
    except AudioFormatError:
        raise
    except Exception:
        # As last resort, copy-through if same extension
        if input_path.suffix.lower() == output_path.suffix.lower():
            shutil.copy2(str(input_path), str(output_path))
            return output_path
        raise AudioFormatError(
            "Konnte Audio nicht konvertieren. Installiere optional: soundfile, pydub + ffmpeg."
        )


def import_audio(input_path: Path, project_media_dir: Path) -> Path:
    """Import audio into a project-local media folder by copying."""
    project_media_dir.mkdir(parents=True, exist_ok=True)
    dest = project_media_dir / input_path.name
    if dest.resolve() != input_path.resolve():
        shutil.copy2(str(input_path), str(dest))
    return dest
