# Changelog v0.0.20.366 — VST3 Device Exact-Reference Hotfix

- Externe **VST3/VST2-Devices** speichern jetzt immer eine kanonische Komplett-Referenz (`__ext_ref`) zusätzlich zu Basis-Pfad und optionalem Sub-Plugin-Namen.
- **Plugins-Browser** gibt diese exakte Referenz bei Add und Drag&Drop direkt mit.
- **DevicePanel** normalisiert VST-Metadaten beim Insert, damit auch ältere oder gemischte Payloads stabil auf dasselbe Sub-Plugin zeigen.
- **FX-Widget** und **Live-Host-Build** bevorzugen jetzt die exakte Referenz statt nur des Bundle-/Dateipfads.
- Ziel des Hotfixes: Multi-Plugin-Bundles wie `lsp-plugins.vst3` sollen beim Insert/Rebuild nicht mehr still das gewählte Sub-Plugin verlieren.
- Keine Änderung am Transport, Mixer, Routing oder DSP-Grundverhalten.
