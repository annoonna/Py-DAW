# SESSION v0.0.20.220 — NOTE-FX Parameter-UI + Slot-FX Collapse (SAFE)

Datum: 2026-03-04

## Ziel
- NOTE-FX in Pro Drum Machine waren zwar droppbar, aber **ohne Parameter-UI** (keine Slider/Werte editierbar).
- Slot-FX Rack war sehr groß und sollte **einklappbar** werden, ohne DnD/Audio zu brechen.

## Änderungen (UI-only, Core unangetastet)

### 1) NOTE-FX: inline Parameter-UI (wie Audio-FX)
- `NoteFxInlineStrip` nutzt jetzt `NoteFxDeviceCard` statt Minimal-Row.
- Jede NOTE-FX Instanz zeigt standardmäßig **Parameter-UI** (expand/collapse pro Device).
- Parameter-UI wird über bestehende `make_note_fx_widget(...)` Widgets erzeugt:
  - Transpose / VelScale / ScaleSnap / Chord / Arp / Random / AI Composer.
- Safe Services-Fassade: `_NoteFxServices` (nur `services.project` + `project_updated`).

### 2) Slot-FX Rack: einklappbar
- `SlotFxInlineRack` bekam einen Toggle-Button (▾/▸), der Body (Chain + Cards) ein/ausblendet.
- UX: Wenn Rack eingeklappt ist und man FX drauf zieht → Rack klappt automatisch auf (DragEnter).

## Dateien
- `pydaw/plugins/drum_machine/drum_widget.py`

## Test
1. Pro Drum Machine → NOTE-FX droppen → Parameter-UI sichtbar, Werte änderbar.
2. Slot-FX Rack einklappen/ausklappen → nichts crasht, DnD bleibt.
3. Drag auf eingeklapptes Slot-FX Rack → klappt auf.

## Risiko
- Niedrig: ausschließlich UI/Widget-Logik, keine AudioEngine/Projektformat-Migration.
