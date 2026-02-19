import mido
from collections import defaultdict

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
              "F#", "G", "G#", "A", "A#", "B"]

def midi_to_note(midi_note: int):
    name = NOTE_NAMES[midi_note % 12]
    octave = midi_note // 12 - 1
    return name, octave

def parse_midi(path: str):
    mid = mido.MidiFile(path)
    events = []
    current_time = 0.0

    buffer = defaultdict(list)

    for msg in mid:
        current_time += msg.time

        if msg.type == "note_on" and msg.velocity > 0:
            name, octave = midi_to_note(msg.note)
            buffer[current_time].append((name, octave))

    last_time = 0.0
    for t in sorted(buffer.keys()):
        delay = t - last_time
        events.append((delay, buffer[t]))
        last_time = t

    total_duration = mid.length
    return events, total_duration
