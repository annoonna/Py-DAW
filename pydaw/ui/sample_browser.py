"""Sample Browser (Pro-DAW-Style) with Drag & Drop + Preview.

v0.0.20.7:
- Integrated Preview Player (Raw / Sync)
- Loop preview (bar-aligned in Sync mode)
- BPM detection (Essentia RhythmExtractor2013) on selection (best-effort)
- Background thread rendering (no GUI freeze)
- Preview cache (LRU) for instant re-audition (no re-render)
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Optional

from .browser_places_prefs import BrowserPlacesPrefs

from PyQt6.QtCore import Qt, QMimeData, QUrl, QDir, pyqtSignal, QThread
from PyQt6.QtGui import QDrag, QFileSystemModel
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QButtonGroup,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QMenu,
)

UNCOMPRESSED_EXTS = {".wav", ".aif", ".aiff", ".au", ".snd"}
LOSSLESS_EXTS = {".flac", ".alac", ".caf", ".wv", ".ape"}
COMPRESSED_EXTS = {".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".aac", ".wma"}
SAMPLER_EXTS = {".sf2", ".sfz"}

PREVIEWABLE_AUDIO_EXTS = set().union(UNCOMPRESSED_EXTS, LOSSLESS_EXTS, COMPRESSED_EXTS)
BROWSABLE_MEDIA_EXTS = set().union(PREVIEWABLE_AUDIO_EXTS, SAMPLER_EXTS)


def _suffix_ci_pattern(ext: str) -> str:
    ext = str(ext or "").strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    chars = []
    for ch in ext[1:]:
        if ch.isalpha():
            chars.append(f"[{ch.lower()}{ch.upper()}]")
        else:
            chars.append(ch)
    return "*." + "".join(chars)


def _name_filters_for_exts(exts: set[str]) -> list[str]:
    return [_suffix_ci_pattern(x) for x in sorted(exts)]


FILTER_PRESETS: dict[str, tuple[str, list[str]]] = {
    "all": ("All Audio", _name_filters_for_exts(BROWSABLE_MEDIA_EXTS)),
    "uncompressed": ("Unkomprimiert", _name_filters_for_exts(UNCOMPRESSED_EXTS)),
    "lossless": ("Lossless", _name_filters_for_exts(LOSSLESS_EXTS)),
    "compressed": ("Compressed", _name_filters_for_exts(COMPRESSED_EXTS)),
    "sampler": ("Sampler (SF2/SFZ)", _name_filters_for_exts(SAMPLER_EXTS)),
    "sf2": ("Nur .sf2", [_suffix_ci_pattern(".sf2")]),
    "sfz": ("Nur .sfz", [_suffix_ci_pattern(".sfz")]),
}


def _is_browser_media_file(path_str: str) -> bool:
    try:
        return Path(path_str).suffix.lower() in BROWSABLE_MEDIA_EXTS
    except Exception:
        return False


def _is_previewable_audio_file(path_str: str) -> bool:
    try:
        return Path(path_str).suffix.lower() in PREVIEWABLE_AUDIO_EXTS
    except Exception:
        return False


def _build_drag_pixmap(path_str: str):
    # lightweight ghost cursor preview (waveform for wav, icon otherwise)
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
    name = Path(path_str).stem
    w, h = 180, 52
    pm = QPixmap(w, h)
    pm.fill(QColor(0, 0, 0, 0))

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # background
    p.setPen(QPen(QColor(255, 255, 255, 40), 1))
    p.setBrush(QColor(30, 30, 30, 235))
    p.drawRoundedRect(0, 0, w-1, h-1, 10, 10)

    ext = Path(path_str).suffix.lower()
    if ext == ".wav":
        try:
            import wave, struct
            wf = wave.open(path_str, 'rb')
            ch = max(1, int(wf.getnchannels()))
            n = min(int(wf.getnframes()), 2200)
            raw = wf.readframes(n)
            sw = int(wf.getsampwidth())
            wf.close()
            if sw == 2 and raw:
                samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)
                # take first channel only
                s = samples[0::ch]
                if s:
                    bins = 110
                    step = max(1, len(s) // bins)
                    mid = 28
                    p.setPen(QPen(QColor(0, 200, 255, 220), 2))
                    for i in range(bins):
                        a = s[i*step:(i+1)*step]
                        if not a:
                            continue
                        mx = max(1, max(abs(int(v)) for v in a))
                        amp = int(14 * mx / 32768.0)
                        x = 10 + i
                        p.drawLine(x, mid-amp, x, mid+amp)
        except Exception:
            pass
    else:
        p.setPen(QPen(QColor(0, 200, 255, 180), 2))
        p.drawEllipse(10, 14, 24, 24)

    # text
    p.setPen(QPen(QColor(240, 240, 240, 240), 1))
    f = QFont()
    f.setPointSize(9)
    f.setBold(True)
    p.setFont(f)
    txt = name[:22] + ("…" if len(name) > 22 else "")
    p.drawText(42, 22, txt)
    p.setPen(QPen(QColor(190, 190, 190, 210), 1))
    f2 = QFont()
    f2.setPointSize(8)
    p.setFont(f2)
    p.drawText(42, 40, ext.upper().replace('.', ''))
    p.end()
    return pm



class _SampleTreeView(QTreeView):
    drag_started = pyqtSignal(str)
    drag_finished = pyqtSignal()

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner

    def startDrag(self, supportedActions):  # noqa: ANN001
        idx = self.currentIndex()
        if not idx.isValid():
            return
        try:
            model = self.model()
            path_str = model.filePath(idx) if model is not None else ""
        except Exception:
            path_str = ""
        if not path_str or not _is_previewable_audio_file(path_str):
            return

        try:
            self.drag_started.emit(Path(path_str).name)
        except Exception:
            pass

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path_str)])

        # Pass BPM hint if available (Arranger can store source_bpm)
        try:
            bpm = getattr(self._owner, "_selected_bpm", None)
            if bpm is not None and abs(float(bpm)) > 0:
                mime.setData("application/x-pydaw-audio-bpm", bytes(str(float(bpm)), "utf-8"))
        except Exception:
            pass

        drag = QDrag(self)
        drag.setMimeData(mime)
        try:
            drag.setPixmap(_build_drag_pixmap(path_str))
            drag.setHotSpot(drag.pixmap().rect().center())
        except Exception:
            pass

        drag.exec(supportedActions)

        try:
            self.drag_finished.emit()
        except Exception:
            pass


class _BPMWorker(QThread):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = str(path)

    def run(self) -> None:
        try:
            from pydaw.plugins.sampler.audio_io import load_audio
            from pydaw.audio.bpm_detect import estimate_bpm
            data, sr = load_audio(self.path, target_sr=48000)
            res = estimate_bpm(data, int(sr), filename_hint=Path(self.path).name)
            self._result = res
        except Exception:
            self._result = None


class _RenderWorker(QThread):
    def __init__(self, path: str, mode: str, loop: bool, project_bpm: float, beats_per_bar: float, source_bpm_hint: Optional[float], parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.mode = str(mode)
        self.loop = bool(loop)
        self.project_bpm = float(project_bpm or 120.0)
        self.beats_per_bar = float(beats_per_bar or 4.0)
        self.source_bpm_hint = float(source_bpm_hint) if source_bpm_hint else None

    def run(self) -> None:
        try:
            import numpy as np
            from pydaw.plugins.sampler.audio_io import load_audio
            from pydaw.audio.time_stretch import time_stretch_stereo
            from pydaw.audio.bpm_detect import estimate_bpm, parse_bpm_from_filename

            data, sr = load_audio(self.path, target_sr=48000)
            sr = int(sr or 48000)
            data = np.asarray(data, dtype=np.float32)
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            if data.shape[1] > 2:
                data = data[:, :2]

            # determine source bpm
            source_bpm = self.source_bpm_hint
            if source_bpm is None:
                source_bpm = parse_bpm_from_filename(Path(self.path).name)
            if source_bpm is None and self.mode == "sync":
                # best-effort audio bpm
                br = estimate_bpm(data, sr, filename_hint=Path(self.path).name)
                if br and br.bpm:
                    source_bpm = float(br.bpm)

            # render
            out = data
            if self.mode == "sync":
                if not source_bpm or source_bpm <= 0:
                    source_bpm = float(self.project_bpm)
                rate = float(self.project_bpm) / float(source_bpm)
                out = time_stretch_stereo(out, rate=rate, sr=sr)

                # bar-aligned looping in Sync mode
                if self.loop:
                    samples_per_beat = float(sr) * 60.0 / float(self.project_bpm or 120.0)
                    bar_samples = int(round(samples_per_beat * float(self.beats_per_bar or 4.0)))
                    bar_samples = max(256, bar_samples)
                    n_bars = max(1, int(round(out.shape[0] / float(bar_samples))))
                    target = n_bars * bar_samples
                    if out.shape[0] > target:
                        out = out[:target]
                    elif out.shape[0] < target:
                        pad = target - out.shape[0]
                        out = np.pad(out, ((0, pad), (0, 0)), mode="constant")

            self._render = (out.astype(np.float32, copy=False), sr, source_bpm)
        except Exception:
            self._render = None


class SampleBrowserWidget(QWidget):
    """File browser for audio samples with drag & drop + preview."""

    audio_drag_started = pyqtSignal(str)
    audio_drag_ended = pyqtSignal()

    def __init__(self, audio_engine=None, transport=None, project_service=None, parent=None):
        super().__init__(parent)
        self.setObjectName("sampleBrowserWidget")

        # Allow the whole Browser Dock to be shrunk "almost closed".
        # The previous fixed/min widths inside the SampleBrowser prevented the
        # right dock separator from moving far enough to the right.
        try:
            self.setMinimumWidth(0)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        self._current_path = str(Path.home())
        self._selected_path: Optional[str] = None
        self._selected_bpm: Optional[float] = None
        self._selected_bpm_conf: float = 0.0
        self._selected_bpm_method: str = ""

        self.audio_engine = audio_engine
        self.transport = transport
        self.project_service = project_service

        self._preview_player = None
        self._preview_name = f"browser_preview:{uuid.uuid4().hex[:8]}"
        self._bpm_worker: Optional[_BPMWorker] = None
        self._render_worker: Optional[_RenderWorker] = None
        self._last_token = 0

        # In-memory LRU cache for preview renders (avoids re-render on repeated audition)
        try:
            from pydaw.audio.preview_cache import DEFAULT_PREVIEW_CACHE
            self._preview_cache = DEFAULT_PREVIEW_CACHE
        except Exception:
            self._preview_cache = None

        self._quick_dirs = self._discover_quick_dirs()
        self._places_prefs = BrowserPlacesPrefs.load()

        self._build_ui()
        self._wire_preview()
        self._register_preview_source()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Path bar
        top = QHBoxLayout()
        self.cmb_quick = QComboBox()
        # No hard minimum width → let the dock collapse.
        try:
            self.cmb_quick.setMinimumWidth(0)
            self.cmb_quick.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        self._populate_quick_combo()
        top.addWidget(self.cmb_quick)

        self.path_edit = QLineEdit(self._current_path)
        self.path_edit.setPlaceholderText("Pfad…")
        top.addWidget(self.path_edit, 1)

        self.btn_go = QPushButton("Öffnen")
        # Keep the usual look (max ~80px) but allow shrinking when the dock is collapsed.
        try:
            self.btn_go.setMaximumWidth(80)
            self.btn_go.setMinimumWidth(0)
            self.btn_go.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        top.addWidget(self.btn_go)

        layout.addLayout(top)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.btn_quick_home = QPushButton("🏠 Home")
        self.btn_quick_samples = QPushButton("🎛 Samples")
        self.btn_quick_sf2 = QPushButton("🎼 SF2")
        self.btn_add_place = QPushButton("⭐ Aktuell")
        for _btn in (self.btn_quick_home, self.btn_quick_samples, self.btn_quick_sf2, self.btn_add_place):
            try:
                _btn.setMinimumWidth(0)
                _btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            except Exception:
                pass
            filter_row.addWidget(_btn)

        filter_row.addWidget(QLabel("Filter:"))
        self.cmb_filter = QComboBox()
        try:
            self.cmb_filter.setMinimumWidth(0)
            self.cmb_filter.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        for key, (label, _patterns) in FILTER_PRESETS.items():
            self.cmb_filter.addItem(label, key)
        filter_row.addWidget(self.cmb_filter, 1)

        layout.addLayout(filter_row)

        content = QHBoxLayout()
        content.setSpacing(6)

        places_col = QVBoxLayout()
        places_col.setSpacing(4)
        self.lbl_places = QLabel("⭐ Orte")
        places_col.addWidget(self.lbl_places)
        self.lst_places = QListWidget()
        try:
            self.lst_places.setMinimumWidth(120)
            self.lst_places.setMaximumWidth(220)
            self.lst_places.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        except Exception:
            pass
        places_col.addWidget(self.lst_places, 1)
        content.addLayout(places_col)

        tree_col = QVBoxLayout()
        tree_col.setContentsMargins(0, 0, 0, 0)
        tree_col.setSpacing(0)

        # File tree
        self.model = QFileSystemModel()
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)
        self.model.setNameFilterDisables(False)
        self._apply_name_filter("all")
        self.model.setRootPath(QDir.rootPath())

        self.tree = _SampleTreeView(owner=self)
        # Let the tree be clipped when collapsing the dock.
        try:
            self.tree.setMinimumWidth(0)
            self.tree.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self._current_path))
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setHeaderHidden(False)
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 110)
        self.tree.setColumnWidth(3, 140)
        tree_col.addWidget(self.tree, 1)
        content.addLayout(tree_col, 1)
        layout.addLayout(content, 1)

        # Preview panel
        prev = QHBoxLayout()
        prev.setSpacing(8)

        self.lbl_sel = QLabel("—")
        self.lbl_sel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        prev.addWidget(self.lbl_sel, 2)

        self.lbl_bpm = QLabel("BPM: —")
        # Keep readable at normal width, but allow collapsing.
        try:
            self.lbl_bpm.setMaximumWidth(110)
            self.lbl_bpm.setMinimumWidth(0)
            self.lbl_bpm.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        prev.addWidget(self.lbl_bpm)

        self.btn_raw = QPushButton("Raw")
        self.btn_raw.setCheckable(True)
        self.btn_sync = QPushButton("Sync")
        self.btn_sync.setCheckable(True)
        self.btn_raw.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_raw)
        self.mode_group.addButton(self.btn_sync)

        prev.addWidget(self.btn_raw)
        prev.addWidget(self.btn_sync)

        self.chk_loop = QCheckBox("Loop")
        prev.addWidget(self.chk_loop)

        self.btn_play = QPushButton("▶ Preview")
        self.btn_stop = QPushButton("■")
        try:
            self.btn_stop.setMaximumWidth(40)
            self.btn_stop.setMinimumWidth(0)
            self.btn_stop.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        prev.addWidget(self.btn_play)
        prev.addWidget(self.btn_stop)

        layout.addLayout(prev)

        # Wiring
        self.cmb_quick.currentIndexChanged.connect(self._on_quick_changed)
        self.btn_quick_home.clicked.connect(lambda: self._jump_to_quick("home"))
        self.btn_quick_samples.clicked.connect(lambda: self._jump_to_quick("samples"))
        self.btn_quick_sf2.clicked.connect(lambda: self._jump_to_quick("sf2"))
        self.btn_add_place.clicked.connect(self._add_current_place)
        self.cmb_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.lst_places.itemDoubleClicked.connect(self._on_place_activated)
        self.lst_places.customContextMenuRequested.connect(self._on_places_context_menu)
        self.btn_go.clicked.connect(self._on_go_clicked)
        self.path_edit.returnPressed.connect(self._on_go_clicked)
        try:
            self.model.directoryLoaded.connect(self._on_directory_loaded)
        except Exception:
            pass

        # Selection changes
        try:
            self.tree.selectionModel().currentChanged.connect(self._on_tree_current_changed)
        except Exception:
            pass

        # Double click plays preview quickly
        self.tree.doubleClicked.connect(lambda _idx: self._on_play_clicked())
        self._reload_places_list()
        # Drag signals
        try:
            self.tree.drag_started.connect(lambda lbl: self.audio_drag_started.emit(lbl))
            self.tree.drag_finished.connect(lambda: self.audio_drag_ended.emit())
        except Exception:
            pass


    def _reload_places_list(self) -> None:
        try:
            self.lst_places.clear()
            builtins = [
                ("🏠 Home", self._quick_dirs.get("home", str(Path.home())), False),
                ("🎛 Samples", self._quick_dirs.get("samples", str(Path.home())), False),
                ("🎼 SF2", self._quick_dirs.get("sf2", str(Path.home())), False),
                ("📥 Downloads", self._quick_dirs.get("downloads", str(Path.home())), False),
                ("🎵 Music", self._quick_dirs.get("music", str(Path.home())), False),
            ]
            for label, path_str, removable in builtins:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, str(path_str))
                item.setData(Qt.ItemDataRole.UserRole + 1, bool(removable))
                self.lst_places.addItem(item)
            for it in self._places_prefs.places:
                path_str = str(it.get("path") or "")
                label = str(it.get("label") or Path(path_str).name or path_str)
                item = QListWidgetItem(f"⭐ {label}")
                item.setToolTip(path_str)
                item.setData(Qt.ItemDataRole.UserRole, path_str)
                item.setData(Qt.ItemDataRole.UserRole + 1, True)
                self.lst_places.addItem(item)
        except Exception:
            pass

    def _on_place_activated(self, item) -> None:  # noqa: ANN001
        try:
            path_str = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if path_str:
                self._set_root(path_str)
        except Exception:
            pass

    def _add_current_place(self) -> None:
        try:
            cur = str(self._current_path or "").strip()
            if not cur:
                return
            label = Path(cur).name or cur
            if self._places_prefs.add_place(label, cur):
                self._places_prefs.save()
                self._reload_places_list()
        except Exception:
            pass

    def _on_places_context_menu(self, pos) -> None:  # noqa: ANN001
        try:
            item = self.lst_places.itemAt(pos)
            if item is None:
                return
            path_str = str(item.data(Qt.ItemDataRole.UserRole) or "")
            removable = bool(item.data(Qt.ItemDataRole.UserRole + 1))
            m = QMenu(self)
            a_open = m.addAction("Öffnen")
            a_add = m.addAction("⭐ Aktuellen Ordner speichern")
            a_remove = m.addAction("🗑 Aus Favoriten entfernen") if removable else None
            act = m.exec(self.lst_places.mapToGlobal(pos))
            if act == a_open and path_str:
                self._set_root(path_str)
            elif act == a_add:
                self._add_current_place()
            elif a_remove is not None and act == a_remove and path_str:
                self._places_prefs.remove_place(path_str)
                self._places_prefs.save()
                self._reload_places_list()
        except Exception:
            pass

    def current_root_path(self) -> str:
        return str(self._current_path or "")

    def open_path(self, path_str: str) -> None:
        self._set_root(path_str)


    def _discover_quick_dirs(self) -> dict[str, str]:
        home = Path.home()

        def _first_existing(candidates: list[Path], fallback: Path) -> str:
            for cand in candidates:
                try:
                    if cand.exists() and cand.is_dir():
                        return str(cand)
                except Exception:
                    pass
            return str(fallback)

        quick = {
            "home": str(home),
            "downloads": _first_existing([home / "Downloads", home / "downloads"], home),
            "music": _first_existing([home / "Music", home / "musik", home / "Musik"], home),
            "samples": _first_existing([
                home / "Samples",
                home / "samples",
                home / "Music" / "Samples",
                home / "Musik" / "Samples",
                home / "sample",
                home / "Sample",
                home / "sample libraries",
                home / "sample_libraries",
            ], home),
            "sf2": _first_existing([
                home / "SF2",
                home / "sf2",
                home / "SF2_Downloads",
                home / "SoundFonts",
                home / "soundfonts",
                home / "Downloads" / "SF2",
            ], home),
            "root": "/",
        }
        return quick

    def _populate_quick_combo(self) -> None:
        try:
            self.cmb_quick.clear()
            self.cmb_quick.addItem("🏠 Home", self._quick_dirs.get("home", str(Path.home())))
            self.cmb_quick.addItem("🎛 Samples", self._quick_dirs.get("samples", str(Path.home())))
            self.cmb_quick.addItem("🎼 SF2", self._quick_dirs.get("sf2", str(Path.home())))
            self.cmb_quick.addItem("📥 Downloads", self._quick_dirs.get("downloads", str(Path.home())))
            self.cmb_quick.addItem("🎵 Music", self._quick_dirs.get("music", str(Path.home())))
            self.cmb_quick.addItem("🗂️ /", self._quick_dirs.get("root", "/"))
        except Exception:
            pass

    def _apply_name_filter(self, preset_key: str) -> None:
        key = str(preset_key or "all")
        if key not in FILTER_PRESETS:
            key = "all"
        try:
            _label, patterns = FILTER_PRESETS[key]
            self.model.setNameFilters(list(patterns))
            self.model.setNameFilterDisables(False)
        except Exception:
            pass

    def _on_filter_changed(self, _idx: int) -> None:
        try:
            key = str(self.cmb_filter.currentData() or "all")
            self._apply_name_filter(key)
            self.tree.setRootIndex(self.model.index(self._current_path))
        except Exception:
            pass

    def _jump_to_quick(self, key: str) -> None:
        try:
            path_str = str(self._quick_dirs.get(str(key), self._quick_dirs.get("home", str(Path.home()))))
            self._set_root(path_str)
            for i in range(self.cmb_quick.count()):
                if str(self.cmb_quick.itemData(i) or "") == path_str:
                    self.cmb_quick.setCurrentIndex(i)
                    break
        except Exception:
            pass

    def _on_directory_loaded(self, path_str: str) -> None:
        try:
            if str(path_str or "") != str(self._current_path):
                return
            self.tree.setColumnWidth(0, 280)
        except Exception:
            pass

    # ------------------------------------------------------------------ Preview wiring

    def _wire_preview(self) -> None:
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.chk_loop.toggled.connect(self._on_loop_toggled)

    def _register_preview_source(self) -> None:
        try:
            if self.audio_engine is None:
                return
            from pydaw.audio.preview_player import PreviewPlayer
            self._preview_player = PreviewPlayer()
            if hasattr(self.audio_engine, "add_source"):
                self.audio_engine.add_source(self._preview_player, name=self._preview_name)
            else:
                self.audio_engine.register_pull_source(self._preview_name, self._preview_player.pull)
            try:
                self.audio_engine.ensure_preview_output()
            except Exception:
                pass
        except Exception:
            self._preview_player = None

    def closeEvent(self, event):  # noqa: ANN001
        try:
            if self.audio_engine is not None and hasattr(self.audio_engine, "unregister_pull_source"):
                self.audio_engine.unregister_pull_source(self._preview_name)
        except Exception:
            pass
        return super().closeEvent(event)

    # ------------------------------------------------------------------ UI handlers

    def _on_quick_changed(self, idx: int) -> None:
        try:
            p = self.cmb_quick.currentData()
            if p:
                self._set_root(str(p))
        except Exception:
            pass

    def _on_go_clicked(self) -> None:
        self._set_root(self.path_edit.text().strip() or str(Path.home()))

    def _set_root(self, path_str: str) -> None:
        try:
            p = Path(path_str).expanduser()
            if p.is_file():
                p = p.parent
            if not p.exists():
                return
            self._current_path = str(p)
            self.path_edit.setText(self._current_path)
            self.tree.setRootIndex(self.model.index(self._current_path))
        except Exception:
            pass

    def _on_tree_current_changed(self, current, _prev):  # noqa: ANN001
        try:
            pth = self.model.filePath(current)
            if not pth or not _is_browser_media_file(pth):
                self._selected_path = None
                self._selected_bpm = None
                self.lbl_sel.setText("—")
                self.lbl_bpm.setText("BPM: —")
                return

            self._selected_path = str(pth)
            self.lbl_sel.setText(Path(pth).name)
            if not _is_previewable_audio_file(pth):
                self._selected_bpm = None
                self.lbl_bpm.setText("BPM: —")
                return
            # immediate filename BPM hint
            try:
                from pydaw.audio.bpm_detect import parse_bpm_from_filename
                hb = parse_bpm_from_filename(Path(pth).name)
                if hb:
                    self._selected_bpm = float(hb)
                    self._selected_bpm_conf = 0.2
                    self._selected_bpm_method = "filename"
                    self.lbl_bpm.setText(f"BPM: {hb:.1f}*")
            except Exception:
                pass

            # start background BPM analysis
            self._start_bpm_analysis(pth)
        except Exception:
            pass

    # ------------------------------------------------------------------ BPM analysis

    def _start_bpm_analysis(self, path: str) -> None:
        try:
            self._last_token += 1
            token = self._last_token

            # stop previous worker
            try:
                if self._bpm_worker is not None and self._bpm_worker.isRunning():
                    self._bpm_worker.requestInterruption()
            except Exception:
                pass

            self.lbl_bpm.setText("BPM: …")
            w = _BPMWorker(path)
            self._bpm_worker = w

            def on_finish():
                try:
                    if token != self._last_token:
                        return
                    res = getattr(w, "_result", None)
                    if res and getattr(res, "bpm", None):
                        self._selected_bpm = float(res.bpm)
                        self._selected_bpm_conf = float(getattr(res, "confidence", 0.0) or 0.0)
                        self._selected_bpm_method = str(getattr(res, "method", "") or "")
                        star = "" if self._selected_bpm_method.startswith("essentia") else "*"
                        self.lbl_bpm.setText(f"BPM: {self._selected_bpm:.1f}{star}")
                    else:
                        if self._selected_bpm is not None:
                            self.lbl_bpm.setText(f"BPM: {self._selected_bpm:.1f}*")
                        else:
                            self.lbl_bpm.setText("BPM: —")
                except Exception:
                    self.lbl_bpm.setText("BPM: —")

            w.finished.connect(on_finish)
            w.start()
        except Exception:
            pass

    # ------------------------------------------------------------------ Rendering / playback

    def _project_bpm(self) -> float:
        # Use transport -> project -> fallback
        try:
            if self.transport is not None:
                return float(getattr(self.transport, "bpm", 120.0) or 120.0)
        except Exception:
            pass
        try:
            if self.project_service is not None:
                return float(getattr(self.project_service.ctx.project, "bpm", 120.0) or 120.0)
        except Exception:
            pass
        return 120.0

    def _beats_per_bar(self) -> float:
        try:
            if self.transport is not None and hasattr(self.transport, "beats_per_bar"):
                return float(self.transport.beats_per_bar() or 4.0)
        except Exception:
            pass
        return 4.0

    def _quantized_delay_samples(self, bpm: float, loop: bool) -> int:
        try:
            if self.transport is None:
                return 0
            playing = bool(getattr(self.transport, "playing", False))
            if not playing:
                return 0
            cur = float(getattr(self.transport, "current_beat", 0.0) or 0.0)
            q = self._beats_per_bar() if loop else 1.0
            if q <= 0:
                q = 1.0
            nxt = math.ceil(cur / q) * q
            delay_beats = max(0.0, float(nxt - cur))
            if delay_beats <= 1e-6:
                return 0
            sr = 48000.0
            sec_per_beat = 60.0 / float(bpm or 120.0)
            return int(round(delay_beats * sec_per_beat * sr))
        except Exception:
            return 0

    def _on_loop_toggled(self, enabled: bool) -> None:
        try:
            if self._preview_player is not None:
                self._preview_player.set_loop(bool(enabled))
        except Exception:
            pass

    def _on_play_clicked(self) -> None:
        path = self._selected_path
        if not path or not _is_previewable_audio_file(path):
            return
        if self._preview_player is None:
            return

        mode = "sync" if self.btn_sync.isChecked() else "raw"
        loop = bool(self.chk_loop.isChecked())
        bpm = self._project_bpm()
        bpb = self._beats_per_bar()
        source_hint = self._selected_bpm

        # Try fast preview-cache hit (no render thread)
        cache = getattr(self, "_preview_cache", None)
        cache_key = None
        if cache is not None:
            try:
                from pydaw.audio.bpm_detect import parse_bpm_from_filename
                hint2 = source_hint if source_hint else parse_bpm_from_filename(Path(path).name)
                # attempt cache lookup with best available hint
                cache_key = cache.make_key(path, mode=mode, loop=loop, project_bpm=bpm, beats_per_bar=bpb, source_bpm_hint=hint2, sr=48000)
                hit = cache.get(cache_key)
                if hit is None and hint2 is not None and source_hint is None:
                    # also try key without hint (legacy)
                    cache_key2 = cache.make_key(path, mode=mode, loop=loop, project_bpm=bpm, beats_per_bar=bpb, source_bpm_hint=None, sr=48000)
                    hit = cache.get(cache_key2)
                    if hit is not None:
                        cache_key = cache_key2
                if hit is not None:
                    buf, sr, source_bpm = hit
                    if source_bpm and (self._selected_bpm is None or abs(float(source_bpm) - float(self._selected_bpm or 0.0)) > 0.5):
                        self._selected_bpm = float(source_bpm)
                        self.lbl_bpm.setText(f"BPM: {self._selected_bpm:.1f}*")
                    try:
                        self._preview_player.set_buffer(buf, sr=int(sr), loop=loop)
                    except Exception:
                        pass
                    delay = 0
                    if mode == "sync":
                        delay = self._quantized_delay_samples(bpm=bpm, loop=loop)
                    self._preview_player.start(delay_samples=delay, loop=loop)
                    return
            except Exception:
                pass

        # stop previous render worker (best-effort)
        try:
            if self._render_worker is not None and self._render_worker.isRunning():
                self._render_worker.requestInterruption()
        except Exception:
            pass

        self.btn_play.setText("… Rendering")
        self.btn_play.setEnabled(False)

        w = _RenderWorker(path, mode=mode, loop=loop, project_bpm=bpm, beats_per_bar=bpb, source_bpm_hint=source_hint)
        self._render_worker = w
        self._last_token += 1
        token = self._last_token

        def on_finish():
            try:
                if token != self._last_token:
                    return
                r = getattr(w, "_render", None)
                if not r:
                    self.btn_play.setText("▶ Preview")
                    self.btn_play.setEnabled(True)
                    return
                buf, sr, source_bpm = r
                # update bpm label if we learned it
                if source_bpm and (self._selected_bpm is None or abs(float(source_bpm) - float(self._selected_bpm or 0.0)) > 0.5):
                    self._selected_bpm = float(source_bpm)
                    self.lbl_bpm.setText(f"BPM: {self._selected_bpm:.1f}*")
                # store in preview cache (LRU)
                try:
                    cache = getattr(self, "_preview_cache", None)
                    if cache is not None:
                        # store under the computed cache_key (if any) and also under the final bpm-hint key
                        k = cache_key
                        if k is None:
                            k = cache.make_key(path, mode=mode, loop=loop, project_bpm=bpm, beats_per_bar=bpb, source_bpm_hint=source_hint, sr=48000)
                        cache.put(k, buf, int(sr), source_bpm)
                        if source_bpm and not source_hint and mode == "sync":
                            k2 = cache.make_key(path, mode=mode, loop=loop, project_bpm=bpm, beats_per_bar=bpb, source_bpm_hint=float(source_bpm), sr=48000)
                            if k2 != k:
                                cache.put(k2, buf, int(sr), source_bpm)
                except Exception:
                    pass

                # set buffer + start
                try:
                    self._preview_player.set_buffer(buf, sr=int(sr), loop=loop)
                except Exception:
                    pass
                delay = 0
                if mode == "sync":
                    delay = self._quantized_delay_samples(bpm=bpm, loop=loop)
                self._preview_player.start(delay_samples=delay, loop=loop)
            finally:
                self.btn_play.setText("▶ Preview")
                self.btn_play.setEnabled(True)

        w.finished.connect(on_finish)
        w.start()

    def _on_stop_clicked(self) -> None:
        try:
            if self._preview_player is not None:
                self._preview_player.stop()
        except Exception:
            pass
