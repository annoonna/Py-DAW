# Session Log — v0.0.20.666

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Kritischer Hotfix — GUI Freeze + Silent Playback
**Aufgabe:** Performance-Probleme und GUI-Einfrierungen nach Rust-Migration beheben

## Was wurde erledigt

### Kritischer Fix: 3 Ebenen

1. **Safety Gate in `should_use_rust()`** — gibt jetzt IMMER `False` zurück
   - Rust Engine ist PoC (Sine-Generator), kann keine Python-Instrumente rendern
   - Python-Engine bleibt einziger aktiver Audio-Pfad
   - Verhindert: Stille, ALSA Underruns, unbenutzbare Playback-Controls

2. **Error-Flood-Schutz in RustEngineBridge**
   - `_shutting_down` Flag stoppt Signal-Emission sofort bei Disconnect
   - RuntimeError("deleted C++ object") wird gefangen → Loop bricht ab
   - Verhindert: GUI-Freeze durch endlose Fehlermeldungen

3. **Graceful Disconnect**
   - `shutdown()` setzt `_shutting_down` VOR Socket-Close
   - Reader-Thread erkennt Flag und beendet sich sauber

### Vorherige Versionen in dieser Session
- v663: Bug-Fix scale_ai.py + Responsive Verdichtung
- v664: Rust 61 Warnings → 0
- v665: Engine Migration Dialog verdrahtet

## Geänderte Dateien
- pydaw/services/engine_migration.py (should_use_rust → False Safety Gate)
- pydaw/services/rust_engine_bridge.py (_shutting_down, RuntimeError Guard)
- VERSION (665 → 666)
- pydaw/version.py (665 → 666)

## Nächste Schritte
- DAW starten → Advanced Sampler testen → Sound muss kommen
- Playhead muss flüssig laufen
- Keine "antwortet nicht" Dialoge mehr

## Offene Fragen an den Auftraggeber
- Keine — bitte testen ob die Probleme behoben sind
