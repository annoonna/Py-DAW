# 📋 TEAM SETUP CHECKLISTE — Py_DAW

**Für jeden Kollegen / Benutzer / Tester.**
**Dieses Dokument stellt sicher, dass jeder die gleiche Umgebung hat.**

---

## 🚀 ERSTMALIGES SETUP (einmal pro Maschine)

### Schritt 1: System-Pakete (einmalig, braucht sudo)

```bash
# Debian/Ubuntu/Kali/Mint:
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-pip \
    pipewire pipewire-jack pipewire-alsa \
    qpwgraph \
    libasound2-dev pkg-config \
    build-essential curl git
```

**Warum diese Pakete?**
| Paket | Wofür |
|-------|-------|
| python3, python3-venv, python3-pip | Python-Grundlage |
| pipewire, pipewire-jack, pipewire-alsa | Audio-System |
| qpwgraph | Audio-Routing visualisieren (hilfreich!) |
| libasound2-dev, pkg-config | Für Rust Audio-Engine Build |
| build-essential | C-Compiler (für Rust Linker) |
| curl | Rust-Installer herunterladen |

### Schritt 2: Py_DAW Setup (automatisch)

```bash
# ZIP entpacken ODER Git klonen
cd Py_DAW_v0_0_20_XXX_TEAM_READY

# ALLES AUTOMATISCH — ein Befehl:
python3 setup_all.py --with-rust

# Das Skript:
# ✅ Erstellt Python venv
# ✅ Installiert alle Python-Pakete
# ✅ Installiert Rust (falls nötig)
# ✅ Baut die Rust Audio-Engine
# ✅ Prüft alles und zeigt Status-Report
```

### Schritt 3: DAW starten

```bash
source myenv/bin/activate
python3 main.py
```

---

## 🔄 BEI JEDEM UPDATE (neue ZIP vom Auftraggeber)

```bash
# 1. Neue ZIP entpacken
unzip Py_DAW_v0_0_20_XXX_TEAM_READY.zip -d work
cd work

# 2. Prüfen ob alles noch da ist
python3 setup_all.py --check

# 3. Falls neue Python-Pakete:
source myenv/bin/activate
pip install -r requirements.txt

# 4. Falls Rust-Code geändert wurde:
cd pydaw_engine && cargo build --release && cd ..

# 5. DAW starten und testen
python3 main.py
```

---

## ✅ CHECKLISTE: "Ist mein System bereit?"

Führe das aus und prüfe die Ergebnisse:

```bash
python3 setup_all.py --check
```

Du solltest sehen:

```
  Python: 3.12.x — ✅
  Rust: rustc 1.xx.x — ✅        (nur mit --with-rust)
  cargo: ✅                        (nur mit --with-rust)
  Engine Binary: ✅ (Release)     (nur mit --with-rust)
  PipeWire: ✅
  ALSA (aplay): ✅
  ALSA Dev-Headers: ✅
  PyQt6: ✅
  numpy: ✅
  sounddevice: ✅
  soundfile: ✅
  msgpack: ✅
  pedalboard: ✅
  venv aktiv: ✅
```

**Minimum für DAW-Start:** Python, PyQt6, numpy ✅
**Für Audio:** + sounddevice, PipeWire ✅
**Für Rust-Engine:** + Rust, ALSA Dev-Headers, Engine Binary ✅

---

## 🛠️ HÄUFIGE PROBLEME

### Problem: "python3: command not found"
```bash
sudo apt install python3
```

### Problem: "No module named 'venv'"
```bash
sudo apt install python3-venv
```

### Problem: "externally-managed-environment"
```bash
# NICHT mit --break-system-packages arbeiten!
# Stattdessen: setup_all.py erstellt automatisch ein venv
python3 setup_all.py
```

### Problem: Rust-Build Fehler "cannot find -lasound"
```bash
sudo apt install libasound2-dev
```

### Problem: Rust-Build Fehler "linker 'cc' not found"
```bash
sudo apt install build-essential
```

### Problem: "cargo: command not found" nach Installation
```bash
source ~/.cargo/env
# Oder Terminal neu öffnen
```

