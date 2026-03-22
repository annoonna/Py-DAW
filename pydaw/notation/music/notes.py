# ChronoScale – Notennamen & Hilfsfunktionen

NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]

def midi_to_name(midi_note: int) -> str:
    name = NOTE_NAMES[midi_note % 12]
    octave = (midi_note // 12) - 1
    return f"{name}{octave}"
