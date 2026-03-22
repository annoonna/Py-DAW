## Neu in v0.0.20.514
- SmartDrop-Morphing-Guard koppelt die read-only Preview-Command-Konstruktion jetzt an einen expliziten **Dry-Command-Executor / do()-undo()-Simulations-Harness**.
- `ProjectService` exponiert dafuer `preview_audio_to_instrument_morph_dry_command_executor`; `ProjectSnapshotEditCommand.do()/undo()` laufen nur gegen einen lokalen Recorder-Callback und beruehren weder Live-Projekt noch Undo-Stack.
- Guard-Dialog zeigt einen neuen Block **Read-only Dry-Command-Executor / do()-undo()-Simulations-Harness** mit do/undo-Zaehlern, Callback-Trace, Callback-Digests und einzelnen Simulations-Schritten.
- Weiterhin bewusst sicher: kein echter Commit, kein Undo-Push, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.513
- SmartDrop-Morphing-Guard koppelt die read-only Before-/After-Snapshot-Command-Factory jetzt an eine explizite **Preview-Command-Konstruktion** mit der echten Constructor-Form `ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)`.
- `ProjectService` exponiert dafuer `preview_audio_to_instrument_morph_preview_snapshot_command`; der spaetere Command wird nur in-memory konstruiert und nicht ausgefuehrt.
- Guard-Dialog zeigt einen neuen Block **Read-only Preview-Command-Konstruktion** mit Constructor, Callback, Feldliste, Payload-Zusammenfassung und einzelnen Preview-Schritten.
- Weiterhin bewusst sicher: kein Commit, kein Undo-Push, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.512
- SmartDrop-Morphing-Guard koppelt die read-only `ProjectSnapshotEditCommand`-/Undo-Huelle jetzt an eine explizite **Before-/After-Snapshot-Command-Factory** mit materialisierten Snapshot-Payload-Metadaten.
- `ProjectService` exponiert dafuer `preview_audio_to_instrument_morph_before_after_snapshot_command_factory`; Before-/After-Snapshots werden nur in-memory materialisiert und als Digests/Byte-Groessen/Top-Level-Keys beschrieben.
- Guard-Dialog zeigt einen neuen Block **Read-only Before-/After-Snapshot-Command-Factory** mit Payload-Zusammenfassung, Delta-Kind und einzelnen Factory-Schritten.
- Weiterhin bewusst sicher: kein Commit, kein Undo-Push, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.511
- SmartDrop-Morphing-Guard koppelt Mutation-Gate und Transaction-Capsule jetzt read-only an eine explizite **ProjectSnapshotEditCommand / Undo-Huelle**.
- `ProjectService` exponiert dafuer sichere read-only Owner-Deskriptoren fuer `ProjectSnapshotEditCommand` und die spaetere Command-/Undo-Huelle.
- Guard-Dialog zeigt einen neuen Block **Read-only ProjectSnapshotEditCommand / Undo-Huelle** mit Huelle-Sequenz und Einzelstatus.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.510
- SmartDrop-Morphing-Guard koppelt die read-only atomaren Entry-Points der leeren Audio-Spur jetzt an ein explizites **Mutation-Gate / Transaction-Capsule**.
- `ProjectService` exponiert dafuer sichere read-only Owner-Deskriptoren fuer Mutation-Gate, Capsule-Entry, Capsule-Commit und Capsule-Rollback; bestehende Snapshot-Helfer werden nur sichtbar angebunden.
- Guard-Dialog zeigt einen neuen Block **Read-only Mutation-Gate / Transaction-Capsule** mit Kapsel-Sequenz und Einzelstatus.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.509
- SmartDrop-Morphing-Guard koppelt den read-only **Pre-Commit-Vertrag** der leeren Audio-Spur jetzt an reale, aber weiterhin gesperrte **Commit-/Undo-/Routing-Entry-Points**.
- Bei Preview/Validate ueber `ProjectService` werden jetzt echte Owner-/Service-Methoden (`preview_audio_to_instrument_morph`, `validate_audio_to_instrument_morph`, `apply_audio_to_instrument_morph`, `set_track_kind`, `undo_stack.push`) im Guard-Plan aufgeloest.
- Guard-Dialog zeigt einen neuen Block **Read-only atomare Commit-/Undo-/Routing-Entry-Points** inklusive Dispatch-Sequenz und Einzelstatus.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.508
- SmartDrop-Morphing-Guard fuehrt fuer die **leere Audio-Spur** jetzt einen eigenen read-only **Pre-Commit-Vertrag** hinter Minimalfall, Apply-Runner und Dry-Run.
- Der neue Vertrag beschreibt Undo-, Routing-, Track-Kind- und Instrument-Commit-/Rollback-Sequenzen sichtbar, bleibt aber vollstaendig preview-only.
- Apply-Readiness und Guard-Dialog zeigen diese neue Pre-Commit-Ebene jetzt explizit an.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.507
- SmartDrop-Morphing-Guard erkennt die **leere Audio-Spur** jetzt explizit als spaeteren ersten echten Minimalfall und qualifiziert sie read-only vor.
- Preview-/Status-Texte und Apply-Preview unterscheiden jetzt sauber zwischen **Minimalfall vorbereitet** und weiter blockierten Audio-Spuren mit Clips/FX.
- Guard-Dialog zeigt einen eigenen Block fuer den spaeteren ersten Minimalfall (leere Audio-Spur).
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.506
- SmartDrop-Morphing-Guard fuehrt jetzt einen eigenen read-only **Snapshot-Transaktions-Dispatch / Apply-Runner** hinter Snapshot-Bundle und Adapter-Ebene.
- Der neue Runner dispatcht Adapter-, Backend-Store-Adapter- und Registry-Slot-Backend-Pfade sichtbar read-only, weiterhin ohne Commit.
- Guard-Dialog und Apply-Readiness zeigen diese neue Apply-Runner-Schicht jetzt explizit an.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation und noch kein echtes Audio->Instrument-Morphing.

