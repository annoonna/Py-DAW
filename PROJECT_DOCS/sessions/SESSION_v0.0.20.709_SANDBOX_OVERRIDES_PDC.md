# Session Log — v0.0.20.709

**Datum:** 2026-03-21
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox P6C + P2C + P4A + RA4 Hybrid PDC
**Aufgabe:** Offene Plugin-Sandbox Checkboxen abarbeiten + Hybrid-PDC

## Was wurde erledigt

### P6C — Pro-Plugin Sandbox Override ✅
- sandbox_overrides.py (NEU): Per-Plugin Override-Service
  - get_override/set_override/should_sandbox/clear_override API
  - QSettings-persistent: "default"/"sandbox"/"inprocess" pro Plugin
- device_panel.py: contextMenuEvent auf _DeviceCard für externe Plugins
  - Rechtsklick auf ext.vst3/vst2/clap/lv2/ladspa → Sandbox-Modus wählen
- fx_chain.py: _try_sandbox_fx nutzt should_sandbox() statt nur global toggle

### P2C — Plugin Latency Report via IPC ✅
- plugin_ipc.py: request_latency() Methode
- sandbox_process_manager.py: latency_samples Feld, get_latency(), event handler
- sandboxed_fx.py: get_latency() delegiert an ProcessManager
- Alle 4 Worker: get_latency command (liest plugin.get_latency()/plugin.latency)

### P4A — Worker-eigene URID Map (LV2) ✅
- lv2_ladspa_worker.py: _registry._world = None vor Plugin-Load
  - Erzwingt frische lilv.World im Subprocess → eigene URID Map

### RA4 — Hybrid Mode PDC ✅
- rust_hybrid_engine.py: compute_hybrid_pdc()
  - Per-Track Kompensation: Rust IPC vs Python Sandbox vs In-Process
  - PDC in get_status() enthalten

## Neue/Geänderte Dateien
- pydaw/services/sandbox_overrides.py (NEU)
- pydaw/ui/device_panel.py (contextMenuEvent)
- pydaw/audio/fx_chain.py (should_sandbox)
- pydaw/services/plugin_ipc.py (request_latency)
- pydaw/services/sandbox_process_manager.py (latency)
- pydaw/services/sandboxed_fx.py (get_latency)
- pydaw/plugin_workers/vst3_worker.py (get_latency cmd)
- pydaw/plugin_workers/vst2_worker.py (get_latency cmd)
- pydaw/plugin_workers/lv2_ladspa_worker.py (get_latency + URID)
- pydaw/plugin_workers/clap_worker.py (get_latency cmd)
- pydaw/services/rust_hybrid_engine.py (hybrid PDC)

## Nächste Schritte
1. P7 (OPTIONAL): Rust Native Plugin Hosting
2. Live-Test: USE_RUST_ENGINE=1 python3 main.py
3. A/B Bounce: Python vs Rust Vergleich
4. Praxis-Test: Sandbox mit echten VST3/CLAP/LV2 Plugins
