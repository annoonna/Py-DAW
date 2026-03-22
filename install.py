"""Installer helper for Py_DAW.

Usage:
    python3 install.py

It will:
- warn if you're not inside a virtual environment
- install/upgrade pip
- install requirements.txt

Note:
- JACK/PipeWire system components are not installed here (distro packages).
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path


def _which(cmd: str) -> str | None:
    """Return full path if a command exists on PATH."""
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(p) / cmd
        if cand.exists() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def _is_debian_like() -> bool:
    """Best-effort detection for Debian/Ubuntu/Kali family."""
    if sys.platform != "linux":
        return False
    try:
        txt = Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    low = txt.lower()
    return ("id_like=" in low and "debian" in low) or ("id=" in low and any(k in low for k in ("kali", "debian", "ubuntu", "linuxmint")))


def _dpkg_installed(pkg: str) -> bool:
    try:
        out = subprocess.check_output(["dpkg-query", "-W", "-f=${Status}", pkg], stderr=subprocess.DEVNULL)
        return b"install ok installed" in out
    except Exception:
        return False


def _maybe_install_lv2_deps() -> None:
    """Optional system deps for LV2 hosting (safe/best-effort).

    On Debian/Kali, the LV2 python binding + utilities are typically provided
    by distro packages:
        - python3-lilv
        - lilv-utils

    This step must NEVER abort the installer.
    """

    if not _is_debian_like():
        return
    if not _which("apt-get"):
        return

    pkgs = ["python3-lilv", "lilv-utils"]
    missing = [p for p in pkgs if not _dpkg_installed(p)]
    if not missing:
        return

    print("\n[LV2] Systempakete fehlen:", ", ".join(missing))
    print("[LV2] Versuche diese automatisch zu installieren (best-effort)…")
    print("      Falls das fehlschlägt, führe manuell aus:")
    print("      sudo apt update && sudo apt install python3-lilv lilv-utils\n")

    # Try root first.
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            _run(["apt-get", "update"])
            _run(["apt-get", "install", "-y", *missing])
            return
    except Exception as exc:
        print("WARN: apt-get (root) failed:", exc)

    sudo = _which("sudo")
    if not sudo:
        return
    try:
        _run([sudo, "apt-get", "update"])
        _run([sudo, "apt-get", "install", "-y", *missing])
    except Exception as exc:
        print("WARN: sudo apt-get failed:", exc)


def _maybe_install_vst2_plugins() -> None:
    """Optional: check for common VST2 plugin packages (Debian/Kali).

    VST2 hosting uses pure ctypes — no Python packages needed.
    This just checks if common VST2 .so plugins are installed.
    v0.0.20.395
    """
    if not _is_debian_like():
        return

    vst2_dir = Path("/usr/lib/vst")
    if vst2_dir.exists():
        so_count = len(list(vst2_dir.glob("*.so")))
        if so_count > 0:
            print(f"\n[VST2] {so_count} VST2 Plugins gefunden in {vst2_dir}")
            return

    # Suggest common packages
    print("\n[VST2] Keine VST2 Plugins gefunden in /usr/lib/vst/")
    print("[VST2] Empfohlene Pakete (optional):")

    suggestions = [
        ("helm", "Helm Wavetable Synthesizer"),
        ("zam-plugins", "Zam Audio Plugins (Compressor, EQ, etc.)"),
        ("tal-plugins", "TAL Audio Plugins (Reverb, Filter, etc.)"),
        ("zynaddsubfx-vst", "ZynAddSubFX Synthesizer"),
    ]
    for pkg, desc in suggestions:
        installed = _dpkg_installed(pkg)
        status = "✓" if installed else "✗"
        print(f"  {status} {pkg} — {desc}")

    print("  Installieren mit: sudo apt install helm zam-plugins")
    print("  VST2 Hosting benötigt KEINE Python-Pakete (reines ctypes).\n")


def _run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> int:
    here = Path(__file__).resolve().parent
    req = here / "requirements.txt"
    if not req.exists():
        print("requirements.txt not found.")
        return 2

    in_venv = (hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix) or bool(os.environ.get("VIRTUAL_ENV"))

    # Always run installs inside a local venv to avoid PEP 668 ("externally-managed-environment")
    # on Kali/Debian. This is SAFE: it does not modify system site-packages.
    py = sys.executable
    if not in_venv:
        print("WARN: Es sieht so aus, als ob du NICHT in einer virtuellen Umgebung bist.")
        print("      Empfehlung: python3 -m venv myenv && source myenv/bin/activate")
        venv_dir = here / "myenv"
        if os.name == "nt":
            vpy = venv_dir / "Scripts" / "python.exe"
        else:
            vpy = venv_dir / "bin" / "python3"
            if not vpy.exists():
                vpy = venv_dir / "bin" / "python"
        if vpy.exists():
            print(f"INFO: Verwende vorhandenes venv: {venv_dir}")
            py = str(vpy)
        else:
            print("INFO: Erstelle lokales venv ./myenv (safe, keine System-Änderung) ...")
            try:
                subprocess.check_call([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)])
            except Exception:
                subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
            if not vpy.exists():
                # Refresh python path after creation
                if os.name == "nt":
                    vpy = venv_dir / "Scripts" / "python.exe"
                else:
                    vpy = venv_dir / "bin" / "python3"
                    if not vpy.exists():
                        vpy = venv_dir / "bin" / "python"
            py = str(vpy)
        print("INFO: Installer nutzt Python:", py)


    # Optional: system packages for LV2 hosting (Debian/Kali)
    # Best-effort only: never abort the installer.
    try:
        _maybe_install_lv2_deps()
    except Exception as exc:
        print("WARN: LV2 deps check/install failed:", exc)

    # Optional: VST2 plugin packages (Debian/Kali)
    try:
        _maybe_install_vst2_plugins()
    except Exception as exc:
        print("WARN: VST2 plugin check failed:", exc)

    try:
        _run([py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    except Exception as exc:
        print("WARN: pip upgrade failed:", exc)

    try:
        _run([py, "-m", "pip", "install", "pedalboard"])
    except Exception as exc:
        print("WARN: pedalboard install failed:", exc)

    try:
        _run([py, "-m", "pip", "install", "maturin"])
    except Exception as exc:
        print("WARN: maturin install failed:", exc)

    try:
        _run([py, "-m", "pip", "install", "patchelf"])
    except Exception as exc:
        print("WARN: patchelf install failed:", exc)

    _run([py, "-m", "pip", "install", "-r", str(req)])

    print("\nOK. Starte danach mit: python3 main.py")
    print("     oder besser:     ./start_daw.sh")
    print()
    print("Optional: Audio/MIDI Abhängigkeiten können Systempakete erfordern (PipeWire-JACK/JACK/ALSA).")
    print("VST2 Plugins: /usr/lib/vst/*.so (ctypes-basiert, keine extra Python-Pakete nötig)")
    print("VST3 Plugins: /usr/lib/vst3/*.vst3 (via pedalboard)")
    print()
    print("Für Rust Audio-Engine (empfohlen für beste Performance):")
    print("    python3 setup_all.py --with-rust")
    print("  Das installiert Rust automatisch und baut die Engine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
