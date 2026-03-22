#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  Py_DAW Starter (Debug Mode via GDB)
#  Startet DAW und liefert Backtrace bei Crash
# ═══════════════════════════════════════════════════════

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Rust-Engine Status (Info only — startet NICHT als Prozess)
if [ -f "$DIR/pydaw_engine/target/release/pydaw_engine" ]; then
    echo "🦀 Rust Audio-Engine: GEBAUT (Toggle: Audio → Rust Audio-Engine)"
else
    echo "🐍 Python Audio-Engine (Rust nicht gebaut)"
fi

# venv aktivieren
VENV_FOUND=0
if [ -n "$VIRTUAL_ENV" ]; then
    VENV_FOUND=1
elif [ -f "$DIR/myenv/bin/activate" ]; then
    . "$DIR/myenv/bin/activate"
    VENV_FOUND=1
elif [ -f "$HOME/myenv/bin/activate" ]; then
    . "$HOME/myenv/bin/activate"
    VENV_FOUND=1
fi

if [ "$VENV_FOUND" = "0" ]; then
    echo "⚠️  Kein venv gefunden! Bitte 'python3 setup_all.py' ausführen."
    exit 1
fi

echo ""
echo "════════════════════════════════════════"
echo "  🐞 Starte Py_DAW im DEBUG-MODUS (GDB)..."
echo "════════════════════════════════════════"
echo ""

gdb -batch -ex "run" -ex "bt" --args python3 main.py

echo "👋 Py_DAW Debug-Session beendet."
