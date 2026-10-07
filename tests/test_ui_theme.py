"""Check theme interactions with real Tk widgets when a display is available."""
import tkinter as tk
from tkinter import ttk
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import app_config as config
from ui_theme import button, style_combobox


class ThemeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)

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
            for name in ("load_layout", "load_saved_playlist", "KeyboardPlayer"):
                patches.enter_context(patch.object(main, name))
            callbacks = {name: patches.enter_context(patch.object(main, name))
                         for name in commands}
            main.main()
            self.assertEqual(main.status_label.cget("background"), config.PANEL_COLOR)
            main.set_status("Playing: example.mid")
            self.assertEqual(main.status_label.cget("text"), "Playing: example.mid")

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(self.root))
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
            # the expanding playlist remains usable at both supported sizes.
            for size in (config.WINDOW_SIZE, "640x600"):
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
