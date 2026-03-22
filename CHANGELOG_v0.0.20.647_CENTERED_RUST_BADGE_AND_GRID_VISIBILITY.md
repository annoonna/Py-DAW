# CHANGELOG v0.0.20.647 — Centered Rust Badge + bessere Topbar-Lesbarkeit

**Datum:** 2026-03-20
**Autor:** GPT-5.4 Thinking
**Arbeitspaket:** User-Hotfix — UI Branding / Toolbar-Ergonomie

## Was wurde gemacht
- Rust-Badge aus der Projekt-Tab-Leiste in einen eigenen zentrierten Branding-Slot der Tool-Leiste verschoben.
- Werkzeug- und Grid-ComboBoxen verbreitert, damit „Zeiger“, „1/16“ und „1/32“ klar lesbar bleiben.
- Combo-Dropdown visuell vergrößert (größere Drop-Down-Zone / Arrow-Fläche), damit der kleine obere Bedienbereich leichter zu treffen ist.
- Python-Badge rechts etwas größer gehalten, damit das kleine Symbol oben besser erkennbar bleibt.
- Projekt-Tab-Leiste leicht entschlackt, weil das Rust-Badge dort nicht mehr rechts hineinquetscht.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/ui/toolbar.py | Zentrierter Rust-Slot, breitere ComboBoxen, klarere Topbar-Geometrie |
| pydaw/ui/project_tab_bar.py | Rust-Badge aus rechter Kante entfernt, Toolbar kompakter |
| pydaw/ui/main_window.py | Klick-Feedback für das neue zentrierte Rust-Badge verdrahtet |
| VERSION | Versionsnummer erhöht |
| pydaw/version.py | Versionskonstante erhöht |

## Was als nächstes zu tun ist
- Optional: letzte Feinschliff-Runde für exakte Badge-Position und Toolbar-Abstände anhand neuer Screenshots.
- Roadmap normal fortsetzen bei AP3 Phase 3C Task 4 — Clip-Warp im Arranger.

## Bekannte Probleme / Offene Fragen
- UI wurde hier syntaktisch geprüft, aber nicht visuell mit laufendem PyQt6 gestartet.
