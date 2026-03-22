# CHANGELOG v0.0.20.370 — VST3 Widget Runtime-Param-Reuse Hotfix

- `Vst3AudioFxWidget` nutzt zuerst die bereits laufende `Vst3Fx`-Instanz aus dem Audio-Engine-FX-Map für Parameter-Metadaten.
- Frisch eingefügte externe VSTs müssen für ihr Parameter-Widget dadurch nicht sofort erneut im Worker geladen werden.
- Kurzer Poll-/Wartepfad vor dem Async-Fallback ergänzt; der responsive Insert bleibt erhalten.
- `Vst3Fx._load()` vermeidet jetzt den unnötigen Zweit-Load für die reine Parameterauslese.
