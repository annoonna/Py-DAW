"""Workbook dialog: shows TEAM docs inside the app.

Menu: Hilfe -> Arbeitsmappe (F1)

Ziel:
- Team-Workflow und Projekt-Dokumentation **im Programm** auffindbar machen.
- Defensive Implementierung: fehlende Dateien/Ordner dürfen niemals crashen.

Hinweis:
- PROJECT_DOCS Struktur hat historisch zwei Session-Ordner:
  - PROJECT_DOCS/sessions
  - PROJECT_DOCS/progress/sessions
  Das Dialog-Fenster sucht in beiden.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# -----------------------------
# Helpers
# -----------------------------


def _clean_action_text(text: str) -> str:
    """Normalize QAction text for display (remove '&' accelerators)."""
    try:
        return (text or "").replace("&", "").strip()
    except Exception:
        return str(text)


def _keyseq_to_text(seq: QKeySequence) -> str:
    try:
        return seq.toString(QKeySequence.SequenceFormat.NativeText)
    except Exception:
        try:
            return seq.toString()
        except Exception:
            return str(seq)


def _collect_action_shortcuts(source: QWidget) -> list[tuple[str, str]]:
    """Collect QAction shortcuts from a widget subtree.

    Returns: List of (shortcut_text, action_text)
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if source is None:
        return out

    try:
        actions = list(source.findChildren(QAction))
    except Exception:
        actions = []

    # Include direct actions attached to the widget as well.
    try:
        actions.extend(list(source.actions() or []))
    except Exception:
        pass

    for a in actions:
        try:
            txt = _clean_action_text(a.text())
            if not txt:
                continue

            seqs: list[str] = []
            try:
                for s in list(a.shortcuts() or []):
                    if s is None:
                        continue
                    st = _keyseq_to_text(s)
                    if st:
                        seqs.append(st)
            except Exception:
                pass

            # Fallback: single shortcut()
            if not seqs:
                try:
                    s = a.shortcut()
                    st = _keyseq_to_text(s) if s else ""
                    if st:
                        seqs = [st]
                except Exception:
                    pass

            if not seqs:
                continue

            shortcut_text = " / ".join(dict.fromkeys(seqs))
            key = (shortcut_text, txt)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        except Exception:
            continue

    out.sort(key=lambda x: (x[0], x[1]))
    return out


