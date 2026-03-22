# -*- coding: utf-8 -*-
"""Plugin registry for instruments/effects.

This keeps the core DAW decoupled from optional plugin modules.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstrumentSpec:
    plugin_id: str
    name: str
    vendor: str = "ChronoScaleStudio"
    category: str = "Instrument"
    description: str = ""
    factory: Callable[..., QWidget] = lambda **_: QWidget()


def get_instruments() -> list[InstrumentSpec]:
    instruments: list[InstrumentSpec] = []

    # Pro Audio Sampler (Qt6)
    try:
        from pydaw.plugins.sampler import SamplerWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.pro_audio_sampler",
                name="Pro Audio Sampler",
                vendor="ChronoScaleStudio",
                category="Sampler",
                description="WAV Sampler mit Pitch/Filter/FX/ADHSR, Preview-Sync (PianoRoll/Notation).",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: SamplerWidget(
                    project_service=project_service,
                    audio_engine=audio_engine,
                    automation_manager=automation_manager,
                ),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: sampler")

    # Bachs Orgel (Qt6)
    try:
        from pydaw.plugins.bach_orgel import BachOrgelWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.bach_orgel",
                name="Bachs Orgel",
                vendor="ChronoScaleStudio",
                category="Orgel",
                description="Barocke Orgel-Synthese mit Presets (Gottesdienst/Plenum/Flöte) und Automation",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: BachOrgelWidget(
                    project_service=project_service,
                    audio_engine=audio_engine,
                    automation_manager=automation_manager,
                ),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: bach_orgel")


    # AETERNA (Qt6)
    try:
        from pydaw.plugins.aeterna import AeternaWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.aeterna",
                name="AETERNA",
                vendor="ChronoScaleStudio",
                category="Flagship Synth",
                description="The Morphogenetic Engine: Formel-/Chaos-/Terrain-Synth mit sakralen Presets und Random-Math.",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: AeternaWidget(
                    project_service=project_service,
                    audio_engine=audio_engine,
                    automation_manager=automation_manager,
                ),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: aeterna")

    # Pro Drum Machine (Qt6)
    try:
        from pydaw.plugins.drum_machine import DrumMachineWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.pro_drum_machine",
                name="Pro Drum Machine",
                vendor="ChronoScaleStudio",
                category="Drums",
                description="16-Pad Drum Machine (C1=Slot1) mit per-Slot Sampler + Pattern-Generator (Skeleton).",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: DrumMachineWidget(
                    project_service=project_service,
                    audio_engine=audio_engine,
                    automation_manager=automation_manager,
                ),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: drum_machine")

    # Fusion Synthesizer (Qt6) — v0.0.20.574
    try:
        from pydaw.plugins.fusion import FusionWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.fusion",
                name="Fusion",
                vendor="ChronoScaleStudio",
                category="Hybrid Synth",
                description="Semi-modularer Hybrid-Synthesizer mit austauschbaren OSC/FLT/ENV Modulen.",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: FusionWidget(
                    project_service=project_service,
                    audio_engine=audio_engine,
                    automation_manager=automation_manager,
                ),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: fusion")

    # Advanced Multi-Sample Sampler (Qt6) — v0.0.20.656
    try:
        from pydaw.plugins.sampler.multisample_widget import MultiSampleEditorWidget
        instruments.append(
            InstrumentSpec(
                plugin_id="chrono.advanced_sampler",
                name="Advanced Sampler",
                vendor="ChronoScaleStudio",
                category="Sampler",
                description="Multi-Sample Sampler: Key×Velocity Zones, Round-Robin, Filter+ADSR, Mod-Matrix, Auto-Mapping.",
                factory=lambda project_service=None, audio_engine=None, automation_manager=None, **_: MultiSampleEditorWidget(),
            )
        )
    except Exception:
        log.exception("Failed to load instrument plugin: advanced_sampler")

    return instruments
