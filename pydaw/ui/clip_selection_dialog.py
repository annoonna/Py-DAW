"""Clip Selection Dialog for Ghost Notes / Layered Editing.

This dialog allows users to select MIDI clips to add as ghost layers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
)

if TYPE_CHECKING:
    from pydaw.services.project_service import ProjectService


class ClipSelectionDialog(QDialog):
    """Dialog to select a MIDI clip for ghost layer.
    
    Usage:
        dialog = ClipSelectionDialog(project_service, current_clip_id, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_clip_id = dialog.get_selected_clip_id()
            if selected_clip_id:
                # Add as ghost layer
                layer_manager.add_layer(selected_clip_id, ...)
    """
    
    def __init__(
        self,
        project_service: ProjectService,
        current_clip_id: Optional[str] = None,
        parent=None,
    ):
        """Initialize clip selection dialog.
        
        Args:
            project_service: Project service to get clips from
            current_clip_id: Current clip ID to exclude from list
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_service = project_service
        self.current_clip_id = current_clip_id
        self._selected_clip_id: Optional[str] = None
        
        self.setWindowTitle("Select MIDI Clip for Ghost Layer")
        self.setModal(True)
        self.resize(500, 400)
        
        self._setup_ui()
        self._load_clips()
    
    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("<b>Select a MIDI Clip to add as Ghost Layer:</b>")
        layout.addWidget(header)
        
        # Info label (clear and simple)
        info = QLabel(
            "<i>Ghost layers show MIDI notes from other clips transparently.<br>"
            "<b>Workflow:</b> Select a clip below → Click 'Add as Ghost Layer'<br>"
            "Only the focused layer (✎) can be edited.</i>"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 10px; margin-bottom: 10px; padding: 8px; background: #333; border-radius: 4px;")
        layout.addWidget(info)
        
        # Search/Filter
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter clips...")
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)
        
        # Clip list
        self.clip_list = QListWidget()
        self.clip_list.setAlternatingRowColors(True)
        self.clip_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.clip_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.select_btn = QPushButton("Add as Ghost Layer")
        self.select_btn.setDefault(True)
        self.select_btn.clicked.connect(self.accept)
        self.select_btn.setEnabled(False)  # Disabled until selection
        button_layout.addWidget(self.select_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Connect selection change
        self.clip_list.itemSelectionChanged.connect(self._on_selection_changed)
    
    def _load_clips(self) -> None:
        """Load all MIDI clips from project."""
        try:
            # Get all MIDI clips from project
            midi_clips = self._get_all_midi_clips()
            
            # Debug: Show how many clips we found
            print(f"[ClipSelectionDialog] Found {len(midi_clips)} MIDI clips")
            
            if not midi_clips:
                # No MIDI clips available
                item = QListWidgetItem("No MIDI clips available in project")
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
                self.clip_list.addItem(item)
                return
            
            # Add clips to list
            for clip_info in midi_clips:
                # Skip current clip
                if clip_info['clip_id'] == self.current_clip_id:
                    continue
                
                # Create list item
                display_text = f"{clip_info['track_name']} / {clip_info['clip_name']}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, clip_info['clip_id'])
                
                # Add tooltip with additional info
                tooltip = (
                    f"Track: {clip_info['track_name']}\n"
                    f"Clip: {clip_info['clip_name']}\n"
                    f"Notes: {clip_info['note_count']}\n"
                    f"Length: {clip_info['length_beats']:.1f} beats"
                )
                item.setToolTip(tooltip)
                
                self.clip_list.addItem(item)
        
        except Exception as e:
            # Error loading clips
            item = QListWidgetItem(f"Error loading clips: {e}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.clip_list.addItem(item)
    
    def _get_all_midi_clips(self) -> list[dict]:
        """Get all MIDI clips from project.
        
        Returns:
            List of clip info dicts with keys:
                - clip_id: str
                - clip_name: str
                - track_id: str
                - track_name: str
                - note_count: int
                - length_beats: float
        """
        clips = []
        
        try:
            project = self.project_service.ctx.project
            
            # Iterate through all clips
            for clip in project.clips:
                # Only MIDI clips (check 'kind' attribute)
                clip_kind = str(getattr(clip, 'kind', '')).lower()
                if clip_kind != 'midi':
                    continue
                
                # Get track info
                track = next(
                    (t for t in project.tracks if t.id == clip.track_id),
                    None
                )
                if not track:
                    continue
                
                # Count notes
                try:
                    notes = self.project_service.get_midi_notes(clip.id)
                    note_count = len(notes) if notes else 0
                except Exception:
                    note_count = 0
                
                # Get clip length
                try:
                    length_beats = float(getattr(clip, 'length_beats', 4.0))
                except Exception:
                    length_beats = 4.0
                
                clips.append({
                    'clip_id': str(clip.id),
                    'clip_name': str(getattr(clip, 'label', 'MIDI Clip')),
                    'track_id': str(clip.track_id),
                    'track_name': str(track.name),
                    'note_count': note_count,
                    'length_beats': length_beats,
                })
        
        except Exception as e:
            print(f"[ClipSelectionDialog] Error getting MIDI clips: {e}")
            import traceback
            traceback.print_exc()
        
        return clips
    
    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change.
        
        Args:
            text: Filter text
        """
        text = text.lower()
        
        for i in range(self.clip_list.count()):
            item = self.clip_list.item(i)
            if not item:
                continue
            
            # Check if item matches filter
            item_text = item.text().lower()
            matches = text in item_text if text else True
            
            # Show/hide item
            item.setHidden(not matches)
    
    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        has_selection = bool(self.clip_list.selectedItems())
        self.select_btn.setEnabled(has_selection)
        
        # Update selected clip ID
        selected_items = self.clip_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            self._selected_clip_id = item.data(Qt.ItemDataRole.UserRole)
        else:
            self._selected_clip_id = None
    
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle item double click - select and close.
        
        Args:
            item: Clicked item
        """
        clip_id = item.data(Qt.ItemDataRole.UserRole)
        if clip_id:
            self._selected_clip_id = clip_id
            self.accept()
    
    def get_selected_clip_id(self) -> Optional[str]:
        """Get selected clip ID.
        
        Returns:
            Selected clip ID or None
        """
        return self._selected_clip_id


# Example usage / test
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton
    
    app = QApplication(sys.argv)
    
    # Mock project service for testing
    class MockProjectService:
        class MockContext:
            class MockProject:
                class MockClip:
                    def __init__(self, id, track_id, label):
                        self.id = id
                        self.track_id = track_id
                        self.label = label
                        self.midi_notes = []
                        self.length_beats = 4.0
                
                class MockTrack:
                    def __init__(self, id, name):
                        self.id = id
                        self.name = name
                
                def __init__(self):
                    self.tracks = [
                        self.MockTrack("track1", "Piano"),
                        self.MockTrack("track2", "Strings"),
                        self.MockTrack("track3", "Bass"),
                    ]
                    self.clips = [
                        self.MockClip("clip1", "track1", "Melody"),
                        self.MockClip("clip2", "track1", "Chords"),
                        self.MockClip("clip3", "track2", "String Pad"),
                        self.MockClip("clip4", "track3", "Bassline"),
                    ]
            
            def __init__(self):
                self.project = self.MockProject()
        
        def __init__(self):
            self.ctx = self.MockContext()
        
        def get_midi_notes(self, clip_id):
            # Return some fake notes
            from pydaw.model.midi import MidiNote
            return [MidiNote(60, 0.0, 1.0)] * 5
    
    # Create test window
    window = QMainWindow()
    window.setWindowTitle("Clip Selection Dialog - Test")
    
    button = QPushButton("Open Clip Selection Dialog")
    
    def show_dialog():
        project_service = MockProjectService()
        dialog = ClipSelectionDialog(project_service, current_clip_id="clip1")
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            clip_id = dialog.get_selected_clip_id()
            print(f"Selected clip: {clip_id}")
            button.setText(f"Selected: {clip_id}")
        else:
            print("Cancelled")
    
    button.clicked.connect(show_dialog)
    window.setCentralWidget(button)
    window.resize(400, 200)
    window.show()
    
    sys.exit(app.exec())
