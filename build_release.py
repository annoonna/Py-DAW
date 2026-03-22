#!/usr/bin/env python3
"""
Py_DAW Release Builder — One script to build them all.

v0.0.20.728

Usage:
    python3 build_release.py              # Build for current OS
    python3 build_release.py --check      # Only check dependencies
    python3 build_release.py --skip-rust  # Skip Rust build (use existing)
    python3 build_release.py --debug      # Build with debug info

This script:
  1. Detects your OS (Linux / macOS / Windows)
  2. Checks + installs all build dependencies
  3. Builds the Rust audio engine (cargo build --release)
  4. Runs Nuitka to create a standalone Python binary
  5. Copies the Rust binary into the Nuitka dist folder
  6. Creates the final distributable package:
     - Linux:   .tar.gz + optional AppImage
     - macOS:   .app bundle + optional .dmg
     - Windows: .exe (onefile or folder)

Cross-compilation is NOT possible — run this on each target OS.
For automated builds on all 3 platforms, use the included
  .github/workflows/build-release.yml

Requirements:
  - Python 3.10+
  - Rust toolchain (rustup)
  - Nuitka (pip install nuitka)
  - Qt6 (PyQt6)
  - OS-specific: gcc/clang, ALSA dev headers (Linux), Xcode CLI (macOS)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Constants ──

SCRIPT_DIR = Path(__file__).parent.resolve()
PYDAW_DIR = SCRIPT_DIR / "pydaw"
ENGINE_DIR = SCRIPT_DIR / "pydaw_engine"
MAIN_PY = SCRIPT_DIR / "main.py"
VERSION_FILE = SCRIPT_DIR / "VERSION"

APP_NAME = "ChronoScaleStudio"
APP_ID = "com.pydaw.chronoscalestudio"
ICON_NAME = "logo"

# Nuitka output directory
DIST_DIR = SCRIPT_DIR / "dist"
BUILD_DIR = SCRIPT_DIR / "build_nuitka"

# ── Colors ──

class C:
    OK = "\033[92m"
    WARN = "\033[93m"
    ERR = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"
    INFO = "\033[96m"

def ok(msg): print(f"{C.OK}✅ {msg}{C.END}")
def warn(msg): print(f"{C.WARN}⚠️  {msg}{C.END}")
def err(msg): print(f"{C.ERR}❌ {msg}{C.END}")
def info(msg): print(f"{C.INFO}ℹ️  {msg}{C.END}")
def header(msg):
    print(f"\n{C.BOLD}{'═' * 60}")
    print(f"  {msg}")
    print(f"{'═' * 60}{C.END}\n")

# ── Platform Detection ──

def detect_platform() -> str:
    s = sys.platform
    if s.startswith("linux"):
        return "linux"
    elif s == "darwin":
        return "macos"
    elif s == "win32":
        return "windows"
    else:
        warn(f"Unknown platform: {s}, assuming Linux")
        return "linux"

def get_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except Exception:
        return "0.0.0"

def run(cmd: list[str], check: bool = True, capture: bool = False, **kw) -> subprocess.CompletedProcess:
    """Run a command with logging."""
    print(f"  {C.INFO}▶ {' '.join(str(c) for c in cmd)}{C.END}")
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, **kw)

def which(name: str) -> Optional[str]:
    return shutil.which(name)

# ── Dependency Checks ──

def check_python() -> bool:
    header("Python prüfen")
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    else:
        err(f"Python {v.major}.{v.minor} — mindestens 3.10 nötig!")
        return False

def check_rust() -> bool:
    header("Rust prüfen")
    if which("rustc") and which("cargo"):
        result = run(["rustc", "--version"], capture=True)
        ok(f"Rust: {result.stdout.strip()}")
        return True
    else:
        warn("Rust nicht gefunden")
        info("Installiere mit: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        return False

def check_nuitka() -> bool:
    header("Nuitka prüfen")
    try:
        result = run([sys.executable, "-m", "nuitka", "--version"], capture=True)
        ok(f"Nuitka: {result.stdout.strip().splitlines()[0]}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        warn("Nuitka nicht installiert")
        info("Installiere mit: pip install nuitka ordered-set")
        try:
            run([sys.executable, "-m", "pip", "install", "nuitka", "ordered-set"])
            ok("Nuitka installiert")
            return True
        except Exception:
            err("Nuitka Installation fehlgeschlagen")
            return False

def check_qt6() -> bool:
    try:
        import PyQt6
        ok(f"PyQt6 verfügbar")
        return True
    except ImportError:
        err("PyQt6 nicht installiert!")
        return False

def check_platform_deps(plat: str) -> bool:
    header(f"Plattform-Abhängigkeiten ({plat})")

    if plat == "linux":
        deps_ok = True
        for tool in ["gcc", "pkg-config"]:
            if which(tool):
                ok(f"{tool}")
            else:
                warn(f"{tool} fehlt — sudo apt install build-essential pkg-config")
                deps_ok = False
        # ALSA headers for Rust cpal
        alsa_h = Path("/usr/include/alsa/asoundlib.h")
        if alsa_h.exists():
            ok("ALSA Dev Headers")
        else:
            warn("libasound2-dev fehlt — sudo apt install libasound2-dev")
            deps_ok = False
        return deps_ok

    elif plat == "macos":
        if which("clang"):
            ok("Xcode CLI Tools")
            return True
        else:
            warn("Xcode CLI Tools fehlen — xcode-select --install")
            return False

    elif plat == "windows":
        if which("cl") or which("gcc"):
            ok("C Compiler")
            return True
        else:
            warn("C Compiler fehlt — installiere Visual Studio Build Tools")
            return False

    return True

# ── Build Steps ──

def build_rust(plat: str) -> Optional[Path]:
    """Build the Rust engine. Returns path to binary."""
    header("Rust Audio-Engine bauen")

    if not ENGINE_DIR.exists():
        err(f"pydaw_engine/ nicht gefunden in {SCRIPT_DIR}")
        return None

    # Determine target binary name
    bin_name = "pydaw_engine.exe" if plat == "windows" else "pydaw_engine"
    release_dir = ENGINE_DIR / "target" / "release"
    bin_path = release_dir / bin_name

    info("cargo build --release ...")
    t0 = time.time()
    try:
        run(["cargo", "build", "--release"], cwd=str(ENGINE_DIR))
    except subprocess.CalledProcessError as e:
        err(f"Rust Build fehlgeschlagen! (exit {e.returncode})")
        return None

    elapsed = time.time() - t0
    if bin_path.exists():
        size_mb = bin_path.stat().st_size / (1024 * 1024)
        ok(f"Engine gebaut in {elapsed:.0f}s ({size_mb:.1f} MB): {bin_path}")
        return bin_path
    else:
        err(f"Binary nicht gefunden: {bin_path}")
        return None

def build_nuitka(plat: str, debug: bool = False) -> Optional[Path]:
    """Build the Python app with Nuitka. Returns path to dist dir."""
    header("Nuitka Standalone-Build")

    if not MAIN_PY.exists():
        err(f"main.py nicht gefunden: {MAIN_PY}")
        return None

    version = get_version()
    dist_name = f"{APP_NAME}-{version}-{plat}"
    output_dir = DIST_DIR / dist_name

    # Base Nuitka arguments
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        f"--output-dir={BUILD_DIR}",
        "--assume-yes-for-download",
        "--remove-output",
        "--no-pyi-file",
        # Include the whole pydaw package
        "--include-package=pydaw",
        # Include data files (icons, templates, docs)
        f"--include-data-dir={PYDAW_DIR}/notation=pydaw/notation",
    ]

    # Include PROJECT_DOCS if present
    docs_dir = SCRIPT_DIR / "PROJECT_DOCS"
    if docs_dir.exists():
        cmd.append(f"--include-data-dir={docs_dir}=PROJECT_DOCS")

    # Include docs/ if present
    extra_docs = SCRIPT_DIR / "docs"
    if extra_docs.exists():
        cmd.append(f"--include-data-dir={extra_docs}=docs")

    # Platform-specific flags
    if plat == "windows":
        icon = SCRIPT_DIR / f"{ICON_NAME}.ico"
        if icon.exists():
            cmd.append(f"--windows-icon-from-ico={icon}")
        cmd.append("--windows-console-mode=attach")

    elif plat == "macos":
        cmd.append("--macos-create-app-bundle")
        icon = SCRIPT_DIR / f"{ICON_NAME}.icns"
        if icon.exists():
            cmd.append(f"--macos-app-icon={icon}")
        cmd.append(f"--macos-app-name={APP_NAME}")

    elif plat == "linux":
        icon = SCRIPT_DIR / f"{ICON_NAME}.png"
        if icon.exists():
            cmd.append(f"--linux-icon={icon}")

    # Debug mode
    if debug:
        cmd.append("--debug")
    else:
        cmd.append("--lto=yes")

    # Product info
    cmd.extend([
        f"--product-name={APP_NAME}",
        f"--product-version={version}",
        f"--company-name=UKNS UG",
        f"--file-description=Py_DAW - Open Source Digital Audio Workstation",
    ])

    # Main entry point
    cmd.append(str(MAIN_PY))

    info("Nuitka Build starten (das dauert 3-10 Minuten)...")
    t0 = time.time()
    try:
        run(cmd)
    except subprocess.CalledProcessError as e:
        err(f"Nuitka Build fehlgeschlagen! (exit {e.returncode})")
        return None

    elapsed = time.time() - t0

    # Find the output directory
    # Nuitka creates main.dist/ in the output dir
    nuitka_dist = BUILD_DIR / "main.dist"
    if not nuitka_dist.exists():
        # Try alternative names
        for candidate in BUILD_DIR.iterdir():
            if candidate.is_dir() and candidate.name.endswith(".dist"):
                nuitka_dist = candidate
                break

    if not nuitka_dist.exists():
        err(f"Nuitka Ausgabe nicht gefunden in {BUILD_DIR}")
        return None

    # Move to final location
    if output_dir.exists():
        shutil.rmtree(output_dir)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(nuitka_dist), str(output_dir))

    ok(f"Nuitka Build fertig in {elapsed:.0f}s: {output_dir}")
    return output_dir

def embed_rust_binary(dist_dir: Path, rust_binary: Path, plat: str) -> bool:
    """Copy the Rust engine binary into the Nuitka dist folder."""
    header("Rust-Binary einbetten")

    bin_name = rust_binary.name
    target = dist_dir / bin_name

    try:
        shutil.copy2(str(rust_binary), str(target))
        # Make executable on Unix
        if plat != "windows":
            os.chmod(str(target), 0o755)
        ok(f"Rust-Binary kopiert: {target}")
        return True
    except Exception as e:
        err(f"Kopieren fehlgeschlagen: {e}")
        return False

def create_package(dist_dir: Path, plat: str) -> Optional[Path]:
    """Create the final distributable package."""
    header("Paket erstellen")

    version = get_version()
    base_name = f"{APP_NAME}-{version}-{plat}-{platform.machine()}"

    if plat == "linux":
        # Create .tar.gz
        archive = DIST_DIR / f"{base_name}.tar.gz"
        info(f"Erstelle {archive.name} ...")
        try:
            import tarfile
            with tarfile.open(str(archive), "w:gz") as tar:
                tar.add(str(dist_dir), arcname=dist_dir.name)
            size_mb = archive.stat().st_size / (1024 * 1024)
            ok(f"Linux-Paket: {archive} ({size_mb:.1f} MB)")
            return archive
        except Exception as e:
            err(f"tar.gz Erstellung fehlgeschlagen: {e}")
            return None

    elif plat == "macos":
        # Create .dmg (if create-dmg available, otherwise .tar.gz)
        if which("create-dmg"):
            dmg = DIST_DIR / f"{base_name}.dmg"
            info(f"Erstelle {dmg.name} ...")
            try:
                run([
                    "create-dmg",
                    "--volname", APP_NAME,
                    "--window-pos", "200", "120",
                    "--window-size", "600", "400",
                    "--app-drop-link", "425", "120",
                    str(dmg),
                    str(dist_dir),
                ])
                ok(f"macOS DMG: {dmg}")
                return dmg
            except Exception:
                warn("create-dmg fehlgeschlagen, erstelle .tar.gz statt .dmg")

        # Fallback: tar.gz
        archive = DIST_DIR / f"{base_name}.tar.gz"
        import tarfile
        with tarfile.open(str(archive), "w:gz") as tar:
            tar.add(str(dist_dir), arcname=dist_dir.name)
        ok(f"macOS-Paket: {archive}")
        return archive

    elif plat == "windows":
        # Create .zip
        archive = DIST_DIR / f"{base_name}.zip"
        info(f"Erstelle {archive.name} ...")
        try:
            import zipfile
            with zipfile.ZipFile(str(archive), "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(str(dist_dir)):
                    for f in files:
                        fp = os.path.join(root, f)
                        arcname = os.path.relpath(fp, str(dist_dir.parent))
                        zf.write(fp, arcname)
            size_mb = archive.stat().st_size / (1024 * 1024)
            ok(f"Windows-Paket: {archive} ({size_mb:.1f} MB)")
            return archive
        except Exception as e:
            err(f"ZIP Erstellung fehlgeschlagen: {e}")
            return None

    return None

# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Py_DAW Release Builder")
    parser.add_argument("--check", action="store_true", help="Nur Abhängigkeiten prüfen")
    parser.add_argument("--skip-rust", action="store_true", help="Rust-Build überspringen")
    parser.add_argument("--debug", action="store_true", help="Debug-Build (langsamer, mehr Info)")
    parser.add_argument("--skip-package", action="store_true", help="Paketierung überspringen")
    args = parser.parse_args()

    plat = detect_platform()
    version = get_version()

    header(f"Py_DAW Release Builder v{version}")
    info(f"Plattform: {plat} ({platform.machine()})")
    info(f"Python: {sys.version}")
    info(f"Verzeichnis: {SCRIPT_DIR}")

    # ── Step 1: Check dependencies ──
    all_ok = True
    all_ok &= check_python()
    all_ok &= check_rust() or args.skip_rust
    all_ok &= check_nuitka()
    all_ok &= check_qt6()
    all_ok &= check_platform_deps(plat)

    if args.check:
        if all_ok:
            ok("Alle Abhängigkeiten vorhanden!")
        else:
            err("Einige Abhängigkeiten fehlen — siehe oben")
        return 0 if all_ok else 1

    if not all_ok:
        err("Abhängigkeiten fehlen! Nutze --check für Details.")
        return 1

    # ── Step 2: Build Rust engine ──
    rust_binary = None
    if not args.skip_rust:
        rust_binary = build_rust(plat)
        if rust_binary is None:
            err("Rust-Build fehlgeschlagen — Abbruch")
            return 1
    else:
        # Try to find existing binary
        bin_name = "pydaw_engine.exe" if plat == "windows" else "pydaw_engine"
        candidate = ENGINE_DIR / "target" / "release" / bin_name
        if candidate.exists():
            rust_binary = candidate
            ok(f"Vorhandene Rust-Binary: {rust_binary}")
        else:
            warn("Keine Rust-Binary gefunden — Engine wird nicht eingebettet")

    # ── Step 3: Build with Nuitka ──
    dist_dir = build_nuitka(plat, debug=args.debug)
    if dist_dir is None:
        err("Nuitka-Build fehlgeschlagen — Abbruch")
        return 1

    # ── Step 4: Embed Rust binary ──
    if rust_binary:
        if not embed_rust_binary(dist_dir, rust_binary, plat):
            warn("Rust-Binary konnte nicht eingebettet werden — App läuft ohne Rust-Engine")

    # ── Step 5: Copy VERSION file ──
    try:
        shutil.copy2(str(VERSION_FILE), str(dist_dir / "VERSION"))
    except Exception:
        pass

    # ── Step 6: Create package ──
    if not args.skip_package:
        package = create_package(dist_dir, plat)
        if package:
            header("BUILD KOMPLETT")
            ok(f"Version: {version}")
            ok(f"Plattform: {plat} ({platform.machine()})")
            ok(f"Paket: {package}")
            ok(f"Größe: {package.stat().st_size / (1024*1024):.1f} MB")
            if rust_binary:
                ok("Rust-Engine: eingebettet ✓")
            else:
                warn("Rust-Engine: NICHT eingebettet (nur Python-Modus)")
            print(f"\n  {C.BOLD}Zum Testen:{C.END}")
            if plat == "linux":
                print(f"    cd {dist_dir}")
                print(f"    ./{dist_dir.name}/main")
            elif plat == "macos":
                print(f"    open {dist_dir}")
            elif plat == "windows":
                print(f"    {dist_dir}\\main.exe")
    else:
        header("BUILD KOMPLETT (ohne Paketierung)")
        ok(f"Dist-Ordner: {dist_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
