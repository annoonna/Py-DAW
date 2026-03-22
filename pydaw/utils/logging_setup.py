"""Logging / stdout-stderr plumbing.

We want two things:
1) When started from a terminal, stdout/stderr must stay visible.
2) Always keep a rotating logfile for debugging (even when started via desktop).

The app uses a lot of `print()` currently; we therefore tee stdout/stderr into
the logfile in addition to configuring the logging module.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO


class _Tee(TextIO):
    def __init__(self, a: TextIO, b: TextIO) -> None:
        self._a = a
        self._b = b

    def write(self, s: str) -> int:  # type: ignore[override]
        n1 = 0
        n2 = 0
        try:
            n1 = self._a.write(s)
        except Exception:
            pass
        try:
            n2 = self._b.write(s)
        except Exception:
            pass
        return max(n1, n2)

    def flush(self) -> None:  # type: ignore[override]
        try:
            self._a.flush()
        except Exception:
            pass
        try:
            self._b.flush()
        except Exception:
            pass


def setup_logging(app_name: str = "ChronoScaleStudio") -> Path:
    """Configure logging and tee stdout/stderr to a rotating file.

    Returns:
        Path to the logfile.
    """
    # Log directory
    log_dir = Path(os.path.expanduser("~/.cache")) / app_name
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # fallback: current directory
        log_dir = Path(".")

    log_path = log_dir / "pydaw.log"

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    try:
        fh = RotatingFileHandler(str(log_path), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)
    except Exception:
        fh = None

    # Terminal handler
    sh = logging.StreamHandler(stream=sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    logger.addHandler(sh)

    # Line-buffered stdout/stderr (helps when the app restarts via exec)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    # Tee print() output into logfile (best-effort)
    if fh is not None:
        try:
            # Open a dedicated file stream for tee (avoid messing with handler internals)
            tee_stream = open(log_path, "a", encoding="utf-8", buffering=1)
            sys.stdout = _Tee(sys.stdout, tee_stream)  # type: ignore[assignment]
            sys.stderr = _Tee(sys.stderr, tee_stream)  # type: ignore[assignment]
        except Exception:
            pass

    logging.getLogger(__name__).info("Logging initialized. Logfile: %s", log_path)
    return log_path


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a named logger.

    This helper existed in earlier revisions; some modules still import it.
    setup_logging() should be called once at app startup (see pydaw/app.py).
    """
    return logging.getLogger(name)
