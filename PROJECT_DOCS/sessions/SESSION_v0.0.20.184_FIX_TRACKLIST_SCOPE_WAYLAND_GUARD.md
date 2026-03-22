# Session: v0.0.20.184 — Fix: TrackList Scope/Method Regression + Wayland-safe Search

## Problem
- Start-Crash: `AttributeError: 'TrackList' object has no attribute 'refresh'` / `_refresh_impl`.
- Root cause: Indentation/Scope regression in `pydaw/ui/arranger.py` caused TrackList methods to leave the class scope.

## Fix (safe)
- Restored a known-good TrackList implementation (Phase 2/3 Track-Header ▾ + Favorites/Recents hooks bleiben).
- Wayland-Guard: Search in Track-▾ Device-Submenus nutzt unter Wayland **Search… Dialog** statt eingebettetem `QLineEdit` im `QMenu`.

## Test
- App startet ohne Traceback.
- Arranger + TrackList werden angezeigt.
- Track-▾ Menü öffnet.
- Device-Submenus: Search funktioniert (Wayland: Dialog / X11: Inline).
