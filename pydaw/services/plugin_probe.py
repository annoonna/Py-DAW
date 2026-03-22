# -*- coding: utf-8 -*-
"""Plugin Safety Probe — Fork-based crash isolation with persistent blacklist.

v0.0.20.725: Full crash-isolated plugin probing with disk-persistent blacklist.

Key features:
- Fork-based crash isolation (SEGFAULT/SIGABRT → only child dies)
- Persistent blacklist survives DAW restarts (JSON on disk)
- Batch probing for scan integration (probe many plugins in one pass)
- Health tracking: crash count, last crash time, signal info
- User-configurable: can manually un-blacklist via clear_blacklist_entry()

Architecture:
    Main Process ──fork()──► Child Process
                              │ try: load plugin
                              │ exit(0) if OK
                              │ SEGFAULT → killed by signal
                   waitpid() ◄─┘
                   WIFEXITED(0)  → safe
                   WIFEXITED(1+) → exception but not crash → safe
                   WIFSIGNALED   → BLACKLISTED (real crash)
                   timeout       → BLACKLISTED (hung plugin)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)

# ── Blacklist entry with crash details ──

@dataclass
class BlacklistEntry:
    """Persistent record of a crashed plugin."""
    plugin_path: str
    plugin_type: str
    plugin_name: str = ""
    reason: str = ""
    signal_name: str = ""
    crash_count: int = 1
    first_crash: float = 0.0
    last_crash: float = 0.0
    user_override: bool = False  # True = user manually un-blacklisted


# ── In-memory state ──
_blacklist: Dict[str, BlacklistEntry] = {}
_safelist: Set[str] = set()
PROBE_TIMEOUT = 10.0
_disk_loaded: bool = False


# ── Disk persistence ──

def _blacklist_path() -> Path:
    base = Path(os.path.expanduser("~/.cache")) / "ChronoScaleStudio"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return Path(".") / "plugin_blacklist.json"
    return base / "plugin_blacklist.json"


def _load_from_disk() -> None:
    """Load persistent blacklist from disk (once per session)."""
    global _disk_loaded
    if _disk_loaded:
        return
    _disk_loaded = True
    path = _blacklist_path()
    try:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        entries = data.get("blacklist", {})
        if not isinstance(entries, dict):
            return
        for key, ed in entries.items():
            if not isinstance(ed, dict):
                continue
            if ed.get("user_override", False):
                continue
            try:
                _blacklist[key] = BlacklistEntry(
                    plugin_path=str(ed.get("plugin_path", "")),
                    plugin_type=str(ed.get("plugin_type", "")),
                    plugin_name=str(ed.get("plugin_name", "")),
                    reason=str(ed.get("reason", "")),
                    signal_name=str(ed.get("signal_name", "")),
                    crash_count=int(ed.get("crash_count", 1)),
                    first_crash=float(ed.get("first_crash", 0)),
                    last_crash=float(ed.get("last_crash", 0)),
                    user_override=False,
                )
            except (ValueError, TypeError):
                continue
        if _blacklist:
            _log.info("[PROBE] Loaded %d blacklisted plugins from disk", len(_blacklist))
    except Exception as e:
        _log.warning("[PROBE] Could not load blacklist from disk: %s", e)


def _save_to_disk() -> None:
    """Save blacklist to disk."""
    path = _blacklist_path()
    try:
        data = {
            "version": 1,
            "updated": time.time(),
            "blacklist": {k: asdict(v) for k, v in _blacklist.items()},
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        _log.warning("[PROBE] Could not save blacklist to disk: %s", e)


# ── Cache key helper ──

def _make_key(plugin_type: str, plugin_path: str,
              plugin_name: str = "", plugin_id: str = "") -> str:
    return f"{plugin_type}:{plugin_path}:{plugin_name}:{plugin_id}"


# ── Main API ──

def is_plugin_safe(plugin_path: str, plugin_type: str = "vst3",
                    plugin_name: str = "", plugin_id: str = "") -> bool:
    """Check if a plugin can be safely loaded without crashing.

    Returns True if safe, False if blacklisted or probe crashed.
    Uses fork() on Linux to isolate the load attempt.
    """
    _load_from_disk()
    cache_key = _make_key(plugin_type, plugin_path, plugin_name, plugin_id)

    if cache_key in _safelist:
        return True
    if cache_key in _blacklist:
        entry = _blacklist[cache_key]
        if entry.user_override:
            return True
        _log.info("[PROBE] Skipping blacklisted plugin: %s (%s)",
                  plugin_path, entry.reason)
        return False

    if not hasattr(os, 'fork'):
        _safelist.add(cache_key)
        return True

    _log.info("[PROBE] Testing plugin: %s (%s)", plugin_path, plugin_type)

    try:
        pid = os.fork()
    except OSError as e:
        _log.warning("[PROBE] fork() failed: %s — allowing plugin", e)
        _safelist.add(cache_key)
        return True

    if pid == 0:
        # ── CHILD PROCESS ──
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
            os.close(devnull)
        except Exception:
            pass
        try:
            _do_probe(plugin_path, plugin_type, plugin_name, plugin_id)
            os._exit(0)
        except SystemExit:
            os._exit(0)
        except Exception:
            os._exit(1)
        finally:
            os._exit(2)
    else:
        # ── PARENT PROCESS ──
        return _wait_for_child(pid, cache_key, plugin_path, plugin_type, plugin_name)


def _wait_for_child(pid: int, cache_key: str, plugin_path: str,
                     plugin_type: str, plugin_name: str) -> bool:
    """Wait for probe child process and evaluate result."""
    start = time.monotonic()
    while True:
        try:
            rpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            _safelist.add(cache_key)
            return True

        if rpid != 0:
            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
                # exit code 1+ = normal exception, NOT a crash
                _safelist.add(cache_key)
                if exit_code == 0:
                    _log.info("[PROBE] ✅ Plugin safe: %s", plugin_path)
                else:
                    _log.info("[PROBE] ✅ Plugin exception (exit %d) but no crash: %s",
                              exit_code, plugin_path)
                return True
            elif os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
                sig_name = _signal_name(sig)
                _add_to_blacklist(cache_key, plugin_path, plugin_type, plugin_name,
                                   f"crashed with signal {sig_name}", sig_name)
                return False
            else:
                _safelist.add(cache_key)
                return True

        elapsed = time.monotonic() - start
        if elapsed > PROBE_TIMEOUT:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except Exception:
                pass
            _add_to_blacklist(cache_key, plugin_path, plugin_type, plugin_name,
                               f"probe timed out after {PROBE_TIMEOUT}s", "TIMEOUT")
            return False

        time.sleep(0.05)


def _add_to_blacklist(cache_key: str, plugin_path: str, plugin_type: str,
                       plugin_name: str, reason: str, sig_name: str) -> None:
    """Add a plugin to the blacklist and persist to disk."""
    now = time.time()
    existing = _blacklist.get(cache_key)
    if existing:
        existing.crash_count += 1
        existing.last_crash = now
        existing.reason = reason
        existing.signal_name = sig_name
    else:
        _blacklist[cache_key] = BlacklistEntry(
            plugin_path=plugin_path,
            plugin_type=plugin_type,
            plugin_name=plugin_name,
            reason=reason,
            signal_name=sig_name,
            crash_count=1,
            first_crash=now,
            last_crash=now,
        )
    _log.warning("[PROBE] 💀 Plugin CRASHED: %s (%s) — BLACKLISTED", plugin_path, reason)
    print(f"[PROBE] 💀 Plugin CRASHED: {plugin_path} ({reason}) — blacklisted",
          file=sys.stderr, flush=True)
    _save_to_disk()


def _signal_name(sig: int) -> str:
    try:
        return signal.Signals(sig).name
    except (ValueError, KeyError):
        return str(sig)


# ── Batch Probe API ──

def probe_batch(plugins: List[Tuple[str, str, str, str]],
                max_parallel: int = 1) -> Dict[str, bool]:
    """Probe multiple plugins efficiently.

    Args:
        plugins: List of (plugin_type, plugin_path, plugin_name, plugin_id)
        max_parallel: Max concurrent probes (1 = sequential, safest)

    Returns:
        Dict of cache_key → is_safe
    """
    _load_from_disk()
    results: Dict[str, bool] = {}
    for plugin_type, plugin_path, plugin_name, plugin_id in plugins:
        cache_key = _make_key(plugin_type, plugin_path, plugin_name, plugin_id)
        if cache_key in _safelist:
            results[cache_key] = True
            continue
        if cache_key in _blacklist and not _blacklist[cache_key].user_override:
            results[cache_key] = False
            continue
        safe = is_plugin_safe(plugin_path, plugin_type, plugin_name, plugin_id)
        results[cache_key] = safe
    return results


# ── Plugin probe implementation (runs in child process) ──

def _do_probe(plugin_path: str, plugin_type: str,
               plugin_name: str, plugin_id: str) -> None:
    """Attempt to load the plugin (runs in child process).

    Any crash here kills only the child process.
    """
    if plugin_type in ("vst3", "vst2"):
        try:
            import pedalboard
            if plugin_type == "vst3":
                p = pedalboard.VST3Plugin(plugin_path, plugin_name=plugin_name or None)
            else:
                p = pedalboard.VST3Plugin(plugin_path)
            del p
        except Exception:
            raise

    elif plugin_type == "clap":
        import ctypes
        try:
            path = plugin_path
            if "::" in path:
                path = path.split("::")[0]
            lib = ctypes.CDLL(path)
            del lib
        except Exception:
            raise

    elif plugin_type == "lv2":
        pass

    elif plugin_type == "ladspa":
        import ctypes
        try:
            lib = ctypes.CDLL(plugin_path)
            del lib
        except Exception:
            raise


# ── Blacklist management API ──

def get_blacklist() -> Dict[str, BlacklistEntry]:
    """Return the current blacklist (cache_key → BlacklistEntry)."""
    _load_from_disk()
    return dict(_blacklist)


def get_blacklist_simple() -> Dict[str, str]:
    """Return blacklist as simple dict (cache_key → reason string).

    Backward-compatible with code that used the old Dict[str, str] API.
    """
    _load_from_disk()
    return {k: v.reason for k, v in _blacklist.items()}


def clear_blacklist() -> None:
    """Clear the entire blacklist (for re-probing)."""
    _blacklist.clear()
    _safelist.clear()
    _save_to_disk()
    _log.info("[PROBE] Blacklist cleared")


def clear_blacklist_entry(plugin_path: str, plugin_type: str = "vst3",
                           plugin_name: str = "", plugin_id: str = "") -> bool:
    """Remove a specific plugin from the blacklist.

    Returns True if the entry was found and un-blacklisted.
    """
    cache_key = _make_key(plugin_type, plugin_path, plugin_name, plugin_id)
    if cache_key in _blacklist:
        _blacklist[cache_key].user_override = True
        _safelist.discard(cache_key)
        _save_to_disk()
        _log.info("[PROBE] User un-blacklisted: %s", plugin_path)
        return True
    return False


def is_blacklisted(plugin_path: str, plugin_type: str = "vst3",
                    plugin_name: str = "", plugin_id: str = "") -> bool:
    """Check if a plugin is in the blacklist without probing."""
    _load_from_disk()
    cache_key = _make_key(plugin_type, plugin_path, plugin_name, plugin_id)
    entry = _blacklist.get(cache_key)
    return bool(entry and not entry.user_override)


def get_crash_count(plugin_path: str, plugin_type: str = "vst3",
                     plugin_name: str = "", plugin_id: str = "") -> int:
    """Get the crash count for a specific plugin."""
    _load_from_disk()
    cache_key = _make_key(plugin_type, plugin_path, plugin_name, plugin_id)
    entry = _blacklist.get(cache_key)
    return entry.crash_count if entry else 0