def _collect_qshortcuts(source: QWidget) -> list[tuple[str, str]]:
    """Collect QShortcut objects from a widget subtree.

    Returns: List of (shortcut_text, description)
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if source is None:
        return out

    try:
        shortcuts = list(source.findChildren(QShortcut))
    except Exception:
        shortcuts = []

    for sc in shortcuts:
        try:
            seq = getattr(sc, "key", None)
            if callable(seq):
                seq = seq()
            if seq is None:
                continue
            st = _keyseq_to_text(seq)
            if not st:
                continue

            desc = ""
            try:
                desc = str(sc.property("pydaw_desc") or "").strip()
            except Exception:
                desc = ""
            if not desc:
                try:
                    desc = str(sc.objectName() or "").strip()
                except Exception:
                    desc = ""
            if not desc:
                desc = "(Shortcut ohne Beschreibung im Code)"

            key = (st, desc)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        except Exception:
            continue

    out.sort(key=lambda x: (x[0], x[1]))
    return out

def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"(Konnte Datei nicht lesen: {path}\n{e})"


def _search_upwards_for_project_root(start: Path, max_depth: int = 6) -> Optional[Path]:
    """Find project root by looking for PROJECT_DOCS and/or VERSION/README_TEAM."""
    try:
        cur = start.resolve()
    except Exception:
        cur = start

    for _ in range(max_depth + 1):
        try:
            if (cur / "PROJECT_DOCS").is_dir():
                return cur
            # fallback signals
            if (cur / "README_TEAM.md").is_file() and (cur / "pydaw").is_dir():
                return cur
            if (cur / "VERSION").is_file() and (cur / "pydaw").is_dir():
                return cur
        except Exception:
            pass

        try:
            if cur.parent == cur:
                break
            cur = cur.parent
        except Exception:
            break

    return None


def _find_project_root() -> Optional[Path]:
    """Try hard to locate the project root.

    Priority:
    1) current working directory (or one of its parents)
    2) repository root (relative to this file)
    """
    # 1) CWD (+ parents)
    try:
        root = _search_upwards_for_project_root(Path.cwd())
        if root:
            return root
    except Exception:
        pass

    # 2) this module location
    try:
        # pydaw/ui/workbook_dialog.py -> pydaw/ui -> pydaw -> project root
        here_root = Path(__file__).resolve().parents[2]
        root = _search_upwards_for_project_root(here_root)
        if root:
            return root
    except Exception:
        pass

    return None


def _find_project_docs(project_root: Optional[Path]) -> Optional[Path]:
    if not project_root:
        return None
    try:
        docs = project_root / "PROJECT_DOCS"
        if docs.is_dir():
            return docs
    except Exception:
        pass
    return None


def _iter_session_dirs(docs_root: Path) -> list[Path]:
    out: list[Path] = []
    for p in (docs_root / "sessions", docs_root / "progress" / "sessions"):
        try:
            if p.is_dir():
                out.append(p)
        except Exception:
            pass
    return out


def _resolve_latest_pointer(pointer_file: Path) -> Optional[Path]:
    """Resolve LATEST.md if it contains a filename on the first line."""
    try:
        first = pointer_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if not first:
            return None
        name = first[0].strip()
        if not name:
            return None
        candidate = (pointer_file.parent / name).resolve()
        if candidate.is_file():
            return candidate
    except Exception:
        return None
    return None


def _latest_session_file(docs_root: Path) -> Optional[Path]:
    """Pick the best 'latest session' file.

    Preference order:
    1) PROJECT_DOCS/sessions/LATEST.md -> referenced file (if valid)
    2) PROJECT_DOCS/progress/sessions newest by mtime
    3) PROJECT_DOCS/sessions newest by mtime
    """
    # 1) sessions/LATEST.md pointer
    try:
        ptr = docs_root / "sessions" / "LATEST.md"
        if ptr.is_file():
            resolved = _resolve_latest_pointer(ptr)
            if resolved:
                return resolved
            # if not resolvable, still show the pointer file
            return ptr
    except Exception:
        pass

    # 2/3) newest by mtime across both session dirs
    candidates: list[Path] = []
    for d in _iter_session_dirs(docs_root):
        try:
            for p in d.glob("*.md"):
                if p.is_file() and p.name.lower() != "latest.md":
                    candidates.append(p)
        except Exception:
            pass

    if not candidates:
        return None

    try:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]
    except Exception:
        return candidates[0]


def _extract_next_steps(todo_text: str, max_lines: int = 80) -> str:
    """Extract a compact list of AVAILABLE tasks from TODO.md.

    This is intentionally heuristic (Markdown formatting differs over time).
    """
    lines = (todo_text or "").splitlines()
    out: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        block = "\n".join(current).strip()
        if block and ("Assignee:" in block and "[ ] AVAILABLE" in block):
            out.append(block)
        current = []

    for ln in lines:
        if ln.strip().startswith("### "):
            flush()
            current = [ln]
        elif current:
            current.append(ln)
        if len(out) >= 10:
            break

    flush()

    if not out:
        return "\n".join(lines[:max_lines])

    header = "# Nächste Schritte (AVAILABLE Tasks)\n\n"
    return header + "\n\n---\n\n".join(out)


def _open_path(path: Path) -> None:
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except Exception:
        pass


@dataclass
class _Tab:
    title: str
    widget: QWidget
    refresh: Callable[[], None]
    get_open_path: Callable[[], Optional[Path]]


# -----------------------------
# Dialog
# -----------------------------


class WorkbookDialog(QDialog):
    """QDialog that shows the team's project workbook."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arbeitsmappe")
        self.setMinimumSize(1020, 740)

        self._root: Optional[Path] = None
        self._docs: Optional[Path] = None

        # Top bar
        top = QHBoxLayout()
        self._lbl_path = QLabel()
        self._lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self._lbl_path, 1)

        self._btn_open_folder = QPushButton("Ordner öffnen")
        self._btn_open_folder.clicked.connect(self._open_docs_folder)
        top.addWidget(self._btn_open_folder)

        self._btn_open_file = QPushButton("Datei öffnen")
        self._btn_open_file.clicked.connect(self._open_current_file)
        top.addWidget(self._btn_open_file)

        btn_refresh = QPushButton("↻ Aktualisieren")
        btn_refresh.clicked.connect(self.refresh_all)
        top.addWidget(btn_refresh)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._update_open_buttons)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(12, 12, 12, 12)
        root_lay.setSpacing(10)
        root_lay.addLayout(top)
        root_lay.addWidget(self._tabs, 1)

        self._tab_defs: list[_Tab] = []
        self._last_session_path: Optional[Path] = None

        self._build_tabs()
        self.refresh_all()

    # -------------------------
    # UI Build
    # -------------------------

    def _mk_text_tab(self, title: str) -> tuple[QWidget, QTextEdit]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(te, 1)
        self._tabs.addTab(w, title)
        return w, te

    def _build_tabs(self) -> None:
        # START
        w_start, te_start = self._mk_text_tab("Start")

        def refresh_start() -> None:
            if not self._root or not self._docs:
                te_start.setPlainText(
                    "PROJECT_DOCS nicht gefunden.\n\n"
                    "Tipp: Starte die App im entpackten Projektordner (dort wo PROJECT_DOCS/ liegt).\n"
                    "Oder öffne ein Projekt aus diesem Ordner, dann Refresh klicken."
                )
                return

            parts: list[str] = []
            parts.append("# Arbeitsmappe (In-App)\n")
            parts.append(f"Projekt-Root: {self._root}\n")
            parts.append(f"PROJECT_DOCS:  {self._docs}\n")
            parts.append("\n---\n")

            # Progress LATEST
            pr_latest = self._docs / "progress" / "LATEST.md"
            if pr_latest.is_file():
                parts.append("\n## PROJECT_DOCS/progress/LATEST.md\n")
                parts.append(_safe_read_text(pr_latest))
            else:
                parts.append("\n## PROJECT_DOCS/progress/LATEST.md\n(Fehlt)\n")

            # Sessions LATEST pointer + resolved session
            parts.append("\n---\n\n## Letzte Session\n")
            latest_sess = _latest_session_file(self._docs)
            if latest_sess and latest_sess.is_file():
                parts.append(f"(Quelle: {latest_sess})\n\n")
                parts.append(_safe_read_text(latest_sess))
            else:
                parts.append("Keine Session-Logs gefunden.\n")

            te_start.setPlainText("\n".join(parts))

        self._tab_defs.append(
            _Tab(
                "Start",
                w_start,
                refresh_start,
                get_open_path=lambda: (self._docs / "progress" / "LATEST.md") if self._docs else None,
            )
        )

        # README_TEAM
        w_readme, te_readme = self._mk_text_tab("README_TEAM")

        def refresh_readme() -> None:
            if not self._root:
                te_readme.setPlainText("Projekt-Root nicht gefunden.")
                return
            te_readme.setPlainText(_safe_read_text(self._root / "README_TEAM.md"))

        self._tab_defs.append(
            _Tab("README_TEAM", w_readme, refresh_readme, get_open_path=lambda: (self._root / "README_TEAM.md") if self._root else None)
        )

        # MASTER_PLAN
        w_master, te_master = self._mk_text_tab("MASTER_PLAN")

        def refresh_master() -> None:
            if not self._docs:
                te_master.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            te_master.setPlainText(_safe_read_text(self._docs / "plans" / "MASTER_PLAN.md"))

        self._tab_defs.append(
            _Tab(
                "MASTER_PLAN",
                w_master,
                refresh_master,
                get_open_path=lambda: (self._docs / "plans" / "MASTER_PLAN.md") if self._docs else None,
            )
        )

        # VISION
        w_vision, te_vision = self._mk_text_tab("VISION")

        def refresh_vision() -> None:
            if not self._docs:
                te_vision.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            te_vision.setPlainText(_safe_read_text(self._docs / "plans" / "VISION.md"))

        self._tab_defs.append(
            _Tab(
                "VISION",
                w_vision,
                refresh_vision,
                get_open_path=lambda: (self._docs / "plans" / "VISION.md") if self._docs else None,
            )
        )

        # TODO
        w_todo, te_todo = self._mk_text_tab("TODO")

        def refresh_todo() -> None:
            if not self._docs:
                te_todo.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            te_todo.setPlainText(_safe_read_text(self._docs / "progress" / "TODO.md"))

        self._tab_defs.append(
            _Tab(
                "TODO",
                w_todo,
                refresh_todo,
                get_open_path=lambda: (self._docs / "progress" / "TODO.md") if self._docs else None,
            )
        )

        # DONE
        w_done, te_done = self._mk_text_tab("DONE")

        def refresh_done() -> None:
            if not self._docs:
                te_done.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            te_done.setPlainText(_safe_read_text(self._docs / "progress" / "DONE.md"))

        self._tab_defs.append(
            _Tab(
                "DONE",
                w_done,
                refresh_done,
                get_open_path=lambda: (self._docs / "progress" / "DONE.md") if self._docs else None,
            )
        )

        # Progress LATEST
        w_pl, te_pl = self._mk_text_tab("Progress: LATEST")

        def refresh_pl() -> None:
            if not self._docs:
                te_pl.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            te_pl.setPlainText(_safe_read_text(self._docs / "progress" / "LATEST.md"))

        self._tab_defs.append(
            _Tab(
                "Progress: LATEST",
                w_pl,
                refresh_pl,
                get_open_path=lambda: (self._docs / "progress" / "LATEST.md") if self._docs else None,
            )
        )

        # Letzte Session
        w_sess, te_sess = self._mk_text_tab("Letzte Session")

        def refresh_sess() -> None:
            self._last_session_path = None
            if not self._docs:
                te_sess.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            latest = _latest_session_file(self._docs)
            if not latest:
                te_sess.setPlainText("Keine Session-Logs gefunden in PROJECT_DOCS/(sessions|progress/sessions).")
                return
            self._last_session_path = latest
            te_sess.setPlainText(_safe_read_text(latest))

        self._tab_defs.append(
            _Tab(
                "Letzte Session",
                w_sess,
                refresh_sess,
                get_open_path=lambda: self._last_session_path,
            )
        )

        # Next steps
        w_next, te_next = self._mk_text_tab("Nächste Schritte")

        def refresh_next() -> None:
            if not self._docs:
                te_next.setPlainText("PROJECT_DOCS nicht gefunden.")
                return
            todo_path = self._docs / "progress" / "TODO.md"
            te_next.setPlainText(_extract_next_steps(_safe_read_text(todo_path)))

        self._tab_defs.append(_Tab("Nächste Schritte", w_next, refresh_next, get_open_path=lambda: None))

        # Shortcuts & Commands (embedded)
        w_shortcuts, te_shortcuts = self._mk_text_tab("Shortcuts & Befehle")

        def refresh_shortcuts() -> None:
            te_shortcuts.setPlainText(self._build_shortcuts_document())

        self._tab_defs.append(_Tab("Shortcuts & Befehle", w_shortcuts, refresh_shortcuts, get_open_path=lambda: None))

    # -------------------------
    # Actions
    # -------------------------

    def _open_docs_folder(self) -> None:
        if self._docs and self._docs.is_dir():
            _open_path(self._docs)

    def _open_current_file(self) -> None:
        idx = self._tabs.currentIndex()
        if idx < 0 or idx >= len(self._tab_defs):
            return
        try:
            path = self._tab_defs[idx].get_open_path()
        except Exception:
            path = None
        if path and path.exists():
            _open_path(path)

    def _update_open_buttons(self) -> None:
        # Enable/disable open buttons based on availability.
        has_docs = bool(self._docs and self._docs.is_dir())
        self._btn_open_folder.setEnabled(has_docs)

        idx = self._tabs.currentIndex()
        path: Optional[Path] = None
        if 0 <= idx < len(self._tab_defs):
            try:
                path = self._tab_defs[idx].get_open_path()
            except Exception:
                path = None
        self._btn_open_file.setEnabled(bool(path and path.exists()))

    # -------------------------
    # Refresh
    # -------------------------

    def refresh_all(self) -> None:
        # Re-locate root/docs each time (user may start the app elsewhere).
        self._root = _find_project_root()
        self._docs = _find_project_docs(self._root)

        if self._root and self._docs:
            self._lbl_path.setText(f"Projekt: {self._root}    |    PROJECT_DOCS: {self._docs}")
        elif self._root:
            self._lbl_path.setText(f"Projekt: {self._root}    |    PROJECT_DOCS: (nicht gefunden)")
        else:
            self._lbl_path.setText("PROJECT_DOCS: (nicht gefunden) – starte die App bitte im Projektordner")

        for t in self._tab_defs:
            try:
                t.refresh()
            except Exception:
                pass

        self._update_open_buttons()


    def _build_shortcuts_document(self) -> str:
        """Build a single help text that lists ALL known shortcuts.

        Strategy:
        - Extract global QActions (menu + commands) from the MainWindow subtree.
        - Extract QShortcut objects (e.g., Ctrl+Tab, B toggle browser) incl. descriptions.
        - Append a curated list for context-sensitive keyPressEvent/wheelEvent shortcuts.

        Must never crash.
        """
        parts: list[str] = []
        parts.append("# 🎹 Tastenkombinationen (Hilfe → Arbeitsmappe)\n")
        parts.append(
            "Hinweis: Manche Shortcuts sind **kontextabhängig** (nur wenn das entsprechende Panel Fokus hat).\n"
            "Diese Liste kombiniert **automatisch** aus dem Programm extrahierte Shortcuts (Menüs/QActions/QShortcut)\n"
            "und eine **kuratierte** Referenz für Editor-Shortcuts (keyPress/wheel).\n"
        )

        # Prefer the dialog parent (MainWindow). Fallback to the active window.
        source = None
        try:
            source = self.parentWidget()
        except Exception:
            source = None

        try:
            if source is None:
                from PyQt6.QtWidgets import QApplication

                source = QApplication.activeWindow()
        except Exception:
            source = None

        # 1) Global actions
        parts.append("\n---\n\n## ✅ Globale Shortcuts (aus Menüs/Actions extrahiert)\n")
        try:
            actions = _collect_action_shortcuts(source) if source is not None else []
        except Exception:
            actions = []

        if actions:
            for sc, txt in actions:
                parts.append(f"- {sc:<18} — {txt}")
        else:
            parts.append("(Konnte keine QAction-Shortcuts automatisch sammeln.)")

        # 2) QShortcut objects
        parts.append("\n\n## ⚡ Zusätzliche Shortcuts (QShortcut)\n")
        try:
            qs = _collect_qshortcuts(source) if source is not None else []
        except Exception:
            qs = []

        if qs:
            for sc, desc in qs:
                parts.append(f"- {sc:<18} — {desc}")
        else:
            parts.append("(Keine QShortcut-Objekte gefunden oder keine Metadaten verfügbar.)")

        # 3) Curated context shortcuts
        parts.append("\n\n---\n\n## 🎛 Kontextabhängig (wenn Panel Fokus hat)\n")
        parts.append(_CONTEXT_SHORTCUTS_CONTENT.strip())
        parts.append("\n\n---\n\n## 🧩 Hinweise\n")
        parts.append(
            "- **Ctrl+Tab / Ctrl+Shift+Tab**: Projekt-Tabs wechseln.\n"
            "- **B**: Browser ein/aus (wenn Hauptfenster aktiv).\n"
            "- Editor-spezifische Shortcuts funktionieren nur, wenn das jeweilige Editor-Widget den Fokus hat.\n"
            "- Wenn du einen Shortcut vermisst: such im Code nach `setShortcut(` / `QShortcut(` / `keyPressEvent`.\n"
        )

        return "\n".join(parts)


