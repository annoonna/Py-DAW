# -*- coding: utf-8 -*-
"""MIDI Service (compat wrapper).

Historisch hieß die zentrale MIDI-Komponente `MidiService`. Ab v0.0.20.x
haben wir sie zu `MidiManager` erweitert (Global-Manager, Recording-ready,
Ghost-Notes, Panic).

Dieses File bleibt bestehen, damit alte Imports nicht brechen:
`from pydaw.services.midi_service import MidiService`
"""

from __future__ import annotations

from typing import Callable

from .midi_manager import MidiManager


class MidiService(MidiManager):
    """Backwards-compatible alias for :class:`~pydaw.services.midi_manager.MidiManager`."""

    def __init__(self, status_cb: Callable[[str], None] | None = None, *, project_service=None, transport=None):
        super().__init__(project_service=project_service, transport=transport, status_cb=status_cb)
