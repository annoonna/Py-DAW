"""AudioConfig — Central audio configuration singleton.

v0.0.20.638 — AP2 Phase 2C (Crossfade an Punch-Grenzen)

Holds audio engine configuration that can be:
- Set programmatically from any service
- Persisted via QSettings (SettingsKeys)
- Later exposed in a Preferences UI

Usage:
    from pydaw.core.audio_config import audio_config
    fade_ms = audio_config.punch_crossfade_ms
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """Central audio configuration.

    All values have sensible defaults. Services read from here,
    UI/Preferences write to here + persist via QSettings.
    """

    # ── Recording ──────────────────────────────────────────
    # Crossfade length at punch in/out boundaries (ms).
    # Applied as linear fade-in at punch-in and fade-out at punch-out
    # to prevent clicks/pops at hard cut boundaries.
    # Range: 0 (hard cut) to 100 ms.  Default: 10 ms.
    punch_crossfade_ms: float = 10.0

    # ── Engine ─────────────────────────────────────────────
    # Default sample rate (used when no backend override exists)
    default_sample_rate: int = 48000

    # Default buffer size
    default_buffer_size: int = 512

    def set_punch_crossfade_ms(self, ms: float) -> None:
        """Set punch crossfade length in milliseconds.

        Args:
            ms: Crossfade length. Clamped to 0–100 ms.
        """
        self.punch_crossfade_ms = max(0.0, min(100.0, float(ms)))
        log.debug("Punch crossfade set to %.1f ms", self.punch_crossfade_ms)

    def crossfade_samples(self, sample_rate: int) -> int:
        """Convert punch_crossfade_ms to samples at the given sample rate.

        Args:
            sample_rate: Sample rate in Hz.

        Returns:
            Number of samples for the crossfade ramp.
        """
        return max(0, int(float(self.punch_crossfade_ms) / 1000.0 * float(sample_rate)))


# Module-level singleton — import and use directly:
#   from pydaw.core.audio_config import audio_config
audio_config = AudioConfig()
