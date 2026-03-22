# SESSION v0.0.20.170 — Clip-Launcher Audio Editor Ctrl+J/Lasso Fix

## Problem
User-Report: Im **Clip-Launcher Audio Editor** (unten im Editor-Tab) werden AudioEvents per Lasso markiert, aber **Ctrl+J** führt keine Consolidate-Aktion aus.
Referenz: In v0.0.20.167 funktioniert es zuverlässig.

## Ursache (wahrscheinlich)
Qt Focus/Selection Edgecases:
- RubberBand selection + embedded widgets können dazu führen, dass `_selected_event_ids` nicht konsistent ist oder Key-Events nicht beim View landen.

## Fix (safe)
1) **Robuste Selection**
   - Neuer Helper `_selected_event_ids_live()` liest im Zweifel die Scene-Selection direkt.
   - Stabil sortiert nach Event-Start.

2) **Consolidate-Helper**
   - Neue Methode `_do_consolidate_events()` als Single-Source für Ctrl+J + Kontextmenü.

3) **Shortcut-Scope (zukunftssicher)**
   - Audio-Editor registriert Ctrl+J Varianten zusätzlich als `WidgetWithChildrenShortcut`:
     - Ctrl+J = bar-anchored
     - Shift+Ctrl+J = trim
     - Alt+Ctrl+J = handles
     - Ctrl+Shift+Alt+J = join (keep events)
   - Dadurch bleibt Verhalten auf den Audio-Editor scoped → keine Side-Effects in Arranger.

4) **Selection-Sync nach RubberBand-Release**
   - View ruft nach `mouseReleaseEvent()` explizit `_on_selection_changed()`.

## Ergebnis
Ctrl+J funktioniert wieder zuverlässig im Clip-Launcher Audio Editor, auch mit Lasso.
