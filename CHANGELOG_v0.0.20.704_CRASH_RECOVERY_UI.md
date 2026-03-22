# CHANGELOG v0.0.20.704 — Crash Recovery UI (P6 komplett)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox Roadmap, Phase P6A/P6B/P6C + P1C Reste

## Was wurde gemacht

### P6A — Track Crash Indicator (Mixer Integration)
- CrashIndicatorBadge in _MixerStrip eingebettet (16px inline Badge)
- Roter 2px-Rand um MixerStrip wenn Plugin gecrasht (Bitwig-Style)
- set_sandbox_state() API auf MixerStrip: hidden/running/crashed/restarting/disabled
- _poll_sandbox_status() aktualisiert jetzt auch Mixer-Strips (nicht nur Statusbar)
- factory_reset_requested Signal für "Neu laden ohne State"

### P6B — Crash Recovery Logic
- CrashLog + CrashLogEntry verdrahtet: _start_sandbox_monitor() verbindet crash_callback → CrashLog
- factory_restart() Methode auf SandboxProcessManager (Reset ohne State)
- CrashLogDialog: Scrollbare Ansicht aller Crash-Events (Memory + Disk)
- Disk-Logs aus ~/.pydaw/crash_logs/ werden geladen (letzte 10 Tage)
- Auto-Recovery war bereits in v700 implementiert (3 Restarts, State-Snapshots)

### P6C — Audio-Menü Integration
- Neues Untermenü: Audio → 🛡️ Plugin Sandbox
  - ☑ Plugin Sandbox (Crash-Schutz) — Toggle, persistent via QSettings
  - 🔄 Alle Plugins neu starten — Kill + Restart aller Worker
  - Sandbox-Status… — Live-Tabelle aller Worker (SandboxStatusDialog)
  - 🔥 Plugin Crash Log… — CrashLogDialog
- SandboxStatusDialog: Live-aktualisierte Tabelle (500ms Refresh) mit
  Track, Plugin, Typ, PID, Status, Crashes, Aktion-Buttons

### P1C — Audio Settings Toggle (Rest)
- CheckBox "Plugin Sandbox aktivieren" in AudioSettingsDialog
- Lädt/speichert audio/plugin_sandbox_enabled via QSettings

### Neue Dateien
- pydaw/ui/sandbox_status_dialog.py (SandboxStatusDialog + CrashLogDialog)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/ui/crash_indicator_widget.py | factory_reset_requested Signal hinzugefügt |
| pydaw/ui/sandbox_status_dialog.py | **NEU**: SandboxStatusDialog + CrashLogDialog |
| pydaw/ui/mixer.py | CrashIndicatorBadge + set_sandbox_state() + roter Crash-Rand |
| pydaw/ui/main_window.py | Sandbox-Submenu, Dialog-Handler, CrashLog-Wiring, Mixer-Strip-Updates |
| pydaw/ui/audio_settings_dialog.py | Sandbox-Toggle CheckBox + load/save |
| pydaw/services/sandbox_process_manager.py | factory_restart() Methode |
| VERSION | 0.0.20.704 |
| pydaw/version.py | 0.0.20.704 |

## Was als nächstes zu tun ist
- Phase P2A: VST3 Worker Process (pedalboard im Subprocess)
- Phase P2B: VST3 GUI im Worker-Prozess
- Phase P2C: VST3 Instrument Sandbox
- Optional P6 Rest: Pro-Plugin Override (Rechtsklick "In Sandbox laden")

## Bekannte Probleme / Offene Fragen
- Pro-Plugin Override (Rechtsklick auf Plugin → "In/Ohne Sandbox laden") noch offen
- Tatsächliche Sandbox-Nutzung erfordert P2-P5 (Format-spezifische Worker)
