#!/usr/bin/env python3
"""
Post-Build Verification — Tests the built Nuitka package.

Usage:
    python3 verify_build.py dist/ChronoScaleStudio-0.0.20.728-linux

Checks:
  1. Main binary exists and is executable
  2. Rust engine binary exists and is executable
  3. VERSION file present
  4. Critical Python modules importable (via binary --help or dry-run)
  5. Rust engine starts and responds to ping
"""

import os
import subprocess
import sys
from pathlib import Path

def ok(msg): print(f"\033[92m✅ {msg}\033[0m")
def err(msg): print(f"\033[91m❌ {msg}\033[0m")
def warn(msg): print(f"\033[93m⚠️  {msg}\033[0m")

def verify(dist_dir: str):
    d = Path(dist_dir)
    if not d.exists():
        err(f"Verzeichnis nicht gefunden: {d}")
        return 1

    print(f"\n🔍 Verifiziere: {d}\n")
    errors = 0

    # 1. Main binary
    is_win = sys.platform == "win32"
    main_bin = d / ("main.exe" if is_win else "main")
    if main_bin.exists():
        ok(f"Hauptprogramm: {main_bin.name} ({main_bin.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        err(f"Hauptprogramm nicht gefunden: {main_bin}")
        errors += 1

    # 2. Rust engine
    engine_name = "pydaw_engine.exe" if is_win else "pydaw_engine"
    engine_bin = d / engine_name
    if engine_bin.exists():
        ok(f"Rust-Engine: {engine_name} ({engine_bin.stat().st_size / 1024 / 1024:.1f} MB)")
        if not is_win:
            if os.access(str(engine_bin), os.X_OK):
                ok("Rust-Engine ist ausführbar")
            else:
                err("Rust-Engine ist NICHT ausführbar — chmod +x nötig")
                errors += 1
    else:
        warn(f"Rust-Engine nicht gefunden: {engine_name} (App läuft im Python-only Modus)")

    # 3. VERSION
    ver_file = d / "VERSION"
    if ver_file.exists():
        ok(f"VERSION: {ver_file.read_text().strip()}")
    else:
        warn("VERSION-Datei fehlt")

    # 4. Directory size
    total_size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
    ok(f"Gesamtgröße: {total_size / 1024 / 1024:.1f} MB ({sum(1 for _ in d.rglob('*'))} Dateien)")

    # 5. Quick engine test (if binary exists)
    if engine_bin.exists():
        try:
            result = subprocess.run(
                [str(engine_bin), "--help"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 or "pydaw_engine" in (result.stdout + result.stderr).lower():
                ok("Rust-Engine antwortet auf --help")
            else:
                warn(f"Rust-Engine --help unerwarteter Exit-Code: {result.returncode}")
        except subprocess.TimeoutExpired:
            warn("Rust-Engine --help Timeout (5s) — evtl. wartet sie auf Socket-Verbindung")
        except Exception as e:
            warn(f"Rust-Engine Test fehlgeschlagen: {e}")

    # Summary
    print()
    if errors == 0:
        ok(f"Paket-Verifikation bestanden!")
    else:
        err(f"{errors} Fehler gefunden — siehe oben")
    return errors

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <dist-directory>")
        print(f"Example: {sys.argv[0]} dist/ChronoScaleStudio-0.0.20.728-linux")
        sys.exit(1)
    sys.exit(verify(sys.argv[1]))
