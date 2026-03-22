# SESSION v0.0.20.237 — LV2: Audible Defaults + Audition Button (2026-03-05)

## Kontext
User sieht LV2-Parameter-UI und `DSP: ACTIVE`, hört aber viele Effekte kaum.
Ursache ist häufig:
- LV2-Plugins starten mit **BYPASS** aktiv oder sehr **dry** Defaults.
- Einige Plugins crashen im Probe (Safe Mode blockt korrekt).

Ziel: **ohne Core-Risiko** die Bedienung verbessern, sodass aktive LV2-FX sofort hörbar werden.

## Änderungen (SAFE)

### 1) LV2 UI: "Audition" Button
- In `Lv2AudioFxWidget` wurde ein **Audition** Button ergänzt.
- Klick setzt best-effort heuristisch typische Parameter:
  - BYPASS → Minimum (meist "nicht bypass")
  - wet/mix → Maximum
  - dry → Minimum
  - wet_dry/dry_wet → Minimum (Annahme 0=wet)
  - feedback/depth/drive → deutlich höhere Werte

Datei:
- `pydaw/ui/fx_device_widgets.py`

### 2) LV2 Insert: Audible Defaults (nur beim Einfügen)
- Beim Einfügen eines `ext.lv2:<URI>` Audio-FX wird **nur** für sehr offensichtliche Controls nachgebessert:
  - `bypass*` → Minimum
  - `wet_dry*` / `dry_wet*` → Minimum
- Wir ändern **keine** anderen Parameter automatisch.

Datei:
- `pydaw/ui/device_panel.py`

## Nicht geändert
- Audio-Engine / FX-Chain DSP bleibt unverändert.
- Safe Mode Blocker bleibt aktiv (crashende Plugins bleiben blockiert).

## Ergebnis
- Viele LV2-FX sind nach Insert **hörbarer**.
- Wenn Defaults trotzdem subtil sind, kann der User mit **Audition** sofort eine klare Wirkung erzwingen.

