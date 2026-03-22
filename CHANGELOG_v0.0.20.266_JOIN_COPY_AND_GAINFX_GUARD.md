# v0.0.20.266

- Fix: Ctrl+J Join/Consolidate MIDI path had `copy.deepcopy(...)` calls without a guaranteed `import copy`, which could abort join and leave inconsistent state.
- Fix: `ProjectService` / `AltProjectService` now import `copy` at module level so deep-copy paths are always available.
- Fix: `GainFxWidget._on_automation_changed()` now safely disconnects if the Qt slider/spinbox has already been deleted, instead of spamming RuntimeError.
