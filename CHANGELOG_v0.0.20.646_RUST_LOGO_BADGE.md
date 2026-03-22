# CHANGELOG v0.0.20.646 — Rust Logo Badge

**Datum:** 2026-03-20
**Autor:** GPT-5.4 Thinking
**Arbeitspaket:** User-Hotfix — UI Branding / Toolbar-Ergonomie

## Was wurde gemacht
- Eigenständiges Rust-Badge in die Projekt-Tab-Leiste nahe **Neues Projekt** / **Öffnen** eingebunden.
- Badge bleibt komplett von `QtLogoButton` getrennt und verwendet ein eigenes, selbst gezeichnetes Widget.
- Größe bewusst auf **30×30 px** in einer etwas höheren Projekt-Tab-Leiste gesetzt, damit das Symbol klarer erkennbar bleibt.
- Optionales Klick-Feedback über die Statusleiste ergänzt, ohne Projekt- oder Audio-Logik anzufassen.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/ui/project_tab_bar.py | Rust-Badge sicher in die Projekt-Tab-Leiste integriert, Höhe/Spacing leicht angepasst |
| pydaw/ui/main_window.py | Klick-Feedback des Badges über Statusleiste verdrahtet |

## Was als nächstes zu tun ist
- Optional: Badge bei Bedarf alternativ in die Menueleisten-Mitte oder in einen separaten Branding-Slot verschiebbar machen.
- Roadmap normal fortsetzen bei AP3 Phase 3C Task 4 (Clip-Warp im Arranger).

## Bekannte Probleme / Offene Fragen
- Das Badge ist absichtlich rein visuell; es startet keine Rust-Engine-Aktion.
