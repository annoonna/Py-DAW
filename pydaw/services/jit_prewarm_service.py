# -*- coding: utf-8 -*-
"""JIT Pre-Warming Service für PyDAW (v0.0.20.66).

Dieser Service kompiliert alle JIT-Kernels beim App-Start, um Audio-Dropouts
(Glitches) beim ersten Abspielen zu vermeiden.

Verwendung:
─────────────────────────────────────────────────────────────────────────────────
    # In main.py oder app.py:
    from pydaw.services.jit_prewarm_service import JitPrewarmService
    
    # Im SplashScreen oder beim Startup:
    prewarm = JitPrewarmService()
    prewarm.start()  # Läuft im Hintergrund
    
    # Optional: Fortschritt überwachen
    prewarm.progress_changed.connect(lambda p, msg: print(f"{p}%: {msg}"))
    prewarm.finished.connect(lambda: print("JIT ready!"))

Architektur:
─────────────────────────────────────────────────────────────────────────────────
┌─────────────────────────────────────────────────────────────────────────────┐
│                              APP STARTUP                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        JitPrewarmService                                │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────┐   │ │
│  │  │ Kernels    │  │ Effects    │  │ Synths     │  │ Essentia Pool  │   │ │
│  │  │ (sine,saw) │  │ (filter)   │  │ (sampler)  │  │ (stretch)      │   │ │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └───────┬────────┘   │ │
│  │        │               │               │                  │            │ │
│  │        └───────────────┴───────────────┴──────────────────┘            │ │
│  │                              ▼                                          │ │
│  │                   JIT COMPILATION QUEUE                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                         AUDIO ENGINE READY
                      (Keine Dropouts beim Start)

Warum ist Pre-Warming wichtig?
─────────────────────────────────────────────────────────────────────────────────
Numba kompiliert Funktionen standardmäßig beim ersten Aufruf ("Lazy Compilation").
Das führt zu einem CPU-Spike von 100-500ms, was bei Audio-Callbacks zu Dropouts
führt. Durch Pre-Warming passiert die Compilation VOR dem ersten Audio-Callback.
"""
from __future__ import annotations

import time
from typing import Optional, List, Callable, Any
from dataclasses import dataclass

try:
    from PyQt6.QtCore import QObject, QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    QObject = object
    QThread = object
    pyqtSignal = None

try:
    import numpy as np
except ImportError:
    np = None


@dataclass
class PrewarmTask:
    """Einzelne Pre-Warm-Aufgabe."""
    name: str
    function: Callable[[], bool]
    weight: int = 1  # Gewichtung für Fortschrittsanzeige


class JitPrewarmWorker(QThread if PYQT_AVAILABLE else object):
    """Worker-Thread für JIT Pre-Warming.
    
    Signals:
        progress_changed(int, str): Fortschritt (0-100) und Statusmeldung
        finished_success(): Erfolgreich abgeschlossen
        finished_error(str): Fehler aufgetreten
    """
    
    if PYQT_AVAILABLE:
        progress_changed = pyqtSignal(int, str)
        finished_success = pyqtSignal()
        finished_error = pyqtSignal(str)
    
    def __init__(self, tasks: List[PrewarmTask], parent=None):
        if PYQT_AVAILABLE:
            super().__init__(parent)
        self.tasks = tasks
        self.total_weight = sum(t.weight for t in tasks)
        self._abort = False
    
    def abort(self):
        """Pre-Warming abbrechen."""
        self._abort = True
    
    def run(self):
        """Worker-Hauptschleife."""
        completed_weight = 0
        errors = []
        
        for task in self.tasks:
            if self._abort:
                break
                
            progress = int((completed_weight / self.total_weight) * 100)
            if PYQT_AVAILABLE:
                self.progress_changed.emit(progress, f"Kompiliere: {task.name}")
            
            try:
                start = time.perf_counter()
                success = task.function()
                elapsed = (time.perf_counter() - start) * 1000
                
                if not success:
                    errors.append(f"{task.name}: Fehlgeschlagen")
                else:
                    print(f"[JIT] ✓ {task.name} ({elapsed:.1f}ms)")
                    
            except Exception as e:
                errors.append(f"{task.name}: {e}")
                print(f"[JIT] ✗ {task.name}: {e}")
            
            completed_weight += task.weight
        
        # Finale Meldung
        if PYQT_AVAILABLE:
            self.progress_changed.emit(100, "JIT-Compilation abgeschlossen")
        
        if errors:
            if PYQT_AVAILABLE:
                self.finished_error.emit("\n".join(errors))
        else:
            if PYQT_AVAILABLE:
                self.finished_success.emit()


