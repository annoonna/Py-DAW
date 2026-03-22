# SESSION v0.0.20.190 — Hotfix: "Zombie"-Fenster / Pop-out bei DevicePanel Refresh

**Datum:** 2026-03-02  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Priorität:** 🔴 HIGH  

## Ausgangslage (User Report)
- Beim Ändern von FX-Werten (z.B. Gain) öffneten sich plötzlich **mehrere kleine Fenster** (doppelt/dreifach).
- Zusätzlich tauchten teilweise weitere Widgets als "lose" Fenster auf.

## Root Cause
`DevicePanel` rebuilt die Chain häufig (z.B. via `project_updated`).
Dabei wurden Widgets aus dem Layout gelöst via:
- `setParent(None)` in `_clear_chain()`
- `setParent(None)` bei Instrument Remove/Replace

**Qt Verhalten:** Ein sichtbares QWidget wird bei `setParent(None)` zum **Top-Level Window**.
=> Alte Cards/Widgets wurden nicht gelöscht, sondern als "Zombie"-Fenster weiter angezeigt.

## Fix (safe, nichts kaputt)
- Einführung eines unsichtbaren **Widget-Stash** (`self._widget_stash`) als Parent.
- Neuer Helper `DevicePanel._stash_widget(widget, delete=...)`:
  - versteckt Widget
  - reparentet in Stash (oder DevicePanel als Fallback)
  - optional `deleteLater()`
- `_clear_chain()`:
  - Persistent Instrument-Widgets werden in den Stash verschoben (nicht gelöscht)
  - Device-Cards werden in den Stash verschoben und `deleteLater()`
- `_remove_instrument()` + `_create_or_replace_instrument_widget()`:
  - alte Instrument-Widgets werden **sauber entsorgt** (stash + deleteLater)

## Geänderte Dateien
- `pydaw/ui/device_panel.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Test-Checkliste (manuell)
1. Projekt starten.
2. Track ▾ → Devices → Add Audio-FX → Gain.
3. Gain mehrfach ändern (Slider/Spinbox) und beobachten:
   - ✅ **Keine** zusätzlichen Fenster erscheinen.
   - ✅ DevicePanel bleibt stabil, keine "alten" Cards bleiben sichtbar.
4. Instrument wechseln/entfernen:
   - ✅ Keine orphaned / pop-out Widgets.

## Notes
Dieser Fix ist rein UI-/Lifecycle-bezogen (Widget Parenting/Deletion).
Keine Änderungen am Audio-Engine-Pfad.
