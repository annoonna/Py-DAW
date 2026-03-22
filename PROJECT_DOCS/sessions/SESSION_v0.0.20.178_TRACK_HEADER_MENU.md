# Session: v0.0.20.178 — Phase 2: Track-Header ▾ + Slot-Safety Fixes

## Ziel
1) **Track-Header ▾** (pro Track) im Arranger/TrackList:
- Routing / Arm / Monitor / Add Device – alles **additiv** (kein Workflow-Bruch).

2) **Crash-Safety**:
- PyQt6 kann bei uncaught Slot Exceptions den Prozess mit SIGABRT beenden.
- Ziel: UI-Callbacks robust machen, ohne bestehende Logik zu verändern.

## Implementiert (safe)
### 1) Track-Header ▾ (pro Track)
- In `Arranger.TrackList` wird pro Track ein kleiner **▾** Button angezeigt.
- Menü-Inhalte:
  - **Routing** (Audio/Bus): Input Pair / Output Pair + Monitoring
  - **Record/Mix:** Arm / Mute / Solo
  - **Devices:**
    - Add Instrument… (Browser) → Browser öffnet Instruments-Tab
    - Add FX… (Browser) → Browser öffnet Effects-Tab
    - Device Panel zeigen → View-Mode „device“
  - **Track ops:** Umbenennen / Track löschen (Master geschützt)

### 2) Slot-Safety / SIGABRT Schutz
- `Arranger.TrackList`: alle Button/Combo Slots laufen über `_safe_ui_call()`.
- `ClipLauncher.refresh()`: Quantize/Mode werden mit `blockSignals(True)` synchronisiert, damit keine re-entrancy entsteht.
- `_launcher_settings_changed()` ist bulletproof (try/except + Fallback).

## Dateien
- `pydaw/ui/arranger.py`
- `pydaw/ui/main_window.py`
- `pydaw/ui/clip_launcher.py`

## Test-Checkliste
- Arranger links (TrackList): bei jedem Track **▾** sichtbar → Menü öffnet.
- Menü:
  - Audio/Bus: Routing → Input/Output umstellen + Monitoring toggeln.
  - Arm/Mute/Solo im Menü toggeln.
  - Devices → „Add Instrument…“ öffnet Browser + Instruments Tab.
  - Devices → „Add FX…“ öffnet Browser + Effects Tab.
  - „Device Panel zeigen“ → Device-Dock sichtbar.
- ClipLauncher: Öffnen/Refresh → kein Crash; Quantize/Mode bleiben korrekt.
