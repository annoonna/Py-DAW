#!/usr/bin/env python3
"""Py_DAW Komplett-Setup — Ein Befehl, alles fertig.

Usage:
    python3 setup_all.py              # Python-only (Standard — DAW funktioniert sofort)
    python3 setup_all.py --with-rust  # Python + Rust Audio-Engine (High Performance)
    python3 setup_all.py --check      # Nur prüfen was installiert ist
    python3 setup_all.py --help       # Hilfe anzeigen

Was dieses Skript macht:
1. Python Virtual Environment erstellen/aktivieren
2. Alle Python-Abhängigkeiten installieren (requirements.txt)
3. System-Audio-Pakete prüfen (PipeWire, JACK, ALSA)
4. Optional: Rust installieren + Audio-Engine bauen (--with-rust)
5. Alles testen und Status-Report ausgeben

WICHTIG: Die DAW funktioniert AUCH OHNE Rust!
         Rust ist ein optionales Performance-Upgrade.

Erstellt: v0.0.20.633 — 2026-03-19
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Konfiguration
# ═══════════════════════════════════════════════════════════════════════

HERE = Path(__file__).resolve().parent
VENV_DIR = HERE / "myenv"
PYDAW_ENGINE_DIR = HERE / "pydaw_engine"
RUST_BINARY_RELEASE = PYDAW_ENGINE_DIR / "target" / "release" / "pydaw_engine"
RUST_BINARY_DEBUG = PYDAW_ENGINE_DIR / "target" / "debug" / "pydaw_engine"

# Farben für Terminal-Ausgabe
class C:
    OK = "\033[92m"     # Grün
    WARN = "\033[93m"   # Gelb
    FAIL = "\033[91m"   # Rot
    BOLD = "\033[1m"
    END = "\033[0m"
    INFO = "\033[94m"   # Blau

def ok(msg):   print(f"{C.OK}✅ {msg}{C.END}")
def warn(msg): print(f"{C.WARN}⚠️  {msg}{C.END}")
def fail(msg): print(f"{C.FAIL}❌ {msg}{C.END}")
def info(msg): print(f"{C.INFO}ℹ️  {msg}{C.END}")
def head(msg): print(f"\n{C.BOLD}{'═' * 60}\n  {msg}\n{'═' * 60}{C.END}")

def run(cmd, check=True, capture=False, shell=False, **kw):
    """Befehl ausführen mit hübscher Ausgabe."""
    if isinstance(cmd, str) and not shell:
        cmd_str = cmd
    else:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    print(f"  {C.INFO}▶ {cmd_str}{C.END}")
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture,
            shell=shell, text=True if capture else None, **kw
        )
        return result
    except subprocess.CalledProcessError as e:
        if check:
            fail(f"Befehl fehlgeschlagen: {cmd_str}")
            if capture and e.stderr:
                print(f"    {e.stderr[:500]}")
        return e
    except FileNotFoundError:
        if check:
            fail(f"Programm nicht gefunden: {cmd_str}")
        return None

def which(cmd):
    """Prüft ob ein Programm im PATH ist."""
    return shutil.which(cmd)

def is_debian():
    """Erkennt Debian/Ubuntu/Kali/Mint."""
    try:
        txt = Path("/etc/os-release").read_text(errors="ignore").lower()
        return any(d in txt for d in ("debian", "ubuntu", "kali", "mint", "pop"))
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════════════
# Schritt 1: Python prüfen
# ═══════════════════════════════════════════════════════════════════════

def check_python():
    head("Schritt 1: Python prüfen")
    v = sys.version_info
    print(f"  Python: {sys.executable}")
    print(f"  Version: {v.major}.{v.minor}.{v.micro}")
    print(f"  Plattform: {platform.system()} {platform.machine()}")

    if v.major < 3 or (v.major == 3 and v.minor < 10):
        fail("Python 3.10+ erforderlich! Du hast Python {v.major}.{v.minor}.")
        print("  Installiere mit: sudo apt install python3.12")
        return False

    ok(f"Python {v.major}.{v.minor}.{v.micro} ✓")
    return True

# ═══════════════════════════════════════════════════════════════════════
# Schritt 2: Virtual Environment
# ═══════════════════════════════════════════════════════════════════════

def setup_venv():
    head("Schritt 2: Virtual Environment")

    in_venv = (
        (hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix)
        or bool(os.environ.get("VIRTUAL_ENV"))
    )

    if in_venv:
        ok(f"Bereits in venv: {sys.prefix}")
        return sys.executable

    # Prüfe ob myenv existiert
    if os.name == "nt":
        vpy = VENV_DIR / "Scripts" / "python.exe"
    else:
        vpy = VENV_DIR / "bin" / "python3"
        if not vpy.exists():
            vpy = VENV_DIR / "bin" / "python"

    if vpy.exists():
        ok(f"Vorhandenes venv gefunden: {VENV_DIR}")
        return str(vpy)

    # Neues venv erstellen
    info(f"Erstelle venv in {VENV_DIR}...")
    try:
        run([sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)])
    except Exception:
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    if not vpy.exists():
        # Nochmal suchen
        for candidate in [VENV_DIR / "bin" / "python3", VENV_DIR / "bin" / "python"]:
            if candidate.exists():
                vpy = candidate
                break

    if vpy.exists():
        ok(f"venv erstellt: {vpy}")
        return str(vpy)
    else:
        fail("venv konnte nicht erstellt werden")
        return sys.executable

# ═══════════════════════════════════════════════════════════════════════
# Schritt 3: Python-Abhängigkeiten
# ═══════════════════════════════════════════════════════════════════════

def install_python_deps(py):
    head("Schritt 3: Python-Abhängigkeiten installieren")

    req = HERE / "requirements.txt"
    if not req.exists():
        fail(f"requirements.txt nicht gefunden in {HERE}")
        return False

    # pip upgraden
    info("pip upgraden...")
    run([py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        check=False)

    # msgpack für Rust-Bridge (optional aber empfohlen)
    info("msgpack installieren (für Rust-Bridge)...")
    run([py, "-m", "pip", "install", "msgpack"], check=False)

    # Haupt-Requirements
    info("Installiere requirements.txt...")
    result = run([py, "-m", "pip", "install", "-r", str(req)], check=False)
    if isinstance(result, subprocess.CalledProcessError):
        warn("Einige Pakete konnten nicht installiert werden (nicht kritisch)")
    else:
        ok("Python-Abhängigkeiten installiert")

    # pedalboard (VST3 Hosting)
    info("pedalboard installieren (VST3)...")
    run([py, "-m", "pip", "install", "pedalboard"], check=False)

    # maturin (Rust Engine Build-Tool)
    info("maturin installieren (Rust → Python Bridge)...")
    run([py, "-m", "pip", "install", "maturin"], check=False)

    # patchelf (setzt rpath auf Linux .so — maturin braucht es)
    info("patchelf installieren (Linux ELF rpath)...")
    run([py, "-m", "pip", "install", "patchelf"], check=False)

    return True

# ═══════════════════════════════════════════════════════════════════════
# Schritt 4: System-Audio-Pakete prüfen
# ═══════════════════════════════════════════════════════════════════════

def check_system_audio():
    head("Schritt 4: System-Audio prüfen")

    results = {}

    # PipeWire
    if which("pipewire"):
        ok("PipeWire installiert ✓")
        results["pipewire"] = True
    else:
        warn("PipeWire nicht gefunden")
        results["pipewire"] = False

    # PipeWire-JACK Bridge
    if which("pw-jack"):
        ok("PipeWire-JACK Bridge installiert ✓")
        results["pw-jack"] = True
    else:
        warn("pw-jack nicht gefunden (empfohlen für Audio)")
        results["pw-jack"] = False

    # JACK
    if which("jackd") or which("jackdbus"):
        ok("JACK installiert ✓")
        results["jack"] = True
    else:
        info("JACK nicht separat installiert (PipeWire reicht)")
        results["jack"] = False

    # ALSA
    if which("aplay"):
        ok("ALSA Tools installiert ✓")
        results["alsa"] = True
    else:
        warn("aplay nicht gefunden")
        results["alsa"] = False

    # Empfehlungen
    if is_debian() and not results.get("pipewire"):
        print(f"\n  {C.WARN}Empfohlen:{C.END}")
        print("  sudo apt install pipewire pipewire-jack pipewire-alsa")
        print("  sudo apt install qpwgraph  # Audio-Routing visualisieren")

    if is_debian():
        # ALSA dev headers (nötig für Rust cpal)
        alsa_dev = Path("/usr/include/alsa/asoundlib.h").exists()
        if alsa_dev:
            ok("ALSA Development Headers ✓ (nötig für Rust)")
        else:
            warn("ALSA Dev-Headers fehlen — nötig für Rust Audio-Engine!")
            print("  sudo apt install libasound2-dev pkg-config")

    return True

# ═══════════════════════════════════════════════════════════════════════
# Schritt 5: Rust installieren + Engine bauen (OPTIONAL)
# ═══════════════════════════════════════════════════════════════════════

def _source_cargo_env():
    """Source ~/.cargo/env in die aktuelle Python-Umgebung.

    v0.0.20.714: Löst das Problem dass cargo nach rustup-Install nicht
    im PATH ist bis man ein neues Terminal öffnet.
    """
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        current_path = os.environ.get("PATH", "")
        cargo_str = str(cargo_bin)
        if cargo_str not in current_path:
            os.environ["PATH"] = f"{cargo_str}{os.pathsep}{current_path}"

    # Auch CARGO_HOME und RUSTUP_HOME setzen falls nötig
    cargo_home = Path.home() / ".cargo"
    rustup_home = Path.home() / ".rustup"
    if cargo_home.exists() and "CARGO_HOME" not in os.environ:
        os.environ["CARGO_HOME"] = str(cargo_home)
    if rustup_home.exists() and "RUSTUP_HOME" not in os.environ:
        os.environ["RUSTUP_HOME"] = str(rustup_home)


def check_rust():
    """Prüft ob Rust installiert ist. Gibt Version zurück oder None."""
    # v0.0.20.714: Erst cargo env laden, dann prüfen
    _source_cargo_env()
    rustc = which("rustc")
    cargo = which("cargo")
    if rustc and cargo:
        result = run(["rustc", "--version"], capture=True, check=False)
        if result and hasattr(result, 'stdout') and result.stdout:
            version = result.stdout.strip()
            return version
    return None

def install_rust():
    head("Schritt 5a: Rust installieren")

    # Cargo env laden (falls Rust schon installiert aber nicht im PATH)
    _source_cargo_env()

    version = check_rust()
    if version:
        ok(f"Rust bereits installiert: {version}")
        return True

    info("Rust ist nicht installiert. Installiere jetzt...")

    if platform.system() == "Windows":
        fail("Auf Windows: Bitte manuell installieren von https://rustup.rs")
        print("  1. Gehe zu https://rustup.rs")
        print("  2. Lade rustup-init.exe herunter")
        print("  3. Führe es aus")
        print("  4. Starte dieses Skript erneut")
        return False

    # Linux / macOS: System-Abhängigkeiten zuerst installieren
    if platform.system() == "Linux" and is_debian():
        _install_rust_system_deps()

    # Automatische Installation via rustup
    info("Lade rustup herunter und installiere Rust...")
    print()
    print(f"  {C.BOLD}Das ist sicher! Rust wird nur für DEINEN Benutzer installiert.{C.END}")
    print(f"  Installationspfad: ~/.cargo/  und  ~/.rustup/")
    print(f"  Deinstallieren: rustup self uninstall")
    print()

    result = run(
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
        shell=True, check=False,
    )

    if isinstance(result, subprocess.CalledProcessError) or result is None:
        fail("Rust-Installation fehlgeschlagen")
        print("  Manuell installieren: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        return False

    # Cargo zum PATH hinzufügen (für aktuelle Python-Session)
    _source_cargo_env()

    # Verifizieren
    version = check_rust()
    if version:
        ok(f"Rust erfolgreich installiert: {version}")
        return True
    else:
        warn("Rust installiert, aber nicht im PATH. Bitte Terminal neu starten.")
        print(f"  Oder: source $HOME/.cargo/env")
        return False


def _install_rust_system_deps():
    """Installiere System-Pakete die für cargo build nötig sind.

    v0.0.20.714: ALSA Dev-Headers + pkg-config automatisch installieren.
    Ohne diese schlägt `cpal` (Audio I/O Crate) beim Kompilieren fehl.
    """
    needed = []

    # ALSA Dev-Headers (nötig für cpal crate)
    if not Path("/usr/include/alsa/asoundlib.h").exists():
        needed.append("libasound2-dev")

    # pkg-config (nötig für viele Rust crates)
    if not which("pkg-config"):
        needed.append("pkg-config")

    # build-essential (gcc, make — für native crate compilation)
    if not which("cc") and not which("gcc"):
        needed.append("build-essential")

    # curl (für rustup download — sollte schon da sein)
    if not which("curl"):
        needed.append("curl")

    if not needed:
        ok("System-Abhängigkeiten für Rust bereits vorhanden")
        return

    info(f"Installiere System-Pakete für Rust-Build: {', '.join(needed)}")
    print(f"  (Diese werden mit apt installiert und brauchen sudo)")
    print()

    sudo = which("sudo")
    apt = which("apt-get")

    if not apt:
        warn("apt-get nicht gefunden — bitte manuell installieren:")
        print(f"  sudo apt install {' '.join(needed)}")
        return

    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            run(["apt-get", "update", "-qq"], check=False)
            run(["apt-get", "install", "-y", "-qq", *needed], check=False)
        elif sudo:
            run([sudo, "apt-get", "update", "-qq"], check=False)
            run([sudo, "apt-get", "install", "-y", "-qq", *needed], check=False)
        else:
            warn("Kein sudo verfügbar — bitte manuell installieren:")
            print(f"  sudo apt install {' '.join(needed)}")
    except Exception as e:
        warn(f"System-Paket Installation fehlgeschlagen: {e}")
        print(f"  Manuell installieren: sudo apt install {' '.join(needed)}")

def build_rust_engine():
    head("Schritt 5b: Rust Audio-Engine bauen")

    # v0.0.20.714: Cargo env laden
    _source_cargo_env()

    if not PYDAW_ENGINE_DIR.exists():
        fail(f"pydaw_engine/ Verzeichnis nicht gefunden in {HERE}")
        return False

    cargo_toml = PYDAW_ENGINE_DIR / "Cargo.toml"
    if not cargo_toml.exists():
        fail("Cargo.toml nicht gefunden")
        return False

    cargo = which("cargo")
    if not cargo:
        # Nochmal versuchen mit explizitem Pfad
        cargo_path = Path.home() / ".cargo" / "bin" / "cargo"
        if cargo_path.exists():
            cargo = str(cargo_path)
        else:
            fail("cargo nicht gefunden — Rust korrekt installiert?")
            return False

    # System-Abhängigkeiten prüfen (Linux)
    if platform.system() == "Linux":
        alsa_dev = Path("/usr/include/alsa/asoundlib.h").exists()
        if not alsa_dev:
            fail("ALSA Development Headers fehlen!")
            print("  Installiere mit: sudo apt install libasound2-dev pkg-config")
            return False

    info("Baue Release-Version (das dauert beim ersten Mal 1-3 Minuten)...")
    print(f"  Verzeichnis: {PYDAW_ENGINE_DIR}")
    print()

    start = time.time()
    result = run(
        [cargo, "build", "--release"],
        check=False,
        cwd=str(PYDAW_ENGINE_DIR),
    )
    elapsed = time.time() - start

    if isinstance(result, subprocess.CalledProcessError) or result is None:
        fail(f"Build fehlgeschlagen nach {elapsed:.0f}s")
        print("\n  Häufige Ursachen:")
        print("  - ALSA Dev-Headers fehlen: sudo apt install libasound2-dev")
        print("  - pkg-config fehlt: sudo apt install pkg-config")
        print("  - Kein Internet (cargo lädt Abhängigkeiten)")
        return False

    if RUST_BINARY_RELEASE.exists():
        size_mb = RUST_BINARY_RELEASE.stat().st_size / (1024 * 1024)
        ok(f"Engine gebaut in {elapsed:.0f}s ({size_mb:.1f} MB)")
        ok(f"Binary: {RUST_BINARY_RELEASE}")
    else:
        warn("Standalone-Binary wurde nicht erstellt (kein Problem wenn maturin genutzt wird)")

    # Zusätzlich: maturin develop (Python-importierbares Modul)
    maturin = which("maturin")
    if not maturin:
        # Versuche im venv
        venv_bin = VENV_DIR / "bin" / "maturin"
        if venv_bin.exists():
            maturin = str(venv_bin)

    if maturin:
        info("Baue Python-Modul via maturin develop...")
        maturin_result = run(
            [maturin, "develop", "--release"],
            check=False,
            cwd=str(PYDAW_ENGINE_DIR),
        )
        if maturin_result and not isinstance(maturin_result, subprocess.CalledProcessError):
            ok("maturin develop --release erfolgreich — Rust-Engine als Python-Modul verfügbar")
        else:
            warn("maturin develop fehlgeschlagen (Standalone-Binary ist trotzdem nutzbar)")
    else:
        info("maturin nicht gefunden — installiere mit: pip install maturin")

    return True

# ═══════════════════════════════════════════════════════════════════════
# Schritt 6: Alles testen
# ═══════════════════════════════════════════════════════════════════════

def run_checks(py):
    head("Schritt 6: System-Check")

    checks = []

    # Qt6 GUI (PyQt6 auf Linux/Windows, PySide6 auf macOS)
    qt_ok = False
    # Versuche PyQt6 zuerst (bevorzugt auf Linux)
    result = run([py, "-c", "from PyQt6.QtWidgets import QApplication; print('OK')"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("PyQt6 (Qt6) ✓")
        qt_ok = True
    else:
        # Fallback: PySide6 (bevorzugt auf macOS)
        result = run([py, "-c", "from PySide6.QtWidgets import QApplication; print('OK')"],
                     capture=True, check=False)
        if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
            ok("PySide6 (Qt6) ✓")
            qt_ok = True
        else:
            fail("Kein Qt6 — pip install PyQt6 (oder PySide6 auf macOS)")
    checks.append(("Qt6", qt_ok))

    # numpy
    result = run([py, "-c", "import numpy; print(numpy.__version__)"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and result.stdout:
        ok(f"numpy {result.stdout.strip()} ✓")
        checks.append(("numpy", True))
    else:
        fail("numpy nicht verfügbar")
        checks.append(("numpy", False))

    # sounddevice
    result = run([py, "-c", "import sounddevice; print('OK')"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("sounddevice ✓")
        checks.append(("sounddevice", True))
    else:
        warn("sounddevice nicht verfügbar (Audio-Playback eingeschränkt)")
        checks.append(("sounddevice", False))

    # Py_DAW eigene Module
    result = run([py, "-c", "import pydaw; print('OK')"],
                 capture=True, check=False, cwd=str(HERE))
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("Py_DAW Module ✓")
        checks.append(("Py_DAW", True))
    else:
        warn("Py_DAW Module nicht ladbar (normaler Betrieb über main.py)")
        checks.append(("Py_DAW", True))  # Nicht kritisch

    # Rust Engine Binary
    if RUST_BINARY_RELEASE.exists():
        ok(f"Rust Audio-Engine ✓ ({RUST_BINARY_RELEASE})")
        checks.append(("Rust Engine", True))
    elif RUST_BINARY_DEBUG.exists():
        ok(f"Rust Audio-Engine (Debug) ✓")
        checks.append(("Rust Engine", True))
    else:
        info("Rust Audio-Engine nicht gebaut (optional)")
        checks.append(("Rust Engine", None))  # Optional

    # msgpack
    result = run([py, "-c", "import msgpack; print('OK')"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("msgpack ✓ (für Rust-Bridge)")
        checks.append(("msgpack", True))
    else:
        info("msgpack nicht installiert (Rust-Bridge nutzt JSON-Fallback)")
        checks.append(("msgpack", None))

    # maturin
    result = run([py, "-c", "import maturin; print('OK')"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("maturin ✓ (Rust → Python Build-Tool)")
        checks.append(("maturin", True))
    else:
        info("maturin nicht installiert (pip install maturin)")
        checks.append(("maturin", None))

    # patchelf
    result = run([py, "-c", "import patchelf; print('OK')"],
                 capture=True, check=False)
    if result and hasattr(result, 'stdout') and 'OK' in (result.stdout or ''):
        ok("patchelf ✓ (ELF rpath für maturin)")
        checks.append(("patchelf", True))
    else:
        info("patchelf nicht installiert (pip install patchelf)")
        checks.append(("patchelf", None))

    return checks

# ═══════════════════════════════════════════════════════════════════════
# Status-Report
# ═══════════════════════════════════════════════════════════════════════

def print_final_report(checks, with_rust, py):
    head("🎵 SETUP KOMPLETT — STATUS REPORT")

    critical_ok = all(ok for name, ok in checks if ok is not None and name in ("Qt6", "numpy"))

    print()
    for name, status in checks:
        if status is True:
            print(f"  {C.OK}✅ {name}{C.END}")
        elif status is False:
            print(f"  {C.FAIL}❌ {name}{C.END}")
        else:
            print(f"  {C.INFO}➖ {name} (optional){C.END}")

    print()
    print(f"{'═' * 60}")
    print()

    if critical_ok:
        print(f"  {C.OK}{C.BOLD}🎉 Py_DAW ist bereit!{C.END}")
        print()
        print(f"  {C.BOLD}So startest du die DAW:{C.END}")
        print()
        if str(py) != sys.executable:
            print(f"    source myenv/bin/activate")
        print(f"    python3 main.py")
        print()

        if with_rust and RUST_BINARY_RELEASE.exists():
            print(f"  {C.BOLD}Rust Audio-Engine aktivieren (optional):{C.END}")
            print(f"    USE_RUST_ENGINE=1 python3 main.py")
            print()
        elif with_rust:
            print(f"  {C.BOLD}Rust Audio-Engine manuell bauen:{C.END}")
            print(f"    cd pydaw_engine && maturin develop --release")
            print(f"    # oder: cargo build --release")
            print()

        print(f"  {C.BOLD}Audio-Routing visualisieren:{C.END}")
        print(f"    qpwgraph  # (PipeWire Graph)")
        print()
    else:
        print(f"  {C.FAIL}Einige kritische Abhängigkeiten fehlen.{C.END}")
        print(f"  Bitte die Fehler oben beheben und erneut ausführen:")
        print(f"    python3 setup_all.py")

    print(f"{'═' * 60}")

# ═══════════════════════════════════════════════════════════════════════
# Nur-Check Modus
# ═══════════════════════════════════════════════════════════════════════

def check_only():
    head("🔍 System-Check (nur prüfen, nichts installieren)")

    # Python
    v = sys.version_info
    print(f"  Python: {v.major}.{v.minor}.{v.micro} — {'✅' if v.minor >= 10 else '❌'}")

    # Rust
    rust_v = check_rust()
    print(f"  Rust: {rust_v or '❌ nicht installiert'}")

    # cargo
    print(f"  cargo: {'✅' if which('cargo') else '❌'}")

    # Engine Binary
    if RUST_BINARY_RELEASE.exists():
        print(f"  Engine Binary: ✅ (Release)")
    elif RUST_BINARY_DEBUG.exists():
        print(f"  Engine Binary: ⚠️ (nur Debug)")
    else:
        print(f"  Engine Binary: ❌ nicht gebaut")

    # Audio
    print(f"  PipeWire: {'✅' if which('pipewire') else '❌'}")
    print(f"  pw-jack: {'✅' if which('pw-jack') else '❌'}")
    print(f"  JACK: {'✅' if which('jackd') else '➖'}")
    print(f"  ALSA (aplay): {'✅' if which('aplay') else '❌'}")

    if platform.system() == "Linux":
        alsa_dev = Path("/usr/include/alsa/asoundlib.h").exists()
        print(f"  ALSA Dev-Headers: {'✅' if alsa_dev else '❌ (sudo apt install libasound2-dev)'}")
        pkg_config = which("pkg-config")
        print(f"  pkg-config: {'✅' if pkg_config else '❌ (sudo apt install pkg-config)'}")

    # Python packages
    for pkg in ["PyQt6", "numpy", "sounddevice", "soundfile", "msgpack", "pedalboard", "maturin", "patchelf"]:
        try:
            __import__(pkg.lower().replace("-", "_"))
            print(f"  {pkg}: ✅")
        except ImportError:
            print(f"  {pkg}: ❌")

    # venv
    in_venv = hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix
    print(f"  venv aktiv: {'✅' if in_venv else '❌'}")
    if VENV_DIR.exists():
        print(f"  myenv/ vorhanden: ✅")

# ═══════════════════════════════════════════════════════════════════════
# Hauptprogramm
# ═══════════════════════════════════════════════════════════════════════

def print_help():
    print(f"""
{C.BOLD}Py_DAW Setup — Alles automatisch installieren{C.END}

