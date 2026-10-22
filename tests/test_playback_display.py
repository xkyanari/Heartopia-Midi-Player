"""Playback presentation follows actual held keys without a Tk display."""
from contextlib import ExitStack
import unittest
from unittest.mock import Mock, patch

import main
from playback_timing import PlaybackClock


class Scheduler:
    def __init__(self):
        self.pending = {}
        self.time = 0
        self.next_id = 0

    def after(self, delay, callback):
        self.next_id += 1
        self.pending[self.next_id] = (self.time + delay, callback)
        return self.next_id

    def after_cancel(self, callback_id):
        self.pending.pop(callback_id, None)

    def step(self):
        callback_id = min(self.pending, key=lambda key: self.pending[key][0])
        self.time, callback = self.pending.pop(callback_id)
        callback()


class PlaybackDisplayTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Scheduler()
        self.label = Mock()
        self.visualizer = Mock()
        self.player = Mock(note_map={"low": "a", "high": "b"})
        self.player.get_playable_key.side_effect = lambda note: note[0]
        for name, value in {
            "root": self.root, "now_playing_label": self.label,
            "visualizer": self.visualizer, "player": self.player,
            "status_label": Mock(), "pressed_keys": [], "playback_after_ids": [],
            "playback_active": False, "playback_gen": 0, "is_paused": False,
            "focus_check_id": None, "current_instrument": "violin",
            "musical_chairs_run_id": 0,
            "time_label": None, "progress_bar": None, "playback_clock": None,
            "time_update_id": None,
        }.items():
            stack.enter_context(patch.object(main, name, value, create=True))
        for name in ("press_key", "release_key", "switch_to_player", "switch_to_heartopia"):
            stack.enter_context(patch.object(main, name))
        stack.enter_context(patch.object(main, "PlaybackClock", side_effect=lambda duration, **kwargs:
                                        PlaybackClock(duration, now=lambda: self.root.time / 1000, **kwargs)))

    def start(self):
        main.start_playback([(0, [("a", 4, 1000)]), (0.1, [("b", 4, 2000)])],
                            on_key_press=main.highlight_keys, song_name="song.mid")

    def test_overlapping_notes_and_natural_completion(self):
        self.start()
        self.label.config.assert_called_with(text="song.mid")
        self.root.step()  # Begin scheduling MIDI notes.
        self.root.step()  # First note.
        self.root.step()  # Second note overlaps the first.
        self.visualizer.show_keys.assert_called_with(["a", "b"], ["a", "b"])
        self.root.step()  # Release only the first note.
        self.visualizer.show_keys.assert_called_with(["b"], ["a", "b"])
        self.label.config.assert_called_with(text="song.mid")
        self.root.step()  # Final note ends.
        self.visualizer.show_keys.assert_called_with([], ["a", "b"])
        self.label.config.assert_called_with(text="Nothing Playing")

    def test_pause_resume_and_stop(self):
        self.start()
        self.root.step()
        self.root.step()
        main.pause_resume()
        self.visualizer.show_keys.assert_called_with([], ["a", "b"])
        self.label.config.assert_called_with(text="song.mid")
        main.pause_resume()
        self.visualizer.show_keys.assert_called_with(["a"], ["a", "b"])
        main.stop()
        self.assertFalse(self.root.pending)
        self.visualizer.show_keys.assert_called_with([], ["a", "b"])
        self.label.config.assert_called_with(text="Nothing Playing")

    def test_selection_and_status_do_not_replace_playing_song(self):
        self.start()
        with patch.object(main, "playlist_box", Mock(curselection=lambda: (1,)), create=True), \
                patch.object(main, "current_index", 0):
            main.on_playlist_select(None)
            main.set_status("Added to Playlist: another.mid")
            self.assertEqual(main.current_index, 1)
            self.label.config.assert_called_with(text="song.mid")

    def test_empty_midi_does_not_show_a_playing_song(self):
        main.start_playback([], on_key_press=main.highlight_keys, song_name="empty.mid")
        self.label.config.assert_called_with(text="Nothing Playing")

    def test_each_playback_mode_supplies_the_actual_song_name(self):
        songs = [{"name": "first.mid", "path": "first.mid"},
                 {"name": "second.mid", "path": "second.mid"}]
        for command in (main.play_selected, main.play_playlist, main.play_musical_chairs):
            with self.subTest(command=command.__name__), ExitStack() as stack:
                stack.enter_context(patch.object(main, "playlist", songs))
                stack.enter_context(patch.object(main, "current_index", 1))
                stack.enter_context(patch.object(main, "playlist_box", Mock(), create=True))
                stack.enter_context(patch.object(main, "loop_mode", "none"))
                stack.enter_context(patch.object(main, "parse_midi", return_value=([(0, [])], 1)))
                stack.enter_context(patch.object(main.random, "randrange", return_value=1))
                playback = stack.enter_context(patch.object(main, "start_playback"))
                command()
                self.assertEqual(playback.call_args.kwargs["song_name"], "second.mid")
                self.assertEqual(playback.call_args.kwargs["duration"], 1)

    def test_pause_during_gap_preserves_note_delay_and_remaining_time(self):
        main.start_playback([(0, []), (10, [("a", 4, 1000)])], duration=11)
        self.root.step()
        self.root.step()
        self.root.time = 2000
        main.pause_resume()
        self.root.time = 7000
        self.assertEqual(main.playback_clock.remaining(), 9)
        main.pause_resume()
        self.root.step()  # Original note callback at 10 seconds must wait.
        main.press_key.assert_not_called()
        self.root.step()  # Remaining gap ends at 15 seconds.
        main.press_key.assert_called_once_with("a")

    def test_playlist_transition_waits_for_paused_time(self):
        main.start_playback([], duration=10)
        finished = Mock()
        main.schedule_song_end(10, finished)
        self.root.time = 2000
        main.pause_resume()
        self.root.time = 7000
        main.pause_resume()
        self.root.step()  # Begin note scheduler (empty MIDI).
        self.root.step()  # Original end callback, now too early.
        finished.assert_not_called()
        self.root.step()
        finished.assert_called_once_with()

    def test_time_display_and_timer_reset_on_stop(self):
        with patch.object(main, "time_label", Mock()) as label, \
                patch.object(main, "progress_bar", Mock(winfo_width=lambda: 200)) as bar:
            main.start_playback([], duration=120)
            self.root.step()
            timer = main.time_update_id
            self.root.pending[timer] = (30000, self.root.pending[timer][1])
            self.root.step()
            label.config.assert_called_with(text="0:30 / 2:00  ·  1:30 Left")
            bar.coords.assert_called_with("played", 0, 0, 50, 4)
            main.stop()
            label.config.assert_called_with(text="0:00 / 0:00  ·  0:00 Left")
            self.assertFalse(self.root.pending)
