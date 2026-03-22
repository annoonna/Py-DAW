# CHANGELOG v0.0.20.633 — Setup-Automatisierung (Alles-Macher Installer)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6

## Was wurde gemacht

### setup_all.py — Das "Alles-Macher" Skript
- **Ein Befehl installiert alles**: `python3 setup_all.py`
- **Automatisch:** venv erstellen, Python-Deps, Audio prüfen, Status-Report
- **Optional Rust:** `python3 setup_all.py --with-rust` installiert Rust + baut Engine
- **Check-Modus:** `python3 setup_all.py --check` prüft nur, ändert nichts
- **Farbige Terminal-Ausgabe** mit klarem Status-Report
- **System-Erkennung:** Debian/Ubuntu/Kali, ALSA Dev-Headers, PipeWire
- **Fehlertolerant:** Jeder Schritt mit try/catch, Fehler sind nicht-fatal

### INSTALL.md — Komplett neu geschrieben
- Schnellstart (1 Befehl)
- Alle Optionen erklärt
- System-Voraussetzungen pro Plattform
- Rust-Engine Anleitung (installieren, aktivieren, deaktivieren)
- Fehlerbehebung für alle häufigen Probleme

### TEAM_SETUP_CHECKLIST.md — Checkliste für Kollegen
- Erstmaliges Setup Schritt-für-Schritt
- Bei-jedem-Update Workflow
- "Ist mein System bereit?" Check-Tabelle
- Häufige Probleme + Lösungen
- Verzeichnis-Struktur erklärt
- "Rust für Einsteiger" Kurzübersicht (Python↔Rust Vergleich)
- Wichtige Befehle Spickzettel

## Geänderte / Neue Dateien

| Datei | Änderung |
|---|---|
| `setup_all.py` | NEU: Komplett-Installer |
| `INSTALL.md` | REWRITE: Neue Anleitung |
| `PROJECT_DOCS/TEAM_SETUP_CHECKLIST.md` | NEU: Team-Checkliste |
| `VERSION` | 0.0.20.632 → 0.0.20.633 |

## Bestehender Code: NICHT verändert
- install.py bleibt als Legacy-Fallback erhalten
- requirements.txt unverändert
- Kein Byte am pydaw/ Code geändert
