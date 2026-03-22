# SESSION v0.0.20.215 — Slot‑FX Rack: Drag&Drop aus Effects Browser (Pro Drum Machine)

**Datum:** 2026-03-04
**Assignee:** GPT‑5.2 Thinking (ChatGPT)
**Direktive:** Nichts kaputt machen (UI‑only, keine Core/DSP‑Refactors)

## Ziel (User Request)
Der User möchte unter **FX Rack** im Pro Drum Machine Slot‑Editor:
- Effekte aus dem Browser **Drag&Drop** hinzufügen
- Alternativ Effekte **auswählen** (ohne Drag)
- Ohne dass das UI/Projekt/Audio kaputt geht

## Umsetzung (safe)
- Neuer **Inline Slot‑FX Rack** im Slot‑Editor (unterhalb der FX‑Zeile)
- Akzeptiert Drops vom EffectsBrowser (_MIME: `application/x-pydaw-plugin`), `kind=audio_fx`
- **Mapping nur für FX, die ProSamplerEngine wirklich unterstützt:**
  - EQ‑5 (eq_enabled)
  - Distortion (dist_mix)
  - Delay‑2 (delay_mix + delay params default)
  - Reverb (reverb_mix)
  - Chorus (chorus_mix)
- Unsupported Drops werden **ignoriert** + Status‑Hint (kein Crash)
- Power‑Buttons pro Slot‑FX (Toggle) + schnelle Mix‑Slider für Mix‑FX
- Der bestehende „Slot FX Rack“ Dialog bleibt als **Details…** erhalten

## Files
- `pydaw/plugins/drum_machine/drum_widget.py`
- `VERSION`, `pydaw/version.py`

## Notes
- Keine Änderungen an DAW‑Core/DevicePanel/AudioEngine
- Persistenz erfolgt über existing `export_state()` / `import_state()` der ProSamplerEngine
