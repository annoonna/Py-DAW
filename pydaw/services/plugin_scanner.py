# -*- coding: utf-8 -*-
"""External plugin scanner (LV2/LADSPA/DSSI/VST).

SAFE DESIGN GOALS
-----------------
This module is intentionally *UI-only*:
- It does NOT load/host plugins.
- It does NOT touch the audio engine.
- It only scans the filesystem for installed plugins and extracts minimal metadata.

We keep this module dependency-free (stdlib only) and best-effort.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class ExtPlugin:
    kind: str  # lv2|ladspa|dssi|vst2|vst3
    plugin_id: str  # stable identifier (LV2 URI or path)
    name: str
    path: str = ""  # filesystem path (bundle dir or binary)
    is_instrument: bool = False  # v0.0.20.406: True if synth/instrument, False if effect


def _cache_base_dir() -> Path:
    base = Path(os.path.expanduser("~/.cache")) / "ChronoScaleStudio"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return Path(".")
    return base


def cache_path() -> Path:
    return _cache_base_dir() / "plugin_cache.json"


def load_cache() -> Dict[str, List[ExtPlugin]]:
    p = cache_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, List[ExtPlugin]] = {}
    try:
        raw = data.get("plugins") or {}
        if not isinstance(raw, dict):
            return {}
        for kind, arr in raw.items():
            if not isinstance(arr, list):
                continue
            items: List[ExtPlugin] = []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                pid = str(it.get("plugin_id") or "")
                nm = str(it.get("name") or "")
                path = str(it.get("path") or "")
                if pid:
                    is_inst = bool(it.get("is_instrument", False))
                    items.append(ExtPlugin(str(kind), pid, nm or pid, path, is_instrument=is_inst))
            out[str(kind)] = items
    except Exception:
        return {}
    return out


def save_cache(plugins: Dict[str, List[ExtPlugin]]) -> None:
    p = cache_path()
    try:
        data = {
            "ts": float(time.time()),
            "plugins": {k: [asdict(x) for x in v] for k, v in plugins.items()},
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def cache_is_fresh(max_age_seconds: float = 3600 * 4) -> bool:
    """Return True if the plugin cache exists and was written less than *max_age_seconds* ago."""
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        ts = float(data.get("ts") or 0)
        return (time.time() - ts) < max_age_seconds
    except Exception:
        return False


def _split_env_paths(varname: str) -> List[Path]:
    raw = os.environ.get(varname) or ""
    if not raw:
        return []
    out: List[Path] = []
    for part in raw.split(os.pathsep):
        part = (part or "").strip()
        if part:
            out.append(Path(os.path.expanduser(part)))
    return out


def _linux_multiarch_libdirs() -> List[Path]:
    roots = []
    for p in (Path("/usr/lib"), Path("/usr/local/lib")):
        roots.append(p)
        try:
            for child in p.iterdir():
                if child.is_dir() and "-linux-gnu" in child.name:
                    roots.append(child)
        except Exception:
            continue
    seen: Set[str] = set()
    out: List[Path] = []
    for r in roots:
        s = str(r)
        if s not in seen:
            seen.add(s)
            out.append(r)
    return out


def default_paths(kind: str) -> List[Path]:
    kind = str(kind)
    home = Path(os.path.expanduser("~"))

    if sys.platform.startswith("linux"):
        libroots = _linux_multiarch_libdirs()
        mapping = {
            "lv2": [*(r / "lv2" for r in libroots), home / ".lv2", home / ".local/lib/lv2"],
            "ladspa": [*(r / "ladspa" for r in libroots), home / ".ladspa", home / ".local/lib/ladspa"],
            "dssi": [*(r / "dssi" for r in libroots), home / ".dssi", home / ".local/lib/dssi"],
            "vst2": [*(r / "vst" for r in libroots), home / ".vst", home / ".local/lib/vst"],
            "vst3": [*(r / "vst3" for r in libroots), home / ".vst3", home / ".local/lib/vst3"],
            "clap": [*(r / "clap" for r in libroots), home / ".clap", home / ".local/lib/clap"],
        }
        return [p for p in mapping.get(kind, [])]

    if sys.platform == "darwin":
        mapping = {
            "vst2": [Path("/Library/Audio/Plug-Ins/VST"), home / "Library/Audio/Plug-Ins/VST"],
            "vst3": [Path("/Library/Audio/Plug-Ins/VST3"), home / "Library/Audio/Plug-Ins/VST3"],
            "lv2": [Path("/Library/Audio/Plug-Ins/LV2"), home / "Library/Audio/Plug-Ins/LV2"],
            "ladspa": [Path("/Library/Audio/Plug-Ins/LADSPA"), home / "Library/Audio/Plug-Ins/LADSPA"],
            "dssi": [Path("/Library/Audio/Plug-Ins/DSSI"), home / "Library/Audio/Plug-Ins/DSSI"],
            "clap": [Path("/Library/Audio/Plug-Ins/CLAP"), home / "Library/Audio/Plug-Ins/CLAP"],
        }
        return [p for p in mapping.get(kind, [])]

    if sys.platform.startswith("win"):
        pf = os.environ.get("ProgramFiles") or r"C:\\Program Files"
        pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\\Program Files (x86)"
        appdata = os.environ.get("APPDATA") or str(home / "AppData/Roaming")
        localappdata = os.environ.get("LOCALAPPDATA") or str(home / "AppData/Local")
        mapping = {
            "vst3": [Path(pf) / "Common Files/VST3", Path(pf86) / "Common Files/VST3", Path(localappdata) / "Programs/Common/VST3"],
            "vst2": [Path(pf) / "VSTPlugins", Path(pf) / "Steinberg/VstPlugins", Path(pf86) / "VSTPlugins", Path(pf86) / "Steinberg/VstPlugins", Path(appdata) / "VSTPlugins"],
            "lv2": [],
            "ladspa": [],
            "dssi": [],
            "clap": [Path(pf) / "Common Files/CLAP", Path(pf86) / "Common Files/CLAP", Path(localappdata) / "Programs/Common/CLAP"],
        }
        return [p for p in mapping.get(kind, [])]

    return []


def resolve_search_paths(kind: str, extra_paths: Optional[Iterable[str]] = None) -> List[Path]:
    kind = str(kind)
    extras = [Path(os.path.expanduser(str(x))) for x in (extra_paths or []) if str(x).strip()]

    env_map = {
        "lv2": "LV2_PATH",
        "ladspa": "LADSPA_PATH",
        "dssi": "DSSI_PATH",
        "vst2": "VST_PATH",
        "vst3": "VST3_PATH",
        "clap": "CLAP_PATH",
    }
    env = _split_env_paths(env_map.get(kind, "")) if env_map.get(kind) else []

    out: List[Path] = []
    if extras:
        if any(p.exists() for p in extras):
            out = extras
    if not out:
        out = default_paths(kind)

    merged: List[Path] = []
    seen: Set[str] = set()
    for p in [*env, *out]:
        try:
            ps = str(p)
            if ps in seen:
                continue
            seen.add(ps)
            merged.append(p)
        except Exception:
            continue
    return merged


def _iter_existing_dirs(paths: Iterable[Path]) -> List[Path]:
    out: List[Path] = []
    seen: Set[str] = set()
    for p in paths:
        try:
            p = Path(p)
            if not p.exists() or not p.is_dir():
                continue
            s = str(p)
            if s in seen:
                continue
            seen.add(s)
            out.append(p)
        except Exception:
            continue
    return out


# NOTE:
# LV2 manifests vary:
# - Some use `a lv2:Plugin` in manifest.ttl
# - Some use `rdf:type lv2:Plugin`
# - Some use full URI: `a <http://lv2plug.in/ns/lv2core#Plugin>`
# - Some only reference other .ttl via rdfs:seeAlso, and the plugin type lives there.
# - SWH (Steve Harris) plugins may use different prefix names (lv2core:Plugin, etc.)
#
# We therefore use multiple permissive regexes and (if needed) scan additional .ttl files
# inside the bundle.
_LV2_PLUGIN_RE = re.compile(
    r"<(?P<uri>[^>]+)>\s+(?:a|rdf:type)\s+[^.]*?\blv2:(?:Plugin|InstrumentPlugin|EffectPlugin)\b",
    re.IGNORECASE | re.DOTALL,
)

# Additional patterns for plugins that use full URIs or different prefixes
_LV2_PLUGIN_RE2 = re.compile(
    r"<(?P<uri>[^>]+)>\s+(?:a|rdf:type)\s+[^.;]*?<http://lv2plug\.in/ns/lv2core#(?:Plugin|InstrumentPlugin|EffectPlugin)>",
    re.IGNORECASE | re.DOTALL,
)

# Broader pattern: any prefix ending with :Plugin, :InstrumentPlugin, :EffectPlugin
_LV2_PLUGIN_RE3 = re.compile(
    r"<(?P<uri>https?://[^>]+)>\s+(?:a|rdf:type)\s+[^.;]*?\w+:(?:Plugin|InstrumentPlugin|EffectPlugin)\b",
    re.IGNORECASE | re.DOTALL,
)

# v0.0.20.408: Regex to detect InstrumentPlugin classification
_LV2_INSTRUMENT_RE = re.compile(
    r"<[^>]+>\s+(?:a|rdf:type)\s+[^.;]*?(?:lv2:|<http://lv2plug\.in/ns/lv2core#)InstrumentPlugin\b",
    re.IGNORECASE | re.DOTALL,
)

_LV2_LABEL_RE = re.compile(r"(?:doap:name|rdfs:label)\s+\"([^\"]+)\"", re.IGNORECASE)


def _lv2_guess_name(uri: str) -> str:
    u = str(uri)
    for sep in ("#", "/"):
        if sep in u:
            u = u.rsplit(sep, 1)[-1]
    return u or uri


def _parse_lv2_manifest(manifest_text: str) -> List[Tuple[str, str]]:
    t = manifest_text or ""
    t = re.sub(r"(^|\s)#.*$", "", t, flags=re.MULTILINE)
    found: List[Tuple[str, str]] = []
    seen_uris: set = set()
    # Try all regex patterns (primary, full-URI, broader prefix)
    for regex in (_LV2_PLUGIN_RE, _LV2_PLUGIN_RE2, _LV2_PLUGIN_RE3):
        for m in regex.finditer(t):
            uri = m.group("uri") or ""
            if not uri or uri in seen_uris:
                continue
            seen_uris.add(uri)
            name = ""
            # Best-effort: try to find a name in the same file near the URI.
            try:
                # Look within a limited window after the match for a label.
                start = max(0, m.start() - 200)
                end = min(len(t), m.end() + 600)
                blob = t[start:end]
                nm = _LV2_LABEL_RE.search(blob)
                if nm:
                    name = str(nm.group(1) or "").strip()
            except Exception:
                name = ""
            if uri:
                found.append((uri, name or _lv2_guess_name(uri)))
    return found


def _parse_lv2_bundle(bundle_dir: Path) -> List[Tuple[str, str]]:
    """Best-effort LV2 bundle scan when manifest parsing yields no plugin URIs."""
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return []

    # Read a limited number of .ttl files to avoid huge bundles.
    ttl_files: List[Path] = []
    try:
        ttl_files = sorted([p for p in bundle_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ttl"])[:16]
    except Exception:
        ttl_files = []

    uris: Dict[str, str] = {}
    for f in ttl_files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        txt = re.sub(r"(^|\s)#.*$", "", txt, flags=re.MULTILINE)
        for regex in (_LV2_PLUGIN_RE, _LV2_PLUGIN_RE2, _LV2_PLUGIN_RE3):
            for m in regex.finditer(txt):
                uri = (m.group("uri") or "").strip()
                if not uri or uri in uris:
                    continue
                nm = ""
                try:
                    start = max(0, m.start() - 200)
                    end = min(len(txt), m.end() + 800)
                    blob = txt[start:end]
                    m2 = _LV2_LABEL_RE.search(blob)
                    if m2:
                        nm = str(m2.group(1) or "").strip()
                except Exception:
                    nm = ""
                uris[uri] = nm or _lv2_guess_name(uri)

    return [(u, n) for u, n in uris.items()]


import shutil as _shutil
import subprocess as _subprocess

# Module-level cache: lv2ls output (populated once, reused for all bundles)
_LV2LS_CACHE: Optional[List[str]] = None
_LV2LS_CACHE_DONE = False


def _get_lv2ls_uris() -> List[str]:
    """Return all known LV2 plugin URIs via lv2ls (called ONCE, cached)."""
    global _LV2LS_CACHE, _LV2LS_CACHE_DONE
    if _LV2LS_CACHE_DONE:
        return _LV2LS_CACHE or []
    _LV2LS_CACHE_DONE = True
    if not _shutil.which("lv2ls"):
        _LV2LS_CACHE = []
        return []
    try:
        p = _subprocess.run(
            ["lv2ls"],
            text=True, errors="replace", capture_output=True,
            timeout=8.0, check=False,
        )
        _LV2LS_CACHE = [line.strip() for line in (p.stdout or "").splitlines() if line.strip()]
    except Exception:
        _LV2LS_CACHE = []
    return _LV2LS_CACHE or []


def _resolve_bundle_via_lv2info(bundle_dir: Path) -> List[Tuple[str, str]]:
    """Resolve LV2 plugin URIs from a bundle dir via cached lv2ls output.

    Uses pure name-matching heuristics — NO per-bundle subprocess spawning.
    This is safe for hundreds of bundles without blocking the UI.
    """
    all_uris = _get_lv2ls_uris()
    if not all_uris:
        return []

    bundle_name = bundle_dir.stem  # e.g. "freq_tracker-swh"
    # Normalize: "freq_tracker-swh" → "freq_tracker_swh" → ["freq", "tracker", "swh"]
    bn_norm = bundle_name.lower().replace("-", "_").replace(".lv2", "")
    parts = [p for p in bn_norm.split("_") if len(p) >= 3]  # skip tiny fragments
    if not parts:
        # Very short bundle name — use full name
        parts = [bn_norm] if bn_norm else []
    if not parts:
        return []

    found: List[Tuple[str, str]] = []
    for uri in all_uris:
        uri_lower = uri.lower().replace("-", "_")
        # Heuristic: the URI's fragment/path should contain the main bundle name parts
        # e.g. bundle "freq_tracker-swh" → URI should contain "freq_tracker"
        # Match if the longest meaningful part appears in the URI
        matched = False
        # Try longest compound first
        compound = "_".join(parts[:-1]) if len(parts) > 1 else parts[0]
        if compound and len(compound) >= 4 and compound in uri_lower:
            matched = True
        elif parts[0] and len(parts[0]) >= 4 and parts[0] in uri_lower:
            # Fallback: first part only (e.g. "compressor" in compressor_stereo-swh)
            # But require the suffix part too to avoid false positives
            if len(parts) > 1:
                suffix = parts[-1]
                if suffix in ("swh", "lv2", "so"):
                    # Known suffix — skip it, match on the content parts
                    matched = any(p in uri_lower for p in parts[:-1] if len(p) >= 3)
                else:
                    matched = parts[0] in uri_lower
            else:
                matched = True

        if matched:
            name = _lv2_guess_name(uri)
            found.append((uri, name))

    return found


def scan_lv2(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    items: List[ExtPlugin] = []
    seen: Set[str] = set()
    for base in _iter_existing_dirs(search_paths):
        try:
            for bundle in base.iterdir():
                try:
                    if not bundle.is_dir() or not bundle.name.lower().endswith(".lv2"):
                        continue
                    manifest = bundle / "manifest.ttl"
                    plugins: List[Tuple[str, str]] = []
                    if manifest.exists() and manifest.is_file():
                        try:
                            txt = manifest.read_text(encoding="utf-8", errors="ignore")
                            plugins = _parse_lv2_manifest(txt)
                        except Exception:
                            plugins = []
                    # Fallback: scan other TTLs in the bundle if manifest doesn't contain plugin types.
                    if not plugins:
                        try:
                            plugins = _parse_lv2_bundle(bundle)
                        except Exception:
                            plugins = []
                    if not plugins:
                        # Last resort: try to resolve plugin URI(s) via lv2info/lv2ls
                        # (SWH and similar plugins may have TTL formats our regex can't parse)
                        try:
                            plugins = _resolve_bundle_via_lv2info(bundle)
                        except Exception:
                            plugins = []
                    if not plugins:
                        # Absolute last resort: store bundle path.
                        # LV2 host code has _plugin_by_bundle_path() for these.
                        pid = str(bundle)
                        if pid not in seen:
                            seen.add(pid)
                            items.append(ExtPlugin("lv2", pid, bundle.name, str(bundle)))
                        continue

                    # v0.0.20.408: Detect InstrumentPlugin in TTL files
                    _is_inst_bundle = False
                    try:
                        for ttl in bundle.iterdir():
                            if ttl.suffix.lower() == ".ttl":
                                try:
                                    ttxt = ttl.read_text(encoding="utf-8", errors="ignore")
                                    if _LV2_INSTRUMENT_RE.search(ttxt):
                                        _is_inst_bundle = True
                                        break
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    for uri, name in plugins:
                        pid = str(uri or "").strip()
                        # Safety: LV2 plugin_id must be a URI, not a filesystem path.
                        if (not pid) or pid.startswith("/") or (":" not in pid):
                            continue
                        if pid in seen:
                            continue
                        seen.add(pid)
                        items.append(ExtPlugin("lv2", pid, name, str(bundle), is_instrument=_is_inst_bundle))
                except Exception:
                    continue
        except Exception:
            continue
    items.sort(key=lambda x: (x.name.lower(), x.plugin_id.lower()))
    return items


def _scan_shared_objects(search_paths: Iterable[Path], kind: str, exts: Tuple[str, ...]) -> List[ExtPlugin]:
    items: List[ExtPlugin] = []
    seen: Set[str] = set()
    max_items = 20000
    for base in _iter_existing_dirs(search_paths):
        try:
            for f in base.iterdir():
                if len(items) >= max_items:
                    break
                try:
                    if not f.is_file() or f.suffix.lower() not in exts:
                        continue
                    pid = str(f)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    items.append(ExtPlugin(kind, pid, f.stem, str(f)))
                except Exception:
                    continue
        except Exception:
            continue
    items.sort(key=lambda x: (x.name.lower(), x.plugin_id.lower()))
    return items


def scan_ladspa(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    exts = (".dll",) if sys.platform.startswith("win") else (".dylib", ".so") if sys.platform == "darwin" else (".so",)
    return _scan_shared_objects(search_paths, "ladspa", exts)


def scan_dssi(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    exts = (".dll",) if sys.platform.startswith("win") else (".dylib", ".so") if sys.platform == "darwin" else (".so",)
    return _scan_shared_objects(search_paths, "dssi", exts)


def scan_vst2(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    items: List[ExtPlugin] = []
    seen: Set[str] = set()
    max_items = 20000

    if sys.platform == "darwin":
        for base in _iter_existing_dirs(search_paths):
            try:
                for d in base.iterdir():
                    if len(items) >= max_items:
                        break
                    try:
                        if not d.is_dir() or not d.name.lower().endswith(".vst"):
                            continue
                        pid = str(d)
                        if pid in seen:
                            continue
                        seen.add(pid)
                        items.append(ExtPlugin("vst2", pid, d.stem, str(d)))
                    except Exception:
                        continue
            except Exception:
                continue
        items.sort(key=lambda x: (x.name.lower(), x.plugin_id.lower()))
        return items

    exts = (".dll",) if sys.platform.startswith("win") else (".so",)
    raw = _scan_shared_objects(search_paths, "vst2", exts)

    # v0.0.20.406: Detect instruments (synths) via subprocess probe
    # Uses is_vst2_instrument() which caches results and uses a 5s timeout per plugin.
    try:
        from pydaw.audio.vst2_host import is_vst2_instrument
        _has_probe = True
    except Exception:
        _has_probe = False

    result: List[ExtPlugin] = []
    for p in raw:
        is_inst = False
        if _has_probe:
            try:
                is_inst = is_vst2_instrument(str(p.path or p.plugin_id))
            except Exception:
                is_inst = False
        result.append(ExtPlugin(p.kind, p.plugin_id, p.name, p.path, is_instrument=is_inst))
    return result


def _should_try_multi_vst_probe(path: Path) -> bool:
    """Return True only for bundles that are known/safe to enumerate eagerly.

    Why this guard exists:
    v0.0.20.364 tried to call ``pedalboard.load_plugin()`` for *every* VST3
    during browser scans to detect multi-plugin bundles. Some plugins (for
    example ZamVerb on Linux) can hang or spam assertions during that eager
    instantiation, which blocked app startup.

    We therefore keep startup scans shallow and only allow eager probing for
    known bundle-style collections where ``pedalboard`` returns the plugin-name
    list quickly and safely. Additional probing can be enabled explicitly via
    ``PYDAW_VST_MULTI_PROBE=1`` if needed for debugging.
    """
    if os.environ.get("PYDAW_VST_MULTI_PROBE", "").strip() == "1":
        return True
    stem = str(path.stem or "").strip().lower().replace("_", "-")
    name = str(path.name or "").strip().lower().replace("_", "-")
    safe_known = {
        "lsp-plugins",
        "lsp-plugins.vst3",
    }
    return stem in safe_known or name in safe_known



def _expand_multi_vst_plugins(kind: str, path: Path, items: List[ExtPlugin], seen: Set[str]) -> bool:
    """Expand one VST bundle/file into separate sub-plugin entries when possible.

    v0.0.20.725: Uses fork-based crash isolation when probing multi-plugin bundles.
    If the probe subprocess crashes (SEGFAULT), the plugin is blacklisted and
    the main process stays alive.

    SAFE HOTFIX:
    We do *not* instantiate arbitrary VSTs during startup scans anymore.
    Only a tiny allow-list of known collection bundles is probed eagerly.
    Everything else remains a plain path entry so the app opens reliably.
    """
    if not _should_try_multi_vst_probe(path):
        return False

    path_s = str(path)

    # v0.0.20.725: Check persistent blacklist first (no fork needed)
    try:
        from pydaw.services.plugin_probe import is_blacklisted
        if is_blacklisted(path_s, kind):
            return False
    except ImportError:
        pass

    # v0.0.20.725: Use fork-based probe for crash isolation
    try:
        from pydaw.services.plugin_probe import is_plugin_safe
        if not is_plugin_safe(path_s, kind):
            return False  # Plugin crashed in probe — blacklisted
    except ImportError:
        pass  # Probe not available — proceed without isolation

    try:
        from pydaw.audio.vst3_host import build_plugin_reference, probe_multi_plugin_names
    except Exception:
        return False

    try:
        sub_plugins = probe_multi_plugin_names(path_s)
    except Exception:
        return False
    if not sub_plugins:
        return False

    for pname in sub_plugins:
        try:
            label = str(pname or "").strip() or path.stem
            pid = build_plugin_reference(path_s, label)
            if pid in seen:
                continue
            seen.add(pid)
            items.append(ExtPlugin(kind, pid, label, path_s))
        except Exception:
            continue
    return True


def scan_vst3(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    items: List[ExtPlugin] = []
    seen: Set[str] = set()
    max_items = 20000
    for base in _iter_existing_dirs(search_paths):
        try:
            for entry in base.iterdir():
                if len(items) >= max_items:
                    break
                try:
                    if entry.is_dir() and entry.name.lower().endswith(".vst3"):
                        is_inst = _check_vst3_is_instrument(entry)
                        before_count = len(items)
                        if _expand_multi_vst_plugins("vst3", entry, items, seen):
                            # Mark newly expanded items with instrument flag
                            if is_inst:
                                for i in range(before_count, len(items)):
                                    p = items[i]
                                    if not p.is_instrument:
                                        items[i] = ExtPlugin(p.kind, p.plugin_id, p.name, p.path, is_instrument=True)
                            continue
                        pid = str(entry)
                        if pid in seen:
                            continue
                        seen.add(pid)
                        items.append(ExtPlugin("vst3", pid, entry.stem, str(entry), is_instrument=is_inst))
                        continue
                    if entry.is_file() and entry.suffix.lower() in (".vst3", ".dll", ".so", ".dylib"):
                        if _expand_multi_vst_plugins("vst3", entry, items, seen):
                            continue
                        pid = str(entry)
                        if pid in seen:
                            continue
                        seen.add(pid)
                        items.append(ExtPlugin("vst3", pid, entry.stem, str(entry)))
                except Exception:
                    continue
        except Exception:
            continue
    items.sort(key=lambda x: (x.name.lower(), x.plugin_id.lower()))
    return items


def _check_vst3_is_instrument(bundle_path: Path) -> bool:
    """Check if a VST3 bundle is an instrument.

    v0.0.20.409: Checks moduleinfo.json (VST3 SDK standard) for SubCategories
    containing 'Instrument'. Falls back to name heuristics for known synths.
    """
    bundle = Path(bundle_path)

    # 1. Check moduleinfo.json (newer VST3 SDK bundles)
    for mi_path in (bundle / "Contents" / "moduleinfo.json", bundle / "moduleinfo.json"):
        try:
            if mi_path.exists():
                import json
                data = json.loads(mi_path.read_text(encoding="utf-8", errors="ignore"))
                for cls in (data.get("Classes") or data.get("classes") or []):
                    subcats = str(cls.get("SubCategories") or cls.get("subCategories") or cls.get("sub_categories") or "")
                    if "instrument" in subcats.lower() or "synth" in subcats.lower():
                        return True
                # If moduleinfo exists but no instrument class found, it's an effect
                return False
        except Exception:
            pass

    # 2. Name-based heuristics for well-known instruments
    name_lower = bundle.stem.lower()
    _KNOWN_INSTRUMENTS = {
        "surge xt", "surge", "dexed", "vital", "helm", "serum", "massive",
        "pigments", "analog lab", "zebra", "zebralette", "u-he", "diva",
        "synth1", "odin2", "juicysfplugin", "sfizz", "fluidsynth",
        "zynaddsubfx", "yoshimi", "amsynth", "obxd", "tal-noisemaker",
        "tal-u-no", "tal-bassline", "cardinal", "distrho-cardinal",
    }
    for kw in _KNOWN_INSTRUMENTS:
        if kw in name_lower:
            return True

    return False


def scan_clap(search_paths: Iterable[Path]) -> List[ExtPlugin]:
    """Scan for CLAP plugins (.clap bundles / shared libraries).

    CLAP files are .clap bundles (macOS) or .clap shared objects (Linux/Windows).
    Each file may contain multiple plugins; we enumerate them all.

    v0.0.20.457 — Initial CLAP scanner
    """
    items: List[ExtPlugin] = []
    seen: Set[str] = set()
    max_items = 20000

    # Platform-specific file extensions
    if sys.platform == "darwin":
        # macOS: .clap bundles (directories like MyPlugin.clap/)
        for base in _iter_existing_dirs(search_paths):
            try:
                for entry in base.iterdir():
                    if len(items) >= max_items:
                        break
                    try:
                        if not entry.name.lower().endswith(".clap"):
                            continue
                        clap_path = str(entry)
                        if clap_path in seen:
                            continue
                        seen.add(clap_path)

                        # macOS bundles: the actual .so is inside Contents/MacOS/
                        so_path = entry / "Contents" / "MacOS" / entry.stem
                        if not so_path.exists():
                            # Try the bundle itself
                            so_path = entry
                            if not entry.is_file():
                                continue

                        # Try to enumerate plugins
                        try:
                            from pydaw.audio.clap_host import enumerate_clap_plugins
                            descs = enumerate_clap_plugins(str(so_path))
                            if descs:
                                for d in descs:
                                    pid = f"{clap_path}::{d.id}"
                                    if pid not in seen:
                                        seen.add(pid)
                                        # v0.0.20.533: Pass is_instrument from CLAP features
                                        items.append(ExtPlugin("clap", pid, d.name or entry.stem, clap_path,
                                                                is_instrument=bool(getattr(d, "is_instrument", False))))
                            else:
                                items.append(ExtPlugin("clap", clap_path, entry.stem, clap_path))
                        except Exception:
                            items.append(ExtPlugin("clap", clap_path, entry.stem, clap_path))
                    except Exception:
                        continue
            except Exception:
                continue
    else:
        # Linux/Windows: .clap files are shared libraries
        exts = (".clap",)
        for base in _iter_existing_dirs(search_paths):
            try:
                for entry in base.iterdir():
                    if len(items) >= max_items:
                        break
                    try:
                        if entry.is_file() and entry.suffix.lower() in exts:
                            clap_path = str(entry)
                            if clap_path in seen:
                                continue
                            seen.add(clap_path)

                            # Try to enumerate plugins
                            try:
                                from pydaw.audio.clap_host import enumerate_clap_plugins
                                descs = enumerate_clap_plugins(clap_path)
                                if descs:
                                    for d in descs:
                                        pid = f"{clap_path}::{d.id}"
                                        if pid not in seen:
                                            seen.add(pid)
                                            # v0.0.20.533: Pass is_instrument from CLAP features
                                            items.append(ExtPlugin("clap", pid, d.name or entry.stem, clap_path,
                                                                    is_instrument=bool(getattr(d, "is_instrument", False))))
                                else:
                                    items.append(ExtPlugin("clap", clap_path, entry.stem, clap_path))
                            except Exception:
                                items.append(ExtPlugin("clap", clap_path, entry.stem, clap_path))
                        elif entry.is_dir() and entry.name.lower().endswith(".clap"):
                            # Some Linux CLAP plugins are directories too
                            clap_path = str(entry)
                            if clap_path in seen:
                                continue
                            seen.add(clap_path)
                            items.append(ExtPlugin("clap", clap_path, entry.stem, clap_path))
                    except Exception:
                        continue
            except Exception:
                continue

    items.sort(key=lambda x: (x.name.lower(), x.plugin_id.lower()))
    return items


def scan_all(extra_paths: Optional[Dict[str, Iterable[str]]] = None) -> Dict[str, List[ExtPlugin]]:
    extra_paths = extra_paths or {}
    return {
        "lv2": scan_lv2(resolve_search_paths("lv2", extra_paths.get("lv2"))),
        "ladspa": scan_ladspa(resolve_search_paths("ladspa", extra_paths.get("ladspa"))),
        "dssi": scan_dssi(resolve_search_paths("dssi", extra_paths.get("dssi"))),
        "vst2": scan_vst2(resolve_search_paths("vst2", extra_paths.get("vst2"))),
        "vst3": scan_vst3(resolve_search_paths("vst3", extra_paths.get("vst3"))),
        "clap": scan_clap(resolve_search_paths("clap", extra_paths.get("clap"))),
    }


def scan_all_with_probe(extra_paths: Optional[Dict[str, Iterable[str]]] = None,
                         probe_types: Optional[Set[str]] = None
                         ) -> Dict[str, List[ExtPlugin]]:
    """Scan all plugins AND probe VST3/CLAP for crash safety.

    v0.0.20.725: Integrates fork-based probing into the scan pass.

    Args:
        extra_paths: Extra search paths per plugin type
        probe_types: Which plugin types to probe (default: {"vst3", "vst2", "clap"}).
                     LV2/LADSPA are generally safe and don't need probing.

    Returns:
        Same format as scan_all(), but blacklisted plugins are EXCLUDED.
        Blacklisted plugins are logged to stderr and saved to disk.
    """
    if probe_types is None:
        probe_types = {"vst3", "vst2", "clap"}

    all_plugins = scan_all(extra_paths)
    result: Dict[str, List[ExtPlugin]] = {}

    # Try importing the probe module
    try:
        from pydaw.services.plugin_probe import is_blacklisted, is_plugin_safe
        has_probe = True
    except ImportError:
        has_probe = False

    for kind, plugins in all_plugins.items():
        if not has_probe or kind not in probe_types:
            result[kind] = plugins
            continue

        safe_plugins: List[ExtPlugin] = []
        n_blacklisted = 0
        for p in plugins:
            # Check persistent blacklist first (no fork needed)
            if is_blacklisted(p.path, p.kind, p.name, p.plugin_id):
                n_blacklisted += 1
                continue
            safe_plugins.append(p)

        if n_blacklisted > 0:
            print(f"[SCAN+PROBE] {kind}: {n_blacklisted} blacklisted plugin(s) excluded",
                  file=sys.stderr, flush=True)

        result[kind] = safe_plugins

    return result