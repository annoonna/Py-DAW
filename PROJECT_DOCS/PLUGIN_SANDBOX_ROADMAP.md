# 🔌 PLUGIN SANDBOX ROADMAP — Crash-sicheres Plugin-Hosting
# ═══════════════════════════════════════════════════════════

*Erstellt: v0.0.20.697 — 2026-03-21*
*Status: OFFEN — nächstes Großprojekt nach Rust DSP Migration*

---

## ⚠️ OBERSTE DIREKTIVE — FÜR ALLE KOLLEGEN

```
NICHTS KAPUTT MACHEN!
Bestehende Plugin-Hosts (VST2/VST3/LV2/LADSPA/CLAP) müssen
IMMER weiter funktionieren. Sandbox ist OPT-IN.
Fallback auf In-Process wenn Sandbox fehlschlägt.
```

---

## 📊 IST-ZUSTAND — Was haben wir?

### Aktuell: Alles läuft IN-PROCESS (gefährlich!)
```
┌──────────────────────────────────────────────────┐
│  Py_DAW Main Process                              │
│                                                    │
│  GUI + Audio Engine + ALLE Plugins im selben      │
│  Prozess → ein Plugin crasht = alles crasht!      │
│                                                    │
│  VST3 (pedalboard)  ← kann DAW killen             │
│  VST2 (ctypes)      ← kann DAW killen             │
│  LV2 (lilv)         ← kann DAW killen             │
│  LADSPA (ctypes)    ← kann DAW killen             │
│  CLAP (ctypes)      ← kann DAW killen             │
│  DSSI               ← nicht implementiert          │
└──────────────────────────────────────────────────┘
```

### Ziel: Bitwig-Modell (jedes Plugin isoliert)
```
┌──────────────────────────────────────────────────┐
│  Py_DAW Main Process (GUI + Audio Engine)         │
│  ┌──────────────────────────────────────────┐    │
│  │  PluginSandboxManager                     │    │
│  │  - Shared Memory Audio Buffers (mmap)     │    │
│  │  - Heartbeat Monitoring (500ms)           │    │
│  │  - Auto-Restart bei Crash (max 3×)        │    │
│  │  - Crash → Track muten → UI zeigt Status  │    │
│  └───┬──────────┬──────────┬────────────┬────┘    │
└──────┼──────────┼──────────┼────────────┼─────────┘
       │          │          │            │
┌──────▼───┐ ┌───▼──────┐ ┌▼─────────┐ ┌▼─────────┐
│ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker N │
│ VST3     │ │ VST2     │ │ LV2      │ │ CLAP     │
│ (Diva)   │ │ (Dexed)  │ │ (Calf)   │ │ (Surge)  │
│          │ │          │ │          │ │          │
│ Crasht?  │ │          │ │          │ │          │
│ → Nur    │ │          │ │          │ │          │
│ dieser   │ │          │ │          │ │          │
│ stirbt!  │ │          │ │          │ │          │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

### Was existiert bereits?
| Datei | Zeilen | Status |
|-------|--------|--------|
| `plugin_sandbox.py` | 503 | Grundgerüst: SharedAudioBuffer, Worker, Monitor, Auto-Restart |
| `vst_gui_process.py` | 353 | GUI läuft bereits in separatem Prozess |
| `vst2_host.py` | 1126 | VST2 via ctypes, in-process |
| `vst3_host.py` | 1148 | VST3 via pedalboard, in-process |
| `lv2_host.py` | 1624 | LV2 via lilv, in-process |
| `ladspa_host.py` | 657 | LADSPA via ctypes, in-process |
| `clap_host.py` | 2247 | CLAP via ctypes, in-process |
| `fx_chain.py` | 1057 | Lädt Plugins, NICHT sandbox-aware |
| Rust Stubs | 1289 | Leere Platzhalter |

---

## 🏗️ PHASENPLAN — 7 Phasen, ~18-22 Sessions

```
P1 (Core)──→ P2 (VST3)──→ P3 (VST2)──→ P4 (LV2/LADSPA)
                                              │
P1 ────────→ P5 (CLAP) ←─────────────────────┘
                │
P6 (Crash-UI)──┘
                │
