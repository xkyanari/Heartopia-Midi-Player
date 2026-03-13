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

    # Track active notes to measure their duration
    active_notes = {}
    event_notes = defaultdict(list)

    for msg in mid:
        current_time += msg.time

        if msg.type == "note_on":
            name, octave = midi_to_note(msg.note)
            if msg.velocity > 0:
                # Note on - start tracking
                active_notes[msg.note] = current_time
            else:
                # Note off (velocity 0)
                if msg.note in active_notes:
                    start_time = active_notes.pop(msg.note)
                    duration_ms = int((current_time - start_time) * 1000)
                    event_notes[start_time].append((name, octave, duration_ms))
        elif msg.type == "note_off":
            name, octave = midi_to_note(msg.note)
            if msg.note in active_notes:
                start_time = active_notes.pop(msg.note)
                duration_ms = int((current_time - start_time) * 1000)
                event_notes[start_time].append((name, octave, duration_ms))

    # Handle notes that never got a note_off
    end_time = current_time
    for note, start_time in list(active_notes.items()):
        name, octave = midi_to_note(note)
        duration_ms = int((end_time - start_time) * 1000)
        event_notes[start_time].append((name, octave, duration_ms))

    last_time = 0.0
    for t in sorted(event_notes.keys()):
        delay = t - last_time
        events.append((delay, event_notes[t]))
        last_time = t

    total_duration = mid.length
    return events, total_duration
