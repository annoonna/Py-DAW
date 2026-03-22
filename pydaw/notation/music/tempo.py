# ChronoScale – Tempo-Hilfsfunktionen

def bpm_to_duration(bpm: int) -> float:
    """
    Viertelnote-Dauer in Sekunden
    """
    return 60.0 / max(20, bpm)
