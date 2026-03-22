# SESSION v0.0.20.226 — Installer: LV2 System-Dependencies (Debian/Kali)

## Kontext
User-Request: LV2 Hosting ist da, aber die notwendigen System-Pakete sollen **automatisch** über `install.py` abgedeckt werden und in `requirements.txt` dokumentiert sein.

**Oberste Direktive:** Nichts kaputt machen → daher: best-effort, niemals hartes Abbruch-Kriterium.

## Änderungen (safe)

### 1) `install.py`
- Added best-effort Debian/Kali detection (`/etc/os-release`).
- Wenn `apt-get` vorhanden ist und Pakete fehlen:
  - versucht `apt-get update` + `apt-get install -y python3-lilv lilv-utils`
  - zuerst als root, sonst via `sudo`
  - Fehler werden nur als WARN geloggt; pip-Install läuft immer weiter.

### 2) `requirements.txt`
- Kommentarblock oben ergänzt:
  - `sudo apt update`
  - `sudo apt install python3-lilv lilv-utils`
- Pip bleibt davon unberührt (Kommentare).

### 3) Version bump
- `VERSION` + `pydaw/version.py` → `0.0.20.226`

## Dateien
- `install.py`
- `requirements.txt`
- `VERSION`
- `pydaw/version.py`

## Test-Notizen
- Installer soll auf Nicht-Debian OS nichts tun.
- Falls `sudo` Passwort benötigt: Benutzer kann eingeben; wenn nicht möglich, bleibt ein Hinweis im Output.

