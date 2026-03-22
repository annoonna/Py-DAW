# SESSION v0.0.20.238 — LV2: Reverb/Delay hörbar + Offline Render SAFE (2026-03-05)

## Kontext
User Report:
- LV2 Plugins zeigen `DSP: ACTIVE`, aber viele Effekte (Reverb/Delay) sind praktisch **nicht hörbar**.
- Einige Plugins crashen (SIGSEGV/SIGBUS) → Safe Mode blockt korrekt.
- Gewünscht: **crashsicheres Offline-Render** (Freeze/Render-ähnlich), ohne die DAW zu gefährden.

## Root Cause (wahrscheinlich)
Ein Teil der LV2 Plugins exponiert **mehr als 2 Audio-Out Ports** (z.B. Dry-Taps, Monitoring-Outs).
Der Host hat bisher die Output-Ports rein nach Index kopiert und dadurch oft die „dry“ Ausgänge
zurück in den Track geschrieben → subjektiv „kein Effekt“, obwohl DSP läuft.

## Änderungen (SAFE)

### 1) LV2 Host: Audio-Port Ordering / Selection (hörbar)
- `pydaw/audio/lv2_host.py`
  - Audio-Port-Metadaten (symbol/name) werden erfasst.
  - Heuristische Scoring-Funktion:
    - Outputs: bevorzugt `out/output/wet/fx/effect`, meidet `dry`
    - Inputs: bevorzugt `in/input`, meidet `sidechain/aux`
  - Ports werden so **geordnet**, dass die ersten 1–2 Outputs sehr wahrscheinlich die „wet/main“ Ausgänge sind.
  - Stabilität bleibt: **alle** Audio-Ports werden weiterhin connected (reduziert Crash-Risiko), aber kopiert werden die „besten“.

### 2) LV2 UI: Audition Dry/Wet Heuristik verbessert
- `pydaw/ui/fx_device_widgets.py`
  - `dry/wet` und `dry_wet` → Richtung „wet“ (MAX)
  - `wet_dry` → Richtung „wet“ (MIN) (best-effort)

### 3) LV2 Insert Defaults: Dry/Wet Heuristik verbessert
- `pydaw/ui/device_panel.py`
  - Beim Einfügen eines LV2 FX werden nur „sichere“ Defaults gesetzt:
    - `bypass*` → MIN
    - `dry_wet*` → MAX
    - `wet_dry*` → MIN

### 4) LV2 Probe: Control-Ports mit Defaultwerten initialisieren
- `pydaw/tools/lv2_probe.py`
  - Probe verbindet Control-Ports jetzt mit **Defaultwerten** (statt 0.0)
  - reduziert False-Blocks, wenn Plugins empfindlich auf 0-Werte reagieren.

### 5) Offline Render: Subprocess (SAFE)
- `pydaw/tools/lv2_offline_render.py` (neu)
- `pydaw/audio/lv2_host.py`: `offline_process_wav_subprocess()` (neu)
- `pydaw/ui/plugins_browser.py`: Context-Menü nutzt jetzt Subprocess-Renderer

Ergebnis:
- Offline-Render kann crashende Plugins testen/rendern, ohne den Hostprozess zu killen.

## Ergebnis / Erwartung
- Reverb/Delay sollten deutlich besser hörbar sein (Port-Auswahl greift).
- Offline-Render ist stabiler (Subprocess).
- Crashende LV2 bleiben live blockiert (Safe Mode), können aber offline ausprobiert werden.
