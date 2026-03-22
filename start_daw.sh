#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  Py_DAW Starter — startet alles automatisch
#  Funktioniert mit bash UND zsh (Kali/Debian/Ubuntu)
#
#  v0.0.20.721 — Audio-Settings Auto-Detection + Rust-Toolchain
# ═══════════════════════════════════════════════════════

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "════════════════════════════════════════"
echo "  🎵 Py_DAW — ChronoScaleStudio"
echo "════════════════════════════════════════"
echo ""

# ─── 1. Rust-Toolchain in PATH laden ──────────────────────────────
# Rustup installiert cargo/rustc nach ~/.cargo/bin.
# Das muss in JEDER neuen Shell gesourct werden.
if [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi
# Fallback: explizit ~/.cargo/bin zum PATH
if [ -d "$HOME/.cargo/bin" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# ─── 2. Python venv aktivieren ────────────────────────────────────
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
    echo "⚠️  Kein Python venv gefunden."
    echo ""
    echo "  Erstmalige Einrichtung (einmal ausführen):"
    echo "    python3 setup_all.py --with-rust"
    echo ""
    echo "  Oder nur Python (ohne Rust):"
    echo "    python3 setup_all.py"
    echo ""
    exit 1
fi

echo "🐍 Python: $(python3 --version 2>&1)"
echo "   venv:   ${VIRTUAL_ENV:-system}"

# ─── 3. Rust-Engine Status ────────────────────────────────────────
RUST_ENGINE="$DIR/pydaw_engine/target/release/pydaw_engine"
CARGO_TOML="$DIR/pydaw_engine/Cargo.toml"
RUST_OK=0

if command -v rustc &>/dev/null && command -v cargo &>/dev/null; then
    echo "🦀 Rust:   $(rustc --version 2>&1)"
    echo "   cargo:  $(cargo --version 2>&1)"

    if [ -f "$RUST_ENGINE" ]; then
        SIZE=$(du -h "$RUST_ENGINE" | cut -f1)
        echo "   Engine: ✅ gebaut ($SIZE)"
        RUST_OK=1
    elif [ -f "$CARGO_TOML" ]; then
        echo "   Engine: ⚠️  nicht gebaut"
        echo ""
        echo "  Soll die Rust Audio-Engine jetzt gebaut werden? (empfohlen)"
        echo "  Das dauert beim ersten Mal 1-3 Minuten."
        echo ""

        # Prüfe ob ALSA Dev-Headers da sind (nötig für cpal)
        if [ -f "/usr/include/alsa/asoundlib.h" ]; then
            read -p "  Rust-Engine jetzt bauen? [J/n] " -n 1 -r REPLY
            echo ""
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo ""
                echo "  🔨 Baue Rust Audio-Engine (Release)..."
                echo ""
                if cargo build --release --manifest-path "$CARGO_TOML" 2>&1; then
                    echo ""
                    echo "  ✅ Rust-Engine erfolgreich gebaut!"
                    RUST_OK=1
                else
                    echo ""
                    echo "  ⚠️  Build fehlgeschlagen — DAW startet trotzdem mit Python-Engine."
                fi
            fi
        else
            echo "  ❌ ALSA Dev-Headers fehlen (nötig für Rust Audio)."
            echo "     Installiere mit: sudo apt install libasound2-dev pkg-config"
            echo "     Danach: cargo build --release --manifest-path $CARGO_TOML"
        fi
    fi
else
    echo "🐍 Audio-Engine: Python (Rust nicht installiert)"
    echo "   Tipp: python3 setup_all.py --with-rust"
fi

# ─── 4. Starte Py_DAW ────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  🎵 Starte Py_DAW..."
if [ "$RUST_OK" = "1" ]; then
    if [ "$USE_RUST_ENGINE" = "0" ]; then
        echo "  🦀 Rust Engine: deaktiviert"
    else
        echo "  🦀 Rust Audio-Engine wird automatisch gestartet"
    fi
    echo "     Deaktivieren: USE_RUST_ENGINE=0 ./start_daw.sh"
fi
echo "════════════════════════════════════════"
echo ""

# Rust-Engine als Hintergrundprozess
# v0.0.20.722: Startet AUTOMATISCH wenn Binary gebaut ist.
#              USE_RUST_ENGINE=0 zum expliziten Deaktivieren.
#              Engine an/aus über Audio-Menü in der DAW steuerbar.
RUST_PID=""
if [ "$USE_RUST_ENGINE" = "0" ]; then
    echo "🦀 Rust Engine: manuell deaktiviert (USE_RUST_ENGINE=0)"
elif [ "$RUST_OK" = "1" ]; then
    echo "🦀 Starte Rust Audio-Engine im Hintergrund..."

    # ─── Audio-Settings aus QSettings lesen (v0.0.20.721) ────────
    # QSettings("ChronoScaleStudio", "Py_DAW") speichert unter:
    #   ~/.config/ChronoScaleStudio/Py_DAW.conf (INI-Format)
    RUST_SR=48000
    RUST_BUF=1024
    QSETTINGS_FILE="$HOME/.config/ChronoScaleStudio/Py_DAW.conf"
    if [ -f "$QSETTINGS_FILE" ]; then
        # Lese sample_rate und buffer_size aus INI-Datei
        _sr=$(python3 -c "
try:
    from PyQt6.QtCore import QSettings
    s = QSettings('ChronoScaleStudio', 'Py_DAW')
    print(int(s.value('audio/sample_rate', 48000)))
except Exception:
    print(48000)
" 2>/dev/null)
        _buf=$(python3 -c "
try:
    from PyQt6.QtCore import QSettings
    s = QSettings('ChronoScaleStudio', 'Py_DAW')
    print(int(s.value('audio/buffer_size', 1024)))
except Exception:
    print(1024)
" 2>/dev/null)
        [ -n "$_sr" ] && RUST_SR="$_sr"
        [ -n "$_buf" ] && RUST_BUF="$_buf"
    fi
    echo "   Audio: ${RUST_SR}Hz / ${RUST_BUF} Samples"

    "$RUST_ENGINE" --sr "$RUST_SR" --buf "$RUST_BUF" &
    RUST_PID=$!
    sleep 0.5
    if kill -0 $RUST_PID 2>/dev/null; then
        echo "   PID: $RUST_PID"
    else
        echo "   ⚠️ Rust-Engine konnte nicht starten — Fallback auf Python"
        RUST_PID=""
    fi
fi

python3 main.py

# ─── 5. Aufräumen ────────────────────────────────────────────────
if [ -n "$RUST_PID" ]; then
    echo ""
    echo "🛑 Stoppe Rust-Engine (PID $RUST_PID)..."
    kill $RUST_PID 2>/dev/null || true
    wait $RUST_PID 2>/dev/null || true
    rm -f /tmp/pydaw_engine.sock
fi

echo "👋 Py_DAW beendet."
