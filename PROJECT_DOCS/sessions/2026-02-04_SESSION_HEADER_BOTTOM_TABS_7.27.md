# Session Log — Pro-DAW Header sichtbar + Bottom Tabs

**Datum:** 2026-02-04  
**Version:** v0.0.19.7.27  
**Assignee:** GPT-5.2

## Problem
- Header (setMenuWidget) war im Running-Build nicht sichtbar, weil `menuBar().hide()` (Qt-Style abhängig) die komplette Menü-Region inkl. `menuWidget` mit ausblendet.
- Im UI fehlten Elemente aus dem Referenz-Screenshot: kompakte Drop-Down-Menüs im Header + Bottom Tabs (ARRANGE/MIX/EDIT) + Snap-Anzeige.

## Änderungen
1) **Header sichtbar gemacht**
- `menuBar().hide()` entfernt. Header bleibt zuverlässig sichtbar (MenuBar wird durch `setMenuWidget` ohnehin ersetzt).

2) **Header Menüs (Pro-DAW-like)**
- Drop-Down Buttons im Header: **☰ / File / Edit / Options**
- Menüs sind direkt mit bestehenden `AppActions` verbunden (Safety-first: keine Logik gelöscht).

3) **Bottom Tabs (Rosegarden-like)**
- Status-Bar Tabs: **ARRANGE / MIX / EDIT**
- Umschalten der Docks:
  - ARRANGE → Editor+Mixer Dock hidden (Arranger volle Höhe)
  - MIX → Mixer Dock sichtbar/aktiv
  - EDIT → Editor Dock sichtbar/aktiv

4) **Snap/Grid Anzeige unten rechts**
- Status-Label rechts; aktualisiert beim Grid-Wechsel.

## Files
- `pydaw/ui/main_window.py`
- `pydaw/version.py`

## Quick Test
- Start → Header sichtbar
- Tabs ARRANGE/MIX/EDIT toggeln → Docks entsprechend
- Taste **B** → Browser ein/aus
- Grid ändern → Snap-Label aktualisiert
