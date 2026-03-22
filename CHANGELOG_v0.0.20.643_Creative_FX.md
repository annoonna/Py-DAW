# CHANGELOG v0.0.20.643 — Creative FX mit Scrawl + KI + UI Fix (AP8 Phase 8B)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP8 Phase 8B — Creative FX + UI Verbesserungen

## Was wurde gemacht

### AP8 Phase 8B — Creative FX mit Scrawl-Zeichenfläche: KOMPLETT ✅ (5/5)

Jeder Creative-Effekt hat eine zeichenbare Scrawl-Kurve die das Effekt-Verhalten
steuert — das ist ein EINZIGARTIGES Feature das es in keiner kommerziellen DAW gibt!

1. **ChorusFx** ✏️ — Scrawl = LFO-Form für Pitch-Modulation
   - Rate, Depth, Voices, Mix + frei zeichenbare LFO-Wellenform
   - Multi-Voice mit Phase-Offset

2. **PhaserFx** ✏️ — Scrawl = Allpass-Sweep-Envelope
   - Rate, Depth, Feedback, Mix + zeichenbarer Sweep-Verlauf
   - 6-stufiger kaskadierer Allpass-Filter

3. **FlangerFx** ✏️ — Scrawl = Delay-Modulations-Kurve
   - Rate, Depth, Feedback, Mix + zeichenbare Comb-Filter-Modulation

4. **DistortionPlusFx** ✏️ — Scrawl IST die Waveshaper-Transferfunktion
   - Drive, Tone, Mix + frei zeichenbare Verzerrungskurve
   - 1024-Sample LUT für schnelle Verarbeitung
   - X-Achse = Input-Signal, Y-Achse = Output — komplett benutzerdefiniert!

5. **TremoloFx** ✏️ — Scrawl = Amplituden-Modulations-Form
   - Rate, Depth, Stereo-Offset, Mix + zeichenbare Volume-Modulation

### KI Curve Generator (Innovation!)
- `ki_generate_curve(effect_type, seed, complexity)` — erzeugt musikalisch
  sinnvolle Kurven je nach Effekt-Typ
- Chorus: asymmetrische LFO-Formen mit Oberton-Wobble
- Phaser: Triangle mit harmonischem Folding
- Flanger: Slow Sweep mit Jet-Dips
- Distortion: S-Kurven mit Asymmetrie und Harmonics
- Tremolo: Rhythmische Patterns (Pulse/Wave/Stutter + Swing)

### UI Verbesserung: Ausklapp-Menüs statt gequetschte Buttons
- DevicePanel Header: 9 kleine Buttons → 2 übersichtliche Dropdown-Menüs
  - "👁 View" → Collapse/Expand/Focus/Reset
  - "🎯 Zone" → Note-FX / Instrument / Audio-FX Fokus
- Originale Buttons bleiben hidden (Keyboard-Shortcuts funktionieren weiter)
- Spart ~70% Header-Breite, keine gequetschte Darstellung mehr

### FX Specs
- Alle 5 Creative FX mit ✏️ Marker im Namen (zeigt Scrawl-Unterstützung)
- Proper defaults für alle Parameter

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/audio/creative_fx.py | NEU: 5 Creative FX DSP + KI Curve Generator |
| pydaw/audio/fx_chain.py | 5 neue Creative FX registriert |
| pydaw/ui/fx_specs.py | Creative FX defaults + ✏️ Labels |
| pydaw/ui/device_panel.py | Dropdown-Menüs statt gequetschte Buttons |
| pydaw/version.py, VERSION | 0.0.20.643 |

## Was als nächstes zu tun ist
- AP8 Phase 8C — Utility FX (Gate, De-Esser, Stereo Widener, Spectrum Analyzer)
- AP4 Phase 4A — Sandboxed Plugin-Hosting
- AP3 Phase 3C Tasks 3-4 (Tempo-Automation, Arranger-Warp)
