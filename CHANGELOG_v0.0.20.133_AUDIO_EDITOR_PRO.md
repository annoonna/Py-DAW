# CHANGELOG v0.0.20.133 — Audio Editor Pro Upgrade

## Neue Features
- Fade In/Out mit ziehbaren Handles (Bitwig-Style)
- Echte Peak-basierte Normalisierung (nicht nur gain=1.0)
- Auto Onset-Erkennung (energiebasiert, adaptive Schwelle)
- Slice at Onsets (Events an Transienten aufteilen)
- Reverse Waveform-Darstellung (gespiegelt + orange Tint)
- Mute Overlay (dunkel + "MUTED" Label)
- Zero-Crossing Snap für Click-freie Schnitte
- Erweiterte Gain-Optionen (+6/-6 dB, Reset)
- Oktav-Transpose (+12/-12 Halbtöne)

## Modell
- Clip: +fade_in_beats, +fade_out_beats

## Service
- normalize_audio_clip(), detect_onsets(), add_onset_at(), clear_onsets()
- find_zero_crossings(), slice_at_onsets()

## Kompatibilität
- 100% rückwärtskompatibel (neue Felder defaulten auf 0.0)
- Keine bestehende Funktionalität verändert
