# Session Log — v0.0.20.104 — Bachs Orgel Klang-Overhaul

**Datum:** 2026-02-21
**Bearbeiter:** Claude Opus 4.6 (Anthropic)
**Task:** Bachs Orgel Sound "blechern/böse" → warm/organisch

---

## Problem (User-Feedback)

> "kuck mal im instrument bach orgel die klinkt blechernt der sound ist total böse"

### Analyse — Warum klingt es blechern?

1. **Exakte Harmonische Verhältnisse** — Alle Pfeifen in perfektem mathematischem Verhältnis
   = klingt digital/steril. Echte Kirchenorgeln haben minimale Verstimmungen (±1-4 Cent)
   zwischen den Pfeifen, was den warmen "Schwebungs"-Effekt erzeugt.

2. **`np.roll`-Stereo** — Das alte Stereo-Widening verschob einfach Samples um 1-2 Positionen.
   Das erzeugt Kammfilter-Interferenzen = metallisches Kratzen bei bestimmten Frequenzen.

3. **Kein Luftgeräusch** — Echte Orgelpfeifen haben ein subtiles Windgeräusch (Air).
   Ohne das wirkt der Klang leblos und synthetisch.

4. **Zu aggressiver Drive** — `tanh`-Sättigung bei Drive/FX erzeugt viele hochfrequente
   Verzerrungsprodukte = harsch/kratzig.

5. **Zu viele Obertöne** — Presets hatten hohe Stop4/Stop2/Reed-Werte, dazu Triangle/Saw
   als Basis-Wellenform = zu viel Höhen-Inhalt.

---

## Lösung (v104)

### Engine (`bach_orgel_engine.py`)

| Feature | Alt (v103) | Neu (v104) |
|---------|-----------|-----------|
| Pipe-Tuning | Exakte Vielfache | ±1-4 Cent Detuning pro Pfeife |
| Chorus | Keiner | 0.31 Hz Drift, ±0.8 Cent |
| Stereo | `np.roll` (Kammfilter!) | Allpass-Dekorrelation + Mid/Side |
| Air/Wind | Keiner | Tiefpass-gefiltertes Rauschen |
| Sättigung | `tanh` (harsch) | Kubischer Soft-Clip (warm) |
| Oszillatoren | Triangle 85/15, Square tanh(2.2) | Triangle 75/25, Square tanh(1.8) |
| Saw | 4 Harmonische | 3 Harmonische (weicher) |
| Filter-Cutoff | 420-5200 Hz | 350-4500 Hz (wärmer) |
| Drive-Stärke | 0.60/0.85 Multiplier | 0.40/0.55 Multiplier |

### Presets (`bach_orgel_widget.py`)

- **Alle Presets auf `wave: 'sine'`** statt Triangle (weniger Obertöne)
- **Stop4/Stop2 reduziert** (weniger hochfrequenter Inhalt)
- **Reed/Click/Drive deutlich reduziert**
- **Neuer `air`-Parameter** in allen Presets (0.05-0.12)
- **Cutoff tiefer** (dunklerer, wärmerer Grundklang)

### Technische Details

- **Pipe-Detuning-Tabelle** mit physikalisch realistischen Werten (±0.9-2.2 Cent)
- **`_detune_freq()`**: Berechnet verstimmte Frequenz per Cent-Formel
- **`OrganVoice.pipe_phases`**: Dict mit unabhängiger Phase pro Pfeife
- **`render_pipe()`**: Rendert jede Pfeife mit eigener Phase + Drift
- **`_soft_clip()`**: `y = x - x³/3` — kubische Sättigung, weniger Obertöne als tanh
- **`_make_stereo()`**: Allpass-Dekorrelation statt destruktivem `np.roll`

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/plugins/bach_orgel/bach_orgel_engine.py` | Komplett überarbeitet (Pipe-Detuning, Drift, Stereo, Air, Soft-Clip) |
| `pydaw/plugins/bach_orgel/bach_orgel_widget.py` | Presets wärmer abgestimmt |
| `pydaw/version.py` | → 0.0.20.104 |
| `pydaw/model/project.py` | → 0.0.20.104 |
| `VERSION` | → 0.0.20.104 |

## NICHT geändert

- Kein anderes Instrument (Sampler, Drums)
- Keine Core-Audio-Engine
- Keine SamplerRegistry
- Kein UI-Layout (nur Preset-Werte)
- API/Contract identisch zu v103

---

## Test-Empfehlung

1. Bachs Orgel laden → Gottesdienst Preset → Akkord spielen → sollte warm + voll klingen
2. Alle Presets durchschalten → nirgends blechern/kratzig
3. Drive/Reed hochdrehen → soll sättigen aber nicht kratzen
4. 16tel-Noten → Fast Gate Release (v103) weiterhin intakt
5. Andere Instrumente (Sampler, Drums) → unverändert funktional
