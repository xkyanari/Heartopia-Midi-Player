"""Check theme interactions with real Tk widgets when a display is available."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock

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
