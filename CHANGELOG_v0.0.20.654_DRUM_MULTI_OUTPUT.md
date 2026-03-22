# CHANGELOG v0.0.20.654 — Drum Machine Multi-Output Engine

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP5 Phase 5C (Wiring) + AP7 Phase 7B Vorbereitung (Drum Machine)

## Was wurde gemacht

### Drum Machine Multi-Output Engine
- **DrumMachineEngine** komplett um Multi-Output erweitert:
  - `set_multi_output(enabled, output_count)` — schaltet zwischen Stereo-Sum und Per-Pad-Outputs
  - `set_slot_output(slot_index, output_index)` — weist Pad einem Output-Paar zu
  - `_slot_output_map: List[int]` — Default: Pad i → Output i
  - `pull()` dispatcht automatisch zu `_pull_stereo()` oder `_pull_multi_output()`
  - `_pull_stereo()` — alter Codepfad, exakt wie vorher (backwards-kompatibel)
  - `_pull_multi_output()` — rendert (frames, 2*output_count) Buffer, jedes Pad in eigenes Stereo-Paar
  - `_multi_buf` Pre-Allokation für Zero-Alloc nach erstem Call
  - Unmapped/Out-of-range Pads fallen auf Output 0 (Parent-Track) zurück
- **Fehlende Methoden** hinzugefügt:
  - `set_fx_context(track_id, rt_params)` — setzt FX-Kontext für per-Slot FX-Chains
  - `rebuild_all_slot_fx()` — kompiliert alle Slot-FX-Chains (war referenziert aber fehlte)

### DrumMachineWidget Multi-Output Wiring
- `set_track_context()` prüft `Track.plugin_output_count` und aktiviert Multi-Output automatisch
- `_pull_fn._pydaw_output_count` wird aus Projektdaten gesetzt
- HybridAudioCallback (v653) splittet den Multi-Channel-Buffer automatisch an Child-Tracks

### Vollständige Pipeline (v652 → v654)
```
Track.plugin_output_routing {1: "trk_kick", 2: "trk_snare", ...}
    → AudioEngine.rebuild_fx_maps() baut _plugin_output_map
    → HybridEngineBridge.set_plugin_output_map() → Atomic Swap
    → render_for_jack() Step 8: prüft _pydaw_output_count
    → DrumMachineEngine.pull() liefert (frames, 32) für 16 Outputs
    → _mix_source_to_track() routet Output 0 → Parent, 1..15 → Child-Tracks
    → Jeder Child-Track hat eigene FX-Chain, Vol/Pan, VU-Meter im Mixer
```

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw/plugins/drum_machine/drum_engine.py` | Multi-Output: set_multi_output(), _pull_multi_output(), _slot_output_map, set_fx_context(), rebuild_all_slot_fx() |
| `pydaw/plugins/drum_machine/drum_widget.py` | set_track_context(): Auto-Multi-Output aus Track.plugin_output_count, _pydaw_output_count Tagging |
| `VERSION` | 0.0.20.654 |
| `pydaw/version.py` | 0.0.20.654 |

## Was als nächstes zu tun ist
- **AP7 Phase 7A — Advanced Sampler**: Multi-Sample Mapping Editor, Round-Robin, Filter+ADSR, Mod-Matrix
- Mixer-UI: "Create Multi-Output Tracks" Button im Drum Machine Widget (erstellt 16 Child-Tracks automatisch)
- Drum Machine Widget: Per-Pad Output-Assignment-Dropdown in der Pad-UI

## Bekannte Probleme / Offene Fragen
- Multi-Output ist aktuell nur aktiv wenn Track.plugin_output_count >= 2 im Projektmodell
  → Braucht UI-Button "Enable Multi-Output" der plugin_output_count + plugin_output_routing setzt
- Sounddevice-Callback hat noch keinen Multi-Output-Pfad (JACK-first, wie von Anno gewünscht)
