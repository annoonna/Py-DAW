#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Py_DAW Smoke Test — validates all modules compile and core imports work.

v0.0.20.712 — Run this after any code changes to ensure nothing is broken.

Usage:
    python3 smoke_test.py

Exit codes:
    0 — All checks passed
    1 — Compilation or import errors found

This does NOT require a running GUI, audio device, or Rust engine.
It only validates Python syntax and import chains.
"""
import os
import sys
import py_compile
import importlib
import traceback

# ---------------------------------------------------------------------------
# 1. Compile-check all .py files
# ---------------------------------------------------------------------------

def check_compilation() -> list:
    """Compile-check every .py file under pydaw/."""
    errors = []
    for root, _dirs, files in os.walk("pydaw"):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    py_compile.compile(path, doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"COMPILE ERROR: {path}: {e}")
    return errors


# ---------------------------------------------------------------------------
# 2. Import-check core modules
# ---------------------------------------------------------------------------

CORE_MODULES = [
    # Core
    "pydaw.core.settings",
    "pydaw.core.settings_store",
    # Model
    "pydaw.model.project",
    # Services — Plugin Sandbox
    "pydaw.services.plugin_ipc",
    "pydaw.services.plugin_sandbox",
    "pydaw.services.sandbox_process_manager",
    "pydaw.services.sandboxed_fx",
    "pydaw.services.sandbox_overrides",
    # Services — Rust
    "pydaw.services.rust_project_sync",
    "pydaw.services.rust_sample_sync",
    "pydaw.services.rust_audio_takeover",
    "pydaw.services.rust_hybrid_engine",
    # Plugin Workers
    "pydaw.plugin_workers",
    "pydaw.plugin_workers.vst3_worker",
    "pydaw.plugin_workers.vst2_worker",
    "pydaw.plugin_workers.lv2_ladspa_worker",
    "pydaw.plugin_workers.clap_worker",
    # Plugins
    "pydaw.plugins.registry",
]


def check_imports() -> list:
    """Try importing core modules."""
    errors = []
    for mod_name in CORE_MODULES:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            # Some modules need PyQt6 etc. — only flag truly broken imports
            err_msg = str(e)
            if "PyQt6" in err_msg or "Qt" in err_msg:
                continue  # Expected: no GUI in headless
            if "pedalboard" in err_msg:
                continue  # Optional: not always installed
            if "lilv" in err_msg:
                continue  # Optional: needs apt install
            if "sounddevice" in err_msg or "soundfile" in err_msg:
                continue  # Optional: audio libs
            errors.append(f"IMPORT ERROR: {mod_name}: {e}")
        except Exception as e:
            # Some modules fail due to missing Qt Application etc.
            err_msg = str(e)
            if "QApplication" in err_msg or "Qt" in err_msg:
                continue
            errors.append(f"IMPORT ERROR: {mod_name}: {e}")
    return errors


# ---------------------------------------------------------------------------
# 3. Validate VERSION file
# ---------------------------------------------------------------------------

def check_version() -> list:
    errors = []
    try:
        with open("VERSION", "r") as f:
            ver = f.read().strip()
        parts = ver.split(".")
        if len(parts) != 4:
            errors.append(f"VERSION format error: expected X.X.X.X, got '{ver}'")
        else:
            for p in parts:
                try:
                    int(p)
                except ValueError:
                    errors.append(f"VERSION non-integer part: '{p}' in '{ver}'")
    except FileNotFoundError:
        errors.append("VERSION file not found!")
    return errors


# ---------------------------------------------------------------------------
# 4. Validate documentation files exist
# ---------------------------------------------------------------------------

REQUIRED_DOCS = [
    "PROJECT_DOCS/ROADMAP_MASTER_PLAN.md",
    "PROJECT_DOCS/TEAM_RELAY_PROTOCOL.md",
    "PROJECT_DOCS/PLUGIN_SANDBOX_ROADMAP.md",
    "PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md",
    "PROJECT_DOCS/sessions/LATEST.md",
    "PROJECT_DOCS/progress/TODO.md",
    "PROJECT_DOCS/progress/DONE.md",
]


def check_docs() -> list:
    errors = []
    for doc in REQUIRED_DOCS:
        if not os.path.isfile(doc):
            errors.append(f"MISSING DOC: {doc}")
    return errors


# ---------------------------------------------------------------------------
# 5. Count Rust .rs files (no compile check, just existence)
# ---------------------------------------------------------------------------

def check_rust_files() -> dict:
    """Count Rust source files and total lines."""
    rs_files = 0
    rs_lines = 0
    for root, _dirs, files in os.walk("pydaw_engine"):
        for f in files:
            if f.endswith(".rs"):
                rs_files += 1
                try:
                    with open(os.path.join(root, f), "r") as fh:
                        rs_lines += sum(1 for _ in fh)
                except Exception:
                    pass
    return {"files": rs_files, "lines": rs_lines}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("  Py_DAW Smoke Test")
    print("=" * 60)

    all_errors = []

    # 1. Compilation
    print("\n[1/5] Checking Python compilation...")
    py_count = sum(1 for r, _, fs in os.walk("pydaw") for f in fs if f.endswith(".py"))
    errs = check_compilation()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ {py_count} .py files compile OK")

    # 2. Imports
    print("\n[2/5] Checking core imports...")
    errs = check_imports()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ {len(CORE_MODULES)} core modules importable")

    # 3. VERSION
    print("\n[3/5] Checking VERSION file...")
    errs = check_version()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        with open("VERSION") as f:
            print(f"  ✅ VERSION = {f.read().strip()}")

    # 4. Documentation
    print("\n[4/5] Checking documentation...")
    errs = check_docs()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ {len(REQUIRED_DOCS)} required docs present")

    # 5. Rust files
    print("\n[5/5] Counting Rust source files...")
    rust = check_rust_files()
    print(f"  📊 {rust['files']} .rs files, {rust['lines']} lines")

    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"  ❌ FAILED — {len(all_errors)} error(s)")
        for e in all_errors:
            print(f"    • {e}")
        return 1
    else:
        print("  ✅ ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
