"""Editor dock widget (Variant A: tab system).

Contains:
- Piano Roll
- Notation (MVP, leichtgewichtig)

Important:
Für den Team-Workflow ist Notation bewusst als leichtes, stabiles Widget
integriert (siehe `pydaw/ui/notation/`).
Die ChronoScaleStudio-Integration bleibt optional in `pydaw/ui/chronoscale_widget.py`.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .pianoroll_editor import PianoRollEditor
from .notation.notation_view import NotationWidget
from .audio_editor.audio_event_editor import AudioEventEditor


class EditorTabs(QWidget):
    status_message = Signal(str)

    def __init__(self, project_service, *, transport=None, editor_timeline=None,
                 status_cb=None, enable_notation_tab: bool | None = None):
        super().__init__()
        self._project_service = project_service
        self._transport = transport

        self.tabs = QTabWidget()
        # v0.0.20.613: editor_timeline an alle Editoren durchreichen
        self.pianoroll = PianoRollEditor(project_service, transport=transport,
                                         editor_timeline=editor_timeline)
        self.audio_editor = AudioEventEditor(project_service, transport=transport,
                                              editor_timeline=editor_timeline)
        # MVP Notation: lightweight integrated view (Task 3).
        # ChronoScaleStudio remains available in pydaw/ui/chronoscale_widget.py,
        # but is intentionally not the default for the TEAM workflow.
        self.notation = NotationWidget(project_service, transport=transport,
                                        editor_timeline=editor_timeline)

        if status_cb:
            self.pianoroll.status_message.connect(status_cb)
            self.notation.status_message.connect(status_cb)
            self.audio_editor.status_message.connect(status_cb)
            self.status_message.connect(status_cb)

        self.tabs.addTab(self.audio_editor, "Audio")
        self.tabs.addTab(self.pianoroll, "Piano Roll")

        # Notation tab can be toggled from "Ansicht".
        self._notation_tab_visible = bool(enable_notation_tab)
        if self._notation_tab_visible:
            self._add_notation_tab()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tabs)

        self._active_clip_id: str | None = None

    def _add_notation_tab(self) -> None:
        if self.tabs.indexOf(self.notation) != -1:
            return
        insert_at = 1 if self.tabs.count() >= 1 else self.tabs.count()
        self.tabs.insertTab(insert_at, self.notation, "Notation")

    def is_notation_tab_visible(self) -> bool:
        return self.tabs.indexOf(self.notation) != -1

    def set_notation_tab_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self.is_notation_tab_visible():
            self._notation_tab_visible = visible
            return

        self._notation_tab_visible = visible
        if visible:
            self._add_notation_tab()
        else:
            idx = self.tabs.currentIndex()
            if self.tabs.widget(idx) is self.notation:
                self.tabs.setCurrentIndex(0)
            i = self.tabs.indexOf(self.notation)
            if i != -1:
                self.tabs.removeTab(i)

    def set_clip(self, clip_id: str | None) -> None:
        self._active_clip_id = clip_id
        self.pianoroll.set_clip(clip_id)
        self.notation.set_clip(clip_id)
        try:
            self.audio_editor.set_clip(clip_id)
        except Exception:
            pass

    def show_audio(self) -> None:
        self.tabs.setCurrentWidget(self.audio_editor)

    def show_pianoroll(self) -> None:
        self.tabs.setCurrentWidget(self.pianoroll)

    def show_notation(self) -> None:
        if not self.is_notation_tab_visible():
            self.status_message.emit("Notation ist deaktiviert (Ansicht → Notation (WIP)).")
            return
        self.tabs.setCurrentWidget(self.notation)
