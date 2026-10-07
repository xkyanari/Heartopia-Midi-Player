"""Player presentation helpers; importing this module creates no widgets."""
import tkinter as tk
from tkinter import ttk

import app_config as config


def button(parent, text, command, *, accent=False, **options):
    """Build a flat button with disabled-aware hover feedback."""
    background = config.ACCENT_COLOR if accent else config.BUTTON_COLOR
    hover = config.ACCENT_HOVER_COLOR if accent else config.HOVER_COLOR
    foreground = config.ACCENT_TEXT_COLOR if accent else config.BUTTON_TEXT_COLOR
    widget = tk.Button(
        parent, text=text, command=command, bg=background, fg=foreground,
        activebackground=hover, activeforeground=foreground,
        disabledforeground=config.FOOTER_TEXT_COLOR, relief=tk.FLAT, bd=0,
        highlightthickness=1, highlightbackground=background,
        highlightcolor=config.ACCENT_COLOR, padx=5, pady=5, cursor="hand2",
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
        "Player.TCombobox", fieldbackground=config.PANEL_COLOR,
        background=config.BUTTON_COLOR, foreground=config.TEXT_COLOR,
        arrowcolor=config.BUTTON_TEXT_COLOR, bordercolor=config.SEPARATOR_COLOR,
        lightcolor=config.PANEL_COLOR, darkcolor=config.PANEL_COLOR,
        padding=3, font=config.UI_FONT,
    )
    style.map(
        "Player.TCombobox",
        fieldbackground=[("readonly", config.PANEL_COLOR)],
        foreground=[("readonly", config.TEXT_COLOR)],
        background=[("active", config.HOVER_COLOR)],
        selectbackground=[("readonly", config.PANEL_COLOR)],
        selectforeground=[("readonly", config.TEXT_COLOR)],
    )
    for option, value in {
        "background": config.PANEL_COLOR, "foreground": config.TEXT_COLOR,
        "selectBackground": config.SELECTION_COLOR,
        "selectForeground": config.TEXT_COLOR, "font": config.UI_FONT,
    }.items():
        root.option_add(f"*TCombobox*Listbox*{option}", value)
