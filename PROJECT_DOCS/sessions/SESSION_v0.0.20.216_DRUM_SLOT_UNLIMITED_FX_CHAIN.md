# SESSION v0.0.20.216 — Drum Slot: Unlimited FX Chain (per Slot) + Inline Rack (No Popup)

Datum: 2026-03-04

## Ziel
User requirement: **Jeder DrumMachine-Slot soll mit beliebig vielen Audio-FX aus dem Browser** (Drag&Drop + Add-Menu) bestückt werden können — ohne DAW-Core zu ändern.

Zusätzlich gewünscht:
- **Power-Button / Bypass je Slot-FX** (klarer Icon-Style)
- **Parameter-UI im Rack** (kein Popup nötig; inline/collapsible)

## Änderungen (safe, UI-only + Engine-local)

### 1) Per-slot Audio-FX Chain im DrumMachineEngine
- `DrumSlotState` enthält jetzt `audio_fx_chain` (JSON-safe):
  - `{type:chain, enabled, mix, wet_gain, devices:[]}`
- Jeder `DrumSlot` hält eine kompilierte `ChainFx` Instanz (aus `pydaw.audio.fx_chain`) mit stabiler FX-ID:
  - `"{track_id}:slot{index}"`
- In `DrumMachineEngine.pull()` wird nach dem Slot-Engine Pull **die Slot-FX Chain in-place** angewendet.
- Rebuild der Chain passiert **nur bei strukturellen Änderungen** (Add/Remove/Enable/Reorder) über `rebuild_slot_fx()`.

### 2) Inline Slot-FX Rack (unlimited) mit Reuse der bestehenden FX Widgets
- Ersetzt das vorherige „nur 5 Effekte“ Rack.
- Reuses `make_audio_fx_widget()` + `AudioChainContainerWidget` über **Dummy-Services**, sodass:
  - volle Parameter-UI pro Effekt verfügbar ist
  - RTParamStore Keys korrekt auf `afx:{slot_fx_track_id}:{device_id}:param` gehen
  - kein globales `audio_engine.rebuild_fx_maps()` ausgelöst wird (Dummy-Engine = no-op)
- UI:
  - Drag&Drop aus Browser (Effects → Audio-FX)
  - Add-Menü mit allen `fx_specs.get_audio_fx()` Einträgen
  - Device Cards mit:
    - **⏻ Power** (Enable/Bypass)
    - Move Up/Down
    - Remove
    - Collapse/Expand (inline parameter UI, kein Popup)

### 3) Persist/Restore
- Slot-FX Chain wird in `DrumMachineEngine.export_state()` pro Slot gespeichert.
- Restore via `import_state()`; anschließend rebuild aller Slot-FX Chains.

## Dateien
- `pydaw/plugins/drum_machine/drum_engine.py`
- `pydaw/plugins/drum_machine/drum_widget.py`

## Hinweise
- Keine Änderungen am Projekt-Core oder Track-FX System.
- Slot-FX Chains laufen post-slot (nach ProSamplerEngine internem FX/Filter).

