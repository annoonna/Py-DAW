# Session Log — v0.0.20.725

**Datum:** 2026-03-22
**Kollege:** Claude Opus 4.6
**Aufgabe:** Persistent Plugin Blacklist + Stability Hardening (11 Phasen)

## Was wurde erledigt

### Phase A: Persistente Plugin-Blacklist (plugin_probe.py)
- BlacklistEntry Dataclass (signal, count, timestamps, user_override)
- JSON-Persistenz ~/.cache/ChronoScaleStudio/plugin_blacklist.json
- Atomic write, lazy-load, Batch-Probe API

### Phase B: Scanner + Probe Integration (plugin_scanner.py)
- scan_all_with_probe(): Excludiert blacklisted Plugins beim Scan

### Phase C: Deferred-Loading CLAP-Support (audio_engine.py)
- CLAP-Instrumente im Deferred Retry + Blacklist-Check

### Phase D: Rust-Bridge Hardening (rust_engine_bridge.py)
- Auto-Reconnect (max 1x) + Reader-Loop 5 Retries

### Phase E: Plugin-Blacklist-Dialog (plugin_blacklist_dialog.py — NEU)
- QDialog mit TreeWidget, Einzel-/Komplett-Entsperrung

### Phase F: Fork-isolierte Multi-Plugin-Expansion (plugin_scanner.py)
- Blacklist + fork-Probe VOR pedalboard-Instanzierung

### Phase G: Plugin-Browser Blacklist-Badges (plugins_browser.py)
- 💀 + [BLACKLISTED] + QColor dimming

### Phase H: Blacklist-Warnung beim Einfügen (plugins_browser.py)
- QMessageBox Warnung + User-Override → clear_blacklist_entry()

### Phase I: FX-Chain Blacklist-Guards (fx_chain.py)
- VST3/VST2/CLAP Blacklist-Prüfung in _compile_devices()
- Crashende Plugins werden beim Projekt-Öffnen übersprungen

### Phase J: Rust Scanner → Browser Merge (plugins_browser.py)
- ScanPlugins wird getriggert wenn Rust-Engine verbunden
- Ergebnisse additiv gemergt (path/pid Deduplizierung)

## Geänderte Dateien
- pydaw/services/plugin_probe.py — Komplett überarbeitet
- pydaw/services/plugin_scanner.py — scan_all_with_probe() + fork-Probe
- pydaw/audio/audio_engine.py — Deferred CLAP + Blacklist
- pydaw/audio/fx_chain.py — Blacklist-Guards für 3 Plugin-Formate
- pydaw/services/rust_engine_bridge.py — Auto-Reconnect + Reader-Loop
- pydaw/ui/plugin_blacklist_dialog.py — NEU
- pydaw/ui/plugins_browser.py — Badges + Warnung + Rust-Merge
- pydaw/ui/main_window.py — Menüeintrag + Handler
- VERSION + pydaw/version.py — 0.0.20.725

## Nächste Schritte
- cargo build --release auf Zielmaschine (Rust-Compiler benötigt)
- Live-Test mit echten Plugins (Surge XT, Vital, Cardinal)

## Offene Fragen
- Rust-Toolchain nicht installierbar in dieser Umgebung
