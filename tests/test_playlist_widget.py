"""Exercise the playlist adapter without creating a Tk window."""
from contextlib import ExitStack
import unittest
from unittest.mock import Mock, patch

import main
import playlist_widget
from playlist_widget import PlaylistView
from themes import DEFAULT_THEME, resolve


class PlaylistViewTests(unittest.TestCase):
    def setUp(self):
        self.view = PlaylistView.__new__(PlaylistView)
        self.view.get_children = Mock(return_value=("first", "second", "third"))

    def test_columns_and_style_use_actual_font_measurements(self):
        font = Mock()
        font.measure.side_effect = lambda text: {"--:--": 50, "999:59": 70}[text]
        font.metrics.return_value = 25
        theme = resolve(DEFAULT_THEME)
        with ExitStack() as stack:
            make_font = stack.enter_context(patch.object(playlist_widget.tkfont, "Font", return_value=font))
            style = stack.enter_context(patch.object(playlist_widget.ttk, "Style")).return_value
            initialize = stack.enter_context(patch.object(playlist_widget.ttk.Treeview, "__init__", return_value=None))
            column = stack.enter_context(patch.object(playlist_widget.ttk.Treeview, "column"))
            parent = Mock()
            self.view.__init__(parent, theme)
        make_font.assert_called_once_with(root=parent, font=playlist_widget.PLAYLIST_FONT)
        initialize.assert_called_once_with(parent, columns=("title", "length"), show="",
                                           selectmode="browse", height=5, style="Playlist.Treeview")
        column.assert_any_call("title", anchor="w", width=180, minwidth=0, stretch=True)
        column.assert_any_call("length", anchor="e", width=82, minwidth=82, stretch=False)
        self.assertEqual(style.configure.call_args.kwargs["rowheight"], 29)
        self.assertEqual(style.configure.call_args.kwargs["fieldbackground"], theme.PANEL_COLOR)
        self.assertEqual(style.configure.call_args.kwargs["foreground"], theme.TEXT_COLOR)
        self.assertEqual(style.map.call_args.kwargs["background"], [("selected", theme.SELECTION_COLOR)])

    def test_insert_keeps_separate_cells_and_expands_for_long_durations(self):
        self.view._font = Mock()
        self.view._font.measure.return_value = 95
        self.view.column = Mock(return_value=82)
        with patch.object(playlist_widget.ttk.Treeview, "insert", return_value="new") as insert:
            self.assertEqual(self.view.insert("end", ("A very long title", "1000:00")), "new")
        insert.assert_called_once_with("", "end", values=("A very long title", "1000:00"))
        self.view.column.assert_any_call("length", width=107, minwidth=107)

    def test_selection_activation_and_visibility_use_current_row_indexes(self):
        self.view.selection = Mock(return_value=("second",))
        self.view.selection_set = Mock()
        self.view.selection_remove = Mock()
        self.view.focus = Mock()
        self.assertEqual(self.view.curselection(), (1,))
        self.view.select_set(2)
        self.view.selection_set.assert_called_once_with("third")
        self.view.select_clear(0, "end")
        self.view.selection_remove.assert_called_once_with("first", "second", "third")
        self.view.activate(2)
        self.view.focus.assert_called_once_with("third")
        with patch.object(playlist_widget.ttk.Treeview, "see") as see:
            self.view.see(2)
        see.assert_called_once_with("third")

    def test_deletion_does_not_leave_stale_row_indexes(self):
        with patch.object(playlist_widget.ttk.Treeview, "delete") as delete:
            self.view.delete(1)
        delete.assert_called_once_with("second")
        self.view.get_children.return_value = ("first", "third")
        self.view.selection = Mock(return_value=("third",))
        self.assertEqual(self.view.curselection(), (1,))
        self.assertEqual(self.view.size(), 2)
        self.view.get_children.return_value = ()
        self.view.selection.return_value = ()
        self.assertEqual(self.view.curselection(), ())
        self.assertEqual(self.view.size(), 0)

    def test_shared_row_values_cover_zero_and_unknown_durations(self):
        for duration, length in ((0, "0:00"), (125, "2:05"), (None, "--:--")):
            self.assertEqual(main.playlist_row_values({"name": "Song", "duration": duration}),
                             ("Song", length))
        self.assertEqual(main.playlist_row_values({"name": "Song"}), ("Song", "--:--"))