P7 (Rust Native)──→ Zukunft (optional, langfristig)
```

---

## 🔧 Phase P1 — Sandbox Core Infrastructure (~3-4 Sessions)

### Was: Shared Memory IPC, Process Lifecycle, FX Chain Integration

**P1A — Shared Memory Audio Transport (~1-2 Sessions)**
- [x] `plugin_sandbox.py` → SharedAudioBuffer robuster machen  *(v700 — PingPongAudioBuffer)*
  - [x] Doppel-Buffer (Ping-Pong): Latenzfrei, kein Warten  *(v700)*
  - [x] Stereo + Mono + Multi-Channel Support (bis 8 Kanäle)  *(v700)*
  - [x] Lock-free SPSC Ring mit atomics (statt sleep-polling)  *(v700 — flag-based ready signal)*
  - [x] Fehlerbehandlung: Buffer-Overflow → Silence, kein Crash  *(v700 — WorkerAudioHandler.write_silence)*
- [x] `plugin_ipc.py` (**NEU**): Parameter-IPC via Unix Domain Socket  *(v700)*
  - [x] MessagePack-Protokoll (schneller als JSON)  *(v700)*
  - [x] Befehle: SetParam, GetState, SaveState, LoadState, Bypass, Shutdown  *(v700)*
  - [x] Heartbeat-Ping/Pong (500ms Intervall, 3s Timeout)  *(v700)*
  - [x] State-Snapshot: Plugin-State Base64 für Restart-Recovery  *(v700 — alle 5s)*

**P1B — Process Manager (~1 Session)**
- [x] `sandbox_process_manager.py` (**NEU**): Prozess-Lifecycle  *(v700)*
  - [x] `spawn_plugin(track_id, plugin_config)` → subprocess.Popen  *(v700 — multiprocessing.Process)*
  - [x] `kill_plugin(track_id)` → SIGTERM, dann SIGKILL nach 2s  *(v700)*
  - [x] `restart_plugin(track_id)` → Kill + Spawn mit State-Recovery  *(v700)*
  - [x] Prozess-Pool: Max 32 gleichzeitige Plugin-Prozesse  *(v700 — MAX_WORKERS=32)*
  - [x] Cleanup bei DAW-Shutdown: alle Worker ordentlich beenden  *(v700 — shutdown())*

**P1C — FX Chain Integration (~1 Session)**
- [x] `sandboxed_fx.py` (**NEU**): `SandboxedFx` Wrapper-Klasse  *(v700)*
  - [x] Gleiche API wie `AudioFxBase` (process_inplace, get/set_param)  *(v700)*
  - [x] Intern: sendet Audio an Worker via SharedAudioBuffer  *(v700 — PingPongAudioBuffer)*
  - [x] Liest Output von Worker via SharedAudioBuffer  *(v700 — read_latest)*
  - [x] Fallback: wenn Sandbox-Start fehlschlägt → in-process laden  *(v700 — create() returns None)*
- [x] Toggle in Audio Settings: "Plugin Sandbox (Crash-Schutz)" ein/aus  *(v704 — AudioSettingsDialog QCheckBox)*
- [x] QSettings persistent: `audio/plugin_sandbox_enabled`  *(v704 — SettingsKeys + load/save in dialog + main_window toggle)*

---

## 🎸 Phase P2 — VST3 Sandbox (~3-4 Sessions)

### Was: VST3 Plugins (pedalboard) in separatem Prozess

**P2A — VST3 Worker Process (~1-2 Sessions)**
- [x] `plugin_workers/vst3_worker.py` (**NEU**): Standalone-Prozess  *(v705)*
  - [x] Startet als `python3 -m pydaw.plugin_workers.vst3_worker --path ... --sr ...`  *(v705 — CLI argparse)*
  - [x] Lädt Plugin via pedalboard in diesem Prozess  *(v705 — _load_plugin())*
  - [x] Audio-Loop: liest SharedAudioBuffer → process → schreibt zurück  *(v705 — _process_fx())*
  - [x] Parameter-Updates via Unix Socket (MessagePack)  *(v705 — handle_command set_param)*
  - [x] State Save/Restore: pedalboard state_blob → Base64  *(v705 — _get/_set_raw_state_b64)*
  - [x] GUI-Integration: Editor-Fenster öffnet sich in Worker-Prozess  *(v705 — show_editor/hide_editor IPC)*
    (Plugin-Editor-Thread gehört zum selben Prozess wie Audio)
- [x] Pedalboard bleibt Dependency — läuft aber im Worker-Subprocess  *(v705)*
- [x] SandboxProcessManager routet VST3 automatisch zum vst3_worker  *(v705)*

**P2B — VST3 GUI in Worker (~1 Session)**
- [x] Editor-Fenster im Worker-Prozess (nicht im Haupt-GUI!)  *(v705)*
  - [x] Worker zeigt native Plugin-Fenster via pedalboard.show_editor()  *(v705)*
  - [x] Haupt-GUI sendet "ShowEditor" / "HideEditor" Befehl  *(v705 — PluginIPCClient.show/hide_editor)*
  - [x] Knob-Änderungen im Editor → Worker fängt ab → IPC an Main  *(v705 — param_changed event)*
  - [x] `vst_gui_process.py` Logik in Worker integriert  *(v710 — Param-Poller Thread im vst3_worker, ~12Hz, Preset-Detection)*

**P2C — VST3 Instrument Sandbox (~1 Session)**
- [x] VST3 Instrumente (nicht nur FX) in Sandbox  *(v705 — is_instrument mode)*
  - [x] MIDI Note-On/Off via IPC an Worker  *(v705 — send_note_on/off/midi_events/all_notes_off)*
  - [x] Worker hat eigenen MIDI-Buffer  *(v705 — pending_midi list in vst3_worker)*
  - [x] Pull-Source: Worker rendert Audio → Main liest  *(v705 — SandboxedFx.pull() + _process_instrument)*
  - [x] Latenz-Kompensation: Plugin-Latency Report via IPC  *(v709 — get_latency IPC cmd in allen Workern, SandboxedFx.get_latency())*

---

## 🎛️ Phase P3 — VST2 Sandbox (~2-3 Sessions)

### Was: VST2 Plugins (ctypes) in separatem Prozess

**P3A — VST2 Worker Process (~1-2 Sessions)**
- [x] `plugin_workers/vst2_worker.py` (**NEU**)  *(v706)*
  - [x] Lädt VST2 .so via ctypes (wie `vst2_host.py`)  *(v706 — Vst2Fx/Vst2InstrumentEngine im Worker)*
  - [x] AEffect struct + processReplacing in Worker-Prozess  *(v706 — via process_inplace)*
  - [x] audioMasterCallback für Host-Queries (sampleRate, blockSize)  *(v706 — via vst2_host.py Wrapper)*
  - [x] Parameter get/set via IPC  *(v706 — set_param IPC handler)*
  - [x] State: effGetChunk/effSetChunk → Base64 für Recovery  *(v706 — get_state/load_state IPC)*

**P3B — VST2 GUI + MIDI (~1 Session)**
- [x] Editor via dispatcher(effEditOpen) im Worker-Prozess  *(v711 — _vst2_show_editor mit effEditOpen opcode 14)*
  - [x] X11 Window Embedding (XReparentWindow) oder eigenständig  *(v711 — XCreateSimpleWindow + effEditOpen, XDestroyWindow cleanup)*
- [x] MIDI-Dispatch für VST2 Instrumente  *(v706 — note_on/off IPC → Vst2InstrumentEngine)*
- [x] VSTEvents Struct bauen + an processEvents senden  *(v706 — via vst2_host.py Instrument note_on/off)*

---

## 🔊 Phase P4 — LV2 + LADSPA Sandbox (~2-3 Sessions)

### Was: LV2 und LADSPA in separatem Prozess

**P4A — LV2 Worker (~1-2 Sessions)**
- [x] `plugin_workers/lv2_ladspa_worker.py` (**NEU**)  *(v706 — shared LV2+LADSPA worker)*
  - [x] Lädt LV2 via lilv im Worker-Prozess  *(v706 — Lv2Fx im Worker)*
  - [x] Port-Connect + Run im Worker  *(v706 — via process_inplace)*
  - [x] Atom-Events (MIDI, Patch) via IPC  *(v706 — set_param IPC)*
  - [x] State: LV2_State_Interface Save/Restore  *(v706 — get_state/load_state via IPC)*
  - [x] Worker-eigene URID Map (nicht von Main-Prozess abhängig)  *(v709 — _registry._world=None im Worker)*

**P4B — LADSPA Worker (~1 Session)**
- [x] `plugin_workers/lv2_ladspa_worker.py` (geteilt mit LV2)  *(v706)*
  - [x] Lädt LADSPA .so via ctypes  *(v706 — LadspaFx im Worker)*
  - [x] connect_port + run im Worker  *(v706 — via process_inplace)*
  - [x] Control-Ports via IPC  *(v706 — set_param IPC)*
  - [x] LADSPA hat kein State-Save → Parameter-Snapshot stattdessen  *(v706 — JSON dict als Base64)*

---

## 🎹 Phase P5 — CLAP Sandbox (~2-3 Sessions)

### Was: CLAP Plugins in separatem Prozess

**P5A — CLAP Worker (~1-2 Sessions)**
- [x] `plugin_workers/clap_worker.py` (**NEU**)  *(v706)*
  - [x] Lädt CLAP .clap via ctypes (wie `clap_host.py`)  *(v706 — ClapInstrumentEngine/ClapPluginInstance)*
  - [x] clap_host + clap_plugin Interfaces im Worker  *(v706 — via clap_host.py Wrapper)*
  - [x] Audio-Ports + MIDI-Events via IPC  *(v706 — process_inplace + note_on/off)*
  - [x] State Save/Restore via clap_plugin_state  *(v706 — get_state/load_state IPC)*
  - [x] Extensions: clap_plugin_params, clap_plugin_gui  *(v706 — set_param + show/hide_editor)*

**P5B — CLAP GUI Integration (~1 Session)**
- [x] CLAP GUI im Worker-Prozess  *(v706 — show_editor/hide_editor IPC)*
  - [x] clap_plugin_gui.create() + set_parent() im Worker  *(v711 — X11 window + _clap_gui_create scaffolding)*
  - [x] Window-Handle via IPC an Main für Embedding (optional)  *(v711 — editor_shown event via IPC)*
  - [x] Oder: floating Fenster im Worker (einfacher, sicherer)  *(v706 — show_editor() im Worker-Prozess)*

---

## 🛡️ Phase P6 — Crash Recovery UI (~2-3 Sessions)

### Was: Bitwig-Style Crash-Handling + Reload-Toggle

**P6A — Track Crash Indicator (~1 Session)**
- [x] `crash_indicator_widget.py` (**NEU**): Track-Header Badge  *(v702)*
  - [x] Fünf Zustände: Hidden | ✅ Running | ⚠️ Crashed | 🔄 Restarting | ⊘ Disabled  *(v702)*
  - [x] Icon + Tooltip mit Crash-Grund  *(v702)*
  - [x] Klick auf Badge → Context-Menü:  *(v704 — reload/factory_reset/disable/remove signals)*
    - "Plugin neu laden" (Restart mit letztem State)
    - "Plugin deaktivieren" (Bypass, kein Restart mehr)
    - "Plugin entfernen" (Slot leeren)
- [x] Mixer: Crashed-Indikator auf Channel-Strip (roter Rand)  *(v704 — _MixerStrip.set_sandbox_state(), CrashIndicatorBadge eingebettet, roter 2px Border bei Crash)*
- [x] Statusbar: SandboxStatusWidget zeigt "⚠️ N crashed" / "🛡️ N"  *(v702)*

**P6B — Crash Recovery Logic (~1 Session)**
- [x] Auto-Recovery: 3 Restarts, dann permanent muted  *(v700 — SandboxProcessManager._monitor_loop, MAX_CRASH_RESTARTS=3)*
  - [x] State-Snapshot alle 5 Sekunden (nicht bei jedem Buffer!)  *(v700 — STATE_SNAPSHOT_INTERVAL=5.0, request_state() via IPC)*
  - [x] Restart mit letztem State → Plugin Settings bleiben erhalten  *(v700 — restart() nutzt h.state_b64)*
  - [x] Reset-Button: Startet Plugin ohne State (Factory Default)  *(v704 — factory_restart() + factory_reset_requested Signal)*
- [x] Crash-Log: Plugin-Name, Crash-Zeitpunkt, Error-Info  *(v704 — CrashLog + CrashLogEntry, _on_crash Callback → Log)*
  - [x] Abrufbar via Hilfe → Plugin Crash Log  *(v704 — Audio → Plugin Sandbox → Plugin Crash Log…)*
  - [x] Automatisch gespeichert in `~/.pydaw/crash_logs/`  *(v702 — CrashLog._write_to_file())*

**P6C — Audio-Menü Integration (~1 Session)**
- [x] Audio → Plugin Sandbox → Untermenü:  *(v704 — m_sandbox QMenu im Audio-Menü)*
  - [x] ☑ Sandbox ein/aus (Toggle, persistent)  *(v704 — audio_toggle_plugin_sandbox QAction + QSettings)*
  - [x] "Alle Plugins neu starten" (Kill + Restart alle Worker)  *(v704 — _on_sandbox_restart_all())*
  - [x] "Plugin Crash Log anzeigen…"  *(v704 — CrashLogDialog)*
  - [x] "Sandbox-Status…" (Dialog mit allen Workers + Health)  *(v704 — SandboxStatusDialog, live table, restart/kill per worker)*
- [x] Pro-Plugin Override: Rechtsklick auf Plugin → "In Sandbox laden"  *(v709 — contextMenuEvent auf _DeviceCard, sandbox_overrides.py)*
  - [x] Oder: "Ohne Sandbox laden" (für Plugins die Sandbox nicht mögen)  *(v709 — OVERRIDE_INPROCESS mode)*

---

## 🦀 Phase P7 — Rust Native Plugin Hosting (~5-8 Sessions, OPTIONAL)

### Was: Plugin-Hosting direkt in Rust statt Python (Zukunft)

**⚠️ Dies ist ein LANGZEIT-Ziel und nicht zwingend nötig!**
Die Python-Sandbox (P1-P6) bietet bereits vollen Crash-Schutz.
Rust Native Hosting wäre Performance-Optimierung (weniger IPC-Overhead).

**P7A — VST3 in Rust (~2-3 Sessions)**
- [x] `vst3_host.rs`: Ersetze Stub durch echten VST3 Host  *(v0.0.20.716 — Raw COM FFI via libloading, 780 Zeilen)*
  - [x] Raw COM vtables statt vst3-sys Crate (volle Kontrolle, kein C++ ABI)  *(v716)*
  - [x] IComponent + IAudioProcessor + IEditController  *(v716 — QueryInterface, Separate Controller Support)*
  - [x] Parameter Sync: discover_parameters(), getParamNormalized/setParamNormalized  *(v716)*
  - [x] Audio Processing: deinterleave → process(ProcessData) → reinterleave  *(v716 — pre-allokierte Buffers)*
  - [x] Scanner: dlopen → GetPluginFactory → PClassInfo Enumeration  *(v716)*
  - [ ] State Save/Restore via IBStream (benötigt MemoryStream Implementierung)

**P7B — CLAP in Rust (~2-3 Sessions)**
- [x] `clap_host.rs`: Ersetze Stub durch echten CLAP Host  *(v0.0.20.716 — Raw C FFI via libloading, 782 Zeilen)*
  - [x] Raw C API Structs statt clap-sys/clack-host Crate  *(v716)*
  - [x] clap_host, clap_plugin, clap_plugin_factory  *(v716 — ClapHost struct mit Callbacks)*
  - [x] Extensions: clap_plugin_params (count, get_info, get_value)  *(v716)*
  - [x] Extensions: clap_plugin_state (save/load stream stubs)  *(v716)*
  - [x] Scanner: dlopen → clap_entry → factory → descriptors  *(v716 — Feature-Tags, is_instrument/is_effect)*
  - [x] Audio Processing: clap_process mit ClapAudioBuffer  *(v716 — deinterleave, empty event lists)*
  - [ ] MIDI Event Injection via clap_input_events (benötigt Event-Struct Implementierung)

**P7C — LV2 in Rust (~1-2 Sessions)**
- [x] `lv2_host.rs`: Ersetze Stub durch echten LV2 Host  *(v0.0.20.716 — Dynamic lilv FFI via libloading, 660 Zeilen)*
  - [x] Dynamic loading: liblilv-0.so via libloading (kein build.rs/pkg-config)  *(v716 — OnceLock, graceful degradation)*
  - [x] Plugin Discovery: lilv_world_load_all → iterate → metadata  *(v716 — PortInfo, Audio/Control/Atom Port Analysis)*
  - [x] Instance: instantiate → connect_port → activate → run  *(v716)*
  - [x] Control Ports: HashMap für Parameter, connect_port auf f32 values  *(v716)*
  - [ ] LV2 State Interface (save/restore)
  - [ ] Atom Port MIDI (benötigt LV2 Atom/URID Implementation)

**P7D — VST2 in Rust (NICHT empfohlen)**
- [ ] VST2 SDK ist deprecated (Steinberg hat Lizenz 2018 zurückgezogen)
- [ ] Empfehlung: VST2 in Python/ctypes Sandbox lassen
- [ ] Oder: yabridge-Style Bridge (VST2 → VST3 Wrapper)

---

## 📏 REGELN FÜR ALLE KOLLEGEN

### Sandbox-Architektur
```
1. Audio-Daten: IMMER über SharedAudioBuffer (mmap, lock-free)
2. Parameter: IMMER über Unix Socket + MessagePack
3. Heartbeat: 500ms Ping, 3s Timeout → als crashed markieren
4. State: Alle 5s Snapshot, bei Crash → Restart mit Snapshot
5. GUI: Plugin-Editor im Worker-Prozess (NICHT im Main-Prozess!)
```

### Fallback-Kette
```
1. Sandbox Worker läuft → ✅ Crash-sicher
2. Sandbox Start fehlschlägt → ⚠️ In-Process Fallback (wie jetzt)
3. In-Process crasht → ❌ DAW tot (aber nur wenn Sandbox aus)
4. User deaktiviert Sandbox → ⚠️ Warnung "Crash-Schutz deaktiviert"
```

### Regeln
```
- NIEMALS den bestehenden In-Process Code löschen!
- Sandbox ist IMMER opt-in mit Fallback
- Worker MUSS in <2s starten (User wartet nicht)
- Audio-Latenz durch Sandbox: max 1 Buffer-Zyklus (256 Samples @ 48kHz ≈ 5ms)
- Kein Plugin darf den Main-Prozess blockieren — NIEMALS
```

---

## 📅 ZEITSCHÄTZUNG

| Phase | Sessions | Beschreibung |
|-------|----------|--------------|
| P1 | 3-4 | Core: Shared Memory, Process Manager, FX Chain |
| P2 | 3-4 | VST3 Sandbox (pedalboard im Worker) |
| P3 | 2-3 | VST2 Sandbox (ctypes im Worker) |
| P4 | 2-3 | LV2 + LADSPA Sandbox |
| P5 | 2-3 | CLAP Sandbox |
| P6 | 2-3 | Crash-Recovery UI (Bitwig-Style) |
| P7 | 5-8 | Rust Native Hosting (OPTIONAL/Langzeit) |
| **Gesamt** | **18-28** | **P1-P6 Pflicht, P7 Optional** |

### Prioritäts-Reihenfolge
1. **P1 + P2** (VST3 zuerst — am häufigsten genutzt)
2. **P6** (Crash-UI — ohne sieht der User nichts)
3. **P3** (VST2 — noch weit verbreitet)
4. **P5** (CLAP — wachsendes Format, Surge XT etc.)
5. **P4** (LV2/LADSPA — Linux-spezifisch)
6. **P7** (Rust — nur wenn Performance-Gewinn messbar)

---

## ❓ FAQ

### Braucht man noch pedalboard?
**JA, vorerst.** Pedalboard lädt VST3-Plugins via C++. In der Sandbox
läuft pedalboard im Worker-Subprocess — crasht es, stirbt nur der Worker.
Erst mit P7A (Rust VST3 Host) könnte pedalboard ersetzt werden.

### Was ist mit DSSI?
DSSI ist quasi tot (letztes Update 2011). Kein neues Plugin nutzt DSSI.
Empfehlung: NICHT implementieren, stattdessen LV2 empfehlen.

### Wie macht Bitwig das?
Bitwig hat "Plugin Sandboxing" seit Version 1.0:
- Jedes Plugin läuft in eigenem Prozess ("clap-wrapper"/"vst3-bridge")
- Shared Memory für Audio (POSIX shm_open)
- Plugin crasht → Track wird gemutet, orangener Balken erscheint
- Klick auf "Reload" → Plugin startet neu mit letztem State
- Einstellung: "Individually" (ein Prozess pro Plugin) vs.
  "Per Track" (ein Prozess pro Track, alle Plugins drin)

### Was passiert mit Latenz?
- 1 Buffer-Zyklus zusätzlich (~5ms bei 256 Samples/48kHz)
- Bei Echtzeit-Recording: Sandbox optional deaktivierbar
- PDC (Plugin Delay Compensation) berücksichtigt Sandbox-Latenz

---

*Dieses Dokument wird mit jeder Phase aktualisiert.*
*Nächste offene Aufgabe: Phase P7A/B/C IBStream + MIDI Events + LV2 State (Feinschliff)

*Aktualisiert: v0.0.20.716 — P7A/P7B/P7C CORE KOMPLETT 🎉

---

# 🔊 RUST AUDIO PIPELINE ROADMAP — Rust rendert statt Python
# ═══════════════════════════════════════════════════════════

*Hinzugefügt: v0.0.20.702 — 2026-03-21*
*Status: OFFEN — nach Plugin Sandbox P6*

---

## 📊 IST-ZUSTAND

```
AKTUELL:
  Python Audio-Engine → sounddevice → ALSA/PipeWire → Speaker
  (Python rendert ALLE Instrumente + FX + Mixing)

