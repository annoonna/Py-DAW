# CHANGELOG v0.0.20.651 — Status Tech Signature

**Datum:** 2026-03-20
**Autor:** GPT-5.4 Thinking
**Typ:** UI-Hotfix / Branding-Refinement (ohne Audio-/Transport-Logik)

## Was wurde gemacht
- Qt-, Python- und Rust-Logos zu einer gemeinsamen Tech-Signatur in der Statusleiste unten rechts zusammengeführt.
- Das Python-Logo aus der oberen Tool-Leiste herausgenommen und denselben Button in die Statusleiste umgehängt, damit die bestehende Animation erhalten bleibt.
- Das Rust-Logo aus der Menümitte deaktiviert und in die Statusleiste verschoben.
- Das Qt-Logo aus der linken Bottom-Nav entfernt und ebenfalls in die Statusleiste verschoben.
- Größen der drei Logos vereinheitlicht und auf die gewünschte Rust-Präsenz abgestimmt.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/ui/main_window.py | Statusleisten-Tech-Signatur aufgebaut, Menü-Rust-Badge deaktiviert, Bottom-Nav bereinigt |
| VERSION | auf 0.0.20.651 erhöht |
| pydaw/version.py | auf 0.0.20.651 erhöht |
| PROJECT_DOCS/progress/TODO.md | Session dokumentiert |
| PROJECT_DOCS/progress/DONE.md | Session dokumentiert |
| PROJECT_DOCS/sessions/SESSION_v0.0.20.651_status_tech_signature.md | neuer Session-Log |
| PROJECT_DOCS/sessions/LATEST.md | auf neue Session gesetzt |

## Was als nächstes zu tun ist
- Optischer Feinschliff nur noch pixelgenau per Screenshot: Abstand der Trio-Signatur zu CPU/GPU bei Bedarf feintrimmen.
- Danach wieder zur Roadmap zurück: AP4 Phase 4B (Preset-Browser).

## Bekannte Probleme / Offene Fragen
- Die GUI konnte in dieser Umgebung nicht live gestartet werden, weil PyQt6 hier nicht installiert ist. Der Patch wurde deshalb per `py_compile` und ZIP-Verifikation abgesichert.
- Python-Animation bleibt aktiv, nutzt jetzt aber die neue Statusleisten-Position.
