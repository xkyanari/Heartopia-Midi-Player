"""Player presentation helpers; importing this module creates no widgets."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

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


class MarqueeLabel(tk.Canvas):
    """A single-line title that pauses and scrolls between its two ends."""

    STEP = 2
    INTERVAL = 35
    PAUSE = 1500

    def __init__(self, parent, *, text, font, bg, fg):
        self._font = tkfont.Font(root=parent, font=font)
        # Match a Label's vertical padding without requesting the text's width.
        super().__init__(parent, width=1, height=self._font.metrics("linespace") + 4,
                         bg=bg, highlightthickness=0, bd=0)
        self._text = text
        self._item = self.create_text(2, 2, text=text, font=self._font,
                                      fill=fg, anchor="nw")
        self._offset = 0
        self._direction = 1
        self._limit = 0
        self._timer = None
        self._destroyed = False
        self.bind("<Configure>", self._restart)
        # Also fires when a parent or Tcl destroys the widget.
        self.bind("<Destroy>", self._on_destroy)

    def configure(self, cnf=None, **options):
        if isinstance(cnf, dict):
            options = {**cnf, **options}
            cnf = None
        changed = "text" in options
        text = options.pop("text", self._text)
        result = super().configure(cnf, **options) if cnf is not None or options or not changed else None
        if changed and text != self._text:
            self._text = text
            self.itemconfigure(self._item, text=text)
            self._restart()
        return result

    config = configure

    def cget(self, key):
        return self._text if key == "text" else super().cget(key)

    def _cancel_timer(self):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _restart(self, event=None):
        if self._destroyed:
            return
        self._cancel_timer()
        self._offset = 0
        self._direction = 1
        self.coords(self._item, 2, 2)
        width = event.width if event is not None else self.winfo_width()
        self._limit = max(0, self._font.measure(self._text) - max(0, width - 4))
        if width > 4 and self._limit and self._text != "Nothing Playing":
            self._timer = self.after(self.PAUSE, self._step)

    def _step(self):
        self._timer = None
        if self._destroyed:
            return
        self._offset = max(0, min(self._limit, self._offset + self.STEP * self._direction))
        self.coords(self._item, 2 - self._offset, 2)
        at_end = self._offset in (0, self._limit)
        if at_end:
            self._direction *= -1
        self._timer = self.after(self.PAUSE if at_end else self.INTERVAL, self._step)

    def _on_destroy(self, event):
        if event.widget is self:
            self._destroyed = True
            self._cancel_timer()


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
    widget = tk.Button(
        parent, text=text, command=command, relief=tk.FLAT, bd=0,
        highlightthickness=1, padx=5, pady=5, cursor="hand2",
        font=options.pop("font", config.UI_FONT), **options,
    )
    style_button(widget, accent=accent)
    return widget


def style_button(widget, *, accent=False):
    """Refresh colours and hover bindings without changing command or state."""
    background = current().ACCENT_COLOR if accent else current().BUTTON_COLOR
    hover = current().ACCENT_HOVER_COLOR if accent else current().HOVER_COLOR
    foreground = current().ACCENT_TEXT_COLOR if accent else current().BUTTON_TEXT_COLOR
    widget.configure(
        bg=background, fg=foreground,
        activebackground=hover, activeforeground=foreground,
        disabledforeground=current().FOOTER_TEXT_COLOR, highlightbackground=background,
        highlightcolor=current().ACCENT_COLOR,
    )

    def set_background(color):
        if str(widget.cget("state")) != tk.DISABLED:
            widget.configure(bg=color)

    widget.bind("<Enter>", lambda event: set_background(hover))
    widget.bind("<Leave>", lambda event: set_background(background))


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
