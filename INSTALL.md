# 🎵 Py_DAW Installation

## Schnellstart (1 Befehl!)

```bash
# Repository klonen oder ZIP entpacken, dann:
cd Py_DAW
python3 setup_all.py
```

**Das war's.** Das Skript installiert automatisch alles.

Danach die DAW starten:
```bash
source myenv/bin/activate   # Virtual Environment aktivieren
python3 main.py              # DAW starten
```

---

## Was setup_all.py macht

1. ✅ Erstellt ein Python Virtual Environment (`myenv/`)
2. ✅ Installiert alle Python-Pakete (PyQt6, numpy, sounddevice, etc.)
3. ✅ Prüft dein Audio-System (PipeWire, JACK, ALSA)
4. ✅ Zeigt dir einen Status-Report was funktioniert

Du brauchst sonst **nichts** manuell zu installieren.

---

## Optionen

```bash
python3 setup_all.py              # Standard (Python-only, DAW funktioniert sofort)
python3 setup_all.py --with-rust  # + Rust Audio-Engine (High Performance)
python3 setup_all.py --check      # Nur prüfen was installiert ist
```

---

## System-Voraussetzungen

### Linux (Debian/Ubuntu/Kali/Mint)

```bash
# Minimum (Python):
sudo apt install python3 python3-venv python3-pip

# Audio (empfohlen):
sudo apt install pipewire pipewire-jack pipewire-alsa qpwgraph

# Nur wenn du die Rust Audio-Engine bauen willst:
sudo apt install libasound2-dev pkg-config curl
```

### macOS

```bash
# Python via Homebrew:
brew install python3

# Audio funktioniert out-of-the-box (CoreAudio)
```

---

## Rust Audio-Engine (OPTIONAL)

**Wichtig: Die DAW funktioniert AUCH OHNE Rust!**

Rust ist ein optionales Performance-Upgrade. Die bestehende Python
Audio-Engine funktioniert einwandfrei. Rust bringt:
- Niedrigere CPU-Last bei vielen Tracks
- Niedrigere Latenz
- Lock-free Audio-Rendering

### Rust installieren + Engine bauen

```bash
# Alles automatisch:
python3 setup_all.py --with-rust

# Oder manuell:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
sudo apt install libasound2-dev pkg-config   # Linux
cd pydaw_engine
cargo build --release
```

### Rust-Engine aktivieren

```bash
# Einmalig zum Testen:
USE_RUST_ENGINE=1 python3 main.py

# Oder permanent in ~/.bashrc:
echo 'export USE_RUST_ENGINE=1' >> ~/.bashrc
```

### Rust-Engine deaktivieren (zurück zu Python)

```bash
python3 main.py                   # Einfach ohne Flag starten
# Oder explizit:
USE_RUST_ENGINE=0 python3 main.py
```

---

## Fehlerbehebung

### "ModuleNotFoundError: No module named 'PyQt6'"
```bash
source myenv/bin/activate    # venv aktivieren
python3 setup_all.py         # Oder neu installieren
```

### "No audio output device found"
```bash
systemctl --user status pipewire    # PipeWire prüfen
aplay -l                            # ALSA Geräte
qpwgraph                            # Audio-Routing visualisieren
```

### "Rust: cargo not found"
```bash
source ~/.cargo/env                 # Rust-Pfad laden
python3 setup_all.py --with-rust   # Oder neu installieren
```

### "error: linker 'cc' not found" (Rust Build)
```bash
sudo apt install build-essential
```

### Status prüfen
```bash
python3 setup_all.py --check
```

---

## Für Entwickler / Team-Kollegen

Siehe `PROJECT_DOCS/TEAM_SETUP_CHECKLIST.md` für die komplette Checkliste.

Kurzversion:
```bash
python3 setup_all.py --with-rust    # Alles installieren
source myenv/bin/activate
python3 main.py                     # Testen
```

Nach jedem Update:
```bash
python3 setup_all.py --check
pip install -r requirements.txt
cd pydaw_engine && cargo build --release  # Falls Rust-Code geändert
```
