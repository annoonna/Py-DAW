# CHANGELOG v0.0.20.655 — Mixer Multi-Output UI + Collapse/Expand

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP5 Phase 5C (Multi-Output UX)

## Was wurde gemacht

### Mixer-Kontextmenü: Multi-Output für Drum Machine
- **Rechtsklick auf Drum-Machine-Kanal** im Mixer zeigt:
  - "🎛 Multi-Output aktivieren (16 Pads)" — erstellt 15 Child-Audio-Tracks
  - "🔇 Multi-Output deaktivieren" — löscht Child-Tracks, Reset auf Stereo
- **Automatische Track-Erstellung:**
  - 15 Child-Tracks mit Namen: "Drum: Snare", "Drum: CHat", ..., "Drum: Pad16"
  - Jeder Child-Track bekommt `track_group_id = parent_track_id` (organisatorische Gruppierung)
  - `Track.plugin_output_routing = {1: child1_id, 2: child2_id, ...}` wird automatisch gesetzt
  - `Track.plugin_output_count = 16` wird aktiviert
  - `AudioEngine.rebuild_fx_maps()` wird aufgerufen → Routing sofort aktiv
- **Erkennung:** Kontextmenü prüft `plugin_type` UND `instrument_state` für Drum-Machine-Tracks

### Collapse/Expand für Multi-Output-Kanäle
- **"📁 Pad-Kanäle ausblenden"** — versteckt alle 15 Child-Strips im Mixer (UI-only)
- **"📂 Pad-Kanäle einblenden"** — zeigt sie wieder
- Collapse-State überlebt `MixerPanel.refresh()` (via `_restore_collapse_states()`)
- State pro Parent-Strip (`_children_collapsed` Attribut)

### Mixer-Strip Kontext-Menü (allgemein)
- Rechtsklick auf jeden Strip zeigt Rename-Option
- Drum-Machine-spezifische Optionen nur bei erkannten Drum-Tracks

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw/ui/mixer.py` | `_MixerStrip.contextMenuEvent()`, `_enable_multi_output()`, `_disable_multi_output()`, `_collapse_children()`, `_expand_children()`, `_set_children_visible()`, `_is_drum_machine_track()`, `_has_multi_output_children()`, `MixerPanel._restore_collapse_states()` |
| `VERSION` | 0.0.20.655 |
| `pydaw/version.py` | 0.0.20.655 |

## Vollständige Multi-Output-Pipeline (v652-v655)
```
1. User: Rechtsklick auf Drum-Track → "Multi-Output aktivieren"
2. _enable_multi_output() erstellt 15 Child-Audio-Tracks
3. Track.plugin_output_routing = {1: "trk_snare", 2: "trk_chat", ...}
4. AudioEngine.rebuild_fx_maps() → baut _plugin_output_map
5. DrumMachineWidget.set_track_context() → engine.set_multi_output(True, 16)
6. DrumMachineEngine.pull() → (frames, 32) Multi-Channel-Buffer
7. HybridAudioCallback.render_for_jack() Step 8:
   - Output 0:2 → Parent-Track "Kick" (vol/pan/FX/meter)
   - Output 2:4 → Child-Track "Snare" (vol/pan/FX/meter)
   - ...
8. Jeder Child-Track hat eigenen Mixer-Strip mit VU-Meter
9. User: "Pad-Kanäle ausblenden" → Collapse (UI-only)
```

## Was als nächstes zu tun ist
- AP7 Phase 7A — Advanced Sampler (Multi-Sample Mapping, Round-Robin)
- AP10 Phase 10C — DAWproject Roundtrip
