# CHANGELOG v0.0.20.67 — Sampler/DrumMachine Audio-Output-Fix

**Datum:** 2026-02-13

## Problem
Pro Audio Sampler und Pro Drum Machine spielten keinen Ton, obwohl Samples korrekt geladen waren.

## Ursachen

### 1. Strikte Sample-Rate-Prüfung
Die `pull()` Methoden in beiden Engines gaben `None` zurück, wenn die angeforderte Sample-Rate nicht exakt mit der Engine-Target-SR übereinstimmte:

```python
# Vorher - PROBLEM:
if int(sr) != int(self.target_sr):
    return None  # ← Stille!
```

Das führte zu vollständiger Stille, wenn:
- Die Audio-Einstellungen 44100 Hz verwendeten, aber die Engines mit 48000 Hz erstellt wurden
- Oder umgekehrt

### 2. SamplerRegistry nicht im HybridCallback (Preview-Mode)
Bei `ensure_preview_output()` wurde die `_sampler_registry` nicht zum HybridAudioCallback durchgereicht.

### 3. Hardcodierte Sample-Rate in Preview-Config
Die sounddevice Preview-Config verwendete hardcodiert 48000 Hz statt der tatsächlichen Audio-Einstellungen.

## Fixes

### Fix 1: Dynamische SR-Anpassung statt Stille
Die Engines passen jetzt ihre `target_sr` dynamisch an, wenn eine andere Sample-Rate angefordert wird:

**sampler_engine.py:**
```python
if int(sr) != int(self.target_sr):
    # Warnung loggen (einmalig)
    # target_sr dynamisch anpassen
    self.target_sr = int(sr)
```

**drum_engine.py:**
```python
if int(sr) != int(self.target_sr):
    # Warnung loggen (einmalig)
    # target_sr für Engine und alle Slots anpassen
    self.target_sr = int(sr)
    for s in self.slots:
        s.engine.target_sr = int(sr)
```

### Fix 2: SamplerRegistry in JACK Preview
`ensure_preview_output()` übergibt jetzt `_sampler_registry` zum HybridCallback:

```python
# v0.0.20.67: Wire sampler registry for preview MIDI routing
if hasattr(self, "_sampler_registry") and self._sampler_registry is not None:
    hybrid_cb._sampler_registry = self._sampler_registry
```

### Fix 3: Dynamische SR in Preview-Config
Die sounddevice Preview-Config verwendet jetzt `get_effective_sample_rate()`:

```python
sr = self.get_effective_sample_rate()
cfg = {
    "mode": "silence",
    "sample_rate": sr,  # ← Nicht mehr hardcodiert 48000
    "sampler_registry": self._sampler_registry,  # ← Für MIDI-Dispatch
    ...
}
```

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/plugins/sampler/sampler_engine.py` | SR-Mismatch → dynamische Anpassung |
| `pydaw/plugins/drum_machine/drum_engine.py` | SR-Mismatch → dynamische Anpassung (inkl. Slots) |
| `pydaw/audio/audio_engine.py` | Preview: SamplerRegistry + dynamische SR |
| `pydaw/version.py` | → 0.0.20.67 |

## Test

1. Starte PyDAW ohne JACK (`python3 main.py`)
2. Erstelle einen Instrument Track
3. Füge Pro Audio Sampler oder Pro Drum Machine hinzu
4. Lade ein Sample
5. Platziere MIDI-Noten im Piano Roll
6. Drücke Play → **Ton sollte hörbar sein**

## Hinweis
Falls die Sample-Rate nicht übereinstimmt, erscheint eine Warnung im Log:
```
ProSamplerEngine: SR mismatch (got 44100, expected 48000). Audio may be pitched incorrectly.
```

Das Audio wird trotzdem ausgegeben. Für beste Qualität sollten Audio-Einstellungen und Engine-SR übereinstimmen.