## Neu in v0.0.20.505
- SmartDrop-Morphing-Guard fuehrt jetzt eine neue read-only Ebene **Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends**.
- Dry-Run dispatcht jetzt auch `capture_adapter_preview()` / `restore_adapter_preview()` / `rollback_adapter_preview()` ueber diese Adapter-Ebene.
- Guard-Dialog zeigt die neue Adapter-/Backend-Store-/Registry-Slot-Backend-Struktur sichtbar an.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation.

## Neu in v0.0.20.373
- Kleiner VST3-Widget-Hotfix: `QCheckBox`-Import ergänzt.
- Async-Fallback bleibt bestehen, macht bei `must be reloaded on the main thread` jetzt automatisch einen sicheren Main-Thread-Retry.
- Fokus blieb bewusst klein und UI-seitig.

## Update v0.0.20.370 — VST3 Widget Runtime-Param-Reuse Hotfix

- Externe **VST3/VST2-Widgets** lesen ihre Parameter jetzt bevorzugt direkt aus der **bereits laufenden DSP-Instanz**.
- Dadurch müssen Plugins wie **Autogain Mono** oder **GOTT Compressor LeftRight** im Device-Fall nicht sofort noch einmal in einem Worker-Thread geladen werden.
- Der **Async-Fallback** aus v0.0.20.368 bleibt erhalten, startet aber erst nach einem kurzen sicheren Warten auf den FX-Rebuild.

## Update v0.0.20.369 — VST3 Mono/Stereo Bus-Adapt Hotfix

- Externe **VST3/VST2 Audio-FX** passen den Main-Bus jetzt sicher zwischen internem Stereo-Host und tatsächlichem Plugin-Bus an.
- **Mono-Plugins** wie **Autogain Mono** oder **Filter Mono** laufen damit jetzt ohne wiederholten `2-channel output`-Fehler im Playback.
- Umsetzung blieb bewusst nur im **VST-Bridge-Pfad**; Mixer, Routing und DSP-Grundarchitektur wurden nicht angefasst.

## Update v0.0.20.359 — Sichtbarer DAWproject Export

- Datei-Menü zeigt jetzt **DAWproject exportieren… (.dawproject)** direkt neben dem Import.
- Export läuft weiter **snapshot-sicher im Hintergrund** und berührt die Live-Session nicht.
- Fortschritt + Summary sind bereits verdrahtet; nächster sicherer Schritt wäre nur noch QA/Optionen.

## Update v0.0.20.353 — TrackList Drop-Markierung

- Arranger-TrackList zeigt beim lokalen Maus-Reorder jetzt eine **sichtbare Drop-Markierung**.
- Nur UI-Feedback; kein Eingriff in Routing/Mixer/DSP.
- Cross-Project-Track-Drag bleibt unverändert.

# 💌 AN JEDEN KOLLEGEN - WICHTIG!

## 🎯 Was du bekommen hast:

**Eine ZIP-Datei:** `Py_DAW_v0_0_20_197_TEAM_READY.zip`

