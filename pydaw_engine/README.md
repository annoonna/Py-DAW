# Py_DAW Rust Audio Engine — Build & Setup

## Voraussetzungen

### Rust Toolchain
```bash
# Rust installieren (falls noch nicht vorhanden)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Verifizieren
rustc --version   # mindestens 1.75+
cargo --version
```

### System-Abhängigkeiten (Linux/Debian)
```bash
# ALSA development headers (für cpal)
sudo apt install libasound2-dev

# PipeWire/JACK (optional, empfohlen)
sudo apt install pipewire pipewire-jack

# Python MessagePack (für die Bridge)
pip install msgpack
```

### System-Abhängigkeiten (macOS)
```bash
# Keine zusätzlichen Pakete nötig — CoreAudio ist im System
pip install msgpack
```

## Bauen

```bash
# Im Repository-Root:
cd pydaw_engine

# Debug Build (schneller, mit Debug-Symbolen)
cargo build

# Release Build (optimiert, für Produktion)
cargo build --release

# Das Binary liegt dann unter:
# Debug:   pydaw_engine/target/debug/pydaw_engine
# Release: pydaw_engine/target/release/pydaw_engine
```

## Starten

### Manuell (zum Testen)
```bash
# Engine starten (wartet auf Python-Client)
./pydaw_engine/target/release/pydaw_engine \
    --socket /tmp/pydaw_engine.sock \
    --sr 44100 \
    --buf 512
```

### Aus Python (automatisch)
```python
from pydaw.services.rust_engine_bridge import RustEngineBridge

bridge = RustEngineBridge.instance()
if bridge.start_engine(sample_rate=44100, buffer_size=512):
    print("Engine läuft!")
    bridge.play()
    # ...
    bridge.shutdown()
```

### Feature-Flag
```bash
# Rust-Engine aktivieren (Default: Python-Engine)
export USE_RUST_ENGINE=1
python3 main.py

# Oder: Engine-Binary-Pfad explizit setzen
export PYDAW_ENGINE_PATH=/pfad/zu/pydaw_engine
```

## Architektur

```
Python (GUI, Projekt-Logik)
    │
    │  Unix Domain Socket (/tmp/pydaw_engine.sock)
    │  Frame: [u32 LE Länge][MessagePack Payload]
    │
    ▼
Rust Engine (Audio-Rendering, Plugins)
    │
    │  cpal (Cross-Platform Audio)
    │
    ▼
ALSA / PipeWire / JACK / CoreAudio / WASAPI
```

### Threads im Rust-Prozess
1. **Audio-Thread** (cpal callback): `process_audio()` — KEINE Allokationen
2. **IPC-Reader**: Liest Commands vom Socket
3. **IPC-Writer**: Sendet Events zum Socket

### IPC-Protokoll
- **Commands** (Python → Rust): Play, Stop, Seek, SetTempo, AddTrack, ...
- **Events** (Rust → Python): PlayheadPosition, MeterLevels, TransportState, ...
- Encoding: MessagePack (schnell, kompakt)
- Framing: `[u32 LE Länge][Payload]`

## Testen

### Phase 1A PoC Test
```bash
# Terminal 1: Engine starten
RUST_LOG=info cargo run

# Terminal 2: Python Test-Client
python3 pydaw_engine/test_bridge.py
```

### Integrations-Test
```python
from pydaw.services.rust_engine_bridge import RustEngineBridge

bridge = RustEngineBridge.instance()
assert bridge.start_engine()
bridge.ping()
bridge.set_tempo(140.0)
bridge.play()
import time; time.sleep(2)
bridge.stop()
bridge.shutdown()
```

## Bekannte Einschränkungen (Phase 1A)

- **Kein Audio-Clip-Rendering** — kommt in Phase 1B
- **Kein Plugin-Hosting** — kommt in Phase 1C
- **Kein MIDI-Dispatch** — kommt in Phase 1B
- **Nur ein Client** gleichzeitig (Single-Connection)
- **Proof-of-Concept:** Sine Wave Generator auf Track 1
- **Python-Engine bleibt der Default** — Rust-Engine nur mit `USE_RUST_ENGINE=1`

## Fehlerbehebung

### "Engine binary not found"
```bash
# Prüfen ob Binary existiert
ls -la pydaw_engine/target/release/pydaw_engine

# Pfad explizit setzen
export PYDAW_ENGINE_PATH=$(pwd)/pydaw_engine/target/release/pydaw_engine
```

### "No audio output device found"
```bash
# ALSA Devices prüfen
aplay -l

# PipeWire Status
pw-cli list-objects | grep -i audio
```

### "Engine socket did not appear"
```bash
# Prüfen ob Port belegt
ls -la /tmp/pydaw_engine.sock
# Alte Socket-Datei entfernen
rm -f /tmp/pydaw_engine.sock
```
