"""Single, modeless player settings window using the shared active palette."""
import tkinter as tk
from tkinter import filedialog

import app_config as config
import ui_theme
from themes import THEMES


class SettingsWindow:
    def __init__(self, root, apply_theme, get_midi_folder, set_midi_folder, conversion):
        self.apply_theme = apply_theme
        self.get_midi_folder, self.set_midi_folder = get_midi_folder, set_midi_folder
        self.conversion = conversion
        self.window = tk.Toplevel(root)
        self.window.title("Settings")
        self.window.geometry("500x540")
        self.window.minsize(460, 520)
        self.window.transient(root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.look = tk.StringVar(value=ui_theme.current().name)
        self.midi = tk.StringVar(value=get_midi_folder())
        self.audio = tk.StringVar(value=conversion.folder)
        self.folder_callback = self.audio.set
        conversion.folder_callbacks.append(self.folder_callback)
        self.unsubscribe = ui_theme.subscribe(self.build)
        self.build(ui_theme.current())

    def build(self, theme):
        for widget in self.window.winfo_children():
            widget.destroy()
        self.window.configure(bg=theme.BACKGROUND_COLOR)
        self.look.set(theme.name)
        tk.Label(self.window, text="Look", bg=theme.BACKGROUND_COLOR,
                 fg=theme.TEXT_COLOR, font=config.TITLE_FONT, anchor="w").pack(fill=tk.X, padx=16, pady=(16, 6))
        for name in THEMES:
            tk.Radiobutton(self.window, text=name.replace("(current)", "(Current)"), variable=self.look, value=name,
                           command=lambda name=name: self.apply_theme(name),
                           bg=theme.BACKGROUND_COLOR, fg=theme.TEXT_COLOR,
                           selectcolor=theme.PANEL_COLOR, activebackground=theme.HOVER_COLOR,
                           activeforeground=theme.TEXT_COLOR, font=config.UI_FONT,
                           anchor="w").pack(fill=tk.X, padx=16, pady=2)
        self.folder_row("MIDI Folder", self.midi, self.choose_midi, self.clear_midi, theme)
        self.folder_row("Audio Folder for Conversion", self.audio, self.choose_audio, None, theme)

    def folder_row(self, title, variable, choose, clear, theme):
        frame = tk.Frame(self.window, bg=theme.PANEL_COLOR)
        frame.pack(fill=tk.X, padx=16, pady=(16, 0))
        tk.Label(frame, text=title, bg=theme.PANEL_COLOR, fg=theme.TEXT_COLOR,
                 font=config.UI_FONT, anchor="w").pack(fill=tk.X, padx=10, pady=(8, 4))
        # A readonly entry keeps even very long paths within the window and selectable.
        tk.Entry(frame, textvariable=variable, state="readonly", relief=tk.FLAT,
                 readonlybackground=theme.PANEL_COLOR, fg=theme.MUTED_TEXT_COLOR,
                 font=config.UI_FONT).pack(fill=tk.X, padx=10, pady=(0, 6))
        actions = tk.Frame(frame, bg=theme.PANEL_COLOR)
        actions.pack(fill=tk.X, padx=10, pady=(0, 8))
        ui_theme.button(actions, "Choose…", choose).pack(side=tk.LEFT, padx=(0, 6))
        if clear is not None:
            ui_theme.button(actions, "Clear", clear).pack(side=tk.LEFT)

    def choose_midi(self):
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.midi.get() or None)
        if folder:
            self.set_midi_folder(folder)
            self.midi.set(self.get_midi_folder())

    def clear_midi(self):
        self.set_midi_folder("")
        self.midi.set("")

    def choose_audio(self):
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.audio.get() or None)
        if folder:
            self.conversion.set_audio_folder(folder)

    def close(self):
        self.unsubscribe()
        self.conversion.folder_callbacks.remove(self.folder_callback)
        self.window.destroy()
