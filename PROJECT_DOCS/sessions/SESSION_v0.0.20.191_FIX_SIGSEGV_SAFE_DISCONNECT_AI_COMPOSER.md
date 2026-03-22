# SESSION v0.0.20.191 — Fix: SIGSEGV (QTimer/Slot) + Signal.disconnect + AI Composer Note‑FX

**Datum:** 2026-03-02  
**Assignee:** GPT-5.2 Thinking (ChatGPT)

## 1) User-Report

1. **Crash / SIGSEGV** beim Start bzw. kurz nach Projektöffnung.
   - GDB zeigte: `PyQtSlot::call → QTimer::timeout → sipQTimer::timerEvent`.
2. Zusätzlich extreme Spam-Logs: `MainWindow._on_project_opened ...` sehr oft.

## 2) Root Cause (tiefen Analyse)

### A) DevicePanel: deleteLater + pending singleShot

Seit v0.0.20.190 wurde das *Zombie-Fenster* Problem (Top-Level Popouts durch `setParent(None)`) durch
ein **Widget-Stash** + `deleteLater()` behoben.

Problem: In DevicePanel/DeviceCards gibt es mehrere `QTimer.singleShot(0, ...)` Callbacks
(z.B. *scroll into view*, *title elide*, *SF2 apply deferred*).

Wenn eine Card während eines Rebuilds per `deleteLater()` entsorgt wird, können noch 0ms-Callbacks
im Eventloop stehen, die danach auf **SIP-deleted** Wrapper zugreifen → PyQt6 kann dabei
**hart segfaulten**.

### B) Qt-Hardening: connect-wrapping bricht disconnect

`pydaw/ui/qt_hardening.py` wrappt Slots in safe try/except.
Dadurch wird bei `signal.connect(fn)` faktisch **der Wrapper** verbunden.

Code, der später `signal.disconnect(fn)` aufruft (z.B. "_once" Pattern), disconnectet dann nicht
mehr korrekt, weil `fn != wrapper(fn)`.

Das kann zu *dauerhaften Once-Handlern* führen und dadurch zu Re-Entrancy/Loops (z.B. mehrfaches
Projekt-open / mehrfaches `_on_project_opened`).

## 3) Fixes (oberste Direktive: nichts kaputt)

### A) Anti-SIGSEGV Guard für SIP-deleted Widgets

- `pydaw/ui/device_panel.py`
  - eingeführt: `_qt_is_deleted(obj)` (PyQt6.sip / sip)
  - `DevicePanel._queue_scroll_card_into_view` nutzt weakref + guard
  - `DevicePanel._scroll_card_into_view` guardt deleted cards
  - `_stash_widget(delete=True)` ruft `deleteLater()` **deferred** via `QTimer.singleShot(0, ...)` auf
  - `DeviceCard._update_title_elide` und `SoundFontWidget._apply_sf2_deferred` guarden deleted wrappers

### B) Qt-Hardening erweitert: safe disconnect

- `pydaw/ui/qt_hardening.py`
  - zusätzlich zu `connect`: patched nun auch `pyqtBoundSignal.disconnect`
  - mapping original callable → wrapped callable (`WeakKeyDictionary`)
  - damit funktioniert `connect(fn) ... disconnect(fn)` wieder korrekt.

## 4) Feature: AI Composer Note‑FX (MVP)

Auf Wunsch: neues Tool als **MIDI/Note‑FX Plugin**.

- `pydaw/ui/fx_specs.py`: neuer Eintrag `chrono.note_fx.ai_composer` (AI Composer)
- `pydaw/ui/fx_device_widgets.py`: neue UI `AiComposerNoteFxWidget`
- `pydaw/music/ai_composer.py`: algorithmische Generator-Engine (seeded, reproducible)

**Wichtig:** Das ist bewusst ein *leichtes* algorithmisches System (Stochastik + Constraints),
keine statischen MIDI-Dateien und keine schweren ML-Abhängigkeiten.

## 5) Tests (manuell)

- Start der App unter Wayland: keine Popout-Fenster beim DevicePanel-Refresh
- UI Interaktionen: Card scroll/title elide → keine Crashes
- Qt Hardening: disconnect("once") Patterns funktionieren wieder
- AI Composer: Parameteränderung persistiert im Projekt + Snapshot Save/Load (JSON)

## 6) Dateien

- `pydaw/ui/device_panel.py`
- `pydaw/ui/qt_hardening.py`
- `pydaw/ui/fx_specs.py`
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/music/ai_composer.py`
- `VERSION`, `pydaw/version.py`
