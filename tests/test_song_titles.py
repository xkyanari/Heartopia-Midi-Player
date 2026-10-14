"""Filename-derived song titles work without a Tk display."""
import unittest
from unittest.mock import Mock, patch

import main


class SongTitleTests(unittest.TestCase):
    def test_filename_titles(self):
        cases = (
            ("payon-theme.mid", "Payon Theme"),
            ("my_song__v2.MIDI", "My Song V2"),
            ("BGM-town.mid", "BGM Town"),
            ("C:/x/BGM-town.mid", "BGM Town"),
            ("don't-stop.mid", "Don't Stop"),
            ("  my_  song\t-theme.MiD", "My Song Theme"),
            ("my_song.mp3", "My Song.mp3"),
            ("my_song", "My Song"),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(main.song_title(path), expected)

    def test_empty_title_falls_back(self):
        for path, expected in (("---.mid", "---"), ("___.MIDI", "___"),
                               (".mid", ".mid"), ("", "")):
            with self.subTest(path=path):
                self.assertEqual(main.song_title(path), expected)

    def test_artist_separators(self):
        cases = (
            ("ABBA - Chiquitita.mid", "ABBA - Chiquitita"),
            ("a-ha - take on me (unplugged).mid", "A Ha - Take On Me (unplugged)"),
            ("ABBA_-_Dancing_Queen.mid", "ABBA - Dancing Queen"),
            ("A1  -  heaven by your side.MIDI", "A1 - Heaven By Your Side"),
            ("ABBA - - Chiquitita.mid", "ABBA - Chiquitita"),
            ("ABBA -- Chiquitita.mid", "ABBA - Chiquitita"),
            ("ABBA_-__-_Chiquitita.mid", "ABBA - Chiquitita"),
            ("ABBA\t-\tchiquitita.mid", "ABBA - Chiquitita"),
            (" - intro.mid", "Intro"),
            ("intro - .mid", "Intro"),
            ("_-_intro_-_.mid", "Intro"),
            (" - - .mid", " - - "),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(main.song_title(path), expected)

    def test_playlist_uses_title_and_preserves_path(self):
        path = "C:/songs/payon-theme.mid"
        playlist_box = Mock()
        with patch.object(main, "playlist", []), \
                patch.object(main, "playlist_box", playlist_box), \
                patch.object(main.mido, "MidiFile", return_value=Mock(length=60)):
            main.append_playlist_song(path)
            self.assertEqual(main.playlist, [
                {"name": "Payon Theme", "path": path, "duration": 60},
            ])
        playlist_box.insert.assert_called_once_with(main.tk.END, "Payon Theme  ·  1:00")


if __name__ == "__main__":
    unittest.main()
