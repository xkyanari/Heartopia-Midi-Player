"""Check theme interactions with real Tk widgets when a display is available."""
import tkinter as tk
from tkinter import ttk
import unittest
from contextlib import ExitStack
from pathlib import Path
import re
from unittest.mock import Mock, patch

import app_config as config
import ui_theme
from themes import DEFAULT_THEME
from ui_theme import MidiVisualizer, button, style_combobox


class VersionTests(unittest.TestCase):
    def test_ui_version_matches_windows_metadata(self):
        metadata = (Path(__file__).resolve().parents[1] / "version_info.txt").read_text(encoding="utf-8")
        version = config.APP_VERSION.removeprefix("v")
        for field in ("FileVersion", "ProductVersion"):
            self.assertEqual(re.search(rf"StringStruct\('{field}', '([^']+)'\)", metadata)[1], version)
        numbers = tuple(int(part) for part in version.split(".")) + (0,)
        for field in ("filevers", "prodvers"):
            recorded = re.search(rf"{field}=\(([^)]+)\)", metadata)[1]
            self.assertEqual(tuple(int(part) for part in recorded.split(",")), numbers)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        ui_theme.set_theme(DEFAULT_THEME)
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)

    def test_visualizer_follows_held_notes_and_resets(self):
        widget = MidiVisualizer(self.root)
        low, middle, high = ({"scan_code": code} for code in (44, 45, 46))
        widget.show_keys([low, high], [low, middle, high])
        for index in (0, 8):
            self.assertEqual(widget.itemcget(widget.bars[index], "fill"), config.ACCENT_COLOR)
            self.assertLess(widget.coords(widget.bars[index])[1], 64)
        widget.show_keys([high], [low, middle, high])
        self.assertEqual(widget.itemcget(widget.bars[0], "fill"), config.SEPARATOR_COLOR)
        self.assertEqual(widget.itemcget(widget.bars[8], "fill"), config.ACCENT_COLOR)
        widget.show_keys([], [])
        for bar in widget.bars:
            self.assertEqual(widget.coords(bar)[1], 64)
            self.assertEqual(widget.itemcget(bar, "fill"), config.SEPARATOR_COLOR)

    def test_hover_and_commands_respect_disabled_state(self):
        for accent, base, hover in (
            (False, config.BUTTON_COLOR, config.HOVER_COLOR),
            (True, config.ACCENT_COLOR, config.ACCENT_HOVER_COLOR),
        ):
            with self.subTest(accent=accent):
                command = Mock()
                widget = button(self.root, "Play", command, accent=accent)
                self.assertEqual(widget.cget("foreground"), config.ACCENT_TEXT_COLOR
                                 if accent else config.BUTTON_TEXT_COLOR)
                widget.pack()
                self.root.update()
                widget.event_generate("<Leave>")
                self.assertEqual(widget.cget("background"), base)
                widget.event_generate("<Enter>")
                self.assertEqual(widget.cget("background"), hover)
                widget.event_generate("<Leave>")
                self.assertEqual(widget.cget("background"), base)
                widget.invoke()
                command.assert_called_once_with()
                # ConversionUI controls state; hover must not change its styling.
                widget.configure(state=tk.DISABLED)
                for event in ("<Enter>", "<Leave>"):
                    widget.event_generate(event)
                    self.assertEqual(widget.cget("background"), base)
                    self.assertEqual(str(widget.cget("state")), tk.DISABLED)
                widget.invoke()
                command.assert_called_once_with()
                widget.configure(state=tk.NORMAL)
                widget.event_generate("<Enter>")
                self.assertEqual(widget.cget("background"), hover)
                widget.destroy()

    def test_combobox_and_dropdown_use_dark_palette_without_switching_theme(self):
        style = ttk.Style(self.root)
        original_theme = style.theme_use()
        style_combobox(self.root)
        style_combobox(self.root)  # Safe to configure another player window.
        self.assertEqual(style.theme_use(), original_theme)
        self.assertEqual(style.lookup("Player.TCombobox", "fieldbackground", ("readonly",)),
                         config.PANEL_COLOR)
        widget = ttk.Combobox(self.root, style="Player.TCombobox",
                              state="readonly", values=("piano", "violin"))
        popup = self.root.tk.call("ttk::combobox::PopdownWindow", str(widget))
        listbox = f"{popup}.f.l"
        self.assertEqual(self.root.tk.call(listbox, "cget", "-background"), config.PANEL_COLOR)
        self.assertEqual(self.root.tk.call(listbox, "cget", "-foreground"), config.TEXT_COLOR)
        self.assertEqual(self.root.tk.call(listbox, "cget", "-selectbackground"),
                         config.SELECTION_COLOR)

    def test_compact_player_fits_and_keeps_transport_commands(self):
        import main

        # Build the actual window without starting services or reading user state.
        commands = ("skip_previous", "play_selected", "play_playlist",
                    "pause_resume", "stop", "skip_next", "toggle_loop",
                    "play_musical_chairs", "load_midi", "delete_selected")
        with ExitStack() as patches:
            patches.enter_context(patch("main.tk.Tk", return_value=self.root))
            patches.enter_context(patch.object(self.root, "mainloop"))
            patches.enter_context(patch("conversion_ui.ConversionUI"))
            for name in ("load_layout", "load_saved_playlist", "load_player_settings", "scan_midi_folder", "KeyboardPlayer"):
                patches.enter_context(patch.object(main, name))
            for name in ("playlist_box", "status_label", "now_playing_label", "player", "playback_clock"):
                patches.enter_context(patch.object(main, name, None))
            patches.enter_context(patch.object(main, "playlist", []))
            callbacks = {name: patches.enter_context(patch.object(main, name))
                         for name in commands}
            main.main()
            self.assertEqual(self.root.title(), f"{config.APP_TITLE} {config.APP_VERSION}")
            self.assertEqual(main.status_label.cget("background"), config.PANEL_COLOR)
            main.set_status("Playing: example.mid")
            self.assertEqual(main.status_label.cget("text"), "Playing: example.mid")
            main.set_now_playing("example.mid")
            main.set_status("Paused")
            self.assertEqual(main.now_playing_label.cget("text"), "example.mid")
            # Long names stay on one line and cannot push controls off-screen.
            main.set_now_playing("very long song name " * 20 + ".mid")

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(self.root))
            self.assertFalse(any(isinstance(widget, tk.Label) and
                                widget.cget("text") == config.APP_VERSION for widget in widgets))
            buttons = {widget.cget("text"): widget for widget in widgets
                       if isinstance(widget, tk.Button)}
            labels = {**config.PLAYBACK_BUTTONS, **config.FILE_BUTTONS}
            for name, callback in callbacks.items():
                key = {"skip_previous": "previous", "skip_next": "next",
                       "toggle_loop": "loop", "play_musical_chairs": "musical_chairs"}.get(name, name)
                buttons[labels[key]].invoke()
                callback.assert_called_once_with()
            main.conversion_ui.attach_button.assert_called_once_with(
                buttons[config.FILE_BUTTONS["convert_audio"]])

            # Check every visible control stays inside the compact window and
            # the expanding playlist remains usable at each supported size.
            for size in ("430x440", config.WINDOW_SIZE, "640x600"):
                self.root.geometry(size)
                self.root.update()
                for widget in widgets:
                    with self.subTest(size=size, widget=str(widget)):
                        x = widget.winfo_rootx() - self.root.winfo_rootx()
                        y = widget.winfo_rooty() - self.root.winfo_rooty()
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width())
                        self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height())
                self.assertGreaterEqual(main.playlist_box.winfo_height(), 60)
