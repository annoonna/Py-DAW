# Session Log — 2026-02-02 — Scale Visualization (Cyan Dots)

**Version bump:** v0.0.19.5.1.18 → v0.0.19.5.1.19  
**Owner:** GPT-5.2  
**Ziel:** Pro-DAW-Style “cyan dots” — erlaubte Skalentöne visuell markieren.

---

## ✅ Umsetzung

### 1) Piano Roll Grid: Cyan Dots + dezente Row-Tint
- Wenn **Scale Lock aktiv** ist und **Scale-Hints aktiviert** sind:
  - Jede erlaubte Tonhöhe bekommt eine dezente cyan Row-Tint.
  - Zusätzlich werden cyan Dots im Grid gerendert (beat-abhängig, zoom-adaptiv).

### 2) Keyboard links: Cyan Dot pro erlaubter Taste
- Im Keyboard werden erlaubte Skalentöne durch einen cyan Dot angezeigt (Pro-DAW-like).

### 3) UI: Toggle für Visualisierung
- Im Scale-Menü gibt es jetzt einen Toggle:
  - **“Scale-Hints (Cyan Dots)”** (persistiert)

---

## 🔧 Geänderte Files
- `pydaw/core/settings.py` (neuer Key: `music/scale_visualize`)
- `pydaw/ui/scale_menu_button.py` (Toggle im Menu + Default)
- `pydaw/ui/pianoroll_canvas.py` (Grid Dots/Tint Rendering)
- `pydaw/ui/pianoroll_editor.py` (Keyboard Dots + Update-Refresh)

---

## 🧪 Quick Test (Manuell)
1) Piano Roll öffnen → Scale auswählen (nicht “Off”) → Scale Lock aktiv.  
2) Keyboard links: cyan dots müssen auf erlaubten Noten erscheinen.  
3) Grid: dezente cyan Markierung + dots sichtbar (zoomen +/- testen).  
4) Scale-Menü → “Scale-Hints (Cyan Dots)” aus → dots verschwinden, Constraint bleibt aktiv.

---

## Nächste mögliche Schritte
- Notation Editor ebenfalls mit cyan hints (Staff/Keyboard Overlay)
- Option: “Dots only” vs “Row Tint” als Unteroption
- Performance: Dots nur im sichtbaren Viewport (falls später nötig)
