"""Fit parsed MIDI events to the selected instrument's range before playback. No Tk."""
from app_config import (
    ARRANGE_ACCOMPANIMENT_HOLD_MS, ARRANGE_CHORD_WINDOW_MS, ARRANGE_DEFAULT_MAX_CHORD,
    ARRANGE_MAX_CHORD, ARRANGE_MAX_HELD_KEYS, ARRANGE_MIN_DURATION_MS, ARRANGE_MIN_HOLD_MS,
    ARRANGE_MIN_VELOCITY, ARRANGE_REBOW_GAP_MS, ARRANGE_SHIFT_MARGIN,
    ARRANGE_SHORT_NOTE_MIN_VELOCITY, KEY_HOLD_MS, SUSTAIN_MAX_MS,
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
    """Drop transcription ghosts; keep everything if that would empty the song.

    Ghosts are quiet. A loud note can be very short when the transcriber writes
    a re-strike as a 1 ms note, so short notes are dropped only when also quiet.
    """
    kept = [note for note in notes if note["velocity"] >= ARRANGE_MIN_VELOCITY and
            (note["duration"] >= ARRANGE_MIN_DURATION_MS or
             note["velocity"] >= ARRANGE_SHORT_NOTE_MIN_VELOCITY)]
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


def _best_shift(candidates, items, fits):
    """No shift unless the best one fits clearly more weight (by the margin)."""
    total = sum(weight for _, weight in items) or 1
    scores = {shift: sum(weight for number, weight in items if fits(number + shift))
              for shift in candidates}
    best = max(scores, key=lambda shift: (scores[shift], -abs(shift)))
    return 0 if scores[0] >= scores[best] - ARRANGE_SHIFT_MARGIN * total else best


def choose_transpose(chords, low, high, chromatic):
    """One shift for the whole song: key for white-key instruments, then octave.

    Songs stay where they are unless a shift clearly helps. The octave is judged
    by the melody (top voice) only: out-of-range bass folds up harmlessly, so it
    must not drag the whole song up an octave.
    """
    every = [(note["number"], _weight(note)) for _, chord in chords for note in chord]
    melody = [(top["number"], _weight(top)) for top in
              (max(chord, key=lambda note: note["number"]) for _, chord in chords)]
    key_shift = 0
    if not chromatic:
        key_shift = _best_shift(range(-5, 7), every,
                                         lambda number: number % 12 in WHITE_PITCH_CLASSES)
    octave_shift = _best_shift(range(-48, 49, 12), melody,
                                        lambda number: low <= number + key_shift <= high)
    return key_shift + octave_shift


def _snap(number, used, previous):
    """Move a black key to a free neighbouring white key, nearest the previous melody note."""
    options = [candidate for candidate in (number - 1, number + 1) if candidate not in used]
    if not options:
        return None
    if previous is None:
        return options[0]
    return min(options, key=lambda candidate: abs(candidate - previous))


def _rebow_limit(gap_ms):
    """Longest hold that still leaves the key up before it is pressed again."""
    return gap_ms - ARRANGE_REBOW_GAP_MS if gap_ms > 2 * ARRANGE_REBOW_GAP_MS else gap_ms / 2


def shape_taps(arranged):
    """Hold times for struck/plucked instruments: a fixed tap, let go early
    enough before a repeat of the same key that the game sees a new press."""
    next_press = {}
    for time, played in reversed(arranged):
        for note in played:
            hold = KEY_HOLD_MS
            if note[0] in next_press:
                hold = min(hold, _rebow_limit((next_press[note[0]] - time) * 1000))
            note[1] = max(ARRANGE_MIN_HOLD_MS, int(hold))
            next_press[note[0]] = time


def shape_sustain(arranged, max_hold):
    """Hold times for bowed instruments, in place on [time, [[number, hold, velocity, melody]]].

    The melody plays legato up to the next melody note; accompaniment is a short
    tap; a key is let go before it is pressed again; and when too many keys would
    be down at once, the accompaniment (then the oldest notes) is cut short.
    """
    next_press, next_onset = {}, None
    for time, played in reversed(arranged):
        for note in played:
            number, hold, _, melody = note
            hold = min(hold, max_hold) if melody else min(hold, ARRANGE_ACCOMPANIMENT_HOLD_MS)
            if melody and next_onset is not None:
                hold = min(hold, (next_onset - time) * 1000)
            if number in next_press:
                hold = min(hold, _rebow_limit((next_press[number] - time) * 1000))
            note[1] = hold
            next_press[number] = time
        next_onset = time

    active = []  # (end, start, note), sorted so cuts hit accompaniment, then oldest.
    for time, played in arranged:
        active = [entry for entry in active if entry[0] > time]
        excess = len(active) + len(played) - ARRANGE_MAX_HELD_KEYS
        if excess > 0:
            active.sort(key=lambda entry: (entry[2][3], entry[1]))
            for _, start, note in active[:excess]:
                # Whole ms: Tk timers reject fractions.
                note[1] = max(ARRANGE_MIN_HOLD_MS, int((time - start) * 1000))
            active = active[excess:]
        for note in played:
            note[1] = max(ARRANGE_MIN_HOLD_MS, int(note[1]))
            active.append((time + note[1] / 1000, time, note))


def arrange(events, note_map, instrument=None):
    """Return (events, report) with every note playable on `note_map`.

    Events keep parse_midi's (delay, [(name, octave, ms, velocity)]) shape, but ms is
    now how long to hold the key on this instrument rather than the note's length.
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
            played.append([number, note["duration"], note["velocity"], note is top])
            if note is top:
                previous_melody = number
        if played:
            arranged.append((time, played))
    if instrument in SUSTAIN_MAX_MS:
        shape_sustain(arranged, SUSTAIN_MAX_MS[instrument])
    else:
        shape_taps(arranged)

    result, last = [], arranged[0][0] if arranged else 0.0
    for index, (time, played) in enumerate(arranged):
        result.append((0.0 if index == 0 else time - last,
                       [(*note_name(number), hold, velocity) for number, hold, velocity, _ in played]))
        last = time
    kept = sum(len(played) for _, played in arranged)
    return result, {"transpose": shift, "notes": len(source), "kept": kept, "snapped": snapped}
