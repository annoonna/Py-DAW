# Session Log — 2026-02-08 — v0.0.20.18

## Kontext
Beim Installieren der Python-Abhängigkeiten über:

```bash
pip install -r requirements.txt
```

trat folgender Fehler auf:

- `ERROR: Could not find a version that satisfies the requirement JACK-Client>=0.6.6`

Auf PyPI existieren für `JACK-Client` derzeit Versionen bis **0.5.5**.

## Ziel
- `pip install -r requirements.txt` soll in einer normalen venv wieder funktionieren.
- Keine inhaltlichen Engine-Änderungen – reiner Requirements-Hotfix.

## Änderungen
### 1) requirements.txt
- Fix: `JACK-Client>=0.6.6` → `JACK-Client>=0.5.5`

### 2) Version / Doku
- Version auf `0.0.20.18` erhöht.
- `INSTALL.md` / `BRIEF_AN_KOLLEGEN.md` / Statusstrings aktualisiert.

## Test-Checkliste (für den Kollegen)
```bash
python3 -m venv myenv
source myenv/bin/activate
pip install -U pip
pip install -r requirements.txt
python3 main.py
```

Optional (system-level, Debian/Kali):
```bash
sudo apt install libjack-jackd2-0
```
