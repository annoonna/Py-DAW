# -*- coding: utf-8 -*-
"""Modular Sampler plugin (PyQt6).

Exports:
- SamplerWidget: the UI device widget
"""

from .sampler_widget import SamplerWidget  # noqa: F401

from .sampler_core import SamplerEngine

# v0.0.20.656 — Advanced Multi-Sample Sampler (AP7 Phase 7A)
from .multisample_model import SampleZone, MultiSampleMap  # noqa: F401
from .multisample_engine import MultiSampleEngine  # noqa: F401
from .multisample_widget import MultiSampleEditorWidget  # noqa: F401
from .auto_mapping import (  # noqa: F401
    auto_map_chromatic, auto_map_drum,
    auto_map_velocity_layers, auto_map_round_robin,
)

__all__ = [
    "SamplerWidget", "SamplerEngine",
    "SampleZone", "MultiSampleMap", "MultiSampleEngine",
    "MultiSampleEditorWidget",
    "auto_map_chromatic", "auto_map_drum",
    "auto_map_velocity_layers", "auto_map_round_robin",
]
