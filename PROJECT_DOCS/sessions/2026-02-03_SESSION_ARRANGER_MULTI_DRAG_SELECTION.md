# Session 2026-02-03 — Arranger Multi-Drag Selection Fix

**Version:** v0.0.19.5.1.31

## Problem
In der Arranger-Ansicht existiert Lasso/Mehrfachauswahl, aber der DAW-Workflow war gebrochen:

- Lasso selektiert mehrere Clips.
- **Klick + Drag** auf einen Clip der Selection sollte die Gruppe bewegen.
- Tatsächlich wurde beim Klick die Auswahl auf **nur diesen** Clip reduziert (solange kein Shift gehalten wurde).

## Fix
DAW-Style Selection Handling:
- Wenn der User auf einen Clip klickt, der **bereits in der aktuellen Mehrfachauswahl** ist, bleibt die Auswahl erhalten.
- Dadurch greift `_drag_move_multi(...)` zuverlässig und bewegt die Gruppe.

## Files
- `pydaw/ui/arranger_canvas.py`

## Test
1. Zwei oder mehr Clips per Lasso markieren.
2. Ohne Shift einen der markierten Clips greifen und ziehen.
3. Erwartung: **Alle markierten Clips** bewegen sich gemeinsam.

