# CHANGELOG v0.0.20.725 — Persistent Plugin Blacklist + Stability Hardening

**Datum:** 2026-03-22
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Stability / Rust Bridge / Scanner / FX Chain / Browser UI

## Was wurde gemacht (11 Phasen)

### A. Persistente Plugin-Blacklist (plugin_probe.py — komplett überarbeitet)
- BlacklistEntry Dataclass: signal_name, crash_count, first/last_crash, user_override
- Disk-Persistenz: ~/.cache/ChronoScaleStudio/plugin_blacklist.json (atomic write)
- Batch-Probe API: probe_batch() für effizientes Massen-Probing
- Neue APIs: is_blacklisted(), get_crash_count(), clear_blacklist_entry()

### B. Scanner + Probe Integration (plugin_scanner.py)
- scan_all_with_probe(): Excludiert blacklisted Plugins beim Scan

### C. Deferred-Loading CLAP-Support (audio_engine.py)
- CLAP-Instrumente beim Deferred Retry + Blacklist-Prüfung vor Retry

### D. Rust-Bridge Hardening (rust_engine_bridge.py)
- Auto-Reconnect bei Engine-Tod (max 1 Versuch)
- Reader-Loop: 5 transiente Fehler tolerieren

### E. Plugin-Blacklist-Dialog (NEU: plugin_blacklist_dialog.py)
- Menü: Audio → Plugin Sandbox → 💀 Plugin-Blacklist…
- TreeView + Einzel-/Komplett-Entsperrung

### F. Fork-isolierte Multi-Plugin-Expansion (plugin_scanner.py)
- _expand_multi_vst_plugins prüft Blacklist + fork-Probe vor pedalboard-Load

### G. Plugin-Browser Blacklist-Badges (plugins_browser.py)
- 💀 Icon + [BLACKLISTED] + gedimmte Farbe

### H. Blacklist-Warnung beim Plugin-Einfügen (plugins_browser.py)
- QMessageBox bei Blacklist-Plugin → User kann Override bestätigen

### I. FX-Chain Blacklist-Guards (fx_chain.py)
- VST3/VST2/CLAP Blacklist-Check in _compile_devices() vor Plugin-Load
- Blacklisted FX werden beim Compile übersprungen → kein Crash beim Projekt-Öffnen

### J. Rust Scanner → Browser Integration (plugins_browser.py)
- _trigger_rust_scan_if_available() triggert jetzt ScanPlugins
- _on_rust_scan_result() mergt Ergebnisse ADDITIV in Browser-Daten
- Keine Duplikate (path/pid-basierte Deduplizierung)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/plugin_probe.py | Komplett überarbeitet: Persistente Blacklist |
| pydaw/services/plugin_scanner.py | scan_all_with_probe() + fork-isolierte Expansion |
| pydaw/audio/audio_engine.py | Deferred retry: CLAP + Blacklist |
| pydaw/audio/fx_chain.py | Blacklist-Guards für VST3/VST2/CLAP FX |
| pydaw/services/rust_engine_bridge.py | Auto-Reconnect + robustere Reader-Loop |
| pydaw/ui/plugin_blacklist_dialog.py | NEU: Blacklist-Verwaltungs-Dialog |
| pydaw/ui/plugins_browser.py | Blacklist-Badges + Insert-Warnung + Rust-Merge |
| pydaw/ui/main_window.py | Blacklist-Dialog Menüeintrag + Handler |
| VERSION | 0.0.20.725 |
| pydaw/version.py | 0.0.20.725 |

## Was als nächstes zu tun ist
- cargo build --release auf Zielmaschine
- Live-Test mit echten Plugins
