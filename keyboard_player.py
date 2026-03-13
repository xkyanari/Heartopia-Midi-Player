import keyboard
import threading
import mido

import ctypes
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
            self.note_map = NOTE_TO_KEY_22
        else:
            # Get instrument definition
            if instrument in INSTRUMENTS:
                instr = INSTRUMENTS[instrument]
                self.note_map = create_note_map_15(instr["start_octave"], instr["keys"])
            else:
                # Fallback to piano
                self.note_map = NOTE_TO_KEY_22

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

            while (name, octave) not in self.note_map and octave < MAX_OCTAVE:
                octave += 1
            while (name, octave) not in self.note_map and octave > MIN_OCTAVE:
                octave -= 1
                
            return self.note_map.get((name, octave))

# MidiInputPlayer: live MIDI keyboard
class MidiInputPlayer:
    def __init__(self, layout="22", instrument="piano", note_to_key=None, on_key_press=None, transpose=0):
        self.on_key_press = on_key_press
        self.transpose = transpose
        self.stop_flag = False
        self.thread = None
        self.instrument = instrument
        
        # Support both old and new initialization
        if note_to_key is not None:
            self.note_to_key = note_to_key
        else:
            if instrument == "piano":
                self.note_to_key = NOTE_TO_KEY_22
            else:
                if instrument in INSTRUMENTS:
                    instr = INSTRUMENTS[instrument]
                    self.note_to_key = create_note_map_15(instr["start_octave"], instr["keys"])
                else:
                    self.note_to_key = NOTE_TO_KEY_22

    def stop(self):
        self.stop_flag = True

    def start(self, port_name=None):
        self.stop_flag = False
        self.thread = threading.Thread(target=self.run, args=(port_name,), daemon=True)
        self.thread.start()

    def run(self, port_name):
        try:
            if port_name is None:
                ports = mido.get_input_names()
                if not ports:
                    print("No MIDI input found.")
                    return
                port_name = ports[0]

            chord_buffer = []
            buffer_timeout = 0.020  # 20 milliseconds window for merging notes into chords
            last_msg_time = 0
            buffer_timer = None

            def process_chord_buffer():
                nonlocal chord_buffer, buffer_timer
                if chord_buffer:
                    # Press all keys in the chord simultaneously
                    pressed_keys = []
                    for midi_note in chord_buffer:
                        key = self.get_playable_key(midi_note)
                        if key:
                            keyboard.press(key)
                            pressed_keys.append(key)
                    
                    if pressed_keys and self.on_key_press:
                        self.on_key_press(pressed_keys)
                    
                    # Release all keys after a short sustain
                    def release_chord(keys):
                        for key in keys:
                            keyboard.release(key)
                        if self.on_key_press:
                            self.on_key_press([])
                    
                    # Schedule release after sustain time (adjust as needed)
                    threading.Timer(0.1, release_chord, args=[pressed_keys]).start()
                    
                    chord_buffer.clear()
                buffer_timer = None
            # -------------------------------------------------------------

            with mido.open_input(port_name) as inport:
                for msg in inport:
                    if self.stop_flag:
                        break
                    
                    current_time = msg.time if hasattr(msg, 'time') else 0
                    
                    if msg.type == 'note_on' and msg.velocity > 0:
                        # Add note to buffer
                        chord_buffer.append(msg.note)
                        
                        # Start or reset the buffer timer
                        if buffer_timer:
                            buffer_timer.cancel()
                        buffer_timer = threading.Timer(buffer_timeout, process_chord_buffer)
                        buffer_timer.start()
                        
                        last_msg_time = current_time
                        
        except Exception as e:
            print(f"MIDI input error: {e}")
        finally:
            # Clean up any remaining timer
            if 'buffer_timer' in locals() and buffer_timer:
                buffer_timer.cancel()

    def get_playable_key(self, midi_note):
        NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
                      "F#", "G", "G#", "A", "A#", "B"]
        midi_note += self.transpose
        
        # Find the min and max MIDI values your current instrument supports
        supported_midi_values = [((oct + 1) * 12 + NOTE_NAMES.index(nm)) 
                                 for (nm, oct) in self.note_to_key.keys()]
        min_midi = min(supported_midi_values)
        max_midi = max(supported_midi_values)

        # Shift the note by full octaves (12 semitones) until it is within range
        while midi_note < min_midi:
            midi_note += 12
        while midi_note > max_midi:
            midi_note -= 12
        # ----------------------------------------------------------
        
        name = NOTE_NAMES[midi_note % 12]
        octave = midi_note // 12 - 1
        
        return self.note_to_key.get((name, octave))
