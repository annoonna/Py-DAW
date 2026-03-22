# Session Log — v0.0.20.491 / Runtime-Capture-Objekt-Vorschau

**Datum:** 2026-03-16
**Entwickler:** OpenAI GPT-5.4 Thinking
**Dauer:** ~18 min
**Version:** 0.0.20.490 → 0.0.20.491

## Task

**Morphing-Guard um Runtime-Capture-Objekt-Vorschau erweitern** — weiterhin komplett read-only und ohne echte Projektmutation.

## Problem-Analyse

1. Seit v0.0.20.490 gab es bereits konkrete Runtime-Snapshot-Handles, aber noch keine greifbare Capture-Objekt-Schicht fuer die spaetere echte Snapshot-Erfassung.
2. Fuer den naechsten sicheren Vorbau fehlte damit noch die Ebene zwischen `handle_key` und einem spaeteren echten Snapshot-/Capture-Objekt.
3. Ziel war deshalb, dieselben Handles in konkrete, deterministische Capture-Objekt-Deskriptoren mit kleiner Payload-Vorschau zu ueberfuehren — weiterhin komplett nicht-mutierend.

## Fix

1. **Guard-Plan baut jetzt Runtime-Capture-Objekte auf**
   - `runtime_snapshot_captures` und `runtime_snapshot_capture_summary` binden Handle-Key, Scope und Capture-Stubs an konkrete Capture-Objekt-Vorschauen.

2. **Capture-Objekte tragen bereits Payload-Vorschau**
   - je nach Snapshot-Typ werden kleine read-only Payloads wie Track-State, Routing, Clip-IDs oder Chain-Device-Listen vorbereitet.

3. **Dialog zeigt die Capture-Ebene explizit an**
   - neuer Detailabschnitt **Runtime-Capture-Objekt-Vorschau** plus Capture-Zusammenfassung im Infotext.

## Betroffene Dateien

- `pydaw/services/smartdrop_morph_guard.py`
- `pydaw/ui/main_window.py`

## Validierung

- `python -m py_compile pydaw/services/smartdrop_morph_guard.py pydaw/ui/main_window.py`
- kleiner Guard-Sanity-Run per `build_audio_to_instrument_morph_plan(...)`

## Naechster sinnvoller Schritt

- **Dieselben Capture-Objekte spaeter an echte Snapshot-Instanzen haengen** — also Undo-/Routing-/Clip-/FX-Snapshots wirklich unter denselben `capture_key`-Objekten materialisieren, weiterhin noch ohne echten Morphing-Apply-Pfad.
