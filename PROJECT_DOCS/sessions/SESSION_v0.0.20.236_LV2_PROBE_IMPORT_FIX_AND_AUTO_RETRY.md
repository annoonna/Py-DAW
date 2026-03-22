# Session v0.0.20.236 — LV2 Probe Import Fix + Auto-Retry

Datum: 2026-03-05  
Autor: GPT-5.2 Thinking

## Ausgangslage
User Report:
- LV2 Plugins zeigen UI/Slider, aber haben **keine hörbare Wirkung**.
- LV2 Devices zeigen: `DSP: BLOCKED (Safe Mode) — python-lilv import failed: No module named 'lilv'`.
- Ursache: Subprocess-Probe läuft mit `sys.executable` (venv) und konnte `lilv` nicht importieren,
  obwohl der LV2 Host im Hauptprozess durch dist-packages injection verfügbar war.

## Änderungen (SAFE)
1) **lv2_probe** robust gemacht (venv kompatibel)
- `pydaw/tools/lv2_probe.py` nutzt jetzt `_ensure_lilv()`:
  - versucht `import lilv`
  - fallback: `site.addsitedir()` für dist-packages/site-packages (inkl. versioned globs)
  - gibt saubere Fehlertexte zurück

2) **Auto-Retry** wenn Cache nur Import-Fehler war
- `pydaw/audio/lv2_host.py`: bei cached `blocked` + reason enthält `python-lilv import failed`
  → einmalig neu proben (ohne dass der User Cache löschen muss).

3) **Scanner**: LV2 plugin_id muss URI sein
- `pydaw/services/plugin_scanner.py`: skippt IDs, die wie Dateipfade aussehen (kein Schema / beginnt mit `/`).

## Erwartetes Ergebnis
- Safe Mode blockt nur noch **wirklich crashende** Plugins.
- Viele LV2 Plugins sollten nun `DSP: ACTIVE` werden und hörbar wirken.
- Wenn ein Plugin in Subprocess crasht → bleibt BLOCKED, DAW bleibt stabil.

## Getestet
- Statischer Check: Module importiert, Syntax ok (py_compile empfohlen).

## Hinweise für den User
- Falls noch alte BLOCKED Einträge sichtbar sind: einfach Plugin erneut hinzufügen oder einmal `Rescan` im Browser.
- System-Bundle-Fehler wie `/usr/lib/lv2/*.lv2.bak` am besten aus `/usr/lib/lv2` heraus verschieben, um lilv-Scan-Noise zu vermeiden.

