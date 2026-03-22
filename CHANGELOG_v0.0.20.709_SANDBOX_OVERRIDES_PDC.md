# CHANGELOG v0.0.20.709 — Plugin Sandbox Overrides + Latency PDC

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox P6C + P2C + P4A + RA4 Hybrid PDC

## Was wurde gemacht

### P6C — Pro-Plugin Sandbox Override ✅
- **sandbox_overrides.py** (NEU): Per-Plugin Override-Service
  - Drei Modi: "default" (global), "sandbox" (erzwungen), "inprocess" (erzwungen ohne Sandbox)
  - QSettings-persistent unter `audio/sandbox_override/<type>/<hash>`
  - `should_sandbox()` API kombiniert per-plugin Override + global Toggle
- **device_panel.py**: `contextMenuEvent` auf `_DeviceCard` für externe Plugins
  - Rechtsklick → "⚙ Global-Einstellung verwenden" / "🛡️ Immer in Sandbox" / "⚡ Ohne Sandbox"
  - Nur für `ext.vst3:`, `ext.vst2:`, `ext.clap:`, `ext.lv2:`, `ext.ladspa:` Plugins
  - Built-in Plugins delegieren an bestehende Chain-Context-Menu
- **fx_chain.py**: `_try_sandbox_fx()` nutzt jetzt `should_sandbox()` statt nur global Toggle

### P2C — Plugin Latency Report via IPC ✅
- **plugin_ipc.py**: `request_latency()` Methode auf PluginIPCClient
  - Sendet `{cmd: "get_latency"}` → Worker antwortet mit `{evt: "latency", samples: int}`
- **sandbox_process_manager.py**: 
  - `latency_samples` Feld auf WorkerHandle
  - `get_latency()` + `request_latency()` Methoden auf SandboxProcessManager
  - Latency in `get_all_status()` enthalten + Event-Handler verdrahtet
- **sandboxed_fx.py**: `get_latency()` → delegiert an ProcessManager
- **Alle 4 Worker** (vst3, vst2, lv2_ladspa, clap): `get_latency` Command Handler
  - Liest `plugin.get_latency()` oder `plugin.latency` Attribut

### P4A — Worker-eigene URID Map (LV2) ✅
- **lv2_ladspa_worker.py**: Forciert frische `lilv.World` Instanz im Worker-Subprocess
  - `_registry._world = None` vor Plugin-Load → eigene URID Map garantiert
  - Verhindert stale State nach fork() und inkonsistente URI-IDs

### RA4 — Hybrid Mode PDC (Latenz-Kompensation) ✅
- **rust_hybrid_engine.py**: `compute_hybrid_pdc()` Methode
  - Berechnet per-Track Kompensation für Rust↔Python Latenzunterschiede
  - Rust IPC = ~1 Buffer Cycle, Python Sandbox = ~1 Buffer Cycle, In-Process = 0
  - Kürzerer Pfad wird verzögert um längsten Pfad zu matchen
  - PDC in `get_status()` enthalten

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/sandbox_overrides.py | **NEU** — Per-Plugin Sandbox Override Service |
| pydaw/ui/device_panel.py | contextMenuEvent auf _DeviceCard (P6C) |
| pydaw/audio/fx_chain.py | should_sandbox() statt global toggle (P6C) |
| pydaw/services/plugin_ipc.py | request_latency() Methode (P2C) |
| pydaw/services/sandbox_process_manager.py | latency_samples, get_latency(), event handler (P2C) |
| pydaw/services/sandboxed_fx.py | get_latency() Methode (P2C) |
| pydaw/plugin_workers/vst3_worker.py | get_latency command (P2C) |
| pydaw/plugin_workers/vst2_worker.py | get_latency command (P2C) |
| pydaw/plugin_workers/lv2_ladspa_worker.py | get_latency + fresh lilv.World (P2C+P4A) |
| pydaw/plugin_workers/clap_worker.py | get_latency command (P2C) |
| pydaw/services/rust_hybrid_engine.py | compute_hybrid_pdc() (RA4) |

## Was als nächstes zu tun ist
- P7 (OPTIONAL): Rust Native Plugin Hosting (vst3-sys, clack-host, lv2-host)
- Live-Test: `USE_RUST_ENGINE=1 python3 main.py`
- A/B Bounce-Vergleich Python vs Rust
- Praxis-Test: Plugin Sandbox mit echten VST3/CLAP Plugins

## Bekannte Probleme / Offene Fragen
- P2B: `vst_gui_process.py` Integration in Worker noch offen (bestehende GUI-Logik bleibt parallel)
- P3B: VST2 Editor (effEditOpen) in Worker-Prozess + X11 Embedding noch offen
- P5B: CLAP GUI clap_plugin_gui.create() + set_parent() im Worker noch offen
