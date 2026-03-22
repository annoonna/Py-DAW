# -*- coding: utf-8 -*-
"""LV2 hosting (Audio-FX) for ChronoScaleStudio / Py_DAW.

Design goals
------------
- SAFE / optional: if lilv is missing, nothing crashes; LV2 FX becomes no-op.
- Real-time friendly: allocate/connect ports at build time; process_inplace() only
  copies buffers + updates control scalars + calls instance.run().

Scope (v0.0.20.225)
-------------------
- LV2 *Audio* effects only (no UI embedding, no MIDI, no state save via LV2 state).
- Supports common port layouts:
  - Stereo in/out (2 in, 2 out)
  - Mono in/out (1 in, 1 out) with simple downmix/upmix

Dependencies
------------
- Optional: python-lilv (Debian/Ubuntu: `sudo apt install python3-lilv lilv-utils`)
- numpy is already a project dependency.

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import re
import shutil
import subprocess
import json
import os
import sys
import time
from pathlib import Path

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import lilv  # type: ignore
    _LILV_IMPORT_ERROR = ""
except Exception as _e:  # pragma: no cover
    # In venvs without system-site-packages, apt-installed modules live in dist-packages.
    # We try to add common dist-packages dirs (and process .pth files) before giving up.
    lilv = None  # type: ignore
    _LILV_IMPORT_ERROR = str(_e)
    try:
        import sys as _sys
        import os as _os
        import glob as _glob
        import site as _site

        cand: list[str] = []
        cand += ["/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"]
        # Versioned dist-packages (Debian/Kali)
        cand += sorted(_glob.glob("/usr/lib/python3*/dist-packages"))
        cand += sorted(_glob.glob("/usr/local/lib/python3*/dist-packages"))

        for p in cand:
            try:
                if p and _os.path.isdir(p):
                    # addsitedir handles .pth processing; much more robust than sys.path.append
                    _site.addsitedir(p)
            except Exception:
                continue

        import lilv  # type: ignore  # noqa: F401
        _LILV_IMPORT_ERROR = ""
    except Exception as _e2:
        lilv = None  # type: ignore
        _LILV_IMPORT_ERROR = str(_e2)



def is_available() -> bool:
    return (lilv is not None) and (np is not None)


def availability_hint() -> str:
    """Human-readable availability info for LV2 live hosting.

    This is shown in the UI when an LV2 device is inserted.
    """
    if np is None:
        return "numpy fehlt (unerwartet)."
    if lilv is None:
        base = "LV2 live-Hosting deaktiviert: python-lilv konnte nicht importiert werden."
        err = str(_LILV_IMPORT_ERROR or "").strip()
        if err:
            # keep short (UI label). Full trace is still visible in terminal logs.
            base += f" (ImportError: {err})"
        # Suggest the most common fixes on Debian/Kali.
        base += "\nFix: sudo apt install python3-lilv lilv-utils liblilv-0-0"
        # Some venv/pip builds may look for the unversioned SONAME.
        if "liblilv" in err and "liblilv-0.so" in err:
            base += "\nWenn ImportError nach 'liblilv-0.so' fragt: sudo apt install liblilv-dev"
        base += "\nFalls du ein venv nutzt: neu erstellen mit --system-site-packages."
        if shutil.which("lv2info"):
            base += "\nHinweis: Param-UI kann trotzdem über lv2info funktionieren."
        return base
    return "OK"


def _safe_str(x: Any) -> str:
    try:
        # lilv.Node has __str__ that returns uri
        return str(x)
    except Exception:
        return ""


@dataclass(frozen=True)
class Lv2ControlInfo:
    symbol: str
    name: str
    minimum: float
    maximum: float
    default: float


@dataclass(frozen=True)
class _PortMeta:
    idx: int
    symbol: str
    name: str


_RE_L_TAG = re.compile(r"(^|[^a-z0-9])l([^a-z0-9]|$)")
_RE_R_TAG = re.compile(r"(^|[^a-z0-9])r([^a-z0-9]|$)")


def _port_key(sym: str, name: str) -> str:
    s = (sym or "") + " " + (name or "")
    return " ".join(s.lower().split())


def _lr_tag(sym: str, name: str) -> str:
    k = _port_key(sym, name)
    if "left" in k or k.endswith("_l") or " l " in k or _RE_L_TAG.search(k):
        return "l"
    if "right" in k or k.endswith("_r") or " r " in k or _RE_R_TAG.search(k):
        return "r"
    return ""


def _score_audio_port(meta: _PortMeta, *, is_input: bool) -> int:
    """Heuristic scoring for LV2 audio ports.

    Some LV2 plugins expose multiple audio in/out ports (e.g. dry/wet taps,
    aux/sidechain, monitoring outs). If we naïvely take the first 2 outputs by
    index, we can end up copying a dry tap back → user hears "no effect".

    This scorer tries to pick the main in/out pair:
    - inputs: prefer "in/input", avoid sidechain/aux
    - outputs: prefer "out/output/wet/fx", avoid "dry"
    """
    k = _port_key(meta.symbol, meta.name)
    score = 0

    if is_input:
        if "in" in k or "input" in k:
            score += 10
        if "side" in k or "sidechain" in k or " sc" in k or "aux" in k:
            score -= 20
        if "out" in k or "output" in k:
            score -= 5
    else:
        if "out" in k or "output" in k:
            score += 10
        if "wet" in k or "fx" in k or "effect" in k:
            score += 8
        if "dry" in k:
            score -= 20
        if "in" in k or "input" in k:
            score -= 5

    # small nudge so that explicit L/R ports come first
    lr = _lr_tag(meta.symbol, meta.name)
    if lr == "l":
        score += 2
    elif lr == "r":
        score += 1

    return score


def _order_stereo_pair(metas: List[_PortMeta]) -> List[_PortMeta]:
    """Ensure a chosen 2-port pair is ordered as L then R when possible."""
    if len(metas) < 2:
        return metas
    a, b = metas[0], metas[1]
    ta = _lr_tag(a.symbol, a.name)
    tb = _lr_tag(b.symbol, b.name)
    if ta == "r" and tb == "l":
        return [b, a] + metas[2:]
    return metas


class _WorldCache:
    """Singleton-style LV2 World cache."""

    def __init__(self) -> None:
        self._world = None
        self._plugins = None
        self._ns = None
        self._by_uri: Dict[str, Any] = {}
        self._ctl_cache: Dict[str, List[Lv2ControlInfo]] = {}

    def world(self):
        if lilv is None:
            return None
        if self._world is None:
            w = lilv.World()
            try:
                w.load_all()
            except Exception:
                # still usable for explicit bundles if user sets LV2_PATH
                try:
                    w.load_all()
                except Exception:
                    pass
            self._world = w
            try:
                self._plugins = w.get_all_plugins()
            except Exception:
                self._plugins = None
            try:
                self._ns = w.ns
            except Exception:
                self._ns = None
        return self._world

    def plugin_by_uri(self, uri: str):
        uri = str(uri or "")
        if not uri:
            return None
        # Some LV2 scanners (including ours in early versions) may store the *bundle path*
        # instead of the LV2 plugin URI when manifest parsing fails. lilv treats that as an
        # invalid URI and can emit noisy errors ("attempt to map invalid URI").
        #
        # We accept bundle paths here as a best-effort compatibility layer.
        if uri.startswith("/") and os.path.isdir(uri):
            return self._plugin_by_bundle_path(uri)
        if uri in self._by_uri:
            return self._by_uri.get(uri)
        w = self.world()
        if w is None:
            return None
        try:
            plugins = self._plugins or w.get_all_plugins()
            node = w.new_uri(uri)
            p = plugins.get_by_uri(node)
            self._by_uri[uri] = p
            return p
        except Exception:
            self._by_uri[uri] = None
            return None

    def _plugin_by_bundle_path(self, bundle_path: str):
        """Best-effort resolve a LV2 plugin from a bundle directory path.

        Note:
        - A bundle can contain multiple plugin URIs; here we return the first match.
        - This exists only to keep old caches/projects usable when they stored bundle
          paths instead of URIs.
        """
        bundle_path = str(bundle_path or "").strip()
        if not bundle_path:
            return None
        key = f"bundle:{bundle_path}"
        if key in self._by_uri:
            return self._by_uri.get(key)

        w = self.world()
        if w is None:
            self._by_uri[key] = None
            return None

        try:
            abs_path = str(Path(bundle_path).expanduser().resolve())
        except Exception:
            abs_path = bundle_path

        # Build a file:// URI for the bundle
        bun_uri = ""
        try:
            # Some lilv builds expose new_file_uri(base, path)
            if hasattr(w, "new_file_uri"):
                bun_uri = _safe_str(w.new_file_uri(None, abs_path))
        except Exception:
            bun_uri = ""
        if not bun_uri:
            try:
                bun_uri = Path(abs_path).as_uri()
            except Exception:
                bun_uri = ""
        if not bun_uri:
            self._by_uri[key] = None
            return None

        try:
            w.load_bundle(w.new_uri(bun_uri))
        except Exception:
            try:
                w.load_bundle(w.new_uri(bun_uri.rstrip("/") + "/"))
            except Exception:
                pass

        try:
            plugins = self._plugins or w.get_all_plugins()
        except Exception:
            plugins = None

        want1 = bun_uri.rstrip("/")
        want2 = want1 + "/"
        try:
            if plugins is not None:
                for p in plugins:
                    try:
                        bu = _safe_str(p.get_bundle_uri()).rstrip("/")
                        if bu == want1 or (bu + "/") == want2:
                            self._by_uri[key] = p
                            return p
                    except Exception:
                        continue
        except Exception:
            pass

        self._by_uri[key] = None
        return None

    def controls_for_uri(self, uri: str) -> List[Lv2ControlInfo]:
        uri = str(uri or "")
        if not uri:
            return []
        if uri in self._ctl_cache:
            return list(self._ctl_cache[uri])
        p = self.plugin_by_uri(uri)
        if p is None:
            self._ctl_cache[uri] = []
            return []
        out: List[Lv2ControlInfo] = []
        try:
            ns = self._ns
            nports = int(p.get_num_ports())

            # Pre-fetch all port ranges at once (correct lilv API).
            # get_port_ranges_float() returns three arrays: (mins, maxs, defaults)
            _all_mins = None
            _all_maxs = None
            _all_defs = None
            try:
                _all_mins, _all_maxs, _all_defs = p.get_port_ranges_float()
            except Exception:
                pass

            for i in range(nports):
                port = p.get_port_by_index(i)
                if port is None:
                    continue
                # Control ports only
                try:
                    if ns is not None:
                        if not port.is_a(ns.lv2.ControlPort):
                            continue
                        # Only input controls
                        if not port.is_a(ns.lv2.InputPort):
                            continue
                    else:
                        # best-effort fallback: accept all ports and filter later
                        pass
                except Exception:
                    continue

                sym = ""
                nm = ""
                try:
                    sym = _safe_str(port.get_symbol())
                except Exception:
                    sym = ""
                try:
                    nm = _safe_str(port.get_name())
                except Exception:
                    nm = ""
                if not sym:
                    continue

                mn = 0.0
                mx = 1.0
                df = 0.0
                try:
                    # Use pre-fetched arrays (correct lilv API)
                    if _all_mins is not None and i < len(_all_mins) and _all_mins[i] is not None:
                        mn = float(_all_mins[i])
                    if _all_maxs is not None and i < len(_all_maxs) and _all_maxs[i] is not None:
                        mx = float(_all_maxs[i])
                    if _all_defs is not None and i < len(_all_defs) and _all_defs[i] is not None:
                        df = float(_all_defs[i])
                    else:
                        df = mn
                except Exception:
                    mn, mx, df = 0.0, 1.0, 0.0

                # sanitize
                if mx <= mn:
                    mx = mn + 1.0
                if df < mn:
                    df = mn
                if df > mx:
                    df = mx

                out.append(Lv2ControlInfo(symbol=sym, name=nm or sym, minimum=mn, maximum=mx, default=df))
        except Exception:
            out = []
        # stable ordering
        out.sort(key=lambda c: c.symbol)
        self._ctl_cache[uri] = list(out)
        return list(out)


_WORLD = _WorldCache()


_LV2INFO_CACHE: Dict[str, List[Lv2ControlInfo]] = {}


def _describe_controls_via_lv2info(uri: str) -> List[Lv2ControlInfo]:
    """Best-effort Control-Port parsing via `lv2info` (lilv-utils).

    This is used as a UI fallback when python-lilv can't be imported.
    It does NOT enable live processing (that still needs python-lilv).
    """
    uri = str(uri or "")
    if not uri:
        return []
    if uri in _LV2INFO_CACHE:
        return list(_LV2INFO_CACHE.get(uri) or [])
    if not shutil.which("lv2info"):
        _LV2INFO_CACHE[uri] = []
        return []
    # NOTE:
    # lv2info (lilv-utils) can print warnings/errors for unrelated broken bundles
    # (e.g. stale LV2 dirs with missing manifest.ttl) and still print valid info
    # for the requested URI. On some systems it returns a non-zero exit code in
    # that case, so we must *not* rely on check_output()/returncode==0.
    try:
        p = subprocess.run(
            ["lv2info", uri],
            text=True,
            errors="replace",
            capture_output=True,
            timeout=5.0,
            check=False,
        )
        # Parse stdout by default. lv2info may emit warnings/errors for unrelated
        # broken bundles to stderr (and sometimes exit non-zero), while still
        # printing valid information for the requested URI to stdout.
        out = (p.stdout or "").strip()
        if not out:
            # Rare fallback: some builds might print to stderr
            out = (p.stderr or "").strip()

    except Exception:
        _LV2INFO_CACHE[uri] = []
        return []

    # Split into Port blocks (common lv2info format)
    ports = re.split(r"\n(?=\s*Port\s+\d+:)", out)
    ret: List[Lv2ControlInfo] = []

    def _find_line_float(txt: str, key: str) -> Optional[float]:
        m = re.search(rf"{re.escape(key)}\s*:?\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", txt)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def _type_blob(blk_txt: str) -> str:
        """Return the full 'Type:' field including wrapped continuation lines."""
        lines = blk_txt.splitlines()
        for i, ln in enumerate(lines):
            if ln.lstrip().startswith("Type:"):
                first = ln.split(":", 1)[1].strip()
                acc = [first] if first else []
                # Continuation lines are indented URIs without a ':' key.
                j = i + 1
                while j < len(lines):
                    s = lines[j].strip()
                    if not s:
                        j += 1
                        continue
                    # Stop at the next key line (e.g. Symbol:, Name:, Minimum: ...)
                    # IMPORTANT: continuation lines are usually URIs like "http://..." which
                    # also contain ':' (scheme), so we must not break on a plain ':'.
                    # Key lines have the pattern "Key: <whitespace>...".
                    if re.match(r"^[A-Za-z][A-Za-z0-9 _-]*:\s+", s):
                        break
                    acc.append(s)
                    j += 1
                return " ".join(acc)
        return ""

    for blk in ports:
        if not re.search(r"^\s*Port\s+\d+:", blk):
            continue
        # Control? (Type block is often wrapped over multiple lines)
        t = _type_blob(blk)
        t_l = (t or "").lower()
        # We mainly care about controllable parameters (Input Control)
        if "controlport" not in t_l:
            continue
        if "inputport" not in t_l:
            continue

        m_sym = re.search(r"^\s*Symbol:\s*([^\s]+)\s*$", blk, flags=re.MULTILINE)
        if not m_sym:
            continue
        sym = m_sym.group(1).strip()

        nm = sym
        m_nm = re.search(r"^\s*Name:\s*(.+)$", blk, flags=re.MULTILINE)
        if m_nm:
            nm = m_nm.group(1).strip().strip('"')

        mn = _find_line_float(blk, "Minimum")  # may be None
        mx = _find_line_float(blk, "Maximum")
        df = _find_line_float(blk, "Default")

        if mn is None:
            mn = 0.0
        if mx is None or mx <= mn:
            mx = mn + 1.0
        if df is None:
            df = mn

        ret.append(Lv2ControlInfo(symbol=sym, name=nm, minimum=float(mn), maximum=float(mx), default=float(df)))

    _LV2INFO_CACHE[uri] = list(ret)
    return ret


def describe_controls(uri: str) -> List[Lv2ControlInfo]:
    """Return LV2 control port infos for a given plugin URI.

    Strategy (SAFE):
    - Prefer python-lilv (best quality).
    - If python-lilv is missing OR returns no controls (some environments/plugins),
      try a best-effort UI fallback via `lv2info` (lilv-utils).

    Note: `lv2info` fallback is UI-only (does not enable live processing).
    """
    uri = str(uri or "")
    if not uri:
        return []

    # 1) Best quality: python-lilv
    if is_available():
        try:
            ctl = _WORLD.controls_for_uri(uri)
        except Exception:
            ctl = []
        if ctl:
            return ctl
        # Safety-net: still try lv2info when lilv yields nothing.

    # 2) UI-only fallback: lv2info
    return _describe_controls_via_lv2info(uri)




def _get_required_features(plugin: Any) -> List[str]:
    """Return required feature URIs for a plugin (best-effort)."""
    out: List[str] = []
    try:
        req = plugin.get_required_features()
        try:
            for n in req:
                s = _safe_str(n)
                if s:
                    out.append(s)
        except Exception:
            # some lilv builds return a list-like
            try:
                out = [str(x) for x in req]
            except Exception:
                out = []
    except Exception:
        out = []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LV2 Safe Mode (crash guard)
#
# Native LV2 plugins are arbitrary .so binaries and can crash the host process
# (SIGBUS/SIGSEGV) during instantiate() or run(). Python cannot catch that.
#
# To keep Py_DAW stable, we probe LV2 plugins in a *subprocess* before allowing
# in-process live hosting. If the probe crashes or fails, we block the plugin
# and show an actionable message in the UI.
#
# Users can override this guard by setting PYDAW_LV2_UNSAFE=1 (not recommended).
# ─────────────────────────────────────────────────────────────────────────────


def _cache_dir() -> Path:
    try:
        p = Path(os.path.expanduser("~/.cache/ChronoScaleStudio"))
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        return Path(".")


_PROBE_CACHE_PATH = _cache_dir() / "lv2_probe_cache.json"
_PROBE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROBE_CACHE_LOADED = False
_LAST_BLOCK_REASON: Dict[str, str] = {}


def safe_mode_enabled() -> bool:
    return str(os.environ.get("PYDAW_LV2_UNSAFE", "0")).strip() not in ("1", "true", "TRUE", "yes", "YES")


def _load_probe_cache() -> None:
    global _PROBE_CACHE_LOADED, _PROBE_CACHE
    if _PROBE_CACHE_LOADED:
        return
    _PROBE_CACHE_LOADED = True
    try:
        data = json.loads(_PROBE_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _PROBE_CACHE = data
    except Exception:
        _PROBE_CACHE = {}


def _save_probe_cache() -> None:
    try:
        _PROBE_CACHE_PATH.write_text(json.dumps(_PROBE_CACHE, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def get_probe_status(uri: str) -> Tuple[str, str]:
    """Return (status, message) for a plugin URI from the probe cache.

    status: unknown|ok|blocked
    """
    _load_probe_cache()
    uri = str(uri or "")
    it = _PROBE_CACHE.get(uri)
    if not isinstance(it, dict):
        return "unknown", ""
    st = str(it.get("status") or "unknown")
    msg = str(it.get("message") or "")
    return st, msg


def _record_probe(uri: str, status: str, message: str) -> None:
    _load_probe_cache()
    uri = str(uri or "")
    if not uri:
        return
    _PROBE_CACHE[uri] = {
        "status": str(status),
        "message": str(message or ""),
        "ts": float(time.time()),
        "py": sys.version.split()[0],
    }
    _save_probe_cache()


def probe_plugin_safe(uri: str, *, force: bool = False, timeout_s: float = 3.0) -> Tuple[bool, str]:
    """Probe a LV2 plugin in a subprocess.

    Returns: (ok, message)
    - ok=True  => safe to attempt in-process instantiate/run
    - ok=False => blocked (crashed/failed/timeout)
    """
    uri = str(uri or "")
    if not uri:
        return False, "Leere LV2 URI"
    if not is_available():
        return False, availability_hint()

    if not safe_mode_enabled():
        return True, "Unsafe mode enabled (PYDAW_LV2_UNSAFE=1)"

    st, msg = get_probe_status(uri)
    if (not force) and st == "ok":
        return True, msg or "OK"
    if (not force) and st == "blocked":
        # If the plugin was previously blocked only because python-lilv
        # was not importable in the probe subprocess, retry once now.
        if msg and ("python-lilv import failed" in msg):
            force = True
        else:
            _LAST_BLOCK_REASON[uri] = msg
            return False, msg

    cmd = [sys.executable, "-m", "pydaw.tools.lv2_probe", "--uri", uri]
    try:
        p = subprocess.run(cmd, text=True, errors="replace", capture_output=True, timeout=float(timeout_s), check=False)
    except subprocess.TimeoutExpired:
        m = f"Probe timeout after {timeout_s:.1f}s"
        _record_probe(uri, "blocked", m)
        _LAST_BLOCK_REASON[uri] = m
        return False, m
    except Exception as e:
        m = f"Probe failed: {type(e).__name__}: {e}"
        _record_probe(uri, "blocked", m)
        _LAST_BLOCK_REASON[uri] = m
        return False, m

    if int(p.returncode) < 0:
        sig = -int(p.returncode)
        m = f"Plugin crashed during probe (signal {sig})"
        tail = (p.stderr or "").strip().splitlines()[-1:]
        if tail:
            m += f": {tail[0]}"
        _record_probe(uri, "blocked", m)
        _LAST_BLOCK_REASON[uri] = m
        return False, m

    out = (p.stdout or "").strip()
    if out:
        try:
            j = json.loads(out.splitlines()[-1])
            if isinstance(j, dict) and bool(j.get("ok")):
                m = str(j.get("message") or "OK")
                _record_probe(uri, "ok", m)
                return True, m
            em = str((j.get("error") if isinstance(j, dict) else "") or "Probe reported failure")
            _record_probe(uri, "blocked", em)
            _LAST_BLOCK_REASON[uri] = em
            return False, em
        except Exception:
            pass

    if int(p.returncode) != 0:
        m = (p.stderr or p.stdout or "Probe failed").strip()
        if not m:
            m = f"Probe failed (exit {p.returncode})"
        m = " ".join(m.split())
        _record_probe(uri, "blocked", m)
        _LAST_BLOCK_REASON[uri] = m
        return False, m

    _record_probe(uri, "ok", "OK")
    return True, "OK"


def last_block_reason(uri: str) -> str:
    return str(_LAST_BLOCK_REASON.get(str(uri or ""), ""))


def _try_instantiate_plugin(plugin: Any, sr: int) -> Tuple[Any, str]:
    """Instantiate a lilv plugin in a version-tolerant way.

    Different python-lilv builds expose either:
    - plugin.instantiate(sr)
    - plugin.instantiate(sr, features)
    - lilv.Instance(plugin, sr, features)

    We try common call patterns and return (instance, debug_string).
    """
    sr = int(sr) if sr else 48000
    attempts: List[str] = []

    # Try plugin.instantiate with/without features
    for label, args in (
        ('plugin.instantiate(sr, [])', (sr, [])),
        ('plugin.instantiate(sr, None)', (sr, None)),
        ('plugin.instantiate(sr)', (sr,)),
    ):
        try:
            inst = plugin.instantiate(*args)
            if inst is not None:
                return inst, label
            attempts.append(f"{label} -> None")
        except TypeError as e:
            attempts.append(f"{label} -> TypeError: {e}")
        except Exception as e:
            attempts.append(f"{label} -> {type(e).__name__}: {e}")

    # Fallback: lilv.Instance
    try:
        if lilv is not None and hasattr(lilv, 'Instance'):
            for label, args in (
                ('lilv.Instance(plugin, sr, [])', (plugin, sr, [])),
                ('lilv.Instance(plugin, sr, None)', (plugin, sr, None)),
                ('lilv.Instance(plugin, sr)', (plugin, sr)),
            ):
                try:
                    inst = lilv.Instance(*args)  # type: ignore[attr-defined]
                    if inst is not None:
                        return inst, label
                    attempts.append(f"{label} -> None")
                except TypeError as e:
                    attempts.append(f"{label} -> TypeError: {e}")
                except Exception as e:
                    attempts.append(f"{label} -> {type(e).__name__}: {e}")
    except Exception:
        pass

    dbg = '; '.join(attempts[:6])
    if len(attempts) > 6:
        dbg += f"; …(+{len(attempts)-6} more)"
    return None, dbg
def _rt_get(rt: Any, key: str, default: float) -> float:
    try:
        if rt is None:
            return float(default)
        if hasattr(rt, "get_smooth"):
            return float(rt.get_smooth(key, default))
        if hasattr(rt, "get_param"):
            return float(rt.get_param(key, default))
        if hasattr(rt, "get_target"):
            return float(rt.get_target(key, default))
    except Exception:
        pass
    return float(default)


class Lv2Fx:
    """LV2 Audio-FX (in-place stereo buffer)."""

    def __init__(
        self,
        *,
        uri: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Optional[Dict[str, Any]] = None,
        sr: int = 48000,
        max_frames: int = 8192,
    ) -> None:
        self.uri = str(uri or "")
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self.sr = int(sr) if sr else 48000
        self.max_frames = int(max_frames) if max_frames else 8192

        self._ok = False
        self._inst = None
        self._err: str = ""
        self._ctl: List[Tuple[int, str, Any, float]] = []  # (port_index, rt_key, buf1, default)
        self._ain_idx: List[int] = []
        self._aout_idx: List[int] = []
        self._ain_bufs: List[Any] = []
        self._aout_bufs: List[Any] = []
        # Which output buffers to copy back to the host stereo buffer.
        # These are *positions* into self._aout_bufs (not LV2 port indices).
        self._main_out_sel: List[int] = [0, 1]
        # Cached meta for debug / potential future UI.
        self._aout_meta: List[_PortMeta] = []

        # Remember auto-selected outputs (so UI can switch back without re-running run() in UI thread).
        self._auto_out_sel: List[int] = [0, 1]

        # Dummy buffers for unconnected ports (output control, CV, etc.)
        # LV2 spec: all non-optional ports MUST be connected to valid buffers.
        # If we don't connect output control ports, the plugin's run() writes
        # to NULL → undefined behavior / silent failure / no audible effect.
        self._dummy_bufs: List[Any] = []

        if not is_available():
            return

        try:
            # Crash guard: probe in subprocess before in-process instantiate.
            # This prevents native LV2 binaries from taking down the whole DAW.
            try:
                ok, why = probe_plugin_safe(self.uri)
                if not ok:
                    self._err = "LV2 Safe Mode: BLOCKED — " + (why or "Probe failed")
                    return
            except Exception:
                # If the probe mechanism itself fails, keep behavior safe and do not load.
                self._err = "LV2 Safe Mode: BLOCKED — probe mechanism failed"
                return

            plugin = _WORLD.plugin_by_uri(self.uri)
            if plugin is None:
                self._err = f"LV2 Plugin nicht gefunden (URI): {self.uri}"
                return

            inst, how = _try_instantiate_plugin(plugin, self.sr)
            if inst is None:
                req = _get_required_features(plugin)
                msg = "LV2 Plugin konnte nicht instanziiert werden."
                if req:
                    # keep short but informative
                    msg += " Required features: " + ", ".join(req[:6])
                    if len(req) > 6:
                        msg += f" …(+{len(req)-6})"
                if how:
                    msg += "\n(" + str(how) + ")"
                self._err = msg
                return
            self._inst = inst


            ns = _WORLD._ns
            nports = int(plugin.get_num_ports())

            # First pass: gather audio ports (with meta) and control ports
            audio_in_m: List[_PortMeta] = []
            audio_out_m: List[_PortMeta] = []
            ctl_ports: List[Tuple[int, Lv2ControlInfo]] = []
            # Track which port indices we explicitly connect
            connected_ports: set = set()

            ctl_info_map = {c.symbol: c for c in describe_controls(self.uri)}

            for i in range(nports):
                port = plugin.get_port_by_index(i)
                if port is None:
                    continue
                try:
                    if ns is not None and port.is_a(ns.lv2.AudioPort):
                        psym = ""
                        pnm = ""
                        try:
                            psym = _safe_str(port.get_symbol())
                        except Exception:
                            psym = ""
                        try:
                            pnm = _safe_str(port.get_name())
                        except Exception:
                            pnm = ""
                        if port.is_a(ns.lv2.InputPort):
                            audio_in_m.append(_PortMeta(idx=i, symbol=psym, name=pnm))
                        elif port.is_a(ns.lv2.OutputPort):
                            audio_out_m.append(_PortMeta(idx=i, symbol=psym, name=pnm))
                        continue
                except Exception:
                    pass

                # Control ports (input)
                try:
                    if ns is not None and port.is_a(ns.lv2.ControlPort) and port.is_a(ns.lv2.InputPort):
                        sym = _safe_str(port.get_symbol())
                        ci = ctl_info_map.get(sym)
                        if ci is None:
                            # fall back: attempt per-port ranges via array lookup
                            mn, mx, df = 0.0, 1.0, 0.0
                            try:
                                _mins, _maxs, _defs = plugin.get_port_ranges_float()
                                if i < len(_mins) and _mins[i] is not None:
                                    mn = float(_mins[i])
                                if i < len(_maxs) and _maxs[i] is not None:
                                    mx = float(_maxs[i])
                                if i < len(_defs) and _defs[i] is not None:
                                    df = float(_defs[i])
                            except Exception:
                                mn, mx, df = 0.0, 1.0, 0.0
                            if mx <= mn:
                                mx = mn + 1.0
                            if df < mn:
                                df = mn
                            if df > mx:
                                df = mx
                            ci = Lv2ControlInfo(symbol=sym or f"p{i}", name=sym or f"p{i}", minimum=mn, maximum=mx, default=df)
                        ctl_ports.append((i, ci))
                except Exception:
                    continue

            # Decide which audio ports we feed/copy first.
            # NOTE: we still connect *all* audio ports to buffers so plugins that
            # expect them won't crash, but we order them so the first pair is
            # most likely the main wet output.
            try:
                audio_in_m.sort(key=lambda m: (-_score_audio_port(m, is_input=True), m.idx))
                audio_out_m.sort(key=lambda m: (-_score_audio_port(m, is_input=False), m.idx))
                audio_in_m = _order_stereo_pair(audio_in_m)
                audio_out_m = _order_stereo_pair(audio_out_m)
            except Exception:
                pass

            audio_in = [m.idx for m in audio_in_m]
            audio_out = [m.idx for m in audio_out_m]

            # Keep meta (same ordering as _aout_idx/_aout_bufs)
            self._aout_meta = list(audio_out_m)

            # Prepare audio buffers
            def _mk_audio_buf():
                return np.zeros((self.max_frames,), dtype=np.float32)

            self._ain_idx = list(audio_in)
            self._aout_idx = list(audio_out)
            self._ain_bufs = [_mk_audio_buf() for _ in self._ain_idx]
            self._aout_bufs = [_mk_audio_buf() for _ in self._aout_idx]

            # Connect audio ports
            for idx, buf in zip(self._ain_idx, self._ain_bufs):
                try:
                    inst.connect_port(int(idx), buf)
                    connected_ports.add(int(idx))
                except Exception:
                    pass
            for idx, buf in zip(self._aout_idx, self._aout_bufs):
                try:
                    inst.connect_port(int(idx), buf)
                    connected_ports.add(int(idx))
                except Exception:
                    pass

            # Connect control ports (input)
            params = params if isinstance(params, dict) else {}
            for idx, ci in ctl_ports:
                sym = str(ci.symbol)
                rt_key = f"afx:{self.track_id}:{self.device_id}:lv2:{sym}"
                # one-float buffer
                buf1 = np.zeros((1,), dtype=np.float32)

                # default: prefer params[sym] if present
                dv = ci.default
                try:
                    if sym in params and isinstance(params.get(sym), (int, float)):
                        dv = float(params.get(sym))
                except Exception:
                    dv = ci.default

                buf1[0] = np.float32(dv)

                # ensure rt key
                try:
                    if hasattr(self.rt_params, "ensure"):
                        self.rt_params.ensure(rt_key, float(dv))
                    elif hasattr(self.rt_params, "set_param"):
                        self.rt_params.set_param(rt_key, float(dv))
                except Exception:
                    pass

                try:
                    inst.connect_port(int(idx), buf1)
                    connected_ports.add(int(idx))
                except Exception:
                    pass

                self._ctl.append((int(idx), rt_key, buf1, float(ci.default)))

            # ── CRITICAL FIX: Connect ALL remaining ports to dummy buffers ──
            # LV2 spec requires all non-optional ports to be connected.
            # Output control ports (latency, meters), CV ports, and Atom/event
            # ports MUST have valid buffers, otherwise run() writes to NULL →
            # undefined behavior, silent processing failures, or no audible effect.
            #
            # This is the #1 cause of "DSP: ACTIVE but no effect heard" with
            # plugins like Guitarix reverbs, SWH effects, etc.
            try:
                for i in range(nports):
                    if i in connected_ports:
                        continue
                    port = plugin.get_port_by_index(i)
                    if port is None:
                        continue
                    try:
                        is_ctl = False
                        is_audio = False
                        try:
                            if ns is not None:
                                is_ctl = bool(port.is_a(ns.lv2.ControlPort))
                                is_audio = bool(port.is_a(ns.lv2.AudioPort))
                        except Exception:
                            pass

                        if is_ctl:
                            # Output control port (latency, meter, etc.)
                            # → 1-float dummy buffer
                            dummy = np.zeros((1,), dtype=np.float32)
                            # Try to set a sensible default for output control ports
                            try:
                                _mins, _maxs, _defs = plugin.get_port_ranges_float()
                                if i < len(_defs) and _defs[i] is not None:
                                    dummy[0] = np.float32(float(_defs[i]))
                            except Exception:
                                pass
                            try:
                                inst.connect_port(int(i), dummy)
                                self._dummy_bufs.append(dummy)
                                connected_ports.add(i)
                            except Exception:
                                pass
                        elif is_audio:
                            # Unexpected unconnected audio port → max_frames buffer
                            dummy = np.zeros((self.max_frames,), dtype=np.float32)
                            try:
                                inst.connect_port(int(i), dummy)
                                self._dummy_bufs.append(dummy)
                                connected_ports.add(i)
                            except Exception:
                                pass
                        else:
                            # Unknown port type (CV, Atom, etc.) → try control-sized buffer
                            dummy = np.zeros((1,), dtype=np.float32)
                            try:
                                inst.connect_port(int(i), dummy)
                                self._dummy_bufs.append(dummy)
                                connected_ports.add(i)
                            except Exception:
                                # Some port types (Atom/event) may reject numpy buffers.
                                # That's OK — we tried our best.
                                pass
                    except Exception:
                        continue
            except Exception:
                pass

            try:
                inst.activate()
            except Exception:
                pass

            # ── Diagnostic logging (safe, stderr only) ──
            try:
                _n_connected = len(connected_ports)
                _n_dummy = len(self._dummy_bufs)
                _n_ain = len(self._ain_idx)
                _n_aout = len(self._aout_idx)
                _n_ctl = len(self._ctl)
                print(f"[LV2] {self.uri}: ports={nports} connected={_n_connected} "
                      f"(ain={_n_ain} aout={_n_aout} ctl_in={_n_ctl} dummy={_n_dummy}) "
                      f"out_sel={self._main_out_sel}",
                      file=sys.stderr, flush=True)
                if nports > _n_connected:
                    _unconnected = [i for i in range(nports) if i not in connected_ports]
                    if _unconnected:
                        print(f"[LV2]   WARNING: {len(_unconnected)} port(s) still unconnected: {_unconnected[:8]}",
                              file=sys.stderr, flush=True)
            except Exception:
                pass

            # Choose which outputs are most likely the *main/wet* stereo pair.
            # Many LV2 plugins expose extra audio outs (dry taps, monitor outs,
            # aux/sidechain, etc.). If we copy back the wrong pair, users hear
            # "no effect" even though DSP is active.
            try:
                self._auto_select_main_outputs()
            except Exception:
                # Never fail init because of heuristics.
                pass


            # Remember auto selection (safe; no extra DSP work).
            try:
                self._auto_out_sel = list(self._main_out_sel or [0, 1])
            except Exception:
                self._auto_out_sel = [0, 1]

            # Apply persisted output selection if present (UI override).
            try:
                sel = None
                if isinstance(params, dict):
                    sel = params.get('__out_sel')
                if isinstance(sel, str) and ',' in sel:
                    parts = [x.strip() for x in sel.split(',') if x.strip()]
                    sel = parts
                if isinstance(sel, (list, tuple)) and len(sel) >= 1:
                    a = int(sel[0])
                    b = int(sel[1]) if len(sel) > 1 else a
                    # clamp to available buffers
                    n = len(self._aout_bufs)
                    if n > 0:
                        if a < 0: a = 0
                        if b < 0: b = 0
                        if a >= n: a = n - 1
                        if b >= n: b = n - 1
                        self._main_out_sel = [a, b]
            except Exception:
                pass

            # Accept only if we have at least some audio IO
            if (len(self._ain_idx) >= 1) and (len(self._aout_idx) >= 1):
                self._ok = True
            else:
                if not self._err:
                    self._err = 'LV2 Plugin hat keine Audio I/O Ports (AudioPort in/out).'
        except Exception as e:
            self._ok = False
            if not self._err:
                self._err = f"LV2 init failed: {type(e).__name__}: {e}"

    def process_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        if not self._ok:
            return
        if np is None:
            return
        inst = self._inst
        if inst is None:
            return

        frames = int(frames)
        if frames <= 0:
            return
        if frames > self.max_frames:
            frames = self.max_frames

        # Update control buffers from RT params
        for _, rt_key, buf1, dv in self._ctl:
            try:
                buf1[0] = np.float32(_rt_get(self.rt_params, rt_key, dv))
            except Exception:
                continue

        # Feed audio inputs
        # Stereo buffer is (frames,2)
        try:
            if len(self._ain_bufs) >= 2:
                self._ain_bufs[0][:frames] = buf[:frames, 0]
                self._ain_bufs[1][:frames] = buf[:frames, 1]
            elif len(self._ain_bufs) == 1:
                # downmix to mono
                self._ain_bufs[0][:frames] = (buf[:frames, 0] + buf[:frames, 1]) * 0.5
        except Exception:
            return

        # Run
        try:
            inst.run(frames)
        except Exception:
            return

        # Copy outputs back
        try:
            sel = self._main_out_sel or [0, 1]
            if len(self._aout_bufs) >= 2:
                a = int(sel[0]) if len(sel) > 0 else 0
                b = int(sel[1]) if len(sel) > 1 else 1
                if a < 0 or a >= len(self._aout_bufs):
                    a = 0
                if b < 0 or b >= len(self._aout_bufs):
                    b = 1 if len(self._aout_bufs) > 1 else 0
                buf[:frames, 0] = self._aout_bufs[a][:frames]
                buf[:frames, 1] = self._aout_bufs[b][:frames]
            elif len(self._aout_bufs) == 1:
                buf[:frames, 0] = self._aout_bufs[0][:frames]
                buf[:frames, 1] = self._aout_bufs[0][:frames]
        except Exception:
            return

    def _auto_select_main_outputs(self) -> None:
        """Pick the most likely audible (wet/main) output pair.

        SAFE heuristic: never throws, never changes the LV2 wiring.
        We already connect *all* audio output ports to buffers; we only
        decide which 1–2 buffers we copy back to the host stereo signal.

        Strategy:
        - Start from name/symbol scoring (already sorted by _score_audio_port)
        - If >2 outputs exist, run a tiny "silent" test with a *very low*
          amplitude impulse to detect dry taps vs wet/main outs.
          (Amplitude is tiny to avoid leaving an audible tail.)
        """
        if np is None:
            return
        if self._inst is None:
            return
        if not self._aout_bufs:
            return

        n_out = len(self._aout_bufs)
        if n_out == 1:
            self._main_out_sel = [0]
            return
        if n_out == 2:
            self._main_out_sel = [0, 1]
            return

        # Default based on current ordering
        best = [0, 1]

        tf = min(2048, int(self.max_frames))
        if tf <= 0:
            self._main_out_sel = best
            return

        try:
            # Clear buffers
            for b in self._ain_bufs:
                b[:tf] = 0.0
            for b in self._aout_bufs:
                b[:tf] = 0.0

            amp = np.float32(1e-3)
            if len(self._ain_bufs) >= 2:
                self._ain_bufs[0][0] = amp
                self._ain_bufs[1][0] = amp
            elif len(self._ain_bufs) == 1:
                self._ain_bufs[0][0] = amp

            self._inst.run(int(tf))
        except Exception:
            self._main_out_sel = best
            return

        # Reference signals for diff scoring
        ref_l = None
        ref_r = None
        try:
            if len(self._ain_bufs) >= 2:
                ref_l = self._ain_bufs[0][:tf]
                ref_r = self._ain_bufs[1][:tf]
            elif len(self._ain_bufs) == 1:
                ref_l = self._ain_bufs[0][:tf]
                ref_r = self._ain_bufs[0][:tf]
        except Exception:
            ref_l = None
            ref_r = None

        def _rms(x) -> float:
            try:
                return float(np.sqrt(np.mean(np.square(x), dtype=np.float64) + 1e-24))
            except Exception:
                return 0.0

        cand = []  # (score, lr, pos)
        for pos, outb in enumerate(self._aout_bufs):
            try:
                meta = self._aout_meta[pos] if pos < len(self._aout_meta) else _PortMeta(idx=-1, symbol='', name='')
                lr = _lr_tag(meta.symbol, meta.name)
                key = _port_key(meta.symbol, meta.name)

                out = outb[:tf]
                ref = ref_l if lr == 'l' else (ref_r if lr == 'r' else ref_l)
                if ref is None:
                    s = _rms(out)
                else:
                    s = _rms(out - ref) + 0.10 * _rms(out)

                if 'dry' in key:
                    s *= 0.25
                if 'monitor' in key or ' mon ' in key:
                    s *= 0.50
                cand.append((float(s), lr, int(pos)))
            except Exception:
                continue

        if not cand:
            self._main_out_sel = best
            return

        cand.sort(key=lambda t: (-t[0], t[2]))
        pick: List[int] = []
        l_best = next((c for c in cand if c[1] == 'l'), None)
        r_best = next((c for c in cand if c[1] == 'r'), None)
        if l_best is not None:
            pick.append(l_best[2])
        if r_best is not None and r_best[2] not in pick:
            pick.append(r_best[2])
        for _, _lr, pos in cand:
            if len(pick) >= 2:
                break
            if pos not in pick:
                pick.append(pos)

        if len(pick) >= 2:
            self._main_out_sel = [pick[0], pick[1]]
        else:
            self._main_out_sel = best

        # Clear impulse residue in buffers (best-effort)
        try:
            for b in self._ain_bufs:
                b[:tf] = 0.0
            for b in self._aout_bufs:
                b[:tf] = 0.0
        except Exception:
            pass


    # ── UI/Debug helpers (safe) ───────────────────────────────────────────
    def get_output_options(self) -> List[Dict[str, Any]]:
        """Return output buffer options as a list of dicts.

        Each option corresponds to a position in `self._aout_bufs` (after sorting).
        Keys: pos, port_index, symbol, name
        """
        out: List[Dict[str, Any]] = []
        try:
            for pos, meta in enumerate(self._aout_meta or []):
                out.append({
                    'pos': int(pos),
                    'port_index': int(getattr(meta, 'idx', -1) or -1),
                    'symbol': str(getattr(meta, 'symbol', '') or ''),
                    'name': str(getattr(meta, 'name', '') or ''),
                })
        except Exception:
            return out
        return out

    def get_output_selection(self) -> List[int]:
        try:
            sel = list(self._main_out_sel or [])
            return [int(x) for x in sel]
        except Exception:
            return [0, 1]

    def get_auto_output_selection(self) -> List[int]:
        try:
            sel = list(self._auto_out_sel or [])
            return [int(x) for x in sel]
        except Exception:
            return [0, 1]

    def set_output_selection(self, sel: List[int]) -> None:
        """Set which output buffers are copied back (thread-safe enough).

        This does not touch LV2 wiring, only the host copy-back selection.
        """
        try:
            if not isinstance(sel, (list, tuple)) or not sel:
                return
            a = int(sel[0])
            b = int(sel[1]) if len(sel) > 1 else a
            n = len(self._aout_bufs)
            if n <= 0:
                return
            if a < 0: a = 0
            if b < 0: b = 0
            if a >= n: a = n - 1
            if b >= n: b = n - 1
            # atomic-ish swap (avoid mutating existing list while audio thread reads)
            self._main_out_sel = [a, b]
        except Exception:
            return

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return comprehensive port/connection diagnostics (UI/debug safe)."""
        try:
            return {
                'uri': str(self.uri),
                'ok': bool(self._ok),
                'err': str(self._err or ''),
                'n_audio_in': len(self._ain_idx),
                'n_audio_out': len(self._aout_idx),
                'n_control_in': len(self._ctl),
                'n_dummy_bufs': len(self._dummy_bufs),
                'audio_in_ports': list(self._ain_idx),
                'audio_out_ports': list(self._aout_idx),
                'output_selection': list(self._main_out_sel or []),
                'auto_output_selection': list(self._auto_out_sel or []),
                'output_meta': [
                    {'pos': pos, 'idx': m.idx, 'sym': m.symbol, 'name': m.name}
                    for pos, m in enumerate(self._aout_meta or [])
                ],
                'control_keys': [
                    {'port': idx, 'rt_key': rk, 'value': float(b[0]) if b is not None else None, 'default': d}
                    for idx, rk, b, d in (self._ctl or [])
                ],
            }
        except Exception as e:
            return {'error': str(e)}


