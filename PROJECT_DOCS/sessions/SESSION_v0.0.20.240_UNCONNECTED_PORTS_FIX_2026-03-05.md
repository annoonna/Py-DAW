# SESSION v0.0.20.240 — LV2 Unconnected Ports Fix

**Datum:** 2026-03-05  
**Bearbeiter:** Claude Opus (Anthropic)  
**Priorität:** 🔴 CRITICAL  

## Ausgangslage
User Report: LV2 FX (Reverb/Delay/Wah etc.) zeigen **DSP: ACTIVE** und Parameter bewegen sich, aber der Sound bleibt praktisch **trocken** (kein hörbarer Effekt). Distortion war teilweise hörbar. Zusätzlich: SWH-Bundles führten zu „attempt to map invalid URI …“.

## Root Cause
**LV2 Spezifikation:** Alle **non-optional Ports müssen verbunden** sein.
Unser Host verband Audio-Ports + Control-Input-Ports, aber **Control-Output-Ports** (Meter/Latency/Level) blieben **unverbunden**.
Viele Plugins schreiben in `run()` auf diese Output-Control-Ports → ohne Buffer ergibt das **undefiniertes Verhalten** (u.a. „kein Audio output“).

## Implementierung (SAFE)
### 1) Alle verbleibenden Ports verbinden
Nach dem normalen Connect von:
- Audio In/Out
- Control Input

werden jetzt **alle restlichen Ports** best-effort an Dummy-Buffer angeschlossen:
- Control-Ports → `np.zeros((1,), float32)`
- zusätzliche Audio-Ports → `np.zeros((max_frames,), float32)`
- unbekannte Typen → best-effort `np.zeros((1,), float32)` (Fehlschläge werden abgefangen)

Die Dummy-Buffer werden in `self._dummy_bufs` gehalten (kein GC).

### 2) Diagnose
`stderr` Logging:
- ports total
- connected count
- dummy buffer count

Damit sieht man sofort, ob ein Plugin viele Output-Control-Ports hat.

## Geänderte Dateien
- `pydaw/audio/lv2_host.py`
- `CHANGELOG_v0.0.20.240_LV2_UNCONNECTED_PORTS.md`

## Testplan
1) LV2 Reverb/Delay auf eine Orgel/Pad-Spur legen → Effekt muss hörbar werden.
2) Terminal: `[LV2] ... dummy=N` sollte bei diesen Plugins >0 sein.
3) Keine Crashes: Safe-Mode Probe bleibt aktiv.

