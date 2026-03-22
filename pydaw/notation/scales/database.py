# ChronoScale – Zentrale Skalen-Datenbank
# lädt Skalen aus JSON
# Grundlage für Anzeige, Playback, KI

import json
from pathlib import Path

SCALE_FILE = Path(__file__).parent / "scales.json"

class ScaleDatabase:
    def __init__(self):
        self.scales = {}
        self.load()

    def load(self):
        with open(SCALE_FILE, "r", encoding="utf-8") as f:
            self.scales = json.load(f)

    def list_systems(self):
        return list(self.scales.keys())

    def list_scales(self, system):
        return list(self.scales.get(system, {}).keys())

    def get_scale(self, system, name):
        return self.scales.get(system, {}).get(name)

    def all_scales(self):
        result = []
        for system, scales in self.scales.items():
            for name in scales:
                result.append((system, name))
        return result


# Singleton
SCALE_DB = ScaleDatabase()

# Backward-compat alias (used by notation.ai.scale_ai and others)
SCALES = SCALE_DB.scales