def offline_process_wav(
    *,
    uri: str,
    in_path: str,
    out_path: str,
    controls: Optional[Dict[str, float]] = None,
    block: int = 1024,
) -> Tuple[bool, str]:
    """Offline: process a WAV/FLAC/etc file through LV2 plugin and write out WAV.

    Best-effort helper for debugging. Not used by the realtime engine.
    """
    if not is_available():
        return False, availability_hint()
    try:
        import soundfile as sf  # type: ignore
    except Exception:
        return False, "soundfile fehlt (pip install soundfile / apt install python3-soundfile)."

    try:
        data, sr = sf.read(str(in_path), dtype="float32", always_2d=True)
    except Exception as e:
        return False, f"Input lesen fehlgeschlagen: {e}"

    if data.shape[1] == 1:
        # make stereo
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] >= 2:
        data = data[:, :2]

    # create dummy rt store
    class _RT:
        def __init__(self):
            self.d = {}
        def ensure(self, k, v):
            self.d.setdefault(k, float(v))
        def set_param(self, k, v):
            self.d[k] = float(v)
        def get_smooth(self, k, default=0.0):
            return float(self.d.get(k, default))

    rt = _RT()

    params = dict(controls or {})
    fx = Lv2Fx(uri=uri, track_id="offline", device_id="offline", rt_params=rt, params=params, sr=int(sr), max_frames=max(2048, int(block)))
    if not fx._ok:
        msg = str(getattr(fx, "_err", "") or "").strip()
        if not msg:
            msg = "LV2 Plugin konnte nicht instanziiert werden (URI stimmt? lilv ok?)."
        return False, msg

    # set controls
    for k, v in (controls or {}).items():
        rt.set_param(f"afx:offline:offline:lv2:{k}", float(v))

    out = np.array(data, copy=True)
    n = out.shape[0]
    bs = int(block)
    if bs <= 0:
        bs = 1024

    i = 0
    while i < n:
        frames = min(bs, n - i)
        # temp view
        chunk = out[i:i+frames, :]
        fx.process_inplace(chunk, frames, int(sr))
        i += frames

    try:
        sf.write(str(out_path), out, int(sr))
    except Exception as e:
        return False, f"Output schreiben fehlgeschlagen: {e}"

    return True, "OK"