Diese enthält:
- ✅ Vollständiges DAW-Projekt
- ✅ Komplette Dokumentation
- ✅ Arbeitsplan mit TODO-Liste
- ✅ Session-Logs (was bisher gemacht wurde)
- ✅ Anleitung für dich

---

## ⚡ DEINE AUFGABE (5 Schritte):

### 1. ZIP entpacken
```bash
unzip Py_DAW_v0_0_20_196_TEAM_READY.zip
cd Py_DAW_v0_0_20_196_TEAM_READY
```

### 2. LIES DAS:
```bash
cat README_TEAM.md
# ← Hier steht ALLES was du wissen musst!
```

### 3. Analysiere Projekt
```bash
# Was wurde gemacht?
cat PROJECT_DOCS/progress/DONE.md

# Was ist zu tun?
cat PROJECT_DOCS/progress/TODO.md

# Letzter Stand?
ls -t PROJECT_DOCS/sessions/ | head -1
cat PROJECT_DOCS/sessions/2026-*_SESSION_*.md
```

### 4. Task nehmen
- Öffne `PROJECT_DOCS/progress/TODO.md`
- Suche Task mit `[ ] AVAILABLE`
- Markiere: `[x] (Dein Name, Datum)`

### 5. Arbeiten!
- Erstelle Session-Log
- Code schreiben
- Dokumentieren
- TODO/DONE updaten
- Version erhöhen
- Neue ZIP erstellen
- An nächsten Kollegen

---

## 📋 WICHTIGSTE REGELN:

1. ✅ **IMMER** in TODO.md Task markieren
2. ✅ **IMMER** Session-Log schreiben
3. ✅ **IMMER** TODO/DONE updaten
4. ✅ **IMMER** VERSION erhöhen
5. ✅ **IMMER** neue ZIP für nächsten

---

## 🎯 ZIEL:

Wir bauen eine **DAW** wie:
- Professioneller Notations-Editor (Linux)
- Pro-DAW

**Gemeinsam, Schritt für Schritt!**

Jeder macht einen Task, dokumentiert, übergibt.

---

## 🆕 Neu in v0.0.20.198 (Kurz)

- Expression-Lane Edit Tools: **Draw / Select / Erase** (Header Buttons)
- Select: Punkt auswählen + Drag verschieben; **Del/Backspace** löscht Punkt
- Erase: Drag löscht Punkte nahe Cursor
- RMB Delete + DoubleClick Add/Delete

## 🆕 Neu in v0.0.20.197 (Kurz)

- **Note Expressions UI (opt‑in):** Expr Toggle + Param Combo im Piano‑Roll Header.
- **Triangle Interaction Model:** Hover‑Triangle, Klick‑Menu, **Alt+Drag Morph**, Doppelklick Focus (ESC exit).
- **Expression Lane (unter Piano‑Roll):** Anzeige + Draw‑Editing + Undo Snapshot.
- **Smooth Micropitch Rendering:** cubic Bezier (Bitwig‑ähnlich).

Details: `PROJECT_DOCS/plans/NOTE_EXPRESSIONS.md` und `PROJECT_DOCS/sessions/LATEST.md`.

---

## 💬 WENN DU NICHT WEITERKOMMST:

1. Siehe `README_TEAM.md` - Vollständige Anleitung
2. Siehe `PROJECT_DOCS/plans/MASTER_PLAN.md` - Übersicht
3. Siehe letzte Session-Logs - Was andere gemacht haben
4. Dokumentiere Problem in Session-Log
5. Markiere in TODO.md als "BLOCKED"
6. Übergib an nächsten Kollegen

---

**Viel Erfolg!** 🚀

**Du bist Teil eines Teams das eine echte DAW baut!**

- Neu in v0.0.19.5.1.6: Notation-Palette + Editor-Notes (Sticky Notes) (MVP).

- ✅ Notation: Tie/Slur Tool (⌒/∿) als Marker-MVP (2 Klicks) + Rendering + Save


## 🎛️ Neu in v0.0.19.7.39
- JACK-Playback nutzt jetzt eine neue `pydaw/audio/dsp_engine.py` (Mixing + Master Gain/Pan).
- Master-Volume/Pan wirkt jetzt auch im JACK/qpwgraph Pfad (wie im sounddevice-Fallback).
- UI: Drag & Drop Audio aus Browser → semitransparentes Clip-Launcher-Overlay über dem Arranger (Drop erzeugt AudioClip + Slot-Zuweisung).
