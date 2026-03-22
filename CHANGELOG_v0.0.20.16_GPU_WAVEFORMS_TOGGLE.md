# CHANGELOG v0.0.20.16 — GPU Waveforms Toggle

**Datum:** 2026-02-08  
**Basis:** v0.0.20.15

---

## ✅ Fix / UX

### Arranger: GPU-Waveforms opt-in + jederzeit abschaltbar
- Neues View-Menü: **Ansicht → GPU Waveforms** (Checkable)
- Persistenz über Settings: `ui/gpu_waveforms_enabled`
- Status-Anzeige unten rechts: **GPU: ON/OFF**

**Warum:** In v0.0.20.14/15 konnte ein OpenGL-Overlay auf manchen Systemen den Arranger-Grid optisch „überdecken“ (wirkt wie „Arranger kaputt“). Jetzt ist GPU-Waveforms **standardmäßig AUS** und kann per Menü gezielt eingeschaltet und sofort wieder ausgeschaltet werden.

### Overlay: Playhead korrekt (Beat → Pixel)
- Wenn GPU-Waveforms aktiv ist, wird der Playhead-Cursor korrekt über `beat * pixels_per_beat` an das Overlay übergeben.
- Zoom-Änderungen syncen das Overlay automatisch.

---

## Dateien

### Geändert
- `pydaw/ui/actions.py` — QAction: `view_toggle_gpu_waveforms` (Ctrl+Shift+G)
- `pydaw/ui/main_window.py` — Menüpunkt + Persistenz + Statusbar-Indikator
- `pydaw/ui/arranger_canvas.py` — Runtime Enable/Disable + Playhead/Zoom Sync
- `pydaw/core/settings.py` — neuer Key: `ui_gpu_waveforms_enabled`
- `pydaw/version.py`, `VERSION` — auf v0.0.20.16 aktualisiert

---

## Test-Checkliste

1. Starten → Arranger muss normal sichtbar sein (Grid nicht verdeckt).
2. Ansicht → GPU Waveforms **AN** → Overlay erscheint.
3. Ansicht → GPU Waveforms **AUS** → Arranger sofort wieder „clean“.
4. Zoom +/- → Overlay bleibt aligned.

