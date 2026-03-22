# 📝 SESSION LOG: 2026-02-28 (ARRANGER - PLAYHEAD + COPY + PERFORMANCE)

**Entwickler:** GPT-5.2 Thinking (ChatGPT)
**Task:** Arranger Freeze / Copy-Workflow / Playhead-Seek wie echte DAW
**Version:** v0.0.20.142 → v0.0.20.143

---

## 🎯 User-Probleme (Screenshots)

1) **GUI-Freeze / „python3 antwortet nicht“** beim Arbeiten im Arranger, besonders bei langen Projekten (Bar 100+ / 500+).
2) **Playhead (rote Linie)** nicht greifbar → kein Seek auf Bar 5/6 möglich → Ctrl+V kann nicht „gezielt“ an Position.
3) **Multi-Clip Copy-Workflow** (Lasso → Ctrl + LMB Drag) soll wie Bitwig/Ableton: Ghost folgt, Drop snapt korrekt.
4) **Performance / Audio-Aussetzer** bei Playback + UI-Interaktion → UI-Updates dürfen Audio nicht „verhungern“ lassen.

---

## ✅ Fixes in v0.0.20.143

### 1) Massive Paint-Performance (CRITICAL)
**Root Cause:** `paintEvent()` benutzte `self.width()` (Canvas-Gesamtbreite) → bei großen Projekten extrem viele Grid-Linien/Bar-Shades werden *pro Tick* gelaufen, obwohl nur der Viewport sichtbar ist.

**Fix:**
- `paintEvent()` rendert jetzt **nur im ClipRect** (`event.rect()`) → loops laufen nur über den **sichtbaren Beat-Bereich**.
- Clips werden nur gerendert, wenn sie den sichtbaren Bereich schneiden (`intersects`).

➡️ Ergebnis: Kein O(project_length) mehr beim Grid-Draw.

### 2) Playhead-Partial-Update
**Root Cause:** `set_playhead()` machte `self.update()` → kompletter Arranger repaint bei jedem Transport-Tick.

**Fix:**
- `set_playhead()` invalidiert nur den **Stripe um alten + neuen Playhead** (kleines QRect).

➡️ Ergebnis: deutlich weniger Paint/Qt-Events → UI bleibt bedienbar, Audio weniger GIL-Pressure.

### 3) Playhead Seek/Drag (wie DAW)
- **Lineal unten (unter Zoom-Strip)**: Klick/Drag setzt Playhead.
- **Direkt auf roter Linie**: Drag funktioniert auch mitten im Canvas.
- **Snap** standard aktiv, **Shift** disables snap (Feinposition).

### 4) Ctrl+Drag Copy Preview (Multi-Clip)
**Alt-DAW-Style:** Original bleibt, Ghost folgt, Drop erzeugt Kopien.

- Ctrl+Drag auf Clip:
  - Wenn Clip Teil der Lasso-Auswahl ist → **ganze Auswahl** wird kopiert.
  - Ghost preview wird gezeichnet.
  - Auf MouseRelease werden Clips **gebatcht** kopiert (deepcopy) + `project._emit_updated()` **einmal**.

➡️ Kein „move-then-restore“ mehr → reduziert Freeze-Risiko massiv.

---

## 🗂️ Geänderte Dateien

- `pydaw/ui/arranger_canvas.py`
- `pydaw/version.py`
- `pydaw/model/project.py`
- `VERSION`
- `PROJECT_DOCS/sessions/LATEST.md`

---

## 🧪 Test-Hinweise

- Sehr große Projekte (Bar 500+): Scroll + Playback + UI bedienen (Selection, Drag, Zoom) → sollte flüssiger sein.
- Playhead: im Lineal unten klicken/ziehen → Ctrl+V sollte jetzt sauber an die Stelle.
- Lasso: mehrere Clips wählen → Ctrl halten + LMB Drag → Ghost, Drop → Kopien snappen.