def build_workbook_action(parent, on_triggered) -> QAction:
    a = QAction("Arbeitsmappe…", parent)
    a.setShortcut("F1")
    a.triggered.connect(on_triggered)
    return a


# Curated context shortcuts (keyPressEvent / wheelEvent etc.).
# The global shortcuts are extracted dynamically in `_build_shortcuts_document()`.
_CONTEXT_SHORTCUTS_CONTENT = """
### 🧱 DevicePanel (Chain / Device-Ansicht)

- Esc — Ansicht zurücksetzen (Zone-Fokus / ◎ Fokus / Collapse-Zustände -> Normalansicht)
- Doppelklick auf Device-Card — Card ein-/ausklappen
- Klick auf ▾ / ▸ im Card-Header — Card ein-/ausklappen

**Header-Buttons (Maus / UI-Befehle):**
- ◪ — Inaktive Devices einklappen
- ▾▾ — Alle Device-Cards einklappen
- ▸▸ — Alle Device-Cards ausklappen
- ◎ — Fokusansicht (nur eine Card offen; Fallback: Instrument)
- N / I / A — Nur NOTE-FX / INSTRUMENT / AUDIO-FX offen
- ↺ — Reset (gleich wie `Esc`)

Hinweis: **N / I / A / ◎ / ↺** sind hier standardmäßig **Header-Buttons** (keine globalen Tastenkürzel).


### 🧭 Arranger (Haupt-Ansicht)

- V — Zeiger / Auswahl
- D — Draw / Zeichnen
- E — Erase / Löschen
- K — Knife / Schneiden

- Ctrl+C — Clips kopieren
- Ctrl+X — Clips ausschneiden
- Ctrl+V — Clips einfügen

- Ctrl+D — Duplizieren
- Ctrl+J — Join (ausgewählte Clips verbinden)
- Ctrl+A — Alles auswählen

- Delete / Backspace — Auswahl löschen
- Ctrl+Z — Undo
- Ctrl+Y / Ctrl+Shift+Z — Redo

- Mausrad — Timeline horizontal zoomen
- Shift+Mausrad — Track-Höhe zoomen
- Alt+Mausrad — Scrollen (an Parent weitergeben)


### 🎹 Piano Roll

- Delete / Backspace — Ausgewählte Noten löschen
- Ctrl+D — Duplizieren

- Mausrad — Vertikal scrollen
- Shift+Mausrad — Horizontal zoomen
- Ctrl+Mausrad — Vertikal zoomen
- Alt+Mausrad — Scrollen (an Parent weitergeben)


### 📝 Notation

**Werkzeuge:**
- D — Draw (Noten setzen)
- S — Select (Noten auswählen)
- E — Erase (Noten löschen)

**Noten setzen (Draw-Modus):**
- Klick — Natürliche Note setzen (C, D, E, F, G, A, H)
- Shift+Klick — Kreuz-Note setzen (Cis, Dis, Fis, Gis, Ais)
- Alt+Klick — Be-Note setzen (Des, Es, Ges, As, B)
- Palette ♯ / ♭ — Vorzeichen dauerhaft aktivieren (nochmal klicken = deaktivieren)

**Bearbeiten:**
- Ctrl+C / Ctrl+X / Ctrl+V — Copy / Cut / Paste
- Delete / Backspace — Löschen
- Ctrl+Z — Undo
- Ctrl+Y / Ctrl+Shift+Z — Redo

**Zoom & Scrollen:**
- Ctrl+0 — Zoom Reset
- Ctrl++ / Ctrl+- — X-Zoom in/out
- + / - Buttons — Zoom in/out (Toolbar)
- Mausrad — Vertikal scrollen
- Shift+Mausrad — Horizontal scrollen
- Ctrl+Mausrad — X-Zoom (Zeit-Achse)
- Ctrl+Shift+Mausrad — Y-Zoom (Notenzeilen-Höhe)

**Kontextmenü:**
- Rechtsklick auf leere Fläche — Kontextmenü mit allen Notations-Symbolen
- Rechtsklick auf Note — Note löschen
- Ctrl+Rechtsklick — Kontextmenü erzwingen (auch auf Noten)

**Schlüssel:**
- Klick auf Schlüssel-Symbol — Schlüssel-Dialog öffnen
- 𝄞 Button (Toolbar) — Schlüssel-Dialog öffnen


### 🎼 Notation-Palette

- Alt+1 .. Alt+7 — Notenwert setzen (1/1 .. 1/64)
- Alt+. — Punktierung an/aus
- Alt+R — Pause-Modus an/aus


### 🔊 Audio-Editor (Event-Editor)

- Ctrl+Mausrad — Horizontal zoomen
- Mittlere Maustaste ziehen — Pan / Verschieben
- Knife-Tool + Shift — Schneiden ohne Grid-Snap


### 🎛 Mixer

- Delete / Backspace — Ausgewählten Track entfernen
"""