class JitPrewarmService(QObject if PYQT_AVAILABLE else object):
    """Service für JIT Pre-Warming beim App-Start.
    
    Dieser Service führt alle notwendigen JIT-Compilations durch, bevor
    der erste Audio-Callback erfolgt.
    
    Signals (PyQt6):
        progress_changed(int, str): Fortschritt und Statusmeldung
        finished(): Pre-Warming abgeschlossen
        
    Usage:
        service = JitPrewarmService()
        service.progress_changed.connect(update_splash_progress)
        service.finished.connect(show_main_window)
        service.start()
    """
    
    if PYQT_AVAILABLE:
        progress_changed = pyqtSignal(int, str)
        finished = pyqtSignal()
    
    def __init__(self, parent=None):
        if PYQT_AVAILABLE:
            super().__init__(parent)
        self._worker: Optional[JitPrewarmWorker] = None
        self._tasks = self._build_task_list()
        
    def _build_task_list(self) -> List[PrewarmTask]:
        """Alle Pre-Warm-Aufgaben zusammenstellen."""
        tasks = []
        
        # 1. JIT-Kernels (Oszillatoren, Filter, Gain)
        tasks.append(PrewarmTask(
            name="Audio DSP Kernels",
            function=self._prewarm_kernels,
            weight=3
        ))
        
        # 2. JIT-Effekte (Filter, Distortion)
        tasks.append(PrewarmTask(
            name="Audio FX Chain",
            function=self._prewarm_effects,
            weight=2
        ))
        
        # 3. Sampler-DSP (falls vorhanden)
        tasks.append(PrewarmTask(
            name="Sampler Engine",
            function=self._prewarm_sampler,
            weight=2
        ))
        
        # 4. Essentia Pool (Time-Stretching)
        tasks.append(PrewarmTask(
            name="Time-Stretch Pool",
            function=self._prewarm_essentia,
            weight=1
        ))
        
        # 5. Ring-Buffer (Lock-Free)
        tasks.append(PrewarmTask(
            name="Ring Buffer",
            function=self._prewarm_ringbuffer,
            weight=1
        ))
        
        return tasks
    
    def _prewarm_kernels(self) -> bool:
        """JIT-Kernels vorwärmen."""
        try:
            from pydaw.audio.jit_kernels import prewarm_all_kernels
            return prewarm_all_kernels()
        except ImportError:
            print("[JIT] jit_kernels nicht gefunden - überspringe")
            return True
        except Exception as e:
            print(f"[JIT] Kernel-Prewarm Fehler: {e}")
            return False
    
    def _prewarm_effects(self) -> bool:
        """JIT-Effekte vorwärmen."""
        try:
            from pydaw.audio.jit_effects import prewarm_all_jit_effects
            return prewarm_all_jit_effects()
        except ImportError:
            print("[JIT] jit_effects nicht gefunden - überspringe")
            return True
        except Exception as e:
            print(f"[JIT] Effects-Prewarm Fehler: {e}")
            return False
    
    def _prewarm_sampler(self) -> bool:
        """Sampler-DSP vorwärmen."""
        try:
            from pydaw.plugins.sampler.dsp import prewarm_sampler_dsp
            return prewarm_sampler_dsp()
        except (ImportError, AttributeError):
            # Sampler hat keine Prewarm-Funktion - das ist OK
            return True
        except Exception as e:
            print(f"[JIT] Sampler-Prewarm Fehler: {e}")
            return False
    
    def _prewarm_essentia(self) -> bool:
        """Essentia Time-Stretch Pool vorwärmen."""
        try:
            from pydaw.audio.essentia_pool import EssentiaStretchPool
            pool = EssentiaStretchPool.get_instance()
            # Pool initialisiert sich selbst
            return pool is not None
        except ImportError:
            return True  # Essentia ist optional
        except Exception as e:
            print(f"[JIT] Essentia-Prewarm Fehler: {e}")
            return False
    
    def _prewarm_ringbuffer(self) -> bool:
        """Ring-Buffer vorwärmen."""
        try:
            from pydaw.audio.ring_buffer import RingBuffer
            if np is not None:
                # Dummy-Ring-Buffer erstellen
                rb = RingBuffer(8192, 2)
                dummy = np.zeros((512, 2), dtype=np.float32)
                rb.write(dummy)
                rb.read(512)
            return True
        except ImportError:
            return True
        except Exception as e:
            print(f"[JIT] RingBuffer-Prewarm Fehler: {e}")
            return False
    
    def start(self) -> None:
        """Pre-Warming starten (async in Worker-Thread)."""
        if PYQT_AVAILABLE:
            self._worker = JitPrewarmWorker(self._tasks, self)
            self._worker.progress_changed.connect(self._on_progress)
            self._worker.finished_success.connect(self._on_finished)
            self._worker.finished_error.connect(self._on_error)
            self._worker.start()
        else:
            # Synchrones Fallback (ohne PyQt)
            self._run_sync()
    
    def start_sync(self) -> bool:
        """Pre-Warming synchron ausführen (blockiert).
        
        Returns:
            True wenn erfolgreich
        """
        return self._run_sync()
    
    def _run_sync(self) -> bool:
        """Synchrone Ausführung aller Tasks."""
        success = True
        total = len(self._tasks)
        
        for i, task in enumerate(self._tasks):
            progress = int((i / total) * 100)
            print(f"[JIT] ({progress}%) {task.name}...")
            
            try:
                if not task.function():
                    success = False
            except Exception as e:
                print(f"[JIT] ✗ {task.name}: {e}")
                success = False
        
        print("[JIT] Pre-Warming abgeschlossen")
        return success
    
    def _on_progress(self, progress: int, message: str) -> None:
        """Progress-Signal weiterleiten."""
        if PYQT_AVAILABLE:
            self.progress_changed.emit(progress, message)
    
    def _on_finished(self) -> None:
        """Erfolgreich abgeschlossen."""
        if PYQT_AVAILABLE:
            self.finished.emit()
    
    def _on_error(self, error: str) -> None:
        """Fehler aufgetreten (trotzdem als "fertig" melden)."""
        print(f"[JIT] Pre-Warming Fehler: {error}")
        if PYQT_AVAILABLE:
            self.finished.emit()
    
    def stop(self) -> None:
        """Pre-Warming abbrechen."""
        if self._worker is not None:
            self._worker.abort()
            self._worker.wait(2000)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE-FUNKTION
