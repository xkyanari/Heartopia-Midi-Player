"""Song-length cache, background length reading, and M3U playlists. No display needed."""
from collections import deque
from contextlib import ExitStack
import os
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

import app_storage
import main


class M3UTests(unittest.TestCase):
    def test_round_trip_keeps_order_lengths_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "songs").mkdir()
            first, second = folder / "songs" / "하이키 - Song.mid", folder / "b.mid"
            playlist = folder / "mix.m3u"
            app_storage.write_m3u(playlist, [
                {"name": "하이키 - Song", "path": str(first), "duration": 125.6},
                {"name": "B", "path": str(second), "duration": None}])
            text = playlist.read_text(encoding="utf-8")
            self.assertIn("#EXTINF:126,하이키 - Song", text)
            self.assertIn(os.path.join("songs", "하이키 - Song.mid"), text)
            self.assertEqual(app_storage.read_m3u(playlist), [(str(first), 126), (str(second), None)])

    def test_reads_plain_and_bom_playlists(self):
        with tempfile.TemporaryDirectory() as directory:
            playlist = Path(directory) / "plain.m3u8"
            playlist.write_text("﻿# comment\r\nsong.mid\r\n\r\n", encoding="utf-8")
            self.assertEqual(app_storage.read_m3u(playlist), [(str(Path(directory) / "song.mid"), None)])


class DurationCacheTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.song = self.directory / "song.mid"
        self.song.write_bytes(b"MThd")
        stack.enter_context(patch.object(main, "duration_cache", {}))
        stack.enter_context(patch.object(main, "duration_cache_dirty", False))
        stack.enter_context(patch.object(main, "playlist", []))
        self.box = stack.enter_context(patch.object(main, "playlist_box", Mock(), create=True))
        self.root = stack.enter_context(patch.object(main, "root", Mock(), create=True))
        stack.enter_context(patch.object(main, "pending_durations", deque()))
        stack.enter_context(patch.object(main, "duration_results", queue.Queue()))
        stack.enter_context(patch.object(main, "duration_worker", None))
        stack.enter_context(patch.object(main, "duration_polling", False))
        self.thread = stack.enter_context(patch.object(main.threading, "Thread"))
        self.thread.return_value.is_alive.return_value = False

    def test_cached_length_is_reused_until_the_file_changes(self):
        self.assertIs(main.lookup_duration(str(self.song)), main.MISSING)
        main.remember_duration(str(self.song), 61.5)
        self.assertEqual(main.lookup_duration(str(self.song)), 61.5)
        self.song.write_bytes(b"MThd changed")
        self.assertIs(main.lookup_duration(str(self.song)), main.MISSING)

    def test_cache_survives_a_restart(self):
        with patch.object(app_storage, "DURATION_CACHE_FILE", str(self.directory / "durations.json")):
            main.remember_duration(str(self.song), 90)
            main.save_durations()
            self.assertEqual(app_storage.load_duration_cache(), main.duration_cache)
            self.assertFalse(main.duration_cache_dirty)

    def test_bulk_load_shows_rows_at_once_and_fills_lengths_later(self):
        with patch.object(main.mido, "MidiFile", return_value=Mock(length=125)) as read:
            main.append_playlist_song(str(self.song), defer=True)
            read.assert_not_called()  # Startup is not blocked on reading the file.
            self.box.insert.assert_called_once_with(main.tk.END, ("Song", "--:--"))
            self.thread.return_value.start.assert_called_once_with()
            main.read_pending_durations()  # What the worker thread runs.
        with patch.object(main, "save_durations") as save:
            main.poll_durations()
        self.box.update_row.assert_called_once_with(0, ("Song", "2:05"))
        self.assertEqual(main.playlist[0]["duration"], 125)
        self.assertEqual(main.lookup_duration(str(self.song)), 125)
        save.assert_called_once_with()

    def test_cached_song_is_not_read_again(self):
        main.remember_duration(str(self.song), 30)
        with patch.object(main.mido, "MidiFile") as read:
            main.append_playlist_song(str(self.song), defer=True)
            main.append_playlist_song(str(self.song))
        read.assert_not_called()
        self.thread.assert_not_called()
        self.assertEqual([entry["duration"] for entry in main.playlist], [30, 30])

    def test_deleted_song_does_not_update_a_row(self):
        main.append_playlist_song(str(self.song), defer=True)
        main.playlist.clear()
        main.duration_results.put((main.pending_durations.popleft(), 10))
        with patch.object(main, "save_durations"):
            main.poll_durations()
        self.box.update_row.assert_not_called()

    def test_open_playlist_replaces_songs_and_reports_missing(self):
        playlist = self.directory / "mix.m3u"
        app_storage.write_m3u(playlist, [
            {"name": "Song", "path": str(self.song), "duration": 75},
            {"name": "Gone", "path": str(self.directory / "gone.mid"), "duration": 10}])
        main.playlist.append({"name": "Old", "path": "old.mid", "duration": 1})
        with patch.object(main.filedialog, "askopenfilename", return_value=str(playlist)), \
                patch.object(main, "save_playlist") as save, patch.object(main, "set_status") as status, \
                patch.object(main.mido, "MidiFile") as read:
            main.open_playlist()
        read.assert_not_called()  # Lengths come from the playlist file.
        self.assertEqual(main.playlist, [{"name": "Song", "path": str(self.song), "duration": 75}])
        self.box.clear.assert_called_once_with()
        save.assert_called_once_with()
        status.assert_called_with("Opened mix.m3u: 1 Songs, 1 Missing")

    def test_save_playlist_as_writes_m3u(self):
        target = self.directory / "saved.m3u"
        main.playlist.append({"name": "Song", "path": str(self.song), "duration": 75})
        with patch.object(main.filedialog, "asksaveasfilename", return_value=str(target)), \
                patch.object(main, "set_status") as status:
            main.save_playlist_as()
        self.assertEqual(app_storage.read_m3u(target), [(str(self.song), 75)])
        status.assert_called_with("Saved saved.m3u: 1 Songs")


if __name__ == "__main__":
    unittest.main()
