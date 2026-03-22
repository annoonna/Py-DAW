# v0.0.20.365 — VST3 Startup Scan Hang Hotfix

## Problem
After v0.0.20.364 the DAW could stop opening on Linux during startup. The plugin browser now tried to detect multi-plugin VST3 bundles by calling `pedalboard.load_plugin()` on every discovered VST3. Some plugins (observed with `ZamVerb.vst3`) do not tolerate that eager scan path and can hang inside the plugin binary while the UI is still booting.

## Fix
- automatic VST3 scans are shallow again
- eager multi-plugin probing is now restricted to known safe bundle collections (`lsp-plugins.vst3`)
- optional debug override via `PYDAW_VST_MULTI_PROBE=1`

## Result
- program opens again
- LSP multi-plugin bundle support remains available in the browser
- no risky core/audio-engine refactor
