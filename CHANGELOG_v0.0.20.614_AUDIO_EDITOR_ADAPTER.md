# CHANGELOG v0.0.20.614 — Clip Launcher Loop Fix + AudioEditor Adapter-Integration

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Typ:** Bugfix (kritisch) + Vervollständigung (Dual-Clock Audio-Clip-Playhead)

---

## CRITICAL FIX: Clip Launcher Clips loopen nicht

### Problem

Clips im Clip Launcher spielten einmal durch und stoppten, obwohl Loop
aktiviert war. Egal welche Loop-Einstellungen — der Clip lief einmal
und war fertig.

### Root Cause

`_check_follow_action()` in `ClipLauncherPlaybackService` hatte die
Default-Werte `next_action='Stopp'` + `next_action_count=1`. Das bedeutete:
nach 1 Loop-Durchlauf wurde die Follow-Action 'Stopp' ausgelöst und der
Clip gestoppt. Die alte Guard-Logik prüfte nur
`next_action == 'Stopp' and next_action_count <= 0` — aber der Default
count war 1, nicht 0.

### Fix

Neue Prüfung: Wenn **beide** Follow-Actions 'Stopp' sind (also keine
Follow-Action konfiguriert), wird sofort returnt → **Clip loopt endlos**.
Das entspricht dem Bitwig/Ableton-Verhalten: Clips loopen bis sie
explizit gestoppt werden oder eine Follow-Action konfiguriert ist.

```python
# VORHER (Bug):
if v.next_action == 'Stopp' and v.next_action_count <= 0:
    return  # nur bei count=0 → Default count=1 fiel durch!

# NACHHER (Fix):
if v.next_action == 'Stopp' and v.next_action_b == 'Stopp':
    return  # keine Follow-Action → loop forever
```

### Betroffene Datei

`pydaw/services/cliplauncher_playback.py` — 3 Zeilen geändert

---

## AudioEditor Adapter-Integration (Dual-Clock)

- **`_last_adapter_beat` Instanzvariable** — Speichert den letzten vom
  Adapter empfangenen Beat.
- **`_local_playhead_beats()`** — Nutzt jetzt `_last_adapter_beat`
  statt `transport.current_beat`. Fallback beibehalten.

### Betroffene Datei

`pydaw/ui/audio_editor/audio_event_editor.py` — +5 Zeilen