### Problem: Kein Sound
```bash
# PipeWire Status:
systemctl --user status pipewire

# Restart:
systemctl --user restart pipewire

# Geräte prüfen:
aplay -l
pw-cli list-objects | grep -i node
```

### Problem: DAW startet, aber GUI hängt
```bash
# Qt-Plattform prüfen:
QT_QPA_PLATFORM=xcb python3 main.py
# Oder:
QT_QPA_PLATFORM=wayland python3 main.py
```

---

## 📁 VERZEICHNIS-STRUKTUR nach Setup

```
Py_DAW/
├── main.py                ← DAW starten
├── setup_all.py           ← Alles-Macher Setup
├── install.py             ← Legacy Python-Only Installer
├── requirements.txt       ← Python-Abhängigkeiten
├── VERSION                ← Aktuelle Version
├── myenv/                 ← Python Virtual Environment (automatisch erstellt)
├── pydaw/                 ← Hauptcode (Python)
│   ├── ui/                ← GUI (PyQt6)
│   ├── services/          ← Business Logic
│   ├── audio/             ← Audio Engine (Python)
│   └── ...
├── pydaw_engine/          ← Rust Audio-Engine (optional)
│   ├── Cargo.toml         ← Rust-Dependencies ("wie requirements.txt")
│   ├── src/               ← Rust Quellcode
│   │   ├── main.rs        ← Engine Entry Point
│   │   ├── audio_graph.rs ← Echtzeit Audio-Graph
│   │   ├── ipc.rs         ← IPC Protokoll
│   │   └── ...
│   └── target/            ← Build-Output (automatisch erstellt)
│       └── release/
│           └── pydaw_engine  ← Das fertige Binary
└── PROJECT_DOCS/          ← Dokumentation
    ├── ROADMAP_MASTER_PLAN.md
    ├── TEAM_RELAY_PROTOCOL.md
    └── TEAM_SETUP_CHECKLIST.md  ← DIESES DOKUMENT
```

---

## 🔑 WICHTIGE BEFEHLE (Spickzettel)

```bash
# Setup
python3 setup_all.py              # Python-only Setup
python3 setup_all.py --with-rust  # + Rust Engine
python3 setup_all.py --check      # Status prüfen

# DAW starten
source myenv/bin/activate         # venv aktivieren (einmal pro Terminal)
python3 main.py                   # DAW normal starten
USE_RUST_ENGINE=1 python3 main.py # Mit Rust-Engine

# Rust-Engine manuell bauen
cd pydaw_engine
cargo build --release             # Optimiert (langsamer Build, schnellere Engine)
cargo build                       # Debug (schneller Build, langsamere Engine)
cargo run                         # Bauen + direkt starten (zum Testen)

# Python-Pakete aktualisieren
pip install -r requirements.txt

# System-Check
aplay -l                          # Audio-Geräte
qpwgraph                          # Audio-Routing (GUI)
rustc --version                   # Rust Version
cargo --version                   # Cargo Version
```

---

## 🦀 RUST FÜR EINSTEIGER — Kurzübersicht

| Python | Rust | Beschreibung |
|--------|------|--------------|
| `requirements.txt` | `Cargo.toml` | Abhängigkeiten definieren |
| `pip install` | `cargo build` | Abhängigkeiten installieren + bauen |
| `python3 main.py` | `cargo run` | Programm starten |
| `venv/` | `target/` | Build-Output Verzeichnis |
| `import numpy` | `use cpal;` | Bibliothek benutzen |

**Cargo macht alles automatisch:** Wenn du `cargo build` ausführst, lädt cargo
automatisch alle Abhängigkeiten herunter, kompiliert sie, und baut das Binary.
Du musst NICHTS manuell herunterladen.

**Erster Build dauert:** 1-3 Minuten (alle Abhängigkeiten werden kompiliert).
Danach: nur wenige Sekunden (nur geänderte Dateien werden neu kompiliert).

---

*Letzte Aktualisierung: v0.0.20.633 — 2026-03-19*
