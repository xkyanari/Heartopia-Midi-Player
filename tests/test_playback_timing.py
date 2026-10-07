import unittest
from unittest.mock import Mock, patch

import main
from playback_timing import PlaybackClock, format_time


class TimingTests(unittest.TestCase):
    def test_minutes_and_seconds(self):
        for seconds, expected in ((0, "0:00"), (65, "1:05"), (3600, "60:00"), (-1, "0:00")):
            self.assertEqual(format_time(seconds), expected)

    def test_pause_resume_delay_speed_and_completion(self):
        now = [0]
        clock = PlaybackClock(120, speed=2, delay=1, now=lambda: now[0])
        self.assertEqual(clock.position(), 0)
        now[0] = 11
        clock.pause()
        now[0] = 31
        self.assertEqual(clock.position(), 10)
        self.assertEqual(clock.remaining(), 50)
        clock.resume()
        now[0] = 41
        self.assertEqual(clock.position(), 20)
        now[0] = 100
        self.assertEqual(clock.position(), 60)
        self.assertEqual(clock.remaining(), 0)


class PlaylistInteractionTests(unittest.TestCase):
    def test_rows_show_length_and_keep_original_path(self):
        with patch.object(main, "playlist", []), \
                patch.object(main, "playlist_box", Mock(), create=True) as box, \
                patch.object(main.mido, "MidiFile", return_value=Mock(length=125)):
            main.append_playlist_song("song.mid")
            box.insert.assert_called_once_with(main.tk.END, "song.mid  ·  2:05")
            self.assertEqual(main.playlist[0]["path"], "song.mid")

    def test_unreadable_file_remains_removable(self):
        with patch.object(main, "playlist", []), \
                patch.object(main, "playlist_box", Mock(), create=True) as box, \
                patch.object(main.mido, "MidiFile", side_effect=OSError("missing")):
            main.append_playlist_song("missing.mid")
            box.insert.assert_called_once_with(main.tk.END, "missing.mid  ·  --:--")
            self.assertIsNone(main.playlist[0]["duration"])

    def test_enter_or_double_click_plays_selection_and_empty_list_is_safe(self):
        with patch.object(main, "playlist_box", Mock(curselection=lambda: (2,)), create=True), \
                patch.object(main, "current_index", None), patch.object(main, "play_selected") as play:
            self.assertEqual(main.activate_playlist_song(), "break")
            self.assertEqual(main.current_index, 2)
            play.assert_called_once_with()
        with patch.object(main, "playlist_box", Mock(curselection=lambda: ()), create=True), \
                patch.object(main, "play_selected") as play:
            main.activate_playlist_song()
            play.assert_not_called()
