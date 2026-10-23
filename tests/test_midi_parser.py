import os
import tempfile
import unittest

import mido

from midi_parser import parse_midi


def write_midi(messages):
    """messages: (seconds_since_previous, type, note, velocity) at 120 BPM, 480 ticks per beat."""
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    for seconds, kind, note, velocity in messages:
        track.append(mido.Message(kind, note=note, velocity=velocity, time=int(seconds * 960)))
    handle, path = tempfile.mkstemp(suffix=".mid")
    os.close(handle)
    midi.save(path)
    return path


class ParseMidiTests(unittest.TestCase):
    def parse(self, messages):
        path = write_midi(messages)
        self.addCleanup(os.unlink, path)
        events, _ = parse_midi(path)
        return [(round(delay, 3), notes) for delay, notes in events]

    def test_restrike_before_note_off_keeps_both_notes(self):
        # Transcribers write the new note-on before the old note-off at the same instant.
        events = self.parse([(0, "note_on", 67, 80), (0.25, "note_on", 67, 90),
                             (0, "note_off", 67, 0), (0.25, "note_off", 67, 0)])
        self.assertEqual(events, [(0.0, [("G", 4, 250, 80)]), (0.25, [("G", 4, 250, 90)])])

    def test_velocity_zero_note_on_ends_a_note(self):
        events = self.parse([(0, "note_on", 60, 70), (0.5, "note_on", 60, 0)])
        self.assertEqual(events, [(0.0, [("C", 4, 500, 70)])])

    def test_unterminated_note_lasts_until_its_next_strike(self):
        events = self.parse([(0, "note_on", 60, 70), (0.5, "note_on", 60, 70), (0.5, "note_off", 60, 0)])
        self.assertEqual(events, [(0.0, [("C", 4, 500, 70)]), (0.5, [("C", 4, 500, 70)])])


if __name__ == "__main__":
    unittest.main()
