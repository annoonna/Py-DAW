"""Project load/save to JSON (v0.0.3)."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Tuple

from pydaw.model.project import Project


PROJECT_EXT = ".pydaw.json"


def ensure_extension(path: Path) -> Path:
    if path.suffixes[-2:] == [".pydaw", ".json"]:
        return path
    if path.suffix == ".json":
        # allow raw .json if user insists
        return path
    return path.with_suffix(PROJECT_EXT)


def save_project(path: Path, project: Project) -> Path:
    path = ensure_extension(path)
    project.modified_utc = datetime.utcnow().isoformat(timespec="seconds")
    try:
        from pydaw.audio.vst3_host import embed_project_state_blobs
        embed_project_state_blobs(project)
    except Exception:
        pass
    data = project.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_project(path: Path) -> Project:
    d = json.loads(path.read_text(encoding="utf-8"))
    return Project.from_dict(d)
