# Session Log — v0.0.20.512 / read-only Before-/After-Snapshot-Command-Factory / materialisierte Payloads

**Datum:** 2026-03-16
**Entwickler:** OpenAI GPT-5.4 Thinking
**Dauer:** ~55 min
**Version:** 0.0.20.511 -> 0.0.20.512

## Task

**Die read-only ProjectSnapshotEditCommand-/Undo-Huelle spaeter an eine explizite Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payloads koppeln** — weiterhin ohne Projektmutation und ohne echtes Audio->Instrument-Morphing.

## Problem-Analyse

1. Seit v0.0.20.511 war der spaetere Minimalfall der leeren Audio-Spur bereits read-only bis an eine explizite `ProjectSnapshotEditCommand`-/Undo-Huelle gekoppelt.
2. Es fehlte aber noch die **explizite Before-/After-Snapshot-Factory**, die spaeter einmal konkrete Snapshot-Payloads in dieselbe Command-Huelle einspeisen wird.
3. Der naechste sichere Schritt durfte weiterhin **keine** Projektmutation und **keinen** Undo-Push freischalten, sondern nur diese Factory read-only mit materialisierten Payload-Metadaten vorverdrahten.

## Fix

1. **Neuer read-only Before-/After-Snapshot-Factory-Report**
   - `pydaw/services/smartdrop_morph_guard.py` fuehrt `RuntimeSnapshotCommandFactoryPayloadReport`, `_build_runtime_snapshot_command_factory_payloads(...)` und `_build_runtime_snapshot_command_factory_payload_summary(...)` ein.
   - Hinter der bestehenden Command-/Undo-Huelle werden jetzt Factory-Preview, Before-/After-Payload-Materialisierung, Restore-Callback und Payload-Paritaet read-only sichtbar vorverdrahtet.
   - Mutation bleibt weiterhin explizit deaktiviert.

2. **ProjectService exponiert expliziten read-only Owner-Pfad fuer die Before-/After-Snapshot-Factory**
   - `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_before_after_snapshot_command_factory` ein.
   - Die Methode materialisiert Before-/After-Snapshot-Payloads nur in-memory und liefert daraus Digests, Byte-Groessen, Top-Level-Keys und Zaehler als Metadaten zurueck.

3. **Guard-Dialog, Statuslabel und Apply-Readiness fuehren die neue Schicht sichtbar mit**
   - `pydaw/ui/main_window.py` parst `runtime_snapshot_command_factory_payloads` / `_summary`.
   - Der Detaildialog fuehrt jetzt den Block **Read-only Before-/After-Snapshot-Command-Factory** mit Payload-Metadaten, Delta-Kind und Factory-Schritten.
   - `preview_label`, `status_label` und die Apply-Readiness haben jetzt einen eigenen Zustand fuer die read-only Payload-Factory-Kopplung.

## Validierung

- `python3 -m py_compile pydaw/services/smartdrop_morph_guard.py pydaw/services/project_service.py pydaw/ui/main_window.py`
- `python3 -m compileall -q pydaw`
- kleiner Mock-Sanity-Run ueber `build_audio_to_instrument_morph_plan(...)`
  - **leere Audio-Spur + Runtime-Owner** -> `runtime_snapshot_command_factory_payload_summary` vorhanden, `payload_state=ready`, `materialized_payload_count=2`, `payload_delta_kind=identical-preview-only`, `status_label` endet auf `Payload-Factory vorbereitet`
  - **Audio-Spur mit FX** -> `payload_state=blocked`, Guard bleibt read-only gesperrt
- ZIP-Integritaet wird vor Auslieferung zusaetzlich geprueft (`testzip OK`)

## Ergebnis

Der SmartDrop-Morphing-Guard besitzt jetzt hinter Mutation-Gate, Transaction-Capsule und `ProjectSnapshotEditCommand`-/Undo-Huelle erstmals eine **explizite read-only Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payload-Metadaten**. Der spaetere Minimalfall der leeren Audio-Spur ist damit bis an konkrete Before-/After-Payload-Beschreibungen read-only vorbereitet — weiterhin komplett ohne echte Mutation.

## Naechster sicherer Schritt

Die read-only Before-/After-Snapshot-Command-Factory spaeter an eine **explizite Preview-Command-Konstruktion (`ProjectSnapshotEditCommand(before=..., after=..., ...)`)** koppeln — weiterhin noch ohne Undo-Push, ohne echten Commit und ohne Projektmutation.