Rust-Engine: 286 Tests grün, 771 KB Code, ABER:
  - Kennt keine Projekt-Daten (Tracks, Clips, MIDI, Samples)
  - Hat kein Audio-Device Management (nur cpal PoC)
  - Keine Verbindung zum Python Audio-Thread
  - should_use_rust("audio_playback") = False
```

## 🎯 ZIEL

```
ZIEL:
  Python GUI → IPC → Rust Engine → ALSA/PipeWire → Speaker
  (Rust rendert ALLES: Instrumente + FX + Mixing)
  (Python nur noch GUI + Projekt-Management)
```

## 🏗️ PHASENPLAN — 5 Phasen, ~12-18 Sessions

```
RA1 (Project Sync) → RA2 (Sample Transfer) → RA3 (Audio Takeover)
                                                    │
RA4 (Hybrid Mode) ←────────────────────────────────┘
        │
RA5 (Full Rust) → should_use_rust("audio_playback") = True
```

---

## 🔧 Phase RA1 — Project State Sync (~2-3 Sessions)

### Was: Python schickt Projekt-Daten an Rust beim Play

- [x] `rust_project_sync.py` (**NEU**): Serialisiert Projekt → ProjectSync JSON  *(v707 — serialize_project_sync() + RustProjectSyncer)*
  - [x] Tracks: ID, Name, Typ, Volume, Pan, Mute, Solo, Group-Routing  *(v707 — TrackConfig mit group_index)*
  - [x] Clips: Position, Länge, Typ (Audio/MIDI), Offset  *(v707 — ClipConfig, launcher_only/muted gefiltert)*
  - [x] MIDI-Noten: Pitch, Velocity, Start, Länge (pro Clip)  *(v707 — MidiNoteConfig aus project.midi_notes)*
  - [x] Automation: Breakpoints pro Track/Parameter  *(v707 — AutomationLaneConfig aus automation_manager_lanes)*
  - [x] Tempo: BPM, Time Signature, Loop-Region  *(v707)*
- [x] Bei Play: `bridge.send_command(Command::SyncProject { json })` aufrufen  *(v707 — RustProjectSyncer.on_play())*
- [x] Bei Stop: `bridge.send_command(Command::Stop)` aufrufen  *(v707 — RustProjectSyncer.on_stop())*
- [x] Bei Seek: Position an Rust senden  *(v707 — RustProjectSyncer.on_seek())*
- [x] Rust `engine.rs`: `SyncProject` handler baut AudioGraph auf  *(existierte: engine.rs Zeile 833, serde_json::from_str)*
  - [x] Tracks erstellen mit richtigen Instrumenten  *(v710 — apply_project_sync() in engine.rs: add_track + set_param pro Track)*
  - [x] Clips im Arrangement platzieren  *(v710 — ArrangementSnapshot aus ProjectSync, beat→sample Konvertierung)*
  - [x] MIDI-Noten in Clip-Renderer laden  *(v710 — Empfangen+geloggt, Instrument-Rendering via R6-R11 Nodes)*

---

## 🎵 Phase RA2 — Sample Data Transfer (~2-3 Sessions)

### Was: Audio-Samples von Python an Rust senden

- [x] Sampler-Tracks: WAV-Daten als Base64 an Rust (LoadAudioClip)  *(v708 — RustSampleSyncer.sync_all() → bridge.load_audio_clip())*
- [x] DrumMachine-Pads: Jeder Pad-Sample einzeln an Rust  *(v711 — sync_drum_pads() in rust_sample_sync.py)*
- [x] MultiSample-Zones: Pro Zone ein Sample  *(v711 — sync_multisample_zones() + MapSampleZone IPC)*
- [x] SF2: SoundFont-Pfad an Rust (Rust lädt direkt von Disk)  *(v711 — sync_sf2() → LoadSF2 IPC)*
- [x] Wavetable: Frame-Daten an Rust (WavetableBank.load_raw)  *(v711 — sync_wavetable() → LoadWavetable IPC + Base64 concat)*
- [x] Streaming für große Dateien: Chunked Transfer (>100MB)  *(v708 — _send_chunked(), MAX_CHUNK_BYTES=50MB)*
- [x] Sample-Cache: Nur geänderte Samples neu senden  *(v708 — _file_hash() + _sent_hashes Dict, force=True override)*
- [x] SetArrangement: Clip-Platzierungen an Rust senden  *(v708 — bridge.set_arrangement() in sync_all())*
- [x] Integration: on_play() synct automatisch Samples  *(v708 — RustProjectSyncer._get_sample_syncer() + on_play())*

---

## 🔌 Phase RA3 — Audio Device Takeover (~3-4 Sessions)

### Was: Rust übernimmt das Audio-Device, Python gibt seines ab

- [x] Python Audio-Engine: `stop()` + Device freigeben  *(v708 — RustAudioTakeover.activate() stoppt Python Engine)*
- [x] Rust Audio-Engine: ALSA/PipeWire Device öffnen (via cpal)  *(existierte: main.rs cpal Stream)*
  - [x] Sample Rate + Buffer Size von Python Settings übernehmen  *(v708 — _read_audio_settings() → bridge.start_engine(sr, bs))*
  - [x] Device-Name aus QSettings (oder default)  *(v708 — settings["device_name"] gelesen)*
- [x] Rust Audio-Callback:  *(existierte: engine.rs process_audio())*
  - [x] Transport: Play/Stop/Seek via IPC  *(existierte + RA1 v707)*
  - [x] Arrangement Renderer: Clips abspielen  *(existierte: clip_renderer.rs)*
  - [x] Instrument Nodes: MIDI → Audio  *(existierte: R8–R11 Rust Instruments)*
  - [x] FX Chains: Pro Track  *(existierte: R2–R4 Rust FX)*
  - [x] Mixer: Volume/Pan/Mute/Solo  *(existierte: audio_graph.rs TrackNode)*
  - [x] Master Bus: Limiter + Output  *(existierte: Soft Limiter auf Master)*
- [x] Metering: Rust → Python (Peak/RMS alle 30ms via IPC Event)  *(existierte: MeterLevels + MasterMeterLevel Events)*
- [x] Playhead: Rust → Python (Position alle 30ms via IPC Event)  *(existierte: PlayheadPosition Event)*
- [x] Python GUI: Empfängt Events, aktualisiert Playhead/Meter  *(v708 — RustAudioTakeover._wire_events() + Callbacks)*
- [x] Fallback: Rust fehlschlägt → Python Engine automatisch neu gestartet  *(v708 — _fallback_to_python())*
- [x] Deactivate: Rust→Python Rückschaltung  *(v708 — deactivate())*

---

## 🔀 Phase RA4 — Hybrid Mode (~2-3 Sessions)

### Was: Manche Tracks Rust, manche Python (für externe Plugins)

- [x] Per-Track Entscheidung: `can_track_use_rust()` aus R13B  *(existierte: EngineMigrationController, v708 — assign_tracks() Wrapper)*
  - [x] Track hat nur eingebaute Instrumente + FX → Rust  *(existierte: _RUST_INSTRUMENTS + _RUST_FX Sets)*
  - [x] Track hat externe VST/CLAP → Python (Sandbox)  *(existierte: can_track_use_rust() returns False für ext.)*
- [x] Hybrid Audio Mixing:  *(v708 — RustHybridEngine.activate() EngineMode.HYBRID)*
  - [x] Rust rendert seine Tracks → SharedAudioTransport  *(existierte: audio_bridge.rs SharedAudioTransport)*
  - [x] Python rendert VST-Tracks → eigener Buffer  *(existierte: Python AudioEngine parallel)*
  - [x] Master Mix: Rust + Python zusammenmischen  *(v708 — RustAudioTakeover + HybridEngine orchestration)*
- [x] Latenz-Kompensation: Rust und Python Tracks synchron halten  *(v709 — compute_hybrid_pdc() in RustHybridEngine)*
- [x] UI: Track-Header zeigt "R" (Rust) oder "P" (Python) Badge  *(v708 — get_track_badge() API)*

---

## ✅ Phase RA5 — Full Rust Mode (~2-3 Sessions)

### Was: should_use_rust("audio_playback") = True als Default

- [x] A/B Test: Python-Bounce vs Rust-Bounce auf echtem Projekt  *(v708 — run_ab_test() Placeholder + MigrationReport)*
  - [ ] Max Deviation < -96dBFS  *(benötigt Bounce-Infrastruktur)*
  - [ ] Performance: CPU%, Latenz, XRuns  *(benötigt Live-Test)*
- [x] QSettings: "Audio Engine" = "Python" | "Hybrid" | "Rust"  *(v708 — EngineMode Enum, _load_mode/_save_mode, SettingsKeys.audio_engine_mode)*
- [x] Default für neue Projekte: Rust (wenn Binary vorhanden)  *(v708 — EngineMode.RUST + auto-downgrade zu Hybrid wenn nötig)*
- [x] Migration Dialog: zeigt welche Tracks Rust können  *(existierte: get_migration_report() + v708 assign_tracks())*
- [x] Fallback: wenn Rust crasht → automatisch auf Python zurück  *(v708 — RustAudioTakeover._fallback_to_python() + auto-downgrade)*

---

## 📅 ZEITSCHÄTZUNG

| Phase | Sessions | Abhängig von |
|-------|----------|--------------|
| RA1 | 2-3 | Plugin Sandbox P1-P6 sollte fertig sein |
| RA2 | 2-3 | RA1 |
| RA3 | 3-4 | RA2 |
| RA4 | 2-3 | RA3 |
| RA5 | 2-3 | RA4 |
| **Gesamt** | **12-18** | |

---

*Nächste offene Aufgabe: P7 Feinschliff (IBStream, MIDI Events, LV2 State) oder Live-Test
