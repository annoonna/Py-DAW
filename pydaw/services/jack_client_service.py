"""
JACK / PipeWire-JACK client integration.

Scope:
- PyDAW appears in qpwgraph as a JACK client with configurable I/O ports.
- Lightweight passthrough monitoring (inputs -> outputs).
- Basic WAV recording (stereo: first two input channels).

Enable/disable:
- env PYDAW_ENABLE_JACK=1 enables JACK client. Default disabled.

Port count:
- PYDAW_JACK_IN  : input channels (1..64), default 2
- PYDAW_JACK_OUT : output channels (1..64), default 2
"""

from __future__ import annotations

import os
import queue
import threading
import time
import contextlib


@contextlib.contextmanager
def _suppress_stderr():
    """Temporär stderr unterdrücken (libjack schreibt direkt nach stderr)."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old = os.dup(2)
        os.dup2(devnull, 2)
        yield
    finally:
        try:
            os.dup2(old, 2)
        except Exception:
            pass
        try:
            os.close(old)
        except Exception:
            pass
        try:
            os.close(devnull)
        except Exception:
            pass

import wave
from typing import Callable, Optional

import numpy as np


class JackClientService:
    def __init__(self, status_cb: Callable[[str], None] | None = None) -> None:
        self._status_cb = status_cb or (lambda _m: None)
        # Thread-safe message queue:
        # The JACK process callback runs on a realtime thread. Touching Qt
        # widgets from that thread can SIGABRT the whole app. We therefore
        # buffer status/error messages and forward them from the JACK service
        # thread.
        self._msg_q: "queue.SimpleQueue[str]" = queue.SimpleQueue()
        self._stop = False
        self._stop_event = threading.Event()  # For graceful thread shutdown
        self._thread: Optional[threading.Thread] = None
        self._client = None

        self._rec_on = False
        self._rec_path: Optional[str] = None
        self._rec_pair: int = 1  # stereo pair index (1..N)
        self._rec_q: "queue.Queue[tuple[np.ndarray, np.ndarray]]" = queue.Queue(maxsize=256)
        self._rec_thread: Optional[threading.Thread] = None

        # Global Input-Monitoring (Passthrough): Inputs -> Outputs.
        # Default OFF to avoid feedback loops. Enable via settings/env.
        self._passthrough = os.environ.get("PYDAW_JACK_MONITOR", "0") == "1"

        # Per-track monitoring routes (preferred). Each route is (in_pair, out_pair, gain).
        # If non-empty, these are mixed in addition to engine output.
        self._monitor_routes: list[tuple[int, int, float]] = []

        self._in_ch = self._read_env_int("PYDAW_JACK_IN", default=2, lo=1, hi=64)
        self._out_ch = self._read_env_int("PYDAW_JACK_OUT", default=2, lo=1, hi=64)

    def _read_env_int(self, key: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(os.environ.get(key, str(default)))
            return max(lo, min(hi, v))
        except Exception:
            return default

    def enabled(self) -> bool:
        return os.environ.get("PYDAW_ENABLE_JACK", "0") == "1"

    @staticmethod
    def probe_available() -> bool:
        """True wenn ein JACK Server erreichbar ist.

        Unter PipeWire ist JACK i.d.R. nur erreichbar, wenn die Anwendung
        mit `pw-jack` gestartet wurde (oder pipewire-jack als Standard-libjack
        installiert ist).
        """
        try:
            # import kann schon fehlschlagen, wenn python-jack-client fehlt.
            import jack  # type: ignore

            with _suppress_stderr():
                c = jack.Client("PyDAWProbe", no_start_server=True)
            try:
                c.deactivate()
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _status(self, msg: str) -> None:
        try:
            self._status_cb(msg)
        except Exception:
            pass

    def apply_config(self, enabled: bool, in_ch: int, out_ch: int, monitor: bool | None = None) -> None:
        """Apply JACK config at runtime and restart client if required."""
        in_ch = max(1, min(64, int(in_ch)))
        out_ch = max(1, min(64, int(out_ch)))

        os.environ["PYDAW_ENABLE_JACK"] = "1" if enabled else "0"
        os.environ["PYDAW_JACK_IN"] = str(in_ch)
        os.environ["PYDAW_JACK_OUT"] = str(out_ch)

        if monitor is not None:
            os.environ["PYDAW_JACK_MONITOR"] = "1" if monitor else "0"
            self._passthrough = bool(monitor)

        changed = (in_ch != self._in_ch) or (out_ch != self._out_ch)
        self._in_ch, self._out_ch = in_ch, out_ch

        running = (self._thread is not None and self._thread.is_alive()) or (self._client is not None)

        if not enabled and running:
            self.shutdown()
            return

        if enabled:
            if running and changed:
                self.shutdown()
                time.sleep(0.2)
            self.start_async(client_name="PyDAW")

    
    def set_render_callback(self, cb) -> None:  # noqa: ANN001
        """Set a render callback for JACK process cycle.

        Signature: cb(frames:int, in_bufs:list[np.ndarray], out_bufs:list[np.ndarray], sr:int)->bool
        Return True if it wrote to out_bufs (engine output).
        """
        self._render_cb = cb

    def clear_render_callback(self) -> None:
        self._render_cb = None

    def set_input_monitoring(self, enabled: bool) -> None:
        """Enable/disable global passthrough monitoring without restarting JACK client."""
        self._passthrough = bool(enabled)
        os.environ["PYDAW_JACK_MONITOR"] = "1" if enabled else "0"
        self._status(f"JACK Input Monitoring: {'ON' if enabled else 'OFF'}")

    def set_monitor_routes(self, routes: list[tuple[int, int, float]]) -> None:
        """Set per-track monitoring routes.

        routes: list of (in_pair, out_pair, gain).
        Ports are mono; pair numbers are stereo pairs (1-based).
        """
        cleaned: list[tuple[int, int, float]] = []
        for (ip, op, g) in routes or []:
            try:
                ip_i = max(1, int(ip))
                op_i = max(1, int(op))
                g_f = float(g)
            except Exception:
                continue
            cleaned.append((ip_i, op_i, g_f))
        self._monitor_routes = cleaned

    def start_async(self, client_name: str = "PyDAW", in_ports: int | None = None, out_ports: int | None = None, monitor: bool | None = None, **_kw) -> None:
        # Backward-compat: some callers use in_ports/out_ports/monitor.
        # Map to apply_config() semantics (channels = mono ports).
        # Alias handling: some callers use monitor_inputs_to_outputs keyword.
        if monitor is None and 'monitor_inputs_to_outputs' in _kw:
            try:
                monitor = bool(_kw.get('monitor_inputs_to_outputs'))
            except Exception:
                monitor = None

        if in_ports is not None or out_ports is not None or monitor is not None:
            try:
                in_ch = int(in_ports) if in_ports is not None else int(self._in_ch)
            except Exception:
                in_ch = int(self._in_ch)
            try:
                out_ch = int(out_ports) if out_ports is not None else int(self._out_ch)
            except Exception:
                out_ch = int(self._out_ch)
            # If monitor is None, keep current passthrough state.
            self.apply_config(enabled=True, in_ch=in_ch, out_ch=out_ch, monitor=monitor)
        if not self.enabled():
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._stop_event.clear()  # Clear stop signal
        self._thread = threading.Thread(target=self._run, args=(client_name,), daemon=True)
        self._thread.start()

    def reconfigure_ports(self, in_ch: int, out_ch: int, passthrough: bool) -> None:
        """Restart the JACK client (same process) to apply a new port layout.

        This avoids restarting the whole GUI while still recreating the underlying
        JACK ports (which requires a new client activation cycle).
        """
        try:
            self._in_ch = max(0, int(in_ch))
            self._out_ch = max(0, int(out_ch))
            self._passthrough = bool(passthrough)
        except Exception:
            return

        if not self.enabled():
            return

        # If the client isn't running yet, just start it.
        if self._client is None:
            self.start_async("PyDAW")
            return

        # Otherwise, shut down the existing client thread and start a fresh one.
        self.shutdown()
        try:
            if self._thread is not None:
                self._thread.join(timeout=1.5)
        except Exception:
            pass
        self._thread = None
        self._client = None
        self._in_ports = []
        self._out_ports = []
        self._stop = False
        self.start_async("PyDAW")

    def shutdown(self) -> None:
        self._stop = True
        self._stop_event.set()  # Signal thread to stop gracefully
        try:
            self.stop_recording()
        except Exception:
            pass

    # ---------------- Recording ----------------

    def start_recording(self, wav_path: str, stereo_pair: int = 1) -> None:
        if not self.enabled():
            self._status("Recording: JACK deaktiviert. Starte PyDAW mit PYDAW_ENABLE_JACK=1.")
            return
        if self._client is None:
            self.start_async("PyDAW")
            self._status("Recording: JACK-Ports werden gestartet… bitte erneut aufnehmen, sobald Ports aktiv sind.")
            return

        self._rec_path = str(wav_path)
        try:
            self._rec_pair = max(1, int(stereo_pair))
        except Exception:
            self._rec_pair = 1
        self._rec_on = True

        if self._rec_thread is None or not self._rec_thread.is_alive():
            self._rec_thread = threading.Thread(target=self._record_writer, daemon=True)
            self._rec_thread.start()

        self._status(f"Recording: aktiv (Stereo {self._rec_pair}) → {self._rec_path}")

    def stop_recording(self) -> None:
        if not self._rec_on:
            return
        self._rec_on = False
        try:
            if self._rec_thread is not None:
                self._rec_thread.join(timeout=2.0)
        except Exception:
            pass
        self._rec_thread = None
        self._rec_path = None
        self._status("Recording: gestoppt.")

    def _record_writer(self) -> None:
        client = self._client
        if client is None or not self._rec_path:
            return

        sr = int(getattr(client, "samplerate", 48000)) or 48000

        try:
            wf = wave.open(self._rec_path, "wb")
            wf.setnchannels(2)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sr)
        except Exception as exc:
            self._status(f"Recording: WAV open failed: {exc}")
            return

        try:
            while self._rec_on or not self._rec_q.empty():
                try:
                    a, b = self._rec_q.get(timeout=0.2)
                except Exception:
                    continue

                a16 = np.clip(a, -1.0, 1.0)
                b16 = np.clip(b, -1.0, 1.0)
                inter = np.empty((len(a16), 2), dtype=np.int16)
                inter[:, 0] = (a16 * 32767.0).astype(np.int16, copy=False)
                inter[:, 1] = (b16 * 32767.0).astype(np.int16, copy=False)
                wf.writeframes(inter.tobytes())
        finally:
            try:
                wf.close()
            except Exception:
                pass

    # ---------------- JACK client thread ----------------

    def _run(self, client_name: str) -> None:
        """JACK client thread - ULTRA-SAFE version with global exception handling."""
        try:
            self._run_inner(client_name)
        except Exception as e:
            # EMERGENCY: Catch ANY exception that escapes
            self._status(f"JACK: Thread crashed: {e}")
            self._client = None
    
    def _run_inner(self, client_name: str) -> None:
        """Inner JACK client logic (can raise exceptions safely)."""
        try:
            import jack  # type: ignore
        except Exception:
            self._status("JACK: python-jack-client nicht verfügbar (pip install JACK-Client).")
            return

        os.environ.setdefault("JACK_NO_START_SERVER", "1")

        try:
            with _suppress_stderr():
                client = jack.Client(client_name)
        except Exception as exc:
            self._status(f"JACK: Kein Server/keine PipeWire-JACK Bridge erreichbar: {exc}")
            return

        try:
            # Pro-DAW-Style: Stereo-Paare als L/R benennen (L1,R1,L2,R2,...).
            # QPWGraph zeigt dann die Ports in einer bekannten, schnellen Zuordnung.
            for i in range(self._in_ch):
                pair_idx = (i // 2) + 1
                lr = "L" if (i % 2) == 0 else "R"
                client.inports.register(f"in_{lr}{pair_idx}")

            for i in range(self._out_ch):
                pair_idx = (i // 2) + 1
                lr = "L" if (i % 2) == 0 else "R"
                client.outports.register(f"out_{lr}{pair_idx}")

            # Cache port objects for auto-connect & diagnostics.
            self._in_ports = list(client.inports)
            self._out_ports = list(client.outports)

            @client.set_process_callback
            def _process(frames: int) -> int:
                """JACK realtime callback - ULTRA-DEFENSIVE version.
                
                CRITICAL: This runs in JACK's realtime thread.
                Any exception that escapes can cause SIGABRT.
                """
                try:
                    # Validate frames
                    if not isinstance(frames, int) or frames <= 0 or frames > 8192:
                        return 0
                    
                    # Get buffers safely
                    try:
                        in_bufs = [p.get_array() for p in client.inports]
                        out_bufs = [p.get_array() for p in client.outports]
                    except Exception:
                        return 0
                    
                    # Validate buffer counts
                    if not in_bufs or not out_bufs:
                        return 0
                    
                    # Clear outputs first (safest default)
                    try:
                        for ch in range(len(out_bufs)):
                            if ch >= 0 and ch < len(out_bufs):
                                buf = out_bufs[ch]
                                if buf is not None and len(buf) >= frames:
                                    buf[:frames] = 0.0
                    except Exception:
                        return 0

                    # Try to call render callback
                    handled = False
                    try:
                        if self._render_cb is not None and callable(self._render_cb):
                            sr = int(getattr(client, "samplerate", 48000))
                            if sr > 0:
                                handled = bool(self._render_cb(frames, in_bufs, out_bufs, sr))
                    except Exception:
                        pass

                    # Per-track monitoring (with bounds checks)
                    try:
                        if self._monitor_routes:
                            for route in list(self._monitor_routes):
                                try:
                                    ip, op, g = route
                                    i0 = (int(ip) - 1) * 2
                                    o0 = (int(op) - 1) * 2
                                    
                                    if i0 < 0 or o0 < 0:
                                        continue
                                    if i0 + 1 >= len(in_bufs) or o0 + 1 >= len(out_bufs):
                                        continue
                                    
                                    gg = float(g)
                                    if gg <= 0.0:
                                        continue
                                    
                                    # Check buffer lengths
                                    if (len(in_bufs[i0]) < frames or len(in_bufs[i0 + 1]) < frames or
                                        len(out_bufs[o0]) < frames or len(out_bufs[o0 + 1]) < frames):
                                        continue
                                    
                                    out_bufs[o0][:frames] += in_bufs[i0][:frames] * gg
                                    out_bufs[o0 + 1][:frames] += in_bufs[i0 + 1][:frames] * gg
                                except Exception:
                                    continue
                    except Exception:
                        pass

                    # Legacy global monitoring
                    try:
                        if self._passthrough and not self._monitor_routes:
                            n = min(len(in_bufs), len(out_bufs))
                            for ch in range(n):
                                if ch >= 0 and ch < len(in_bufs) and ch < len(out_bufs):
                                    if len(in_bufs[ch]) >= frames and len(out_bufs[ch]) >= frames:
                                        out_bufs[ch][:frames] += in_bufs[ch][:frames]
                    except Exception:
                        pass

                    # Recording
                    try:
                        if self._rec_on and len(in_bufs) >= 1:
                            p = max(1, int(getattr(self, "_rec_pair", 1)))
                            i0 = (p - 1) * 2
                            if i0 < 0 or i0 >= len(in_bufs):
                                i0 = 0
                            i1 = i0 + 1
                            
                            if len(in_bufs[i0]) >= frames:
                                a = in_bufs[i0][:frames].copy()
                                b = in_bufs[i1][:frames].copy() if (i1 < len(in_bufs) and len(in_bufs[i1]) >= frames) else a.copy()
                                try:
                                    self._rec_q.put_nowait((a, b))
                                except Exception:
                                    pass
                    except Exception:
                        pass

                except Exception:
                    # EMERGENCY: Catch everything
                    pass
                
                # ALWAYS return 0
                return 0

            # WICHTIG (Stabilität): Auto-Connect vor dem Aktivieren.
            # Hintergrund: Bei manchen PipeWire-JACK Setups kann gleichzeitiges Processing + Connect
            # (insb. via Python/CFFI) sporadisch SIGABRT auslösen.
            self._client = client
            self._status(f"JACK: Ports registriert (in={self._in_ch}, out={self._out_ch}).")

            try:
                self._auto_connect_outputs()
            except Exception as e:
                self._status(f"JACK: Auto-Connect Outputs fehlgeschlagen: {e}")

            client.activate()
        except Exception as exc:
            self._status(f"JACK: Port-Registration fehlgeschlagen: {exc}")
            try:
                client.close()
            except Exception:
                pass
            return

        # Main thread loop - ULTRA-SAFE for Python 3.13 + JACK
        import time
        try:
            while not self._stop:
                try:
                    # Shorter sleep intervals to be more responsive
                    for _ in range(10):  # 10 x 0.05s = 0.5s total
                        if self._stop:
                            break
                        time.sleep(0.05)
                except (KeyboardInterrupt, SystemExit):
                    self._status("JACK: Interrupted by user")
                    break
                except Exception as e:
                    # Emergency: Log but continue
                    self._status(f"JACK: Loop error: {e}")
                    time.sleep(0.1)
        except Exception as e:
            # EMERGENCY: Catch EVERYTHING
            self._status(f"JACK: Fatal error in main loop: {e}")
        finally:
            # ALWAYS cleanup
            try:
                if client:
                    client.deactivate()
            except Exception:
                pass
            try:
                if client:
                    client.close()
            except Exception:
                pass
            self._client = None
            self._status("JACK: beendet.")

    def _auto_connect_outputs(self) -> None:
        """Versucht, die ersten beiden Outputs automatisch auf die physikalischen Playback-Ports zu verbinden.

        Strategie:
        1) Erst versuchen "system:playback_1/2" (klassisches JACK).
        2) Falls nicht vorhanden: physikalische Audio-Input-Ports suchen (PipeWire-JACK liefert diese i.d.R.).
        """
        try:
            if not self._client or not self._out_ports:
                return

            c = self._client

            # 1) klassisches JACK "system"-Alias
            targets = []
            try:
                p1 = c.get_ports(name_pattern="system:playback_1")
                p2 = c.get_ports(name_pattern="system:playback_2")
                if p1 and p2:
                    targets = [p1[0], p2[0]]
            except Exception:
                targets = []

            # 2) PipeWire-JACK: physikalische Playback-Ports (Input Ports)
            if not targets:
                try:
                    phys = c.get_ports(is_physical=True, is_input=True, is_audio=True)
                    # Stabil sortieren, damit L/R in richtiger Reihenfolge bleibt.
                    phys = sorted(phys, key=lambda p: p.name)
                    if len(phys) >= 2:
                        targets = [phys[0], phys[1]]
                except Exception:
                    targets = []

            if len(targets) < 2:
                return

            outL = self._out_ports[0]
            outR = self._out_ports[1] if len(self._out_ports) > 1 else None
            if not outR:
                return

            # Nur verbinden, wenn noch nicht verbunden.
            try:
                if targets[0] not in outL.connections:
                    c.connect(outL, targets[0])
            except Exception:
                pass
            try:
                if targets[1] not in outR.connections:
                    c.connect(outR, targets[1])
            except Exception:
                pass

            self._status("JACK: Main Out auto-verbunden (L/R).")
        except Exception:
            # Auto-Connect darf niemals den Client killen.
            return