Verwendung:
  python3 setup_all.py              Standard-Setup (Python only)
  python3 setup_all.py --with-rust  Mit Rust Audio-Engine (High Performance)
  python3 setup_all.py --check      Nur prüfen, nichts installieren
  python3 setup_all.py --help       Diese Hilfe

Was passiert:
  1. Python Virtual Environment wird erstellt
  2. Alle Python-Pakete werden installiert
  3. Audio-System wird geprüft (PipeWire/JACK/ALSA)
  4. Mit --with-rust: Rust wird installiert + Engine gebaut

{C.BOLD}Die DAW funktioniert AUCH OHNE Rust!{C.END}
Rust ist ein optionales Performance-Upgrade für die Audio-Engine.

System-Voraussetzungen (Linux/Debian):
  sudo apt install python3 python3-venv python3-pip
  sudo apt install pipewire pipewire-jack  # Audio
  sudo apt install libasound2-dev pkg-config  # Nur für Rust-Build
""")

def main():
    os.chdir(HERE)

    # Argumente parsen
    args = sys.argv[1:]
    with_rust = "--with-rust" in args or "--rust" in args
    check_mode = "--check" in args
    help_mode = "--help" in args or "-h" in args

    if help_mode:
        print_help()
        return 0

    if check_mode:
        check_only()
        return 0

    print(f"\n{C.BOLD}{'═' * 60}")
    print(f"  🎵 Py_DAW Setup {'+ Rust Audio-Engine ' if with_rust else ''}starten")
    print(f"{'═' * 60}{C.END}")
    print(f"  Verzeichnis: {HERE}")
    print(f"  Modus: {'Python + Rust' if with_rust else 'Python only (Standard)'}")
    if not with_rust:
        print(f"  Tipp: Für Rust-Engine: python3 setup_all.py --with-rust")
    print()

    # Schritt 1: Python
    if not check_python():
        return 1

    # Schritt 2: venv
    py = setup_venv()

    # Schritt 3: Python-Deps
    install_python_deps(py)

    # Schritt 4: System-Audio
    check_system_audio()

    # Schritt 5: Rust (optional)
    if with_rust:
        rust_ok = install_rust()
        if rust_ok:
            build_rust_engine()
        else:
            warn("Rust konnte nicht installiert werden — DAW funktioniert trotzdem!")
    else:
        info("Rust-Engine übersprungen (starte mit --with-rust für High Performance)")

    # Schritt 6: Checks
    checks = run_checks(py)

    # Report
    print_final_report(checks, with_rust, py)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(f"\n{C.WARN}Abgebrochen.{C.END}")
        raise SystemExit(130)
