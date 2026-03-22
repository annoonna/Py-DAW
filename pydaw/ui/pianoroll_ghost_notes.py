"""Ghost Notes extension for PianoRollCanvas.

This module provides ghost notes rendering capabilities for the Piano Roll.
It extends the existing PianoRollCanvas with methods to render MIDI notes
from multiple clips/tracks simultaneously.

Usage:
    Add this import to pianoroll_canvas.py:
        from pydaw.ui.pianoroll_ghost_notes import GhostNotesRenderer
    
    In PianoRollCanvas.__init__, add:
        self.ghost_renderer = GhostNotesRenderer(self)
        self.layer_manager = LayerManager()
    
    In paintEvent, before rendering main notes, add:
        self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from pydaw.ui.pianoroll_canvas import PianoRollCanvas
    from pydaw.model.ghost_notes import LayerManager


class GhostNotesRenderer:
    """Renders ghost notes from multiple MIDI clips in Piano Roll.
    
    Features:
    - Multi-layer visualization
    - Opacity-based rendering (30% for locked layers)
    - Color-coded layers
    - Respects layer visibility and lock states
    """
    
    def __init__(self, canvas: PianoRollCanvas):
        """Initialize ghost notes renderer.
        
        Args:
            canvas: Parent piano roll canvas
        """
        self.canvas = canvas
    
    def render_ghost_notes(
        self,
        painter: QPainter,
        layer_manager: LayerManager,
    ) -> None:
        """Render all visible ghost note layers.
        
        Args:
            painter: QPainter to use for rendering
            layer_manager: Layer manager with ghost layers
        """
        # Get all visible layers (sorted by z_order, back to front)
        layers = layer_manager.get_visible_layers()
        
        # Render each layer
        for layer in layers:
            # Skip the focused layer - it will be rendered normally
            if layer.is_focused:
                continue
            
            self._render_layer_notes(painter, layer)
    
    def _render_layer_notes(
        self,
        painter: QPainter,
        layer,  # GhostLayer type
    ) -> None:
        """Render notes from a single ghost layer.
        
        Args:
            painter: QPainter to use
            layer: Ghost layer to render
        """
        try:
            # Get notes from this layer's clip
            notes = self.canvas.project.get_midi_notes(layer.clip_id)
            if not notes:
                return
            
            # Calculate note rectangles for this layer
            note_rects = self._layer_note_rects(notes)
            
            # Render each note with layer opacity and color
            for rect, note in note_rects:
                self._render_ghost_note(
                    painter,
                    rect,
                    note,
                    layer.color,
                    layer.opacity,
                    layer.state.value,
                )
        
        except Exception as e:
            # Silently handle missing clips or errors
            pass
    
    def _layer_note_rects(self, notes: list) -> list[tuple[QRectF, object]]:
        """Calculate rectangles for notes from a ghost layer.
        
        Args:
            notes: List of MIDI notes
        
        Returns:
            List of (QRectF, MidiNote) tuples
        """
        rects = []
        
        for note in notes:
            try:
                pitch = int(note.pitch)
                start_beats = float(note.start_beats)
                length_beats = float(note.length_beats)
                
                # Convert to pixel coordinates
                x = self.canvas._beat_to_x(start_beats)
                y = self.canvas._pitch_to_y(pitch)
                w = length_beats * self.canvas.pixels_per_beat
                h = self.canvas.pixels_per_semitone
                
                rect = QRectF(x, y, max(4.0, w - 1.0), max(4.0, h - 1.0))
                rects.append((rect, note))
            
            except Exception:
                continue
        
        return rects
    
    def _render_ghost_note(
        self,
        painter: QPainter,
        rect: QRectF,
        note,  # MidiNote type
        color: QColor,
        opacity: float,
        state: str,
    ) -> None:
        """Render a single ghost note.
        
        Args:
            painter: QPainter to use
            rect: Note rectangle
            note: MIDI note data
            color: Layer color
            opacity: Rendering opacity (0.0-1.0)
            state: Layer state (active/locked/hidden)
        """
        # Create color with opacity
        note_color = QColor(color)
        note_color.setAlpha(int(255 * opacity))
        
        # Create outline color (slightly darker)
        outline_color = QColor(color).darker(120)
        outline_color.setAlpha(int(180 * opacity))
        
        # Subtle glow for ghost notes (optional)
        if opacity > 0.25:
            painter.setPen(Qt.PenStyle.NoPen)
            glow_expand = 2.0
            glow_color = QColor(color)
            glow_color.setAlpha(int(30 * opacity))
            glow_rect = rect.adjusted(-glow_expand, -glow_expand, glow_expand, glow_expand)
            glow_path = self._rounded_path(glow_rect, radius=4.0)
            painter.fillPath(glow_path, QBrush(glow_color))
        
        # Main note body
        inner_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        note_path = self._rounded_path(inner_rect, radius=3.0)
        
        pen = QPen(outline_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(note_color))
        painter.drawPath(note_path)
        
        # Lock indicator (small lock icon in corner)
        if state == "locked":
            self._draw_lock_indicator(painter, rect, opacity)
    
    def _draw_lock_indicator(
        self,
        painter: QPainter,
        rect: QRectF,
        opacity: float,
    ) -> None:
        """Draw a small lock icon on locked ghost notes.
        
        Args:
            painter: QPainter to use
            rect: Note rectangle
            opacity: Current opacity
        """
        # Only draw lock if note is wide enough
        if rect.width() < 20:
            return
        
        # Small lock icon in top-right corner
        lock_size = min(8, rect.height() * 0.4)
        lock_x = rect.right() - lock_size - 2
        lock_y = rect.top() + 2
        
        lock_color = QColor(255, 255, 255)
        lock_color.setAlpha(int(180 * opacity))
        
        painter.setPen(QPen(lock_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Simple lock shape: rectangle with arc on top
        lock_rect = QRectF(lock_x, lock_y + lock_size * 0.3, lock_size * 0.6, lock_size * 0.7)
        painter.drawRect(lock_rect)
        
        # Arc on top (lock shackle)
        arc_rect = QRectF(lock_x - lock_size * 0.1, lock_y, lock_size * 0.8, lock_size * 0.6)
        painter.drawArc(arc_rect, 0, 180 * 16)  # 180 degrees
    
    @staticmethod
    def _rounded_path(rect: QRectF, radius: float = 4.0) -> QPainterPath:
        """Create a rounded rectangle path.
        
        Args:
            rect: Rectangle to round
            radius: Corner radius
        
        Returns:
            QPainterPath with rounded rectangle
        """
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path


# Helper functions to integrate into existing PianoRollCanvas

def integrate_ghost_notes_rendering(canvas_instance):
    """Helper to integrate ghost notes into existing PianoRollCanvas.
    
    Call this in PianoRollCanvas.__init__:
        integrate_ghost_notes_rendering(self)
    
    Args:
        canvas_instance: PianoRollCanvas instance
    """
    from pydaw.model.ghost_notes import LayerManager
    
    # Add layer manager and renderer
    canvas_instance.layer_manager = LayerManager()
    canvas_instance.ghost_renderer = GhostNotesRenderer(canvas_instance)
    
    # Store original paintEvent
    original_paint = canvas_instance.paintEvent
    
    def new_paint_event(event):
        """Enhanced paintEvent with ghost notes support."""
        # Create painter
        from PyQt6.QtGui import QPainter
        
        painter = QPainter(canvas_instance)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Render background and grid (from original)
        # ... (this would need to be extracted from original paintEvent)
        
        # Render ghost notes BEFORE main notes
        if hasattr(canvas_instance, 'ghost_renderer') and hasattr(canvas_instance, 'layer_manager'):
            canvas_instance.ghost_renderer.render_ghost_notes(painter, canvas_instance.layer_manager)
        
        # Continue with original painting
        painter.end()
        original_paint(event)
    
    # Replace paintEvent (note: this is a simplified example)
    # In practice, we would modify the paintEvent in pianoroll_canvas.py directly
    # canvas_instance.paintEvent = new_paint_event


# Example standalone test
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from PyQt6.QtGui import QPainter, QColor
    from PyQt6.QtCore import QRectF
    
    # This would need actual PianoRollCanvas and ProjectService to run
    print("Ghost Notes Renderer - Test Mode")
    print("This module extends PianoRollCanvas with ghost notes rendering.")
    print("\nIntegration steps:")
    print("1. Import: from pydaw.ui.pianoroll_ghost_notes import GhostNotesRenderer")
    print("2. In __init__: self.ghost_renderer = GhostNotesRenderer(self)")
    print("3. In paintEvent: self.ghost_renderer.render_ghost_notes(p, self.layer_manager)")
    print("\nGhost notes will be rendered with 30% opacity for locked layers.")
