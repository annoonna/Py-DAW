# CHANGELOG v0.0.20.649 — Rust-Badge exakt in der oberen Mitte

**Datum:** 2026-03-20
**Autor:** GPT-5.4 Thinking
**Arbeitspaket:** User-Hotfix — UI Branding / Topbar-Feinjustierung

## Was wurde gemacht
- Rust-Badge aus der Transport-Leiste entfernt und als eigenes Overlay direkt auf der Menüleiste platziert.
- Badge horizontal in die visuelle Mitte der oberen Menüzeile gesetzt, mit Schutzabstand rechts von `Hilfe`, damit keine Menüpunkte überdeckt werden.
- Badge wird bei Fenstergrößenänderungen automatisch neu zentriert.
- Transport-Leiste bleibt wieder frei für ihre eigentlichen Bedienelemente.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw/ui/main_window.py` | Zentrales Menüleisten-Badge erstellt, positioniert und per Resize nachgeführt |
| `pydaw/ui/transport.py` | Vorheriges Transport-Badge entfernt |
| `VERSION` | Auf `0.0.20.649` erhöht |
| `pydaw/version.py` | Versionsstring auf `0.0.20.649` erhöht |

## Was als nächstes zu tun ist
- Optional nur noch responsive Verdichtung für sehr kleine Fensterbreiten.
- Danach wieder zurück auf die Roadmap-Aufgaben, z. B. Clip-Warp im Arranger.

## Bekannte Probleme / Offene Fragen
- Der Fix ist als reiner Layout-Hotfix umgesetzt und per `py_compile` geprüft. Ein visueller Laufzeittest war in dieser Umgebung nicht möglich.
