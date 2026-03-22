# SESSION v0.0.20.181 — 2026-03-01

## Kontext
User meldet weiterhin **SIGABRT / "Unhandled Python exception"** unter PyQt6 (Wayland), trotz vorheriger Slot-Sicherungen.
Ziel: **Stabilität erhöhen** + Phase 4.5 UX (⭐ Favorites direkt in Browser-Listen).

## Änderungen (safe, additiv)

### Phase 4.5 — ⭐ Favorites direkt in Browser-Listen
- `pydaw/ui/instrument_browser.py`
  - Star-Hitbox links (x < 18px) toggelt Favorite (★/☆)
  - Kontextmenü-Fallback
  - Alle Slots defensiv (kein uncaught Qt-Slot)
- `pydaw/ui/effects_browser.py`
  - Star-Hitbox links toggelt Favorite (Note-FX + Audio-FX)
  - Kontextmenü-Fallback
  - Slots defensiv

### Stabilität (Wayland / SIGABRT)
- `pydaw/ui/arranger.py`
  - Track-▾ Menü wird **lazy** auf `aboutToShow` gebaut (kein Menü/Widget-Build beim Start)
  - Track-▾ Search-Menüs: **Wayland Guard** (Search-Dialog statt eingebettetem QLineEdit in QMenu)
- `pydaw/ui/project_tab_bar.py`
  - Timer-Slot `_activate_hovered_tab` exception-safe

## Tests (manuell)
- App startet ohne `NameError` / Start-Crash.
- Browser → Instruments/Effects: ⭐ klicken toggelt Favorites.
- TrackList ▾: Menü öffnet, Search funktioniert (Wayland: Dialog), keine Start-SIGABRTs.

## Nächste Schritte
- Phase 5: ⭐ Buttons auch in Favorites/Recents Quick Tabs (DeviceQuickListWidget) + einheitliche Stern-UX.
- Optional: Command Palette (Ctrl+P) für Actions/Devices.
