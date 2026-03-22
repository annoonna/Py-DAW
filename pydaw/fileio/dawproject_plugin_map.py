"""DAWproject Plugin Mapping — VST3/CLAP/LV2 ID ↔ DAWproject Device ID.

The DAWproject format uses a ``deviceID`` attribute on <Plugin> elements to
identify plugins across different DAWs.  The standard conventions are:

  - VST3:  ``"plugin:<vst3_class_id_hex>"``  (32-char hex TUID)
  - CLAP:  ``"clap:<clap_id>"``              (reverse-domain string)
  - AU:    ``"au:<type>/<subtype>/<manufacturer>"``
  - Builtin: ``"device:<daw_name>/<device_name>"``

This module provides a bidirectional mapping layer so Py_DAW can:
  1. Export its internal plugin IDs to spec-compliant DAWproject deviceIDs
  2. Import DAWproject deviceIDs and resolve them to Py_DAW plugin types
  3. Maintain a well-known-plugins database for common VST3/CLAP plugins

v0.0.20.658 — AP10 Phase 10C (Claude Opus 4.6, 2026-03-20)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PluginIdentity:
    """Canonical representation of a plugin across formats."""
    format: str = ""          # "VST3" | "CLAP" | "LV2" | "LADSPA" | "INTERNAL"
    plugin_id: str = ""       # format-specific unique ID
    display_name: str = ""    # human-readable name
    vendor: str = ""          # plugin vendor
    category: str = ""        # "instrument" | "audio-fx" | "note-fx" | "analyzer"


@dataclass
class PluginMapEntry:
    """One entry in the well-known plugin database."""
    dawproject_id: str = ""     # e.g. "plugin:ABCDEF1234567890..."
    pydaw_id: str = ""          # e.g. "vst3:Diva" or "clap:com.u-he.Diva"
    display_name: str = ""
    vendor: str = ""
    format: str = ""            # "VST3" | "CLAP" | "LV2"
    category: str = ""          # "instrument" | "audio-fx"
    aliases: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal (Chrono/Py_DAW) ↔ DAWproject mapping
# ---------------------------------------------------------------------------

# Built-in instruments
_INTERNAL_INSTRUMENT_MAP: Dict[str, str] = {
    # pydaw_id -> dawproject deviceID
    "chrono.pro_sampler":        "device:ChronoScaleStudio/ProSampler",
    "chrono.sampler":            "device:ChronoScaleStudio/ProSampler",
    "sampler":                   "device:ChronoScaleStudio/ProSampler",
    "chrono.pro_drum_machine":   "device:ChronoScaleStudio/ProDrumMachine",
    "chrono.drum_machine":       "device:ChronoScaleStudio/ProDrumMachine",
    "drum_machine":              "device:ChronoScaleStudio/ProDrumMachine",
    "chrono.aeterna":            "device:ChronoScaleStudio/Aeterna",
    "aeterna":                   "device:ChronoScaleStudio/Aeterna",
    "sf2":                       "device:ChronoScaleStudio/SF2Player",
    "chrono.sf2":                "device:ChronoScaleStudio/SF2Player",
}

# Built-in FX
_INTERNAL_FX_MAP: Dict[str, str] = {
    "chrono.fx.eq":              "device:ChronoScaleStudio/ParametricEQ",
    "chrono.fx.compressor":      "device:ChronoScaleStudio/Compressor",
    "chrono.fx.reverb":          "device:ChronoScaleStudio/Reverb",
    "chrono.fx.delay":           "device:ChronoScaleStudio/Delay",
    "chrono.fx.limiter":         "device:ChronoScaleStudio/Limiter",
    "chrono.fx.chorus":          "device:ChronoScaleStudio/Chorus",
    "chrono.fx.phaser":          "device:ChronoScaleStudio/Phaser",
    "chrono.fx.flanger":         "device:ChronoScaleStudio/Flanger",
    "chrono.fx.distortion":      "device:ChronoScaleStudio/Distortion",
    "chrono.fx.tremolo":         "device:ChronoScaleStudio/Tremolo",
    "chrono.fx.gate":            "device:ChronoScaleStudio/Gate",
    "chrono.fx.deesser":         "device:ChronoScaleStudio/DeEsser",
    "chrono.fx.stereo_widener":  "device:ChronoScaleStudio/StereoWidener",
    "chrono.fx.utility":         "device:ChronoScaleStudio/Utility",
    "chrono.fx.spectrum":        "device:ChronoScaleStudio/SpectrumAnalyzer",
}

# Built-in Note-FX
_INTERNAL_NOTE_FX_MAP: Dict[str, str] = {
    "chrono.note_fx.arp":            "device:ChronoScaleStudio/Arpeggiator",
    "chrono.note_fx.chord":          "device:ChronoScaleStudio/ChordGenerator",
    "chrono.note_fx.scale_snap":     "device:ChronoScaleStudio/ScaleQuantizer",
    "chrono.note_fx.randomizer":     "device:ChronoScaleStudio/Randomizer",
    "chrono.note_fx.note_echo":      "device:ChronoScaleStudio/NoteEcho",
    "chrono.note_fx.velocity_curve": "device:ChronoScaleStudio/VelocityCurve",
}

# Reverse lookup: dawproject deviceID → pydaw_id (first match wins)
_DAWPROJECT_TO_PYDAW: Dict[str, str] = {}
for _pydaw_id, _daw_id in {**_INTERNAL_INSTRUMENT_MAP, **_INTERNAL_FX_MAP, **_INTERNAL_NOTE_FX_MAP}.items():
    _DAWPROJECT_TO_PYDAW.setdefault(_daw_id, _pydaw_id)


# ---------------------------------------------------------------------------
# Well-known third-party plugins (common VST3/CLAP plugins)
# ---------------------------------------------------------------------------

_WELL_KNOWN_PLUGINS: List[PluginMapEntry] = [
    # Synthesizers
    PluginMapEntry(dawproject_id="plugin:D39D5B69D6AF42FA", pydaw_id="vst3:Serum", display_name="Serum", vendor="Xfer Records", format="VST3", category="instrument"),
    PluginMapEntry(dawproject_id="clap:com.u-he.Diva", pydaw_id="clap:com.u-he.Diva", display_name="Diva", vendor="u-he", format="CLAP", category="instrument"),
    PluginMapEntry(dawproject_id="clap:com.u-he.Zebra2", pydaw_id="clap:com.u-he.Zebra2", display_name="Zebra2", vendor="u-he", format="CLAP", category="instrument"),
    PluginMapEntry(dawproject_id="clap:org.surge-synth-team.surge-xt", pydaw_id="clap:org.surge-synth-team.surge-xt", display_name="Surge XT", vendor="Surge Synth Team", format="CLAP", category="instrument"),
    PluginMapEntry(dawproject_id="clap:com.vital.synth", pydaw_id="clap:com.vital.synth", display_name="Vital", vendor="Matt Tytel", format="CLAP", category="instrument"),
    # FX
    PluginMapEntry(dawproject_id="clap:com.tokyodawn.TDRKotelnikov", pydaw_id="clap:com.tokyodawn.TDRKotelnikov", display_name="TDR Kotelnikov", vendor="Tokyo Dawn Records", format="CLAP", category="audio-fx"),
    PluginMapEntry(dawproject_id="clap:org.surge-synth-team.surge-xt-fx", pydaw_id="clap:org.surge-synth-team.surge-xt-fx", display_name="Surge XT FX", vendor="Surge Synth Team", format="CLAP", category="audio-fx"),
]

# Index well-known plugins by various keys
_KNOWN_BY_DAWPROJECT_ID: Dict[str, PluginMapEntry] = {e.dawproject_id: e for e in _WELL_KNOWN_PLUGINS}
_KNOWN_BY_PYDAW_ID: Dict[str, PluginMapEntry] = {e.pydaw_id: e for e in _WELL_KNOWN_PLUGINS}
_KNOWN_BY_NAME: Dict[str, PluginMapEntry] = {e.display_name.lower(): e for e in _WELL_KNOWN_PLUGINS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pydaw_id_to_dawproject_device_id(pydaw_plugin_id: str) -> str:
    """Convert a Py_DAW plugin_id to a DAWproject-compliant deviceID string.

    Handles internal plugins, VST3, CLAP, LV2, LADSPA.
    Falls back to ``"device:unknown/<plugin_id>"`` for unrecognised plugins.
    """
    if not pydaw_plugin_id:
        return ""

    pid = str(pydaw_plugin_id)

    # 1) Direct internal map lookup
    if pid in _INTERNAL_INSTRUMENT_MAP:
        return _INTERNAL_INSTRUMENT_MAP[pid]
    if pid in _INTERNAL_FX_MAP:
        return _INTERNAL_FX_MAP[pid]
    if pid in _INTERNAL_NOTE_FX_MAP:
        return _INTERNAL_NOTE_FX_MAP[pid]

    # 2) Well-known third-party plugins
    if pid in _KNOWN_BY_PYDAW_ID:
        return _KNOWN_BY_PYDAW_ID[pid].dawproject_id

    # 3) Format-based inference
    lower = pid.lower()

    # VST3: "vst3:<name>" or raw UUID
    if lower.startswith("vst3:"):
        name_part = pid[5:]
        # If it looks like a hex UUID, use plugin: prefix
        if re.match(r'^[0-9A-Fa-f]{16,32}$', name_part):
            return f"plugin:{name_part.upper()}"
        return f"plugin:vst3/{name_part}"

    # CLAP: already a reverse-domain id
    if lower.startswith("clap:"):
        return f"clap:{pid[5:]}"

    # LV2: URI-based
    if lower.startswith("lv2:") or lower.startswith("ext.lv2:"):
        uri = pid.split(":", 1)[1] if ":" in pid else pid
        return f"lv2:{uri}"

    # LADSPA: numeric ID or name
    if lower.startswith("ladspa:"):
        return f"ladspa:{pid[7:]}"

    # Internal/chrono prefix fallback
    if lower.startswith("chrono.") or lower.startswith("internal."):
        return f"device:ChronoScaleStudio/{pid.split('.')[-1]}"

    return f"device:unknown/{pid}"


def dawproject_device_id_to_pydaw_id(dawproject_id: str) -> Optional[str]:
    """Try to resolve a DAWproject deviceID to a Py_DAW plugin_id.

    Returns None if the plugin cannot be mapped (foreign/unknown plugin).
    """
    if not dawproject_id:
        return None

    did = str(dawproject_id)

    # 1) Direct reverse lookup for our own devices
    if did in _DAWPROJECT_TO_PYDAW:
        return _DAWPROJECT_TO_PYDAW[did]

    # 2) Well-known third-party plugins
    if did in _KNOWN_BY_DAWPROJECT_ID:
        return _KNOWN_BY_DAWPROJECT_ID[did].pydaw_id

    # 3) Format-based inference
    if did.startswith("clap:"):
        return f"clap:{did[5:]}"
    if did.startswith("lv2:"):
        return f"lv2:{did[4:]}"
    if did.startswith("ladspa:"):
        return f"ladspa:{did[7:]}"
    if did.startswith("plugin:vst3/"):
        return f"vst3:{did[12:]}"
    if did.startswith("plugin:"):
        # Raw VST3 hex TUID
        hex_part = did[7:]
        if re.match(r'^[0-9A-Fa-f]{16,32}$', hex_part):
            return f"vst3:{hex_part}"
        return f"vst3:{hex_part}"

    # ChronoScaleStudio internal device
    if did.startswith("device:ChronoScaleStudio/"):
        name_part = did.split("/", 1)[1] if "/" in did else did
        # Try case-insensitive lookup
        for pydaw_id, daw_id in {**_INTERNAL_INSTRUMENT_MAP, **_INTERNAL_FX_MAP, **_INTERNAL_NOTE_FX_MAP}.items():
            if daw_id == did:
                return pydaw_id
        return f"chrono.{name_part.lower()}"

    return None


def resolve_plugin_identity(
    pydaw_id: Optional[str] = None,
    dawproject_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> PluginIdentity:
    """Best-effort resolution from any available identifier to a PluginIdentity."""
    fmt = ""
    pid = ""
    name = display_name or ""
    vendor = ""
    category = ""

    # Try well-known database
    if pydaw_id and pydaw_id in _KNOWN_BY_PYDAW_ID:
        entry = _KNOWN_BY_PYDAW_ID[pydaw_id]
        return PluginIdentity(format=entry.format, plugin_id=entry.pydaw_id,
                              display_name=entry.display_name, vendor=entry.vendor,
                              category=entry.category)
    if dawproject_id and dawproject_id in _KNOWN_BY_DAWPROJECT_ID:
        entry = _KNOWN_BY_DAWPROJECT_ID[dawproject_id]
        return PluginIdentity(format=entry.format, plugin_id=entry.pydaw_id,
                              display_name=entry.display_name, vendor=entry.vendor,
                              category=entry.category)
    if display_name and display_name.lower() in _KNOWN_BY_NAME:
        entry = _KNOWN_BY_NAME[display_name.lower()]
        return PluginIdentity(format=entry.format, plugin_id=entry.pydaw_id,
                              display_name=entry.display_name, vendor=entry.vendor,
                              category=entry.category)

    # Infer format from ID prefixes
    source_id = pydaw_id or dawproject_id or ""
    lower = source_id.lower()
    if lower.startswith("vst3:") or lower.startswith("plugin:"):
        fmt = "VST3"
    elif lower.startswith("clap:"):
        fmt = "CLAP"
    elif lower.startswith("lv2:") or lower.startswith("ext.lv2:"):
        fmt = "LV2"
    elif lower.startswith("ladspa:"):
        fmt = "LADSPA"
    elif lower.startswith("chrono.") or lower.startswith("device:chronoscalestudio"):
        fmt = "INTERNAL"
    pid = pydaw_id or (dawproject_device_id_to_pydaw_id(dawproject_id) if dawproject_id else "") or ""

    return PluginIdentity(format=fmt, plugin_id=pid, display_name=name, vendor=vendor, category=category)


def get_all_internal_mappings() -> Dict[str, str]:
    """Return a copy of all internal pydaw_id → dawproject_id mappings."""
    result = {}
    result.update(_INTERNAL_INSTRUMENT_MAP)
    result.update(_INTERNAL_FX_MAP)
    result.update(_INTERNAL_NOTE_FX_MAP)
    return result
