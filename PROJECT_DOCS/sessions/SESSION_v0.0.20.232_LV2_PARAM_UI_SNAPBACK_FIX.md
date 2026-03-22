# Session v0.0.20.232 — LV2 Param‑UI: Slider‑Snapback Fix

**Date:** 2026-03-04  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Directive:** SAFE — minimal, targeted changes only ("oberste Direktive: nichts kaputt machen")

## Problem (User Report)
- LV2 Plugin‑UI wird angezeigt (Parameter‑Slider/Spinbox sichtbar).
- Beim Bewegen der Slider springen die Werte wieder zurück → Plugin‑Controls wirken "nicht bedienbar".

## Root Cause
- Die LV2 Param‑UI emittierte nach (debounced) Wertänderungen `ProjectService.project_updated`.
- Der **DevicePanel** hört auf `project_updated` und rendert die komplette Device‑Chain neu.
- Während man einen Slider zieht (viele Änderungen pro Sekunde) wird das LV2 Widget dadurch zerstört/neu gebaut.
  → UI wirkt, als würde sie "zurückspringen".

## Fix (safe)
- LV2 Param‑Änderungen emittieren jetzt nur noch `project_changed` (Dirty‑State / Titel‑Indikator),
  **kein** `project_updated` (kein Full‑Rebuild während Drag).
- Ergebnis: Slider bleiben stabil, Parameter lassen sich sauber einstellen.

## Bonus (Hinweisqualität)
- `availability_hint()` ergänzt um:
  - `liblilv-0-0` als häufig fehlendes Runtime‑Paket
  - Hinweis auf `liblilv-dev`, falls ImportError explizit `liblilv-0.so` verlangt

## Files changed
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/audio/lv2_host.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Manual Test (expected)
- LV2 Device hinzufügen → Param‑Liste sichtbar.
- Slider ziehen → Werte bleiben stehen (kein "snap back"), auch bei schnellen Bewegungen.
- Fenster/Titel zeigt Dirty‑State (über `project_changed`).
