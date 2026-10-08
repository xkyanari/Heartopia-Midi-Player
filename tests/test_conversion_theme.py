"""Conversion presentation checks; no audio dependencies or display required."""
from contextlib import ExitStack
import queue
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import app_config as config
from conversion_ui import ConversionUI, ConvertDialog
import ui_theme
from themes import DEFAULT_THEME, THEMES


class ConversionThemeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        ui_theme.set_theme(DEFAULT_THEME)
        # Destroy first so the dialog unsubscribes before restoring the theme.
        self.addCleanup(lambda: ui_theme.set_theme(DEFAULT_THEME))
        self.addCleanup(self.root.destroy)
        self.service = Mock(events=queue.Queue())
        self.owner = ConversionUI(self.root, Mock(), Mock(), self.service)
        self.owner.ready = True
        self.owner.folder = "C:/audio"
        self.owner.settings = {"checkpoint_path": "C:/model.pth"}

    def open(self):
        self.owner.open()
        return self.owner.dialog

    def buttons(self, dialog):
        return {button.cget("text"): button for button, _ in dialog._buttons}

    def test_buttons_keep_commands_and_theme_colours(self):
        commands = {"folder": "change_folder", "refresh": "refresh", "browse": "browse",
                    "model": "choose_model", "download": "redownload",
                    "convert": "convert", "cancel": "cancel"}
        with ExitStack() as patches:
            callbacks = {key: patches.enter_context(patch.object(ConvertDialog, name))
                         for key, name in commands.items()}
            dialog = self.open()
            callbacks["refresh"].reset_mock()  # Initial folder scan.
            buttons = self.buttons(dialog)
            self.assertEqual(len(dialog.controls), 6)
            theme = ui_theme.current()
            for key, callback in callbacks.items():
                button = buttons[config.CONVERSION_BUTTONS[key]]
                self.assertEqual(button.cget("relief"), tk.FLAT)
                self.assertEqual(button.cget("bg"), theme.ACCENT_COLOR if key == "convert"
                                 else theme.BUTTON_COLOR)
                self.assertEqual(button.cget("fg"), theme.ACCENT_TEXT_COLOR if key == "convert"
                                 else theme.BUTTON_TEXT_COLOR)
                button.invoke()
                callback.assert_called_once_with()
            self.assertNotIn(buttons[config.CONVERSION_BUTTONS["cancel"]], dialog.controls)

    def test_theme_switch_keeps_selection_scan_and_running_progress(self):
        dialog = self.open()
        row = {"path": "C:/audio/piano.wav", "name": "piano.wav", "size": 100,
               "modified": 0, "midi": False}
        dialog.handle({"type": "scan", "token": dialog.scan_token, "rows": [row]})
        dialog.tree.selection_set("0")
        dialog.select()
        dialog.convert()
        dialog.dispatched = True
        dialog.handle({"type": "download", "bytes": 50, "total": 100})
        snapshot = (dialog.scan_token, dialog.task_token, dialog.started, dialog.stage,
                    dialog.info.get(), dialog.model.get(), dialog.rows.copy())
        tree, progress = dialog.tree, dialog.progress
        commands = [button.cget("command") for button, _ in dialog._buttons]
        scans = self.service.scan.call_count
        style = ttk.Style(self.root)
        original_theme = style.theme_use()
        unrelated = style.lookup("TProgressbar", "background")
        for name, theme in THEMES.items():
            ui_theme.set_theme(name)
            self.assertEqual(dialog.window.cget("bg"), theme.BACKGROUND_COLOR)
            for widget, colours in dialog._colours:
                for option, role in colours.items():
                    self.assertEqual(widget.cget(option), getattr(theme, role))
            for button, accent in dialog._buttons:
                self.assertEqual(button.cget("bg"), theme.ACCENT_COLOR if accent else theme.BUTTON_COLOR)
                self.assertEqual(str(button.cget("state")), tk.DISABLED if button in dialog.controls else tk.NORMAL)
            for name, option, expected, state in (
                ("Conversion.Treeview", "background", theme.PANEL_COLOR, ()),
                ("Conversion.Treeview", "background", theme.SELECTION_COLOR, ("selected",)),
                ("Conversion.Treeview.Heading", "background", theme.BUTTON_COLOR, ()),
                ("Conversion.Horizontal.TProgressbar", "background", theme.ACCENT_COLOR, ()),
                ("Conversion.Horizontal.TProgressbar", "troughcolor", theme.SEPARATOR_COLOR, ()),
                ("Conversion.Vertical.TScrollbar", "background", theme.BUTTON_COLOR, ()),
                ("Conversion.Vertical.TScrollbar", "troughcolor", theme.PANEL_COLOR, ()),
            ):
                self.assertEqual(style.lookup(name, option, state), expected)
            self.assertEqual((dialog.scan_token, dialog.task_token, dialog.started, dialog.stage,
                              dialog.info.get(), dialog.model.get(), dialog.rows), snapshot)
            self.assertEqual(dialog.source.get(), row["path"])
            self.assertEqual(dialog.folder.get(), "C:/audio")
            self.assertEqual(dialog.tree.selection(), ("0",))
            self.assertIs(dialog.tree, tree)
            self.assertIs(dialog.progress, progress)
            self.assertEqual(str(progress["mode"]), "determinate")
            self.assertEqual(progress["value"], 50)
            self.assertEqual(progress["maximum"], 100)
            self.assertEqual([button.cget("command") for button, _ in dialog._buttons], commands)
            self.assertEqual(self.service.scan.call_count, scans)
            self.assertEqual(style.theme_use(), original_theme)
            self.assertEqual(style.lookup("TProgressbar", "background"), unrelated)
        dialog.finish()
        self.assertTrue(all(str(button.cget("state")) == tk.NORMAL for button in dialog.controls))

    def test_hover_uses_new_theme_and_respects_busy_state(self):
        dialog = self.open()
        self.root.deiconify()
        self.root.update()
        ui_theme.set_theme("Paper Sage")
        theme = ui_theme.current()
        for button, accent in dialog._buttons:
            base = theme.ACCENT_COLOR if accent else theme.BUTTON_COLOR
            hover = theme.ACCENT_HOVER_COLOR if accent else theme.HOVER_COLOR
            button.event_generate("<Enter>")
            self.assertEqual(button.cget("bg"), hover)
            button.event_generate("<Leave>")
            self.assertEqual(button.cget("bg"), base)
            button.configure(state=tk.DISABLED)
            button.event_generate("<Enter>")
            self.assertEqual(button.cget("bg"), base)

    def test_close_unsubscribes_including_parent_destruction(self):
        subscribers = len(ui_theme._subscribers)
        dialog = self.open()
        self.assertEqual(len(ui_theme._subscribers), subscribers + 1)
        dialog.close()
        self.assertEqual(len(ui_theme._subscribers), subscribers)
        dialog = self.open()
        dialog.window.destroy()
        self.assertEqual(len(ui_theme._subscribers), subscribers)
        ui_theme.set_theme("Paper Sage")  # No callback into destroyed widgets.

    def test_minimum_size_keeps_controls_and_table_visible(self):
        dialog = self.open()
        self.root.deiconify()
        dialog.window.geometry("650x540")
        dialog.folder.set("C:/" + "long audio folder/" * 30)
        dialog.model.set("C:/" + "long model folder/" * 30 + "piano.pth")
        for name in THEMES:
            ui_theme.set_theme(name)
            self.root.update()
            for widget in [dialog.tree, dialog.scroll, dialog.progress,
                           *(button for button, _ in dialog._buttons)]:
                x = widget.winfo_rootx() - dialog.window.winfo_rootx()
                y = widget.winfo_rooty() - dialog.window.winfo_rooty()
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + widget.winfo_width(), dialog.window.winfo_width())
                self.assertLessEqual(y + widget.winfo_height(), dialog.window.winfo_height())
            self.assertGreaterEqual(dialog.tree.winfo_height(), 70)
