## v0.0.20.191 — Fix: SIGSEGV (QTimer/Slot) + Signal.disconnect + AI Composer Note‑FX

### Fixes
- **Stability:** verhindert SIGSEGV durch QTimer/singleShot Callbacks auf SIP-deleted Widgets.
- **Qt-Hardening:** `signal.disconnect(fn)` funktioniert wieder korrekt trotz Slot-Wrapping.

### Features
- **AI Composer (Note‑FX):** algorithmische MIDI-Generierung (seeded) + JSON Snapshots.
