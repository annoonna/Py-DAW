# Changelog v0.0.20.581 — Fusion Scrawl State Save/Load Fix

- Projekt-/Preset-State von Fusion enthaelt jetzt `scrawl_points`, `scrawl_smooth` und `wt_file_path`.
- Scrawl-Canvas-Aenderungen triggern den bestehenden debounced Persist-Pfad.
- Restore synchronisiert den gespeicherten Scrawl-Zustand wieder in Engine, aktive Voices und Editor-Anzeige.
