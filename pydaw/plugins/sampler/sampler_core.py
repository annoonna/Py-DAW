"""Sampler core (engine) module.

This file exists for modularity: UI lives in sampler_widget.py, DSP helpers in dsp.py,
and the engine is re-exported here as SamplerEngine.

We keep sampler_engine.py for backward compatibility (older imports).
"""

from .sampler_engine import SamplerEngine

__all__ = ["SamplerEngine"]
