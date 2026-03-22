# Session v0.0.20.240 — LV2 Unconnected Ports Fix (2026-03-05)

## Ziel
LV2 Audio-FX zeigen "DSP: ACTIVE" mit richtigen Parameterwerten, aber **kein hörbarer Effekt** (Reverb, Delay, Wah etc. — Distortion funktioniert).

## Root-Cause Analyse (3 Probleme gefunden)

### Problem 1: Output-Control-Ports NICHT verbunden (CRITICAL)
**Hauptursache.** Die LV2-Spezifikation verlangt: *alle nicht-optionalen Ports MÜSSEN an gültige Buffer verbunden sein.* Unser Host verband:
- ✅ Audio Input Ports
- ✅ Audio Output Ports
- ✅ Control INPUT Ports (die man in der UI sieht)
- ❌ Control OUTPUT Ports (Latenz, Meter, Level-Outs)
- ❌ CV Ports, Atom Ports

Wenn `run()` aufgerufen wird, schreibt das Plugin in NULL-Pointer für Output-Control-Ports. Viele Plugins (Guitarix Reverb, SWH Effects) haben solche Ports. Das Ergebnis ist *undefiniertes Verhalten* — typischerweise produziert das Plugin keinen Output oder kopiert das Dry-Signal durch.

**Fix:** Nach Audio + Control-Input Verbindungen werden ALLE restlichen Ports an Dummy-Buffer angeschlossen. Diese werden in `self._dummy_bufs` gehalten (kein GC).

### Problem 2: `get_port_ranges_float()` falsch aufgerufen
Die lilv Python API gibt `(mins_array, maxs_array, defaults_array)` zurück — drei Arrays mit einem Eintrag pro Port. Der alte Code versuchte `plugin.get_port_ranges_float(port)` mit einem Port-Argument, was fehlschlug → Exception → Defaults 0.0/1.0/0.0.

Wenn ein Reverb-Plugin z.B. `Dry/Wet` Default = 0.5 hat, wurde stattdessen 0.0 (komplett trocken) gesetzt.

**Fix:** Korrekte Array-basierte API: `_mins, _maxs, _defs = plugin.get_port_ranges_float()` und dann per Index `i` zugreifen.

### Problem 3: SWH Plugins verwenden Bundle-Pfade statt URIs
Der Plugin-Scanner nutzt Regex um LV2 URIs aus manifest.ttl zu parsen. SWH-Plugins (Steve Harris) können TTL-Formate haben, die unsere Regexes nicht matchen → Scanner speichert den Dateisystem-Pfad (z.B. `/usr/lib/lv2/freq_tracker-swh.lv2`) als `plugin_id` statt der richtigen URI.

Beim Laden: `lilv` kann mit Bundle-Pfaden nicht umgehen → "attempt to map invalid URI" → BLOCKED.

**Fix:**
- 3 zusätzliche Regex-Patterns für verschiedene LV2 TTL-Formate (Full-URI, andere Prefixes)
- `lv2ls` + `lv2info` Fallback für Bundles die kein Regex matcht
- Bundle-Pfad als absolute letzte Fallback-Option (nicht mehr primär)

## Geänderte Dateien
- `pydaw/audio/lv2_host.py` — Port-Verbindung, get_port_ranges_float, Diagnostik
- `pydaw/services/plugin_scanner.py` — Erweiterte TTL-Regexes, lv2info Fallback
- `VERSION` → 0.0.20.240

## Test-Anleitung
1. PyDAW starten, LV2 Reverb laden (z.B. `_reverb_stereo` von Guitarix)
2. Konsole prüfen: `[LV2] ... ports=N connected=N (ain=2 aout=2 ctl_in=5 dummy=M)`
3. Alle Ports sollten connected sein (kein WARNING)
4. Audio abspielen → Reverb-Effekt muss hörbar sein
5. SWH-Plugins: Rescan → sollten jetzt korrekte URIs haben
6. Audition-Button testen → heuristische Parameter setzen

## Nächste Schritte
- [ ] LV2 State Save/Restore (Preset-System)
- [ ] MIDI-Atom-Ports für LV2 Instrument-Plugins
- [ ] LV2 Worker Thread für plugins mit schedule-feature
