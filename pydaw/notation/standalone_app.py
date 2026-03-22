"""Standalone notation preview.

This is intentionally isolated from the DAW process so that any
Qt/graphics/scene issues inside the notation prototype cannot freeze
the main application.

It is a WIP utility.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PyDAW notation preview (standalone)")
    parser.add_argument("--project", default=None, help="Project path (optional)")
    ns = parser.parse_args(argv)

    app = QApplication(sys.argv)

    try:
        # Import *inside* the try so we can show a helpful dialog on failure.
        from pydaw.notation.gui.score_view import ScoreView  # noqa: WPS433
        from PyQt6.QtWidgets import QMainWindow

        w = QMainWindow()
        w.setWindowTitle("PyDAW — Notation Preview (WIP)")
        view = ScoreView()
        w.setCentralWidget(view)

        if ns.project:
            # Placeholder: project integration comes later.
            w.setWindowTitle(f"PyDAW — Notation Preview (WIP) — {os.path.basename(ns.project)}")

        w.resize(1200, 800)
        w.show()
        return app.exec()
    except Exception:
        tb = traceback.format_exc()
        # Print for terminal users.
        print(tb, file=sys.stderr)
        QMessageBox.critical(
            None,
            "Notation Preview — Fehler",
            "Die Notation-Vorschau konnte nicht gestartet werden.\n\n"
            "Details (Traceback) wurden in die Konsole ausgegeben.",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
