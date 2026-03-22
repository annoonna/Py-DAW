"""FluidSynth service for MIDI playback with SoundFonts.

Provides high-quality MIDI synthesis using FluidSynth and SF2 files.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal as Signal


class FluidSynthService(QObject):
    """Service for FluidSynth MIDI synthesis.
    
    Features:
    - Load SF2 SoundFont files
    - Play MIDI notes in real-time
    - Program change support
    - Audio routing to JACK/PipeWire
    """
    
    error = Signal(str)
    status = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._synth = None
        self._driver = None
        self._soundfont_id = -1
        self._available = False
        self._lock = threading.Lock()
        self._initialized = False
        
        # DON'T initialize FluidSynth at startup
        # Only initialize when user actually wants to use it
        # This prevents SDL3/ALSA crashes on startup
        self.status.emit("FluidSynth bereit (bei Bedarf)")
    
    def _ensure_initialized(self) -> bool:
        """Lazy initialization - only when needed."""
        if self._initialized:
            return self._available
        
        self._initialized = True
        self._initialize()
        return self._available
    
    def _initialize(self) -> None:
        """Initialize FluidSynth."""
        try:
            import fluidsynth
            
            # Create synth with safe settings (no audio driver by default)
            self._synth = fluidsynth.Synth()
            
            # Don't start audio driver automatically - prevents SDL3/ALSA crashes
            # Audio will be routed through JACK/PipeWire if needed
            try:
                self._synth.start(driver=None)  # No automatic driver
                self.status.emit("FluidSynth bereit (Audio über JACK/PipeWire)")
            except Exception as e:
                # Fallback: try without driver parameter
                self._synth.start()
                self.status.emit("FluidSynth bereit")
            
            self._available = True
            
        except ImportError:
            self.error.emit(
                "FluidSynth nicht verfügbar. "
                "Installieren Sie pyFluidSynth: pip install pyfluidsynth"
            )
            self._available = False
        except Exception as e:
            # Don't crash on FluidSynth errors - just disable it
            self.error.emit(f"FluidSynth nicht verfügbar: {e}")
            self._available = False
            self._synth = None
    
    def _detect_audio_driver(self) -> str | None:
        """Detect available audio driver."""
        # Check for JACK (PipeWire-JACK)
        if os.environ.get("JACK_DEFAULT_SERVER") or os.environ.get("PW_JACK"):
            return "jack"
        
        # Check for PipeWire
        if os.path.exists("/run/user/1000/pipewire-0"):
            return "pipewire"
        
        # Fallback to ALSA
        return "alsa"
    
    def is_available(self) -> bool:
        """Check if FluidSynth is available."""
        if not self._initialized:
            return True  # Assume available until tried
        return self._available
    
    def load_soundfont(self, sf2_path: str | Path) -> bool:
        """Load a SoundFont file.
        
        Args:
            sf2_path: Path to SF2 file
            
        Returns:
            True if loaded successfully
        """
        # Initialize on first use
        if not self._ensure_initialized():
            return False
        
        if not self._available or not self._synth:
            self.error.emit("FluidSynth nicht verfügbar")
            return False
        
        sf2_path = Path(sf2_path)
        if not sf2_path.exists():
            self.error.emit(f"SoundFont nicht gefunden: {sf2_path}")
            return False
        
        try:
            with self._lock:
                # Unload previous soundfont
                if self._soundfont_id >= 0:
                    self._synth.sfunload(self._soundfont_id)
                
                # Load new soundfont
                self._soundfont_id = self._synth.sfload(str(sf2_path))
                
                if self._soundfont_id < 0:
                    self.error.emit(f"Fehler beim Laden von {sf2_path.name}")
                    return False
                
                # Select the soundfont for all channels
                for channel in range(16):
                    self._synth.program_select(channel, self._soundfont_id, 0, 0)
                
                self.status.emit(f"SoundFont geladen: {sf2_path.name}")
                return True
                
        except Exception as e:
            self.error.emit(f"SoundFont Ladefehler: {e}")
            return False
    
    def note_on(self, channel: int, pitch: int, velocity: int) -> None:
        """Play a MIDI note.
        
        Args:
            channel: MIDI channel (0-15)
            pitch: MIDI note number (0-127)
            velocity: Note velocity (0-127)
        """
        if not self._ensure_initialized():
            return
        
        if not self._available or not self._synth:
            return
        
        try:
            with self._lock:
                self._synth.noteon(channel, pitch, velocity)
        except Exception as e:
            self.error.emit(f"Note On Fehler: {e}")
    
    def note_off(self, channel: int, pitch: int) -> None:
        """Stop a MIDI note.
        
        Args:
            channel: MIDI channel (0-15)
            pitch: MIDI note number (0-127)
        """
        if not self._available or not self._synth:
            return
        
        try:
            with self._lock:
                self._synth.noteoff(channel, pitch)
        except Exception as e:
            self.error.emit(f"Note Off Fehler: {e}")
    
    def program_change(self, channel: int, program: int) -> None:
        """Change MIDI program (instrument).
        
        Args:
            channel: MIDI channel (0-15)
            program: Program number (0-127)
        """
        if not self._available or not self._synth or self._soundfont_id < 0:
            return
        
        try:
            with self._lock:
                self._synth.program_change(channel, program)
        except Exception as e:
            self.error.emit(f"Program Change Fehler: {e}")
    
    def all_notes_off(self) -> None:
        """Stop all playing notes on all channels."""
        if not self._available or not self._synth:
            return
        
        try:
            with self._lock:
                for channel in range(16):
                    for pitch in range(128):
                        self._synth.noteoff(channel, pitch)
        except Exception:
            pass
    
    def set_gain(self, gain: float) -> None:
        """Set master gain.
        
        Args:
            gain: Gain value (0.0 to 2.0, default 0.2)
        """
        if not self._available or not self._synth:
            return
        
        try:
            with self._lock:
                self._synth.setting('synth.gain', max(0.0, min(2.0, gain)))
        except Exception as e:
            self.error.emit(f"Gain Fehler: {e}")
    
    def cleanup(self) -> None:
        """Clean up FluidSynth resources."""
        if not self._available:
            return
        
        try:
            self.all_notes_off()
            
            with self._lock:
                if self._soundfont_id >= 0 and self._synth:
                    self._synth.sfunload(self._soundfont_id)
                    self._soundfont_id = -1
                
                if self._synth:
                    self._synth.delete()
                    self._synth = None
                
                if self._driver:
                    del self._driver
                    self._driver = None
            
        except Exception:
            pass
