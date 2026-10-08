"""Settings logic needs no display; actual layout checks skip without Tk."""
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import queue
import re
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import app_config as config
import app_storage
import main
import ui_theme
from conversion_ui import ConversionUI
from playback_timing import PlaybackClock
from themes import COLOR_ROLES, DEFAULT_THEME, THEMES, playback_labels


class SettingsLogicTests(unittest.TestCase):
    def setUp(self):
        ui_theme.set_theme(DEFAULT_THEME)
        self.addCleanup(ui_theme.set_theme, DEFAULT_THEME)

    def test_instrument_display_loads_old_keys_and_saves_keys_without_display(self):
        variable = tk.StringVar(master=tk.Tcl())
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            path = Path(directory) / "layout.json"
            stack.enter_context(patch.object(app_storage, "LAYOUT_FILE", str(path)))
            stack.enter_context(patch.object(app_storage, "state_file_lock", side_effect=nullcontext))
            stack.enter_context(patch.object(main, "instrument_var", variable, create=True))
            stack.enter_context(patch.object(main, "current_layout", "22"))
            stack.enter_context(patch.object(main, "current_instrument", "piano"))
            player = stack.enter_context(patch.object(main, "player", Mock()))
            status = stack.enter_context(patch.object(main, "set_status"))
            for key in main.INSTRUMENTS:
                with self.subTest(instrument=key):
                    path.write_text(json.dumps({"layout": "22", "instrument": key}), encoding="utf-8")
                    main.load_layout()
                    self.assertEqual(variable.get(), key.title())
                    main.on_instrument_change()
                    self.assertEqual(main.current_instrument, key)
                    self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["instrument"], key)
                    player.set_layout_and_instrument.assert_called_with("22", key)
                    status.assert_called_with(f"Instrument: {key.title()}")
            variable.set("Wooden Bass")
            main.on_instrument_change()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["instrument"], "wooden bass")

    def test_six_complete_palettes_and_play_labels(self):
        self.assertEqual(len(THEMES), 6)
        for name, theme in THEMES.items():
            with self.subTest(theme=name):
                for role in COLOR_ROLES:
                    self.assertRegex(getattr(theme, role), r"^#[0-9a-fA-F]{6}$")
                self.assertEqual(set(theme.sections), {"song", "instrument", "transport", "modes", "playlist"})
                self.assertEqual(set(playback_labels(theme)), set(config.PLAYBACK_BUTTONS))
                self.assertEqual(playback_labels(theme)["play_selected"], "▶ Play")
        self.assertEqual(THEMES["Studio Amber"].sections[0], "instrument")
        self.assertEqual(THEMES["Graphite Blue"].sections[0], "playlist")
        self.assertEqual(THEMES["Soft Plum"].sections[1], "transport")

    def test_saved_theme_loaded_and_invalid_theme_falls_back(self):
        for value, expected in (("Paper Sage", "Paper Sage"), ("removed", DEFAULT_THEME),
                                (None, DEFAULT_THEME), (["bad"], DEFAULT_THEME)):
            with patch.object(main, "load_settings", return_value={"theme": value, "midi_input_folder": "MIDI"}), \
                    patch.object(main, "midi_folder", ""):
                main.load_player_settings()
                self.assertEqual(ui_theme.current().name, expected)
                self.assertEqual(main.midi_folder, "MIDI")
        with patch.object(main, "load_settings", side_effect=PermissionError()), \
                patch.object(main, "midi_folder", ""):
            main.load_player_settings()
            self.assertEqual(ui_theme.current().name, DEFAULT_THEME)

    def test_palettes_match_the_draft_css(self):
        css = (Path(__file__).resolve().parents[1] / "docs/ui-drafts/index.html").read_text(encoding="utf-8")
        roles = {"bg": "BACKGROUND_COLOR", "panel": "PANEL_COLOR", "button": "BUTTON_COLOR",
                 "text": "TEXT_COLOR", "muted": "MUTED_TEXT_COLOR", "line": "SEPARATOR_COLOR",
                 "accent": "ACCENT_COLOR", "on-accent": "ACCENT_TEXT_COLOR", "selected": "SELECTION_COLOR"}
        for selector, name in (("midnight", "Midnight Teal"), ("paper", "Paper Sage"),
                               ("studio", "Studio Amber"), ("plum", "Soft Plum"), ("graphite", "Graphite Blue")):
            block = re.search(r"\." + selector + r"\s*\{([^}]+)\}", css)[1]
            variables = dict(re.findall(r"--([\w-]+):\s*(#[\da-fA-F]+)", block))
            for variable, role in roles.items():
                self.assertEqual(getattr(THEMES[name], role), variables[variable])

    def test_switch_rebuilds_and_saves_without_stopping(self):
        songs = [{"path": "one.mid"}]
        clock = PlaybackClock(30)
        with patch.object(main, "playlist", songs), patch.object(main, "playback_clock", clock), \
                patch.object(main, "playback_active", True), patch.object(main, "stop") as stop, \
                patch.object(main, "cancel_playback") as cancel, \
                patch.object(main, "build_player_ui") as rebuild, \
                patch.object(main, "conversion_ui", Mock()) as conversion:
            main.apply_theme("Soft Plum")
            rebuild.assert_called_once_with()
            conversion.save.assert_called_once_with({"theme": "Soft Plum"})
            self.assertIs(main.playlist, songs)
            self.assertIs(main.playback_clock, clock)
            self.assertTrue(main.playback_active)
            stop.assert_not_called()
            cancel.assert_not_called()

    def test_subscription_and_unsubscribe(self):
        callback = Mock()
        unsubscribe = ui_theme.subscribe(callback)
        try:
            ui_theme.set_theme("Midnight Teal")
            callback.assert_called_once_with(THEMES["Midnight Teal"])
            unsubscribe()
            ui_theme.set_theme("Paper Sage")
            self.assertEqual(callback.call_count, 1)
        finally:
            unsubscribe()

    def test_startup_loads_playlist_before_folder_scan(self):
        events = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(main.tk, "Tk", return_value=Mock()))
            stack.enter_context(patch("conversion_ui.ConversionUI"))
            stack.enter_context(patch.object(main, "KeyboardPlayer"))
            stack.enter_context(patch.object(main, "instrument_var", Mock(), create=True))
            for name in ("load_player_settings", "build_player_ui", "load_layout", "load_saved_playlist", "scan_midi_folder"):
                stack.enter_context(patch.object(main, name, side_effect=lambda name=name: events.append(name)))
            stack.enter_context(patch.object(main, "root", None, create=True))
            stack.enter_context(patch.object(main, "player", None))
            stack.enter_context(patch.object(main, "conversion_ui", None, create=True))
            main.main()
        self.assertLess(events.index("load_saved_playlist"), events.index("scan_midi_folder"))

    def test_folder_scan_new_midi_only_sorted_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            folder = Path(directory)
            for name in ("z.mid", "a.MIDI", "existing.mid", "other.mp3"):
                (folder / name).touch()
            (folder / "nested").mkdir()
            (folder / "nested" / "hidden.mid").touch()
            songs = [{"path": str(folder / "nested" / ".." / "existing.mid")}]
            stack.enter_context(patch.object(main, "midi_folder", directory))
            stack.enter_context(patch.object(main, "playlist", songs))
            append = stack.enter_context(patch.object(main, "append_playlist_song",
                side_effect=lambda path: songs.append({"path": path})))
            save = stack.enter_context(patch.object(main, "save_playlist"))
            stack.enter_context(patch.object(main, "set_status"))
            main.scan_midi_folder()
            self.assertEqual([Path(call.args[0]).name for call in append.call_args_list], ["a.MIDI", "z.mid"])
            save.assert_called_once_with()
            main.scan_midi_folder()
            self.assertEqual(append.call_count, 2)
            self.assertEqual(save.call_count, 1)

    def test_folder_error_and_load_dialog_directory(self):
        with patch.object(main, "midi_folder", "missing"), \
                patch.object(main.os, "scandir", side_effect=FileNotFoundError("missing")), \
                patch.object(main, "set_status") as status, \
                patch.object(main, "append_playlist_song") as append:
            main.scan_midi_folder()
            self.assertIn("Cannot Read MIDI Folder", status.call_args.args[0])
            append.assert_not_called()
            with patch.object(main.filedialog, "askopenfilenames", return_value=()) as picker:
                main.load_midi()
                self.assertEqual(picker.call_args.kwargs["initialdir"], "missing")

    def test_midi_folder_persisted_and_clear_does_not_delete_playlist(self):
        with patch.object(main, "midi_folder", ""), patch.object(main, "playlist", [{"path": "one.mid"}]), \
                patch.object(main, "scan_midi_folder") as scan, patch.object(main, "conversion_ui", Mock()) as conversion:
            main.set_midi_folder("new")
            self.assertEqual(main.midi_folder, "new")
            scan.assert_called_once_with()
            conversion.save.assert_called_with({"midi_input_folder": "new"})
            main.set_midi_folder("")
            self.assertEqual(len(main.playlist), 1)

    def test_audio_folder_sync_and_late_initialization(self):
        service = Mock(events=queue.Queue())
        service.closed.is_set.return_value = False
        owner = ConversionUI(Mock(), Mock(), Mock(), service=service)
        dialog = Mock()
        owner.dialog = dialog
        callback = Mock()
        owner.folder_callbacks.append(callback)
        owner.set_audio_folder("chosen")
        self.assertEqual(owner.folder, "chosen")
        self.assertEqual(owner.settings["audio_input_folder"], "chosen")
        service.save.assert_called_with({"audio_input_folder": "chosen"})
        dialog.folder.set.assert_called_with("chosen")
        dialog.refresh.assert_called_once_with()
        callback.assert_called_with("chosen")
        service.events.put({"type": "initialized", "settings": {"instrument": "piano"},
                            "folder": "old", "missing": []})
        owner._poll()
        self.assertEqual(owner.folder, "chosen")
        self.assertEqual(owner.settings["audio_input_folder"], "chosen")


class PlayerThemeWidgetTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        ui_theme.set_theme(DEFAULT_THEME)
        self.addCleanup(ui_theme.set_theme, DEFAULT_THEME)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in {"root": self.root, "playlist_box": None, "status_label": None,
                            "now_playing_label": None, "time_label": None, "progress_bar": None,
                            "visualizer": None, "player": Mock(note_map={"C": "a"}),
                            "playlist": [{"name": "song.mid", "path": "song.mid", "duration": 90}],
                            "current_index": 0, "current_instrument": "violin", "loop_mode": "all",
                            "playback_active": True, "is_paused": True, "pressed_keys": ["a"],
                            "playback_after_ids": ["scheduled-note"], "time_update_id": "timer",
                            "playback_clock": PlaybackClock(90), "instrument_var": None,
                            "settings_window": None, "conversion_ui": Mock()}.items():
            stack.enter_context(patch.object(main, name, value, create=True))

    def test_all_themes_preserve_state_commands_and_fit(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        with ExitStack() as stack:
            commands = {key: stack.enter_context(patch.object(main, name)) for key, name in {
                "previous": "skip_previous", "play_selected": "play_selected", "next": "skip_next",
                "pause_resume": "pause_resume", "stop": "stop", "play_playlist": "play_playlist"}.items()}
            main.build_player_ui()
            main.playlist_box.select_set(0)
            main.set_status("Paused")
            song = "Gary Valenciano - Pasko Na, Sinta Ko.mid " * 4
            main.set_now_playing(song)
            original_clock = main.playback_clock
            for name in THEMES:
                with self.subTest(theme=name):
                    old_title = main.now_playing_label
                    old_timer = old_title._timer
                    main.apply_theme(name)
                    if main.now_playing_label is not old_title:
                        self.assertIsNone(old_title._timer)
                        if old_timer is not None:
                            self.assertNotIn(old_timer, self.root.tk.call("after", "info"))
                    self.assertEqual(main.playlist_box.size(), 1)
                    self.assertEqual(main.playlist_box.curselection(), (0,))
                    self.assertEqual(main.instrument_var.get(), "Violin")
                    self.assertEqual(main.loop_mode, "all")
                    self.assertEqual(main.status_label.cget("text"), "Paused")
                    self.assertEqual(main.now_playing_label.cget("text"), song)
                    self.assertIs(main.playback_clock, original_clock)
                    self.assertEqual(main.time_update_id, "timer")
                    self.assertEqual(main.playback_after_ids, ["scheduled-note"])
                    self.assertTrue(main.playback_active)
                    self.assertTrue(main.is_paused)
                    for key, callback in commands.items():
                        callback.reset_mock()
                        main.transport_buttons[key].invoke()
                        callback.assert_called_once_with()
                    widgets = list(descendants(self.root))
                    instrument_box = next(widget for widget in widgets if isinstance(widget, ttk.Combobox))
                    self.assertEqual(tuple(instrument_box.cget("values")),
                                     tuple(key.title() for key in main.INSTRUMENTS))
                    self.assertFalse(any(isinstance(widget, tk.Label) and
                                         widget.cget("text") == config.APP_VERSION for widget in widgets))
                    for size in (config.WINDOW_SIZE, "%dx%d" % self.root.minsize(), "720x800"):
                        self.root.geometry(size)
                        self.root.update()
                        self.assertIsNotNone(main.now_playing_label._timer)
                        self.assertGreaterEqual(self.root.winfo_height(), self.root.winfo_reqheight())
                        for widget in widgets:
                            x = widget.winfo_rootx() - self.root.winfo_rootx()
                            y = widget.winfo_rooty() - self.root.winfo_rooty()
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width())
                            self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height())
                        self.assertGreaterEqual(main.playlist_box.winfo_height(), 60)

    def test_settings_singleton_and_live_palette(self):
        main.build_player_ui()
        owner = main.conversion_ui
        owner.folder = "audio"
        owner.folder_callbacks = []
        main.open_settings()
        window = main.settings_window
        try:
            main.open_settings()
            self.assertIs(main.settings_window, window)
            self.assertEqual(len([w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]), 1)
            main.apply_theme("Paper Sage")
            self.assertTrue(window.window.winfo_exists())
            self.assertEqual(window.window.cget("background"), THEMES["Paper Sage"].BACKGROUND_COLOR)
        finally:
            window.close()
