# -*- coding: utf-8 -*-
"""OscMidiInput (v0.0.20.609)

Bitwig-Style OSC MIDI Input Source.
Listens for OSC messages on a configurable UDP port and injects them
as MIDI notes into MidiManager via inject_message(source='osc').

OSC address patterns (matching common DAW conventions):
  /note/on   [pitch:int, velocity:int, channel:int]
  /note/off  [pitch:int, channel:int]
  /cc        [controller:int, value:int, channel:int]

Requires: python-osc (pip install python-osc)
Falls back gracefully if not installed.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:
    from pythonosc import dispatcher as osc_dispatcher  # type: ignore
    from pythonosc import osc_server  # type: ignore
    _HAS_OSC = True
except ImportError:
    _HAS_OSC = False


class OscMidiInput(QObject):
    """Receives OSC note messages and injects them into MidiManager."""

    status = Signal(str)
    error = Signal(str)

    def __init__(self, midi_manager=None, port: int = 9000, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._midi_manager = midi_manager
        self._port = int(port)
        self._server = None
        self._thread = None
        self._running = False

    @staticmethod
    def is_available() -> bool:
        return bool(_HAS_OSC)

    @property
    def port(self) -> int:
        return self._port

    def set_midi_manager(self, mm) -> None:
        self._midi_manager = mm

    def start(self, port: int = 0) -> bool:
        """Start the OSC server on the given UDP port. Returns True on success."""
        if not _HAS_OSC:
            try:
                self.error.emit("OSC: python-osc nicht installiert (pip install python-osc)")
            except Exception:
                pass
            return False

        if self._running:
            self.stop()

        if port > 0:
            self._port = int(port)

        try:
            disp = osc_dispatcher.Dispatcher()
            disp.map("/note/on", self._handle_note_on)
            disp.map("/note/off", self._handle_note_off)
            disp.map("/cc", self._handle_cc)
            disp.set_default_handler(self._handle_default)

            self._server = osc_server.ThreadingOSCUDPServer(
                ("0.0.0.0", self._port), disp
            )
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._running = True
            self._thread.start()
            try:
                self.status.emit(f"OSC: Listening on port {self._port}")
            except Exception:
                pass
            return True
        except Exception as exc:
            try:
                self.error.emit(f"OSC: Start fehlgeschlagen: {exc}")
            except Exception:
                pass
            return False

    def stop(self) -> None:
        """Stop the OSC server."""
        self._running = False
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
        if self._thread is not None:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None
        try:
            self.status.emit("OSC: Gestoppt")
        except Exception:
            pass

    # ---- OSC handlers ----

    def _handle_note_on(self, address: str, *args) -> None:
        """OSC /note/on [pitch, velocity, channel?]"""
        if len(args) < 2:
            return
        pitch = int(args[0])
        vel = int(args[1])
        ch = int(args[2]) if len(args) > 2 else 0
        self._inject_note("note_on", pitch, vel, ch)

    def _handle_note_off(self, address: str, *args) -> None:
        """OSC /note/off [pitch, channel?]"""
        if len(args) < 1:
            return
        pitch = int(args[0])
        ch = int(args[1]) if len(args) > 1 else 0
        self._inject_note("note_off", pitch, 0, ch)

    def _handle_cc(self, address: str, *args) -> None:
        """OSC /cc [controller, value, channel?]"""
        if len(args) < 2:
            return
        mm = self._midi_manager
        if mm is None:
            return
        ctrl = int(args[0])
        val = int(args[1])
        ch = int(args[2]) if len(args) > 2 else 0
        try:
            import mido  # type: ignore
            msg = mido.Message("control_change", control=ctrl, value=val, channel=ch)
            mm.inject_message(msg, source="osc")
        except ImportError:
            pass
        except Exception:
            pass

    def _handle_default(self, address: str, *args) -> None:
        """Ignore unknown OSC addresses silently."""
        pass

    def _inject_note(self, mtype: str, pitch: int, vel: int, ch: int) -> None:
        mm = self._midi_manager
        if mm is None:
            return
        try:
            import mido  # type: ignore
            msg = mido.Message(mtype, note=max(0, min(127, pitch)),
                               velocity=max(0, min(127, vel)), channel=max(0, min(15, ch)))
            mm.inject_message(msg, source="osc")
        except ImportError:
            # Fallback without mido
            try:
                from pydaw.services.computer_keyboard_midi import _FakeMsg
                mm.inject_message(_FakeMsg(mtype, pitch, vel, ch), source="osc")
            except Exception:
                pass
        except Exception:
            pass

    def shutdown(self) -> None:
        self.stop()
