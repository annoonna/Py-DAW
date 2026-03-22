"""Application bootstrap."""

from __future__ import annotations

import os
import sys
import traceback
import faulthandler
import signal

from PyQt6.QtWidgets import QApplication

from .utils.logging_setup import setup_logging

from .core.settings import SettingsKeys
from .core.settings_store import get_value
from .services.container import ServiceContainer
from .ui.main_window import MainWindow
from .fileio import recovery


def run(argv: list[str] | None = None) -> int:
    """Start GUI application."""
    argv = argv if argv is not None else sys.argv

    # Early logging (before Qt): keep terminal output + write logfile.
    # This is critical when the app restarts itself via exec (PipeWire-JACK / port changes).
    try:
        setup_logging(app_name="ChronoScaleStudio")
    except Exception:
        pass


    # AUTO_PW_JACK: Wenn Backend=JACK gewählt ist, aber kein JACK-Server erreichbar ist,
    # starten wir uns automatisch über pw-jack neu (PipeWire-JACK). Dadurch muss der User
    # nichts im Terminal tippen und QPWGraph sieht den Client sofort.
    try:
        from shutil import which
        from .services.jack_client_service import JackClientService

        keys = SettingsKeys()
        backend = str(get_value(keys.audio_backend, "sounddevice"))
        under_pw = os.environ.get("PYDAW_UNDER_PW_JACK") == "1" or os.environ.get("PW_JACK") == "1"
        pw = which("pw-jack")

        if backend == "jack" and (not under_pw) and pw and (not JackClientService.probe_available()):
            env = os.environ.copy()
            env["PYDAW_UNDER_PW_JACK"] = "1"
            env["PW_JACK"] = "1"
            # Projektpfad merken, damit nach Restart nicht ein leeres Projekt erscheint
            if env.get("PYDAW_REOPEN_PROJECT") is None:
                # wenn bereits ein Projekt geladen war, wird es von MainWindow beim Audio-Apply gesetzt
                pass
            os.execvpe(pw, [pw, sys.executable, *argv], env)
    except Exception:
        # Niemals blockieren – im Zweifel normal starten.
        pass

    # Crash/exception diagnostics: if Qt aborts (SIGABRT) we want a Python stack dump.
    try:
        faulthandler.enable(all_threads=True)
        for sig in (signal.SIGABRT, signal.SIGSEGV, signal.SIGFPE, signal.SIGILL):
            try:
                faulthandler.register(sig, all_threads=True, chain=True)
            except Exception:
                pass
    except Exception:
        pass

    class SafeApplication(QApplication):
        """QApplication that prevents PyQt6 aborts on unhandled exceptions.

        PyQt6/Qt may terminate the whole process with SIGABRT when an exception
        escapes a Qt event handler (e.g. during painting or slot execution).
        Catching here keeps the GUI alive and logs the traceback.
        """

        def notify(self, receiver, event):  # noqa: N802
            try:
                return super().notify(receiver, event)
            except Exception:
                try:
                    traceback.print_exc()
                except Exception:
                    pass
                return False

    app = SafeApplication(argv)

    # v0.0.20.185: Qt hardening (prevents SIGABRT on some Wayland/PyQt6 setups)
    # If a Python exception escapes a Qt virtual method (paintEvent/eventFilter/etc.),
    # SIP/PyQt can call qFatal("Unhandled Python exception") -> SIGABRT.
    # We defensively wrap our own UI classes so exceptions are swallowed + logged.
    try:
        from .ui.qt_hardening import harden_qt_virtuals, harden_signal_slots

        # v0.0.20.186: Slot safety. Prevents PyQt6 qFatal("Unhandled Python exception")
        # by wrapping Python slots connected via signal.connect.
        try:
            harden_signal_slots()
        except Exception:
            pass

        # v0.0.20.185: Virtual method hardening for pydaw.ui classes.
        harden_qt_virtuals()
    except Exception:
        pass

    # Apply persisted JACK/PipeWire-JACK preferences early (before services are created).
    #
    # IMPORTANT: This controls *port visibility / routing* in qpwgraph and is independent
    # from the engine backend (sounddevice vs jack). We must not force-switch backend.
    keys = SettingsKeys()
    jack_en = str(get_value(keys.jack_enable, "0"))
    jack_enabled = jack_en.lower() in ("1", "true", "yes", "on")

    # Enable/disable the JACK client according to user settings.
    os.environ["PYDAW_ENABLE_JACK"] = "1" if jack_enabled else "0"

    try:
        os.environ["PYDAW_JACK_IN"] = str(int(get_value(keys.jack_in_ports, 2)))
        os.environ["PYDAW_JACK_OUT"] = str(int(get_value(keys.jack_out_ports, 2)))
        os.environ["PYDAW_JACK_MONITOR"] = "1" if str(get_value(keys.jack_input_monitor, "0")).lower() in ("1","true","yes","on") else "0"
    except Exception:
        os.environ.setdefault("PYDAW_JACK_IN", "2")
        os.environ.setdefault("PYDAW_JACK_OUT", "2")
        os.environ.setdefault("PYDAW_JACK_MONITOR", "0")

    services = ServiceContainer.create_default()

    # v0.0.20.173: Crash-recovery session marker (Bitwig-style).
    # We mark the session as "unclean" at startup and flip to clean on normal close.
    try:
        keys = SettingsKeys()
        lastp = str(get_value(keys.last_project, "") or "")
        recovery.mark_startup(lastp)
    except Exception:
        try:
            recovery.mark_startup("")
        except Exception:
            pass

    window = MainWindow(services=services)
    window.show()

    return app.exec()
