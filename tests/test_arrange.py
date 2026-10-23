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

    def test_low_bass_does_not_move_an_in_range_melody(self):
        # Bass below the piano's C3 folds up; it must not push the song up an octave.
        events = [(0.0 if i == 0 else 0.5, chord("C2", "E2", "G2", name))
                  for i, name in enumerate(["E4", "G4", "C5", "B4"])]
        arranged, report = arrange(events, note_map("piano"), "piano")
        self.assertEqual(report["transpose"], 0)
        self.assertEqual([notes[0] for notes in numbers(arranged)], [64, 67, 72, 71])

    def test_song_already_in_c_is_not_transposed_on_white_key_instruments(self):
        # C major with one short chromatic passing note.
        events = [(0.0 if i == 0 else 0.25, chord(name))
                  for i, name in enumerate(["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6"])]
        events.insert(4, (0.25, chord("F#5", duration=100)))
        self.assertEqual(arrange(events, note_map("violin"), "violin")[1]["transpose"], 0)

    def test_ghost_notes_are_dropped_but_never_the_whole_song(self):
        events = [(0.0, chord("C4", "E4") + chord("G4", velocity=5)),
                  (0.5, chord("D4", duration=10, velocity=30)), (0.5, chord("F4", duration=1))]
        arranged, _ = arrange(events, note_map("piano"), "piano")
        self.assertEqual(numbers(arranged), [[64, 60], [65]])  # Loud 1 ms re-strike kept.
        quiet = [(0.0, chord("C4", velocity=5))]
        self.assertEqual(numbers(arrange(quiet, note_map("piano"), "piano")[0]), [[60]])

    def test_chords_are_capped_deduplicated_and_keep_melody_and_bass(self):
        # Melody is in range, so no shift; C2 folds onto C3. Cap keeps top, bottom, then the loudest.
        events = [(0.0, chord("C3", "E4", "G4", velocity=40) + chord("C2", velocity=90)
                   + chord("B4", velocity=100) + chord("D4", velocity=70))]
        arranged, _ = arrange(events, note_map("piano"), "piano")
        played = numbers(arranged)[0]
        self.assertEqual(len(played), 4)
        self.assertEqual(len(set(played)), 4)
        self.assertEqual(played, [71, 48, 62, 64])  # B4 melody, C3 bass, then D4 and E4.

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

    def held_keys(self, arranged):
        """Most keys down at once, and presses of a key that is still down."""
        time, ends, most, repressed = 0.0, {}, 0, 0
        for delay, notes in arranged:
            time += delay
            ends = {key: end for key, end in ends.items() if end > time + 1e-9}
            for note in notes:
                repressed += (note[0], note[1]) in ends
                ends[(note[0], note[1])] = time + note[2] / 1000
            most = max(most, len(ends))
        return most, repressed

    def test_violin_melody_is_legato_and_accompaniment_short(self):
        # Pedalled piano: every note rings for 3 s.
        events = [(0.0 if i == 0 else 0.5, chord("C3", "G3", name, duration=3000))
                  for i, name in enumerate(["E5", "F5", "G5"])]
        arranged, _ = arrange(events, note_map("violin"), "violin")
        for index, (_, notes) in enumerate(arranged):
            melody, *accompaniment = notes
            self.assertEqual(melody[2], 500 if index < 2 else 3000)
            self.assertTrue(all(note[2] <= 250 for note in accompaniment))
        self.assertLessEqual(self.held_keys(arranged)[0], 3)

    def test_sustained_holds_are_capped_and_repeated_keys_rebowed(self):
        events = [(0.0 if i == 0 else 0.1, chord(*names, duration=6000))
                  for i, names in enumerate([("C4", "E4", "G4"), ("C4", "F4", "A4"), ("D4", "G4", "B4")])]
        for instrument in ("violin", "cello"):
            with self.subTest(instrument=instrument):
                arranged, _ = arrange(events, note_map(instrument), instrument)
                self.assertEqual(self.held_keys(arranged), (3, 0))
                self.assertTrue(all(note[2] <= 5000 for _, notes in arranged for note in notes))

    def test_struck_instruments_tap_and_let_go_before_quick_repeats(self):
        # Repeated eighth notes 150 ms apart, then a long note.
        events = [(0.0, chord("G4")), (0.15, chord("G4")), (0.15, chord("G4", "C4", duration=3000))]
        for instrument in ("piano", "lute"):
            with self.subTest(instrument=instrument):
                arranged, _ = arrange(events, note_map(instrument), instrument)
                holds = [[note[2] for note in notes] for _, notes in arranged]
                self.assertEqual(holds, [[110], [110], [250, 250]])
                self.assertEqual(self.held_keys(arranged)[1], 0)

    def test_notes_without_velocity_are_accepted(self):
        arranged, _ = arrange([(0.0, [("C", 4, 300)])], note_map("lute"), "lute")
        self.assertEqual(numbers(arranged), [[60]])


if __name__ == "__main__":
    unittest.main()
