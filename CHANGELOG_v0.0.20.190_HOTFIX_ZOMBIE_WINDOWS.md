## v0.0.20.190 — Hotfix: "Zombie"-Fenster (DevicePanel Refresh poppt Widgets aus)

### Problem
- Beim Ändern von FX-Parametern (z.B. Gain) öffneten sich plötzlich viele kleine Fenster.
- Ursache: Widgets wurden beim DevicePanel-Rebuild mit `setParent(None)` aus Layouts gelöst.
  Sichtbare Widgets werden dadurch zu Top-Level Windows und bleiben offen.

### Fix (safe)
- DevicePanel nutzt jetzt einen unsichtbaren Widget-Stash + Helper `_stash_widget()`.
- Rebuild-Cleanup: Cards werden versteckt und `deleteLater()` statt `setParent(None)`.
- Instrument Remove/Replace entsorgt alte Widgets sauber.

### Files
- `pydaw/ui/device_panel.py`
- `VERSION`, `pydaw/version.py`
