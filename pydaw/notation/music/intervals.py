# ChronoScale – Intervall-Analyse (Wolfsquinte)

def find_wolf_fifth(intervals_cent, threshold=15):
    """
    Findet Index der Wolfsquinte, falls vorhanden.
    Rückgabe: Index oder None
    """
    for i, cent in enumerate(intervals_cent):
        if abs(cent - 700) > threshold:
            # starke Abweichung von reiner Quinte
            return i
    return None
