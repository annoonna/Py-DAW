## v0.0.20.262 — FX Automation UI RT Sync

Safe UI-only fix: automatisierte Audio-FX-Werte bewegen jetzt die sichtbaren Regler/Slider auch dann zuverlässig, wenn die reine Qt-Signalroute im Device-Panel oder in eingebetteten Pro-Drum-Slot-FX-Widgets nicht greift.

- `pydaw/ui/fx_device_widgets.py`
  - `AudioChainContainerWidget`: leichter UI-Sync-Timer liest `RTParamStore` und spiegelt `wet_gain` / `mix` sichtbar in die Dials.
  - `LadspaAudioFxWidget`: leichter UI-Sync-Timer liest `RTParamStore` und spiegelt LADSPA-Parameter sichtbar in Slider + Spinbox.
  - bestehende `parameter_changed`-Signalpfade bleiben erhalten; der Timer ist nur ein sicherer Fallback für sichtbare UI-Synchronität.

Wichtig:
- keine Änderung an Audio-Rendering, Lane-Interpolation oder Plugin-Hosting
- nur sichtbare UI-Synchronisierung ergänzt
