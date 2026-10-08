"""Player presentation helpers; importing this module creates no widgets."""
import tkinter as tk
from tkinter import ttk

import app_config as config
from themes import DEFAULT_THEME, resolve

_active = resolve(DEFAULT_THEME)
_subscribers = []


def current():
    """Return the active palette and layout data (also usable by other windows)."""
    return _active


def subscribe(callback):
    """Callback receives the new theme; return an unsubscribe function."""
    _subscribers.append(callback)

    def unsubscribe():
        if callback in _subscribers:
            _subscribers.remove(callback)

    return unsubscribe


def set_theme(name):
    global _active
    theme = resolve(name)
    if theme is _active:
        return
    _active = theme
    for callback in tuple(_subscribers):
        callback(theme)


class MidiVisualizer(tk.Canvas):
    """Light pitch-group bars for held MIDI keys, without an animation timer."""

    def __init__(self, parent):
        super().__init__(parent, width=72, height=72, bg=current().PANEL_COLOR,
                         highlightthickness=0, bd=0)
        self.bars = [self.create_rectangle(2 + i * 6, 64, 6 + i * 6, 68,
                                           fill=current().SEPARATOR_COLOR, outline="")
                     for i in range(12)]

    def show_keys(self, keys, key_order):
        # Different instruments use different pitch ranges and keyboard maps.
        # Playback keys are scan-code dictionaries, so compare by equality.
        ordered = []
        for key in key_order:
            if key not in ordered:
                ordered.append(key)
        levels = [0] * len(self.bars)
        for index, key in enumerate(ordered):
            if key in keys:
                levels[index * len(self.bars) // len(ordered)] += 1
        for index, (bar, level) in enumerate(zip(self.bars, levels)):
            height = min(60, 20 + level * 13) if level else 4
            self.coords(bar, 2 + index * 6, 68 - height, 6 + index * 6, 68)
            self.itemconfigure(bar, fill=current().ACCENT_COLOR if level
                               else current().SEPARATOR_COLOR)


def button(parent, text, command, *, accent=False, **options):
    """Build a flat button with disabled-aware hover feedback."""
    background = current().ACCENT_COLOR if accent else current().BUTTON_COLOR
    hover = current().ACCENT_HOVER_COLOR if accent else current().HOVER_COLOR
    foreground = current().ACCENT_TEXT_COLOR if accent else current().BUTTON_TEXT_COLOR
    widget = tk.Button(
        parent, text=text, command=command, bg=background, fg=foreground,
        activebackground=hover, activeforeground=foreground,
        disabledforeground=current().FOOTER_TEXT_COLOR, relief=tk.FLAT, bd=0,
        highlightthickness=1, highlightbackground=background,
        highlightcolor=current().ACCENT_COLOR, padx=5, pady=5, cursor="hand2",
        font=options.pop("font", config.UI_FONT), **options,
    )

    def set_background(color):
        if str(widget.cget("state")) != tk.DISABLED:
            widget.configure(bg=color)

    widget.bind("<Enter>", lambda event: set_background(hover))
    widget.bind("<Leave>", lambda event: set_background(background))
    return widget


def style_combobox(root):
    """Use clam elements only for the player selector, including on Windows."""
    style = ttk.Style(root)
    for element in ("field", "downarrow", "padding", "textarea"):
        name = f"Player.Combobox.{element}"
        if name not in style.element_names():
            style.element_create(name, "from", "clam", f"Combobox.{element}")
    style.layout("Player.TCombobox", [("Player.Combobox.field", {
        "sticky": "nswe", "children": [
            ("Player.Combobox.downarrow", {"side": "right", "sticky": "ns"}),
            ("Player.Combobox.padding", {"sticky": "nswe", "children": [
                ("Player.Combobox.textarea", {"sticky": "nswe"}),
            ]}),
        ],
    })])
    style.configure(
        "Player.TCombobox", fieldbackground=current().PANEL_COLOR,
        background=current().BUTTON_COLOR, foreground=current().TEXT_COLOR,
        arrowcolor=current().BUTTON_TEXT_COLOR, bordercolor=current().SEPARATOR_COLOR,
        lightcolor=current().PANEL_COLOR, darkcolor=current().PANEL_COLOR,
        padding=3, font=config.UI_FONT,
    )
    style.map(
        "Player.TCombobox",
        fieldbackground=[("readonly", current().PANEL_COLOR)],
        foreground=[("readonly", current().TEXT_COLOR)],
        background=[("active", current().HOVER_COLOR)],
        selectbackground=[("readonly", current().PANEL_COLOR)],
        selectforeground=[("readonly", current().TEXT_COLOR)],
    )
    for option, value in {
        "background": current().PANEL_COLOR, "foreground": current().TEXT_COLOR,
        "selectBackground": current().SELECTION_COLOR,
        "selectForeground": current().TEXT_COLOR, "font": config.UI_FONT,
    }.items():
        root.option_add(f"*TCombobox*Listbox*{option}", value)
