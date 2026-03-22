"""
Bounce Progress Dialog — Echtzeit-Fortschrittsanzeige mit Cyan-Glow.

v0.0.20.690 — Zeigt einen animierten Fortschrittsbalken während
Bounce-in-Place / Freeze / Export Operationen.

Usage:
    dlg = BounceProgressDialog(parent, title="Bounce in Place")
    dlg.show()
    dlg.set_progress(0.5, "Rendering Track 1...")
    dlg.close()
"""

from __future__ import annotations

import time
import logging
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication,
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont
except ImportError:
    QDialog = None  # type: ignore

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Cyan-Glow Stylesheet
# ═══════════════════════════════════════════════════════════════════════════

_CYAN = "#00e5ff"
_CYAN_DIM = "#007c8a"
_CYAN_GLOW = "#00fffb"
_BG_DARK = "#181c24"
_BG_CARD = "#1e2330"
_TEXT = "#e0e8f0"
_TEXT_DIM = "#8090a8"

BOUNCE_DIALOG_STYLE = f"""
QDialog {{
    background: {_BG_DARK};
    border: 1px solid {_CYAN_DIM};
    border-radius: 12px;
}}

QLabel#title_label {{
    color: {_CYAN};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 0;
}}

QLabel#status_label {{
    color: {_TEXT};
    font-size: 12px;
    padding: 2px 0;
}}

QLabel#time_label {{
    color: {_TEXT_DIM};
    font-size: 11px;
    padding: 1px 0;
}}

QProgressBar {{
    background: {_BG_CARD};
    border: 1px solid {_CYAN_DIM};
    border-radius: 8px;
    height: 22px;
    text-align: center;
    color: {_TEXT};
    font-size: 11px;
    font-weight: 600;
}}

QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0.0 {_CYAN_DIM},
        stop:0.3 {_CYAN},
        stop:0.7 {_CYAN},
        stop:1.0 {_CYAN_GLOW}
    );
    border-radius: 7px;
}}
"""


class BounceProgressDialog(QDialog if QDialog is not None else object):
    """Modaler Bounce-Fortschrittsdialog mit Cyan-Glow-Styling.

    Features:
    - Animierter Cyan-Gradient Fortschrittsbalken
    - Echtzeit Status-Text + verstrichene Zeit
    - Glow-Puls Effekt via QTimer
    - Nicht-blockierend: pumpt Qt Events bei jedem set_progress()
    """

    def __init__(self, parent=None, title: str = "Bounce in Place"):
        if QDialog is None:
            return
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(460, 160)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(BOUNCE_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)

        # Title
        self._title = QLabel(f"⚡  {title}")
        self._title.setObjectName("title_label")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 10000)
        self._bar.setValue(0)
        self._bar.setFormat("%p%")
        layout.addWidget(self._bar)

        # Status text
        self._status = QLabel("Vorbereitung …")
        self._status.setObjectName("status_label")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # Time label
        self._time_label = QLabel("")
        self._time_label.setObjectName("time_label")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._time_label)

        self._start_time: float = time.monotonic()
        self._last_pump: float = 0.0

        # Glow pulse animation
        self._glow_phase: int = 0
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._pulse_glow)
        self._glow_timer.start(60)  # ~16fps pulse

    def set_progress(self, fraction: float, status: str = ""):
        """Update progress (0.0–1.0) and optional status text."""
        if QDialog is None:
            return
        frac = max(0.0, min(1.0, float(fraction)))
        self._bar.setValue(int(frac * 10000))

        if status:
            self._status.setText(status)

        # Elapsed time
        elapsed = time.monotonic() - self._start_time
        if elapsed > 0.5:
            if frac > 0.01:
                eta = (elapsed / frac) * (1.0 - frac)
                self._time_label.setText(
                    f"{elapsed:.1f}s  ·  noch ~{eta:.1f}s"
                )
            else:
                self._time_label.setText(f"{elapsed:.1f}s")

        # Pump Qt events (max 30 Hz to avoid overhead)
        now = time.monotonic()
        if now - self._last_pump > 0.033:
            self._last_pump = now
            try:
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
            except Exception:
                pass

    def set_status(self, text: str):
        """Update only the status text."""
        if QDialog is None:
            return
        self._status.setText(text)

    def finish(self, message: str = "Fertig!"):
        """Set progress to 100% and show finish message."""
        self.set_progress(1.0, message)
        elapsed = time.monotonic() - self._start_time
        self._time_label.setText(f"✓ {elapsed:.1f}s")
        # Pump one last time so the user sees 100%
        try:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _pulse_glow(self):
        """Animate the glow effect on the progress bar border."""
        self._glow_phase = (self._glow_phase + 1) % 60
        # Oscillate border brightness
        t = self._glow_phase / 60.0
        import math
        bright = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * 2.0 * math.pi))
        r = int(0 * bright)
        g = int(229 * bright)
        b = int(255 * bright)
        glow_color = f"rgb({r},{g},{b})"
        # Also pulse the shadow glow
        shadow_alpha = int(80 + 120 * bright)
        self._bar.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {glow_color}; }}"
        )

    def closeEvent(self, event):
        try:
            self._glow_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Create + show dialog (convenience for render methods)
# ═══════════════════════════════════════════════════════════════════════════

def create_bounce_progress(parent=None, title: str = "Bounce in Place") -> Optional[BounceProgressDialog]:
    """Create and show a bounce progress dialog. Returns None if no Qt app."""
    if QDialog is None:
        return None
    try:
        app = QApplication.instance()
        if app is None:
            return None
        dlg = BounceProgressDialog(parent, title=title)
        dlg.show()
        app.processEvents()
        return dlg
    except Exception:
        return None
