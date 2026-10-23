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

    # A re-strike ends the pitch's sounding note, like a piano key. Transcribed
    # MIDI often writes the new note-on before the old note's note-off at the
    # same instant; that note-off belongs to the note already ended, so skip it.
    active_notes = {}
    restruck_at = {}
    event_notes = defaultdict(list)

    def finish(note, start_time, velocity, end_time):
        name, octave = midi_to_note(note)
        duration_ms = int((end_time - start_time) * 1000)
        event_notes[start_time].append((name, octave, duration_ms, velocity))

    for msg in mid:
        current_time += msg.time

        if msg.type == "note_on" and msg.velocity > 0:
            if msg.note in active_notes:
                finish(msg.note, *active_notes[msg.note], current_time)
                restruck_at[msg.note] = current_time
            active_notes[msg.note] = (current_time, msg.velocity)
        elif msg.type in ("note_on", "note_off"):
            # note_off, or note_on with velocity 0
            restrike = restruck_at.pop(msg.note, None)
            if restrike is not None and abs(current_time - restrike) < 0.002:
                continue
            if msg.note in active_notes:
                finish(msg.note, *active_notes.pop(msg.note), current_time)

    # Handle notes that never got a note_off
    end_time = current_time
    for note, (start_time, velocity) in list(active_notes.items()):
        finish(note, start_time, velocity, end_time)

    sorted_event_times = sorted(event_notes.keys())
    last_time = sorted_event_times[0] if sorted_event_times else 0.0
    for index, t in enumerate(sorted_event_times):
        # Start at the first note instead of playing leading MIDI silence.
        delay = 0.0 if index == 0 else t - last_time
        events.append((delay, event_notes[t]))
        last_time = t

    total_duration = mid.length
    return events, total_duration