def offline_process_wav_subprocess(
    *,
    uri: str,
    in_path: str,
    out_path: str,
    controls: Optional[Dict[str, float]] = None,
    block: int = 1024,
    timeout_s: float = 30.0,
) -> Tuple[bool, str]:
    """Offline render through LV2 in a subprocess (SAFE).

    Unlike offline_process_wav() this never risks taking down the GUI process.
    If the LV2 binary crashes, only the subprocess dies.
    """
    uri = str(uri or "")
    if not uri:
        return False, "Leere LV2 URI"

    # We still need lilv/numpy to be importable in the subprocess.
    if np is None:
        return False, "numpy fehlt (unerwartet)."

    env = dict(os.environ)
    # Allow rendering even for plugins that would be blocked live.
    env.setdefault("PYDAW_LV2_UNSAFE", "1")

    ctl_json = ""
    try:
        if isinstance(controls, dict) and controls:
            ctl_json = json.dumps({str(k): float(v) for k, v in controls.items() if isinstance(v, (int, float))})
    except Exception:
        ctl_json = ""

    cmd = [
        sys.executable,
        "-m",
        "pydaw.tools.lv2_offline_render",
        "--uri",
        uri,
        "--in",
        str(in_path),
        "--out",
        str(out_path),
        "--block",
        str(int(block) if block else 1024),
    ]
    if ctl_json:
        cmd += ["--controls-json", ctl_json]

    try:
        p = subprocess.run(cmd, text=True, errors="replace", capture_output=True, timeout=float(timeout_s), check=False, env=env)
    except subprocess.TimeoutExpired:
        return False, f"Offline render timeout after {timeout_s:.1f}s"
    except Exception as e:
        return False, f"Offline render failed: {type(e).__name__}: {e}"

    # Crashed?
    if int(p.returncode) < 0:
        sig = -int(p.returncode)
        return False, f"Offline render subprocess crashed (signal {sig})"

    out = (p.stdout or "").strip()
    if out:
        try:
            j = json.loads(out)
            if isinstance(j, dict):
                ok = bool(j.get("ok"))
                msg = str(j.get("message") or "")
                return ok, msg or ("OK" if ok else "Failed")
        except Exception:
            # fall through
            pass

    # fallback: stderr
    err = (p.stderr or "").strip()
    if err:
        # keep last line readable
        lines = err.splitlines()
        return False, lines[-1]
    return False, "Offline render failed (no output)"
