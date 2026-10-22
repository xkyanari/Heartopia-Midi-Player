"""Fit parsed MIDI events to the selected instrument's range before playback. No Tk."""
from app_config import (
    ARRANGE_CHORD_WINDOW_MS, ARRANGE_DEFAULT_MAX_CHORD, ARRANGE_MAX_CHORD,
    ARRANGE_MIN_DURATION_MS, ARRANGE_MIN_VELOCITY,
)
from midi_parser import NOTE_NAMES

WHITE_PITCH_CLASSES = {0, 2, 4, 5, 7, 9, 11}
DEFAULT_VELOCITY = 100


def note_number(name, octave):
    return (octave + 1) * 12 + NOTE_NAMES.index(name)


def note_name(number):
    return NOTE_NAMES[number % 12], number // 12 - 1


def instrument_range(note_map):
    """Return (lowest, highest, chromatic) for a {(name, octave): key} map."""
    numbers = [note_number(name, octave) for name, octave in note_map]
    chromatic = any(number % 12 not in WHITE_PITCH_CLASSES for number in numbers)
    return min(numbers), max(numbers), chromatic


def _weight(note):
    # Long, loud notes matter most; cap duration so one held chord cannot dominate.
    return min(max(note["duration"], 1), 1000) * note["velocity"]


def _fold(number, low, high):
    while number < low:
        number += 12
    while number > high:
        number -= 12
    return number


def _flatten(events):
    """Absolute-time notes; parse_midi notes are (name, octave, duration_ms[, velocity])."""
    notes, time = [], 0.0
    for delay, chord in events:
        time += delay
        for note in chord:
            notes.append({"time": time, "number": note_number(note[0], note[1]),
                          "duration": note[2] if len(note) > 2 else 0,
                          "velocity": note[3] if len(note) > 3 else DEFAULT_VELOCITY})
    return notes


def _clean(notes):
    """Drop transcription ghosts; keep everything if that would empty the song."""
    kept = [note for note in notes if note["velocity"] >= ARRANGE_MIN_VELOCITY and
            note["duration"] >= ARRANGE_MIN_DURATION_MS]
    return kept or notes


def _group_onsets(notes):
    """Merge near-simultaneous onsets (staggered transcribed chords) into one chord."""
    chords = []
    for note in sorted(notes, key=lambda note: (note["time"], note["number"])):
        if chords and (note["time"] - chords[-1][0]) * 1000 <= ARRANGE_CHORD_WINDOW_MS:
            chords[-1][1].append(note)
        else:
            chords.append((note["time"], [note]))
    return chords


def choose_transpose(chords, low, high, chromatic):
    """One shift for the whole song: best key for white-key instruments, then best octave."""
    weighted = []
    for _, chord in chords:
        top = max(note["number"] for note in chord)
        for note in chord:
            # The melody (top voice) should land in range more than accompaniment.
            weighted.append((note["number"], _weight(note) * (2 if note["number"] == top else 1)))

    def best(candidates, score):
        return max(candidates, key=lambda shift: (score(shift), -abs(shift)))

    key_shift = 0
    if not chromatic:
        key_shift = best(range(-5, 7), lambda shift: sum(
            weight for number, weight in weighted if (number + shift) % 12 in WHITE_PITCH_CLASSES))
    octave_shift = best(range(-48, 49, 12), lambda shift: sum(
        weight for number, weight in weighted if low <= number + key_shift + shift <= high))
    return key_shift + octave_shift


def _snap(number, used, previous):
    """Move a black key to a free neighbouring white key, nearest the previous melody note."""
    options = [candidate for candidate in (number - 1, number + 1) if candidate not in used]
    if not options:
        return None
    if previous is None:
        return options[0]
    return min(options, key=lambda candidate: abs(candidate - previous))


def arrange(events, note_map, instrument=None):
    """Return (events, report) with every note playable on `note_map`.

    Events keep parse_midi's (delay, [(name, octave, duration_ms, velocity)]) shape.
    """
    low, high, chromatic = instrument_range(note_map)
    max_chord = ARRANGE_MAX_CHORD.get(instrument, ARRANGE_DEFAULT_MAX_CHORD)
    source = _flatten(events)
    cleaned = _clean(source)
    chords = _group_onsets(cleaned)
    shift = choose_transpose(chords, low, high, chromatic) if chords else 0

    arranged, snapped, previous_melody = [], 0, None
    for time, chord in chords:
        top = max(chord, key=lambda note: note["number"])
        bottom = min(chord, key=lambda note: note["number"])
        rest = sorted((note for note in chord if note is not top and note is not bottom),
                      key=lambda note: -note["velocity"])
        ordered = [top] + ([bottom] if bottom is not top else []) + rest
        used, played = set(), []
        for note in ordered:
            if len(played) >= max_chord:
                break
            number = _fold(note["number"] + shift, low, high)
            if not chromatic and number % 12 not in WHITE_PITCH_CLASSES:
                number = _snap(number, used, previous_melody if note is top else None)
                if number is None:
                    continue
                snapped += 1
            if number in used:
                continue
            used.add(number)
            played.append((*note_name(number), note["duration"], note["velocity"]))
            if note is top:
                previous_melody = number
        if played:
            arranged.append((time, played))

    result, last = [], arranged[0][0] if arranged else 0.0
    for index, (time, played) in enumerate(arranged):
        result.append((0.0 if index == 0 else time - last, played))
        last = time
    kept = sum(len(played) for _, played in arranged)
    return result, {"transpose": shift, "notes": len(source), "kept": kept, "snapped": snapped}
