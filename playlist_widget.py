"""Two-column playlist with the index-based operations used by the player."""
import tkinter as tk
from tkinter import font as tkfont, ttk

from app_config import PLAYLIST_FONT


class PlaylistView(ttk.Treeview):
    def __init__(self, parent, theme):
        self._font = tkfont.Font(root=parent, font=PLAYLIST_FONT)
        style = ttk.Style(parent)
        # Only the tree area is needed: no native border or column headings.
        style.layout("Playlist.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Playlist.Treeview", background=theme.PANEL_COLOR,
            fieldbackground=theme.PANEL_COLOR, foreground=theme.TEXT_COLOR,
            font=PLAYLIST_FONT, rowheight=self._font.metrics("linespace") + 4,
            borderwidth=0,
        )
        style.map("Playlist.Treeview",
                  background=[("selected", theme.SELECTION_COLOR)],
                  foreground=[("selected", theme.TEXT_COLOR)])
        super().__init__(parent, columns=("title", "length"), show="",
                         selectmode="browse", height=5, style="Playlist.Treeview")
        self.column("title", anchor=tk.W, width=180, minwidth=0, stretch=True)
        width = max(self._font.measure(text) for text in ("--:--", "999:59")) + 12
        self.column("length", anchor=tk.E, width=width, minwidth=width, stretch=False)

    def _fit_length(self, values):
        # Grow for unusually long durations, keeping the width fixed on resize.
        width = self._font.measure(values[1]) + 12
        if width > self.column("length", "width"):
            self.column("length", width=width, minwidth=width)

    def insert(self, index, values):
        self._fit_length(values)
        return super().insert("", index, values=values)

    def update_row(self, index, values):
        self._fit_length(values)
        self.item(self.get_children()[index], values=values)

    def clear(self):
        super().delete(*self.get_children())

    def curselection(self):
        selected = set(self.selection())
        return tuple(index for index, item in enumerate(self.get_children()) if item in selected)

    def select_set(self, index):
        self.selection_set(self.get_children()[index])

    def select_clear(self, first, last=None):
        items = self.get_children()
        stop = len(items) if last == tk.END else (first if last is None else last) + 1
        self.selection_remove(*items[first:stop])

    def activate(self, index):
        self.focus(self.get_children()[index])

    def see(self, index):
        super().see(self.get_children()[index])

    def delete(self, index):
        super().delete(self.get_children()[index])

    def size(self):
        return len(self.get_children())
