
import random
from pydaw.notation.scales.database import SCALE_DB

def random_scale():
    """Return a random (system, name) tuple from the scale database."""
    all_scales = SCALE_DB.all_scales()
    if not all_scales:
        return ("western", "major")
    return random.choice(all_scales)
