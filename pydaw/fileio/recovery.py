"""Crash-recovery + autosave (v0.0.20.173).

Goals (Bitwig-style):
- If the app is killed (SIGINT / frozen UI / crash), we keep a recent autosave.
- On next start, ask the user whether to restore the last project state.

Safety:
- Autosave writes a separate JSON file (does NOT touch the main project file).
- No packaging of media, no destructive operations.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


APP_NAME = "ChronoScaleStudio"


def _config_dir() -> Path:
    return Path.home() / ".config" / APP_NAME


def state_path() -> Path:
    return _config_dir() / "session_state.json"


def read_state() -> Dict[str, Any]:
    try:
        p = state_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def write_state(st: Dict[str, Any]) -> None:
    try:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def mark_startup(last_project: str = "") -> None:
    st = read_state()
    st["last_seen_utc"] = datetime.utcnow().isoformat(timespec="seconds")
    if last_project:
        st["last_project"] = str(last_project)
    # assume unclean until the window closes normally
    st["clean_exit"] = False
    write_state(st)


def mark_clean_exit() -> None:
    st = read_state()
    st["last_seen_utc"] = datetime.utcnow().isoformat(timespec="seconds")
    st["clean_exit"] = True
    write_state(st)


def recovery_dir_for_project(project_path: Path) -> Path:
    return project_path.parent / ".recovery"


def latest_autosave_path(project_path: Path) -> Path:
    return recovery_dir_for_project(project_path) / "autosave_latest.pydaw.json"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_autosave(project_path: Path, project_obj: Any) -> Optional[Path]:
    """Write an autosave snapshot next to the project.

    Returns the latest autosave path.
    """
    try:
        project_path = Path(project_path)
    except Exception:
        return None

    try:
        data = asdict(project_obj)
    except Exception:
        try:
            data = project_obj.to_dict()  # type: ignore[attr-defined]
        except Exception:
            return None

    # annotate
    try:
        data["__autosave__"] = {
            "utc": datetime.utcnow().isoformat(timespec="seconds"),
            "project_file": str(project_path),
        }
    except Exception:
        pass

    rec_dir = recovery_dir_for_project(project_path)
    rec_dir.mkdir(parents=True, exist_ok=True)

    latest = latest_autosave_path(project_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = rec_dir / f"autosave_{ts}.pydaw.json"

    payload = json.dumps(data, indent=2, ensure_ascii=False)
    try:
        _atomic_write(latest, payload)
    except Exception:
        try:
            latest.write_text(payload, encoding="utf-8")
        except Exception:
            return None

    # best-effort stamped copy
    try:
        stamped.write_text(payload, encoding="utf-8")
    except Exception:
        pass

    # keep only a handful of stamped autosaves
    try:
        files = sorted(rec_dir.glob("autosave_*.pydaw.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[10:]:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass

    # update global session state
    try:
        st = read_state()
        st["last_project"] = str(project_path)
        st["last_autosave"] = {
            "path": str(latest),
            "utc": datetime.utcnow().isoformat(timespec="seconds"),
        }
        st["clean_exit"] = False
        write_state(st)
    except Exception:
        pass

    return latest


def should_prompt_restore() -> Tuple[Optional[Path], Optional[Path]]:
    """Return (project_path, autosave_path) if we should prompt restore."""
    st = read_state()
    try:
        clean = bool(st.get("clean_exit", True))
    except Exception:
        clean = True

    if clean:
        return (None, None)

    lp = str(st.get("last_project", "") or "").strip()
    if not lp:
        return (None, None)

    proj_path = Path(lp)
    if not proj_path.exists():
        return (None, None)

    a = latest_autosave_path(proj_path)
    if not a.exists():
        return (None, None)

    return (proj_path, a)
