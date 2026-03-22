# Session v0.0.20.578 — Fusion MIDI/Range/Realtime-Safety Hotfix

**Datum:** 2026-03-17
**Entwickler:** OpenAI GPT-5.4 Thinking
**Task:** Fusion haengt/kippt bei GUI-Bedienung und MIDI-CC-Steuerung stabilisieren
**Prioritaet:** CRITICAL — User-Report: Fusion friert bei GUI/MIDI ein, BachOrgel nicht

---

## Problem-Analyse

Der neue Fusion-Performance-Fix aus v0.0.20.577 hat zwar die grobe Lock-Contention beseitigt,
aber im praktischen Einsatz blieben drei kritische Schwachstellen:

1. **Falsche Knob-Ranges im Fusion-Widget**
   - `CompactKnob` war effektiv immer 0..100.
   - Fusion uebergab zwar sinnvolle Bereiche (`pitch_st -7..+7`, `pan -100..+100`,
     `mode 0..3`, `voices 1..8`, `damp_freq 200..20000`), diese wurden aber ignoriert.
   - Ergebnis: ungueltige/unsaubere Werte im Engine-Graph, speziell bei MIDI-CC.

2. **Dynamische Extra-Knobs waren nicht voll re-verdrahtet**
   - Nach OSC/FLT/ENV-Wechsel wurden neue Widgets erzeugt.
   - Diese waren nicht konsequent wieder an Automation/MIDI Learn angebunden.
   - Alte CC-Listener konnten im AutomationManager haengen bleiben.

3. **Race zwischen GUI/MIDI-Thread und Audio-Render**
   - `FusionEngine.set_param()` schrieb direkt in aktive Voice-Objekte,
     waehrend `pull()` parallel dieselben OSC/FLT/ENV-Objekte renderte.
   - Unter starkem CC-Drehen konnte das zu instabilem Verhalten, Hangs oder Abstuerzen fuehren.

---

## Loesung

### A) `CompactKnob` kann jetzt echte Wertebereiche

**Datei:** `pydaw/plugins/sampler/ui_widgets.py`

- `CompactKnob` erweitert um:
  - `setRange(min, max)`
  - `minimum()` / `maximum()`
  - normierte Arc-/Pointer-Darstellung ueber beliebige Bereiche
  - MIDI-CC-Skalierung 0..127 -> `min..max`
  - Tooltip-/Value-Text passend zum echten Bereich

**Wirkung:**
- Fusion-Knoepfe arbeiten jetzt wirklich mit ihren vorgesehenen Bereichen.
- Kritische Parameter wie `pitch_st`, `pan`, `voices`, `mode`, `unison_voices`, `damp_freq`
  laufen nicht mehr in falsche 0..100-Defaultwerte.

### B) Fusion-Widget korrekt neu verdrahtet

**Datei:** `pydaw/plugins/fusion/fusion_widget.py`

- `_make_knob()` setzt jetzt die echten Bereiche auf dem Knob.
- Neue Helper-Methode `_bind_knob_automation()` fuer sauberes Re-Binding.
- Dynamische OSC/FLT/ENV-Extra-Knobs:
  - werden beim Rebuild aus `_knobs` sauber entfernt
  - alte MIDI-CC-Listener werden abgemeldet
  - neue Widgets werden sofort wieder an Automation + MIDI Learn gebunden
- `randomize()` nutzt jetzt den echten Bereich jedes Knobs.
- `FusionWidget._on_knob_changed()` korrigiert/erweitert Skalierungen fuer:
  - `flt.env_amount` (-100..100 -> -1..1)
  - `flt.mode`, `flt.feedback`, `flt.damp_freq`
  - `aeg.loop`
  - `osc.unison_mode`, `osc.unison_voices`, `osc.unison_spread`, `osc.index`, `osc.smooth`
  - sowie bestehende Pitch/Pan/Detune/Ratio-/Shape-Faelle

**Wirkung:**
- Fusion fuehlt sich jetzt wie die anderen Instrumente verdrahtet an.
- Modulwechsel hinterlaesst keine "toten" oder falsch gemappten Extra-Knobs mehr.

### C) Realtime-sichere Param-Synchronisation in Fusion

**Datei:** `pydaw/plugins/fusion/fusion_engine.py`

- `set_param()` arbeitet jetzt unter Lock nur noch auf dem **shared state**.
- Aktive Voices werden **nicht mehr mitten im Rendern** direkt mutiert.
- Neue Methode `_sync_active_voice_params_locked()`:
  - uebernimmt die aktuellen Shared-Parameter
  - appliziert sie gesammelt auf aktive Voices
  - und zwar am sicheren Pull-Rand **unter Lock vor dem Snapshot**
- `set_oscillator()` / `set_filter()` / `set_envelope()` sind jetzt ebenfalls gelockt.

**Wirkung:**
- Kein Mid-Render-Param-Mutate mehr durch GUI/MIDI Learn.
- Stabiler bei schnellem CC-Drehen und waehrend laufendem Audio.

---

## Geaenderte Dateien

1. `pydaw/plugins/sampler/ui_widgets.py`
2. `pydaw/plugins/fusion/fusion_widget.py`
3. `pydaw/plugins/fusion/fusion_engine.py`

---

## Validierung

### Statisch
- `python3 -m py_compile` auf allen 3 geaenderten Dateien: **OK**

### Laufzeitnah (headless Engine-Smoke-Test)
- FusionEngine instanziiert
- `note_on()` + parallele `set_param()`-Aenderungen + `pull()` in Threads
- keine Exceptions, Buffer-Shape korrekt, kein Deadlock

---

## Nichts kaputt gemacht ✅

- Kein Umbau der Fusion-Architektur
- Kein Eingriff in andere Instrumente ausser der allgemein nuetzlichen Range-Erweiterung von `CompactKnob`
- Default-0..100-Verhalten fuer bestehende Plugins bleibt erhalten
- Preset-/Instrument-State bleibt kompatibel
- Automation/MIDI Learn bleibt auf bestehendem Pfad

---

## Nächste sinnvolle Schritte

1. User-Test: Fusion + MIDI Learn auf mehreren Parametern pruefen
2. Optional: dezenter Guard/Throttle fuer sehr schnelle CC-Bursts
3. Danach erst neue Features (LFO/FX/Unison) — erst Stabilitaet sichern
