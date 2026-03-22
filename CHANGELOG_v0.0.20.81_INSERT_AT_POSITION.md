# CHANGELOG v0.0.20.81 — Device-Drop "Insert at Position"

**Datum:** 2026-02-15
**Developer:** Claude Opus 4.6

## Feature: Insert-at-Position für Device-Drop

### Vorher (v0.0.20.80)
Beim Droppen von Note-FX / Audio-FX Devices wurde das neue Device **immer am Ende** der Kette angehängt (`list.append`). Um es an die richtige Position zu bringen, musste man danach die Up/Down-Buttons benutzen.

### Nachher (v0.0.20.81)
Devices werden an der **Cursor-Position** eingefügt. Ein visueller Drop-Indicator (vertikale cyan-Linie) zeigt in Echtzeit, wo das Device landen wird.

### Implementierung

**Neues Widget:**
- `_DropIndicator(QFrame)`: 3px breite cyan-Linie, wird als Overlay auf `chain_host` positioniert

**Neue Methoden in `DevicePanel`:**
- `_update_drop_indicator(event, kind)`: Berechnet Insert-Position aus Cursor-X
- `_get_chain_card_positions(kind)`: Sammelt (x, width) aller Cards einer Zone
- `_get_zone_start_x(kind)`: Startposition für leere Zonen
- `_show_drop_indicator_at(x)`: Positioniert + zeigt Indicator
- `_hide_drop_indicator()`: Versteckt Indicator + resettet State

**Geänderte API:**
- `add_note_fx_to_track(track_id, plugin_id, *, insert_index=-1)`
- `add_audio_fx_to_track(track_id, plugin_id, *, insert_index=-1)`
- `-1` = append (Rückwärtskompatibel), `0..N` = `list.insert(index, device)`

**Algorithmus:**
1. DragMove → Event-Position via `globalPosition` + `mapFromGlobal` auf chain_host umrechnen
2. Cards der passenden Zone sammeln (Note-FX: index 0..N-1, Audio-FX: index N+1..N+M)
3. Cursor-X mit Card-Center vergleichen → Insert-Index bestimmen
4. Indicator an der Gap-Position zwischen Cards anzeigen
5. Drop → gespeicherten Index nutzen, Indicator verstecken

### Geänderte Dateien
- `pydaw/ui/device_panel.py` (~+160 Zeilen)
- `pydaw/version.py`
- `pydaw/model/project.py`
- `VERSION`
