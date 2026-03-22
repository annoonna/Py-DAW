# SESSION v0.0.20.177 (2026-03-01)

## Ziel
Phase 1.5 umsetzen: **Gain/Pan Micro-Controls (G/P)** auch im **Audio-Editor** bereitstellen – identisches Verhalten wie im Arranger, ohne bestehende Workflows zu verändern.

## Umsetzung (safe)
- Audio-Editor (`pydaw/ui/audio_editor/audio_event_editor.py`):
  - Neue Micro-Controls als kleine Buttons **G** und **P** im Clip-Header.
  - Drag-Logik:
    - **G**: vertikal = Gain (dB-mapped), **SHIFT** = Quick-Pan (horizontal)
    - **P**: horizontal = Pan, **SHIFT** = Fine (langsamer)
  - Mini Pan-Dot im **P** Button.
  - Cursor-Safety: Klick auf Micro-Controls (oder Fade-Handle) setzt **nicht** mehr die blaue Cursor-Linie.

## Warum ist das sicher?
- Keine bestehenden Shortcuts geändert.
- Keine Änderungen an ProjectService/Model-Format.
- Updates laufen über `ProjectService.update_audio_clip_params()` (Single Source of Truth).
- Während Drag wird Refresh unterdrückt, um Qt-Rebuild während MouseMove zu vermeiden.

## Testplan
1) Audio-Clip öffnen → Audio-Editor sichtbar.
2) Oben im Clip **G/P** sehen.
3) **G** ziehen (hoch/runter) → Gain ändert sich.
4) **SHIFT + G** ziehen (links/rechts) → Pan ändert sich.
5) **P** ziehen (links/rechts) → Pan ändert sich.
6) **SHIFT + P** ziehen → feinere Pan-Änderung.
7) Klick auf G/P: Cursor-Linie bleibt unverändert (kein Neben-Klick).

## Nächster Schritt
- Phase 2: Track-Header ▾ (Routing/Arm/Monitor/Add Device)
