import unittest

from arrange import arrange, instrument_range, note_number
from keyboard_player import KeyboardPlayer


def note_map(instrument):
    return KeyboardPlayer(instrument=instrument).note_map


def chord(*names, duration=500, velocity=80):
    return [(name[:-1], int(name[-1]), duration, velocity) for name in names]


def numbers(events):
    return [[note_number(note[0], note[1]) for note in notes] for _, notes in events]


class ArrangeTests(unittest.TestCase):
    def test_ranges_come_from_the_note_map(self):
        self.assertEqual(instrument_range(note_map("piano")), (48, 84, True))
        self.assertEqual(instrument_range(note_map("violin")), (60, 84, False))
        self.assertEqual(instrument_range(note_map("cello")), (36, 60, False))

    def test_every_note_is_playable_on_every_instrument(self):
        # Wide piano transcription: A0 bass to C8 sparkle, with accidentals.
        events = [(0.0, chord("A0", "C#4", "E4", "C8")), (0.5, chord("F#2", "A#5", "D#7")),
                  (0.5, chord("G1", "B3", "D5", "F5", "G6"))]
        for instrument in ("piano", "lute", "wooden bass", "recorder", "violin", "cello"):
            with self.subTest(instrument=instrument):
                player = KeyboardPlayer(instrument=instrument)
                arranged, report = arrange(events, player.note_map, instrument)
                self.assertTrue(arranged)
                for _, notes in arranged:
                    for note in notes:
                        self.assertIn((note[0], note[1]), player.note_map)

    def test_white_key_instruments_transpose_to_the_key_with_fewest_accidentals(self):
        # E-flat major scale; one semitone up/down is not enough, so a global shift is expected.
        scale = ["D#4", "F4", "G4", "G#4", "A#4", "C5", "D5", "D#5"]
        events = [(0.0 if i == 0 else 0.25, chord(name)) for i, name in enumerate(scale)]
        arranged, report = arrange(events, note_map("violin"), "violin")
        self.assertEqual(report["snapped"], 0)
        self.assertEqual(report["kept"], len(scale))
        self.assertEqual(report["transpose"] % 12, 9)  # E-flat -> C major.
        melody = [notes[0] for notes in numbers(arranged)]
        self.assertEqual(melody, sorted(melody))  # Scale still rises.

    def test_piano_keeps_key_and_only_moves_by_octaves(self):
        events = [(0.0, chord("D#6", "G6")), (0.5, chord("A#6"))]
        arranged, report = arrange(events, note_map("piano"), "piano")
        self.assertEqual(report["transpose"] % 12, 0)
        self.assertEqual(numbers(arranged), [[79, 75], [82]])  # Melody first, down an octave.

    def test_ghost_notes_are_dropped_but_never_the_whole_song(self):
        events = [(0.0, chord("C4", "E4") + chord("G4", velocity=5)), (0.5, chord("D4", duration=10))]
        arranged, _ = arrange(events, note_map("piano"), "piano")
        self.assertEqual(numbers(arranged), [[64, 60]])
        quiet = [(0.0, chord("C4", velocity=5))]
        self.assertEqual(numbers(arrange(quiet, note_map("piano"), "piano")[0]), [[60]])

    def test_chords_are_capped_deduplicated_and_keep_melody_and_bass(self):
        # Up an octave fits all six notes; the cap keeps top, bottom, then the loudest.
        events = [(0.0, chord("C3", "E4", "G4", velocity=40) + chord("C2", velocity=90)
                   + chord("B4", velocity=100) + chord("D4", velocity=70))]
        arranged, _ = arrange(events, note_map("piano"), "piano")
        played = numbers(arranged)[0]
        self.assertEqual(len(played), 4)
        self.assertEqual(len(set(played)), 4)
        self.assertEqual(played, [83, 48, 74, 60])  # B5 melody, C3 bass, then D5 and C4.

    def test_notes_folding_onto_one_key_play_once(self):
        arranged, _ = arrange([(0.0, chord("C3", "C6", "C7"))], note_map("violin"), "violin")
        played = numbers(arranged)[0]
        self.assertEqual(len(played), len(set(played)))

    def test_staggered_onsets_merge_and_timing_is_preserved(self):
        events = [(0.0, chord("C4")), (0.01, chord("E4")), (1.0, chord("G4"))]
        arranged, _ = arrange(events, note_map("piano"), "piano")
        self.assertEqual(len(arranged), 2)
        self.assertEqual(arranged[0][0], 0.0)
        self.assertAlmostEqual(arranged[1][0], 1.01)

    def test_notes_without_velocity_are_accepted(self):
        arranged, _ = arrange([(0.0, [("C", 4, 300)])], note_map("lute"), "lute")
        self.assertEqual(numbers(arranged), [[60]])


if __name__ == "__main__":
    unittest.main()
