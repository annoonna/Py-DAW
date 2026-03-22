# SESSION v0.0.20.239 — LV2: Auto-Select Wet Outputs (2026-03-05)

## Ziel
User hört bei vielen LV2 Reverb/Delay Effekten **keine** Änderung, obwohl UI `DSP: ACTIVE` anzeigt.

## Diagnose
- Einige LV2 Plugins exportieren **mehr als 2 Audio-Out Ports** (z.B. Dry-Tap/Monitor/Aux).
- Selbst mit heuristischem Ordering kann die "erste" Stereo-Paarung weiterhin ein Dry-Tap sein.
- Ergebnis: Host kopiert zwar Audio zurück, aber eben den dry output → wirkt wie "kein Effekt".

## Fix (SAFE)
- `pydaw/audio/lv2_host.py`
  - LV2 verbindet weiterhin **alle Audio-Out Ports** (keine Wiring-Änderung).
  - Neu: `_auto_select_main_outputs()`
    - Init-only: winziger, sehr leiser Impuls-Test (2048 Frames max, Amplitude 1e-3).
    - Bewertet Output-Buffers nach "Wetness" (RMS(out-ref) + kleiner RMS(out) Anteil).
    - Wählt bestes L/R Paar (falls tags) bzw. top2 als Rückgabe.
  - `process_inplace()` kopiert nun die **gewählten** Output-Buffers zurück statt starr Out0/Out1.

## Version / Dateien
- Version bump: `0.0.20.238` → `0.0.20.239`
- Dateien:
  - `pydaw/audio/lv2_host.py`
  - `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
  - `PROJECT_DOCS/progress/TODO.md`, `DONE.md`, `LATEST.md`

## Hinweise
- Der Testimpuls wird nach der Auswahl aus Buffers gelöscht (best-effort) und ist sehr leise.
- Crash-Schutz (Safe Mode Probe + Offline Render Subprocess) bleibt unverändert.
