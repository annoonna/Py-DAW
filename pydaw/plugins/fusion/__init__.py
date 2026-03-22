# ChronoScale Fusion — Semi-modular Hybrid Synthesizer
# v0.0.20.576: Wavetable + Scrawl oscillators

from .fusion_engine import FusionEngine  # noqa: F401

# Widget import is lazy — only succeeds when PyQt6 is available
try:
    from .fusion_widget import FusionWidget  # noqa: F401
except ImportError:
    pass
