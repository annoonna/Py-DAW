# -*- coding: utf-8 -*-
"""Drum Machine plugin (PyQt6).

Phase 1 (skeleton):
- 4x4 pad grid (Pro-DAW Drum Machine inspired)
- Per-slot local sampler engines (ProSamplerEngine per pad)
- Summed pull-source audio routed to track output (per-track faders + VU)
- MIDI mapping: C1 (MIDI 36) = Slot 1, then chromatic upwards

Notes:
- This plugin is intentionally modular and only registered via
  `pydaw.plugins.registry`.
"""

from .drum_widget import DrumMachineWidget  # noqa: F401

__all__ = ["DrumMachineWidget"]
