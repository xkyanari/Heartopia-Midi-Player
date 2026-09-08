import ctypes
from keyboard_layout import create_scan_code_note_map
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

# Instrument definitions: (start_octave, (C, D, E, F, G, A, B), end_octave)
INSTRUMENTS = {
    "lute": {"start_octave": 3, "end_octave": 5, "keys": ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"]},
    "wooden bass": {"start_octave": 2, "end_octave": 4, "keys": ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"]},
    "piano": {"start_octave": 3, "end_octave": 6, "keys": None},  # Uses NOTE_TO_KEY_22 layout
    "recorder": {"start_octave": 5, "end_octave": 7, "keys": ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"]},
    "violin": {"start_octave": 4, "end_octave": 6, "keys": ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"]},
    "cello": {"start_octave": 2, "end_octave": 4, "keys": ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"]},
}

NATURAL_NOTES = ["C", "D", "E", "F", "G", "A", "B"]

def note_to_midi_value(name, octave):
    """Convert note name and octave to MIDI note value."""
    midi_value = (octave + 1) * 12 + NATURAL_NOTES.index(name)
    return midi_value

def create_note_map_15(start_octave, keys):
    """Create a 15-key note mapping for white notes only."""
    note_map = {}
    key_idx = 0
    for octave in range(start_octave, start_octave + 3):  # 3 octaves = 21 notes, take first 15
        for note in NATURAL_NOTES:
            if key_idx < len(keys):
                note_map[(note, octave)] = keys[key_idx]
                key_idx += 1
    return note_map

NOTE_TO_KEY_15 = create_note_map_15(4, ["a", "s", "d", "f", "g", "h", "j", "q", "w", "e", "r", "t", "y", "u", "i"])

NOTE_TO_KEY_22 = {
 # --- LOW OCTAVE (Octave 3) ---
    ("C", 3): ",",  ("C#", 3): "l",
    ("D", 3): ".",  ("D#", 3): ";",
    ("E", 3): "/",  
    ("F", 3): "o",  ("F#", 3): "0",
    ("G", 3): "p",  ("G#", 3): "-",
    ("A", 3): "[",  ("A#", 3): "=",
    ("B", 3): "]",

    # --- MIDDLE OCTAVE (Octave 4) ---
    ("C", 4): "z",  ("C#", 4): "s",
    ("D", 4): "x",  ("D#", 4): "d",
    ("E", 4): "c",
    ("F", 4): "v",  ("F#", 4): "g",
    ("G", 4): "b",  ("G#", 4): "h",
    ("A", 4): "n",  ("A#", 4): "j",
    ("B", 4): "m",

    # --- HIGH OCTAVE (Octave 5) ---
    ("C", 5): "q",  ("C#", 5): "2",
    ("D", 5): "w",  ("D#", 5): "3",
    ("E", 5): "e",
    ("F", 5): "r",  ("F#", 5): "5",
    ("G", 5): "t",  ("G#", 5): "6",
    ("A", 5): "y",  ("A#", 5): "7",
    ("B", 5): "u",

    # --- TOP NOTE ---
    ("C", 6): "i",
}

NOTE_TO_KEY_22_US = create_scan_code_note_map(NOTE_TO_KEY_22)

MIN_OCTAVE = 1
MAX_OCTAVE = 7

# KeyboardPlayer: plays MIDI files
class KeyboardPlayer:
    def __init__(self, layout="22", instrument="piano"):
        self.stop_flag = False
        self.instrument = instrument
        self.set_layout_and_instrument(layout, instrument)

    def set_layout(self, layout):
        """Deprecated: use set_layout_and_instrument instead."""
        self.set_layout_and_instrument(layout, self.instrument)

    def set_layout_and_instrument(self, layout, instrument):
        """Set both layout and instrument."""
        self.layout = layout
        self.instrument = instrument
        
        if instrument == "piano":
            self.note_map = NOTE_TO_KEY_22_US
        else:
            # Get instrument definition
            if instrument in INSTRUMENTS:
                instr = INSTRUMENTS[instrument]
                self.note_map = create_scan_code_note_map(
                    create_note_map_15(instr["start_octave"], instr["keys"])
                )
            else:
                # Fallback to piano with US scan codes
                self.note_map = NOTE_TO_KEY_22_US

    def stop(self):
        self.stop_flag = True

    def get_playable_key(self, note):
            name, octave = note
            
            flats_to_sharps = {
                "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"
            }
            if name in flats_to_sharps:
                name = flats_to_sharps[name]

            # For 15-key instruments (non-piano), transpose sharps/flats to nearest white key
            if self.instrument != "piano" and "#" in name:
                sharps_to_white = {
                    "C#": "C",
                    "D#": "E",
                    "F#": "G",
                    "G#": "A",
                    "A#": "B"
                }
                if name in sharps_to_white:
                    name = sharps_to_white[name]
                    # Optionally adjust octave if needed, but for simplicity, keep same octave

            # Convert note name and octave to MIDI value for octave math
            midi_value = (octave + 1) * 12 + ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"].index(name)
            
            # Find the min and max MIDI values your current instrument supports
            supported_midi_values = [((oct + 1) * 12 + ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"].index(nm)) 
                                     for (nm, oct) in self.note_map.keys()]
            min_midi = min(supported_midi_values)
            max_midi = max(supported_midi_values)

            # Shift the note by full octaves (12 semitones) until it is within range
            while midi_value < min_midi:
                midi_value += 12
            while midi_value > max_midi:
                midi_value -= 12
            
            # Convert back to note name and octave
            name = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][midi_value % 12]
            octave = midi_value // 12 - 1
            # ----------------------------------------------------------
                
            return self.note_map.get((name, octave))