# ═══════════════════════════════════════════════════════════════════════════════

def prewarm_audio_engine_sync() -> bool:
    """Convenience-Funktion: Audio-Engine synchron vorwärmen.
    
    Kann direkt beim App-Start aufgerufen werden:
    
        from pydaw.services.jit_prewarm_service import prewarm_audio_engine_sync
        
        if __name__ == "__main__":
            print("Initialisiere Audio-Engine...")
            prewarm_audio_engine_sync()
            # ... rest of app startup
    
    Returns:
        True wenn erfolgreich
    """
    service = JitPrewarmService()
    return service.start_sync()


def get_numba_status() -> dict:
    """Numba-Status abrufen (für Debugging/Info).
    
    Returns:
        Dict mit Numba-Informationen
    """
    result = {
        "available": False,
        "version": None,
        "llvmlite_version": None,
        "cpu_features": [],
        "cache_dir": None,
    }
    
    try:
        import numba
        result["available"] = True
        result["version"] = numba.__version__
        
        try:
            import llvmlite
            result["llvmlite_version"] = llvmlite.__version__
        except ImportError:
            pass
        
        try:
            from numba import config
            result["cache_dir"] = str(config.CACHE_DIR)
        except Exception:
            pass
        
        try:
            from numba.core.cpu_options import InstructionSet
            result["cpu_features"] = list(InstructionSet.value)
        except Exception:
            pass
            
    except ImportError:
        pass
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI-TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("PyDAW JIT Pre-Warming Service")
    print("=" * 60)
    
    # Numba-Status anzeigen
    status = get_numba_status()
    print(f"\nNumba verfügbar: {status['available']}")
    if status['available']:
        print(f"  Version: {status['version']}")
        print(f"  llvmlite: {status['llvmlite_version']}")
        print(f"  Cache: {status['cache_dir']}")
    
    print("\n" + "-" * 60)
    print("Starte Pre-Warming...\n")
    
    start_time = time.perf_counter()
    success = prewarm_audio_engine_sync()
    elapsed = (time.perf_counter() - start_time) * 1000
    
    print("\n" + "-" * 60)
    print(f"Pre-Warming {'erfolgreich' if success else 'fehlgeschlagen'}")
    print(f"Gesamtzeit: {elapsed:.1f}ms")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
