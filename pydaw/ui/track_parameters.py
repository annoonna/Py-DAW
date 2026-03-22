from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class TrackParametersPanel(QWidget):
    """Parameter list per track (DAW-style Inspector), with placeholders.

    This is intentionally simple: it gives a stable UI contract now, while the
    audio engine / plugin hosting / routing evolve.
    """

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._track_id = ""

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Parameter", "Value"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.tree)

        # Refresh when the project changes.
        self.project.project_updated.connect(self.refresh)
        self.refresh()

    def set_track(self, track_id: str) -> None:
        self._track_id = str(track_id or "")
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()

        trk = None
        if self._track_id:
            trk = next((t for t in self.project.ctx.project.tracks if t.id == self._track_id), None)

        if not trk:
            it = QTreeWidgetItem(["Keine Spur ausgewählt.", ""])
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree.addTopLevelItem(it)
            return

        # Mixer params
        mixer = QTreeWidgetItem(["Mixer", ""])
        self.tree.addTopLevelItem(mixer)
        QTreeWidgetItem(mixer, ["Volume", f"{trk.volume:.3f}"])
        QTreeWidgetItem(mixer, ["Pan", f"{trk.pan:.3f}"])
        QTreeWidgetItem(mixer, ["Automation", str(trk.automation_mode)])

        # Sends / buses (placeholder)
        sends = QTreeWidgetItem(["Sends / Bus", "(Platzhalter)"])
        self.tree.addTopLevelItem(sends)
        QTreeWidgetItem(sends, ["Send A", "-"])
        QTreeWidgetItem(sends, ["Send B", "-"])
        QTreeWidgetItem(sends, ["Bus Route", "-"])

        # Plugin slots (placeholder)
        plugs = QTreeWidgetItem(["Plugins", "(Platzhalter)"])
        self.tree.addTopLevelItem(plugs)
        QTreeWidgetItem(plugs, ["Slot 1", "Empty"])
        QTreeWidgetItem(plugs, ["Slot 2", "Empty"])
        QTreeWidgetItem(plugs, ["Slot 3", "Empty"])

        self.tree.expandAll()
