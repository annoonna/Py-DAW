# Session Log — v0.0.20.704

**Datum:** 2026-03-21
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox P6A/P6B/P6C — Crash Recovery UI
**Aufgabe:** Bitwig-Style Crash-UI komplett implementieren

## Was wurde erledigt

### Phase P6A — Track Crash Indicator (Mixer) ✅
- CrashIndicatorBadge in _MixerStrip eingebettet
- Roter 2px Border bei Crash, verschwindet bei Recovery
- set_sandbox_state() API: hidden/running/crashed/restarting/disabled
- _poll_sandbox_status() schreibt jetzt auch Mixer-Strips
- factory_reset_requested Signal auf Badge

### Phase P6B — Crash Recovery Logic ✅
- CrashLog mit crash_callback am SandboxProcessManager verdrahtet
- factory_restart() ohne State-Recovery (Factory Default)
- CrashLogDialog: In-Memory + Disk-Logs (~/.pydaw/crash_logs/)
- Auto-Recovery war v700: 3 Restarts, 5s State-Snapshots

### Phase P6C — Audio-Menü Integration ✅
- Audio → 🛡️ Plugin Sandbox Untermenü:
  - Toggle, Restart-All, Status-Dialog, Crash-Log
- SandboxStatusDialog: Live-Tabelle aller Worker
- CrashLogDialog: Scrollbare Log-Ansicht

### P1C Rest ✅
- AudioSettingsDialog: Sandbox-Toggle CheckBox + QSettings

## Geänderte Dateien
- pydaw/ui/crash_indicator_widget.py (factory_reset_requested Signal)
- pydaw/ui/sandbox_status_dialog.py (**NEU**)
- pydaw/ui/mixer.py (Badge + set_sandbox_state + Crash-Rand)
- pydaw/ui/main_window.py (Submenu, Dialogs, CrashLog-Wiring)
- pydaw/ui/audio_settings_dialog.py (Sandbox CheckBox)
- pydaw/services/sandbox_process_manager.py (factory_restart)
- VERSION, pydaw/version.py

## Nächste Schritte
1. Phase P2A — VST3 Worker Process (pedalboard im Subprocess)
2. Phase P2B — VST3 GUI im Worker
3. Phase P2C — VST3 Instrument Sandbox
4. Dann P3 (VST2), P4 (LV2/LADSPA), P5 (CLAP)

## Offene Fragen an den Auftraggeber
- Pro-Plugin Override (Rechtsklick "In Sandbox laden") zurückgestellt
- P2-P5 Worker fehlen noch — Sandbox UI ist fertig, aber ohne Worker-Prozesse
  wird noch kein Plugin tatsächlich sandboxed
