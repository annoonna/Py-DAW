# CHANGELOG v0.0.20.645 — Toolbar Readability Hotfix

**Datum:** 2026-03-20
**Autor:** GPT-5.2 Thinking
**Arbeitspaket:** User-Hotfix — Transport-/Toolbar-Ergonomie

## Was wurde gemacht
- Projekt-Tabs in eine eigene Toolbar-Zeile verschoben, damit Transport- und Tool-Leiste nicht mehr in eine einzige Zeile gequetscht werden.
- TransportPanel kompakter gemacht: kleinere Transport-Buttons, schmalere BPM/TS-Felder, kompaktere Pre/Post/Count-In-Steuerung.
- Rechte obere Controls bleiben dadurch lesbar; Python-Logo und Tool-Leiste bekommen wieder Luft.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/ui/main_window.py | Expliziter Toolbar-Break nach der Projekt-Tab-Leiste |
| pydaw/ui/transport.py | Kompaktere, lesbarere Transport-Leiste mit kleineren Controls |
| CHANGELOG.md | Eintrag für v0.0.20.645 ergänzt |
| PROJECT_DOCS/ROADMAP_MASTER_PLAN.md | UI-Hotfix-Checkbox ergänzt + Stand aktualisiert |
| PROJECT_DOCS/progress/TODO.md | Session-Eintrag + nächste Schritte ergänzt |
| PROJECT_DOCS/progress/DONE.md | Session-Eintrag ergänzt |
| PROJECT_DOCS/sessions/SESSION_v0.0.20.645_TRANSPORT_TOOLBAR_READABILITY.md | Session-Log |
| PROJECT_DOCS/sessions/LATEST.md | Auf neue Session aktualisiert |
| VERSION | Versionsnummer erhöht |
| pydaw/version.py | Versionskonstante erhöht |

## Was als nächstes zu tun ist
- Roadmap weiter bei AP3 Phase 3C Task 4: Clip-Warp im Arranger.
- Optional: Bei sehr schmalen Fenstern eine zusätzliche responsive Verdichtung oder Umbruch-Logik für die Transport-Zeile ergänzen.

## Bekannte Probleme / Offene Fragen
- UI konnte in dieser Umgebung nicht visuell gestartet werden, daher basiert der Fix auf sicherer Layout-Entzerrung + py_compile-Verifikation.
