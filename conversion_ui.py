"""Tk-only presentation; all filesystem/model work is delegated to the service."""
from datetime import datetime
from pathlib import Path
import queue
import sys
import time
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import app_config as config
import ui_theme
from conversion_service import ConversionService, model_destination


class ConversionUI:
    def __init__(self, root, on_converted, set_status, service=None):
        self.root, self.on_converted, self.set_status = root, on_converted, set_status
        self.service = service or ConversionService()
        self.settings, self.missing = {}, []
        self.folder = ""
        self.ready = self.busy = self.closing = False
        self.button = self.dialog = None
        self._pending_settings = {}
        self.folder_callbacks = []
        self.root.after(config.CONVERSION_UI_POLL_MS, self._poll)

    def attach_button(self, button):
        self.button = button
        self.button.config(state=tk.DISABLED if not self.ready or self.busy or self.closing else tk.NORMAL)

    def open(self):
        if not self.ready or self.closing:
            return
        if self.missing:
            message = (config.CONVERSION_STANDARD_BUILD_TEXT if getattr(sys, "frozen", False)
                       else f"Install conversion dependencies first:\n{config.CONVERSION_INSTALL_COMMAND}")
            messagebox.showerror(config.CONVERSION_TITLE, message, parent=self.root)
            return
        if self.dialog is not None:
            self.dialog.window.lift()
        else:
            self.dialog = ConvertDialog(self)

    def save(self, updates):
        self.settings.update(updates)
        if not self.ready:
            self._pending_settings.update(updates)
        self.service.save(updates)

    def set_audio_folder(self, folder):
        """Shared folder setter for Settings and the conversion dialog."""
        self.folder = folder
        self.save({"audio_input_folder": folder})
        self._notify_folder()
        if self.dialog is not None:
            self.dialog.folder.set(folder)
            self.dialog.refresh()

    def _notify_folder(self):
        for callback in tuple(self.folder_callbacks):
            callback(self.folder)

    def set_busy(self, busy):
        self.busy = busy
        if self.button is not None:
            self.button.config(state=tk.DISABLED if busy or self.closing else tk.NORMAL)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.set_busy(True)
        self.set_status("Closing: stopping conversion and cleaning temporary files…")
        self.service.shutdown()

    def _poll(self):
        try:
            while True:
                event = self.service.events.get_nowait()
                kind = event["type"]
                if kind == "initialized":
                    self.settings = {**event["settings"], **self._pending_settings}
                    self.folder = self._pending_settings.get("audio_input_folder", event["folder"])
                    self._pending_settings.clear()
                    self._notify_folder()
                    self.missing = event["missing"]
                    self.ready = True
                    if self.button is not None and not self.closing:
                        self.button.config(state=tk.NORMAL)
                    if event.get("warning"):
                        self.set_status(event["warning"])
                elif kind == "model_ready":
                    self.settings["checkpoint_path"] = event["path"]
                elif kind == "success":
                    self.on_converted(event["path"])
                    if event.get("warning"):
                        self.set_status(event["warning"])
                elif kind == "warning":
                    self.set_status(event["message"])
                if self.dialog is not None and not self.closing:
                    self.dialog.handle(event)
        except queue.Empty:
            pass
        if self.closing and self.service.closed.is_set():
            self.root.destroy()
            return
        if self.dialog is not None and not self.closing:
            self.dialog.tick()
        self.root.after(config.CONVERSION_UI_POLL_MS, self._poll)


class ConvertDialog:
    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root, bg=ui_theme.current().BACKGROUND_COLOR)
        self.window.title(config.CONVERSION_TITLE)
        self.window.geometry(config.CONVERSION_DIALOG_SIZE)
        self.window.minsize(650, 540)
        self.window.transient(owner.root)  # Deliberately no grab: playback remains usable.
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.folder = tk.StringVar(value=owner.folder)
        self.source = tk.StringVar()
        self.info = tk.StringVar(value="Choose an audio file, then click Convert.")
        self.model = tk.StringVar(value=owner.settings.get("checkpoint_path") or str(model_destination()))
        self.rows = {}
        self.scan_token = self.task_token = None
        self.dispatched = self.close_when_done = False
        self.started = self.transcribe_started = self.estimate = None
        self.stage = ""
        self.controls = []
        self._colours = []
        self._buttons = []
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(2, weight=1)

        header = self.frame(self.window, "BACKGROUND_COLOR")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self.label("CONVERT AUDIO", parent=header, background="BACKGROUND_COLOR",
                   font=config.TITLE_FONT).pack(side=tk.LEFT)
        self.label("PIANO TO MIDI", parent=header, background="BACKGROUND_COLOR",
                   foreground="ACCENT_COLOR").pack(side=tk.RIGHT)

        info_card = self.card(1)
        self.label(config.CONVERSION_SCOPE_TEXT, parent=info_card).pack(fill=tk.X, padx=10, pady=(8, 0))
        self.label(config.CONVERSION_CPU_TEXT, parent=info_card,
                   foreground="MUTED_TEXT_COLOR").pack(fill=tk.X, padx=10)
        self.path_field(info_card, self.folder).pack(fill=tk.X, padx=10, pady=(4, 0))
        toolbar = self.frame(info_card)
        toolbar.pack(fill=tk.X, padx=10, pady=(4, 8))
        for key, command in (("folder", self.change_folder), ("refresh", self.refresh), ("browse", self.browse)):
            self.button(toolbar, config.CONVERSION_BUTTONS[key], command).pack(side=tk.LEFT, padx=(0, 6))
        files_card = self.card(2)
        self.label("AUDIO FILES", parent=files_card, foreground="MUTED_TEXT_COLOR").pack(
            fill=tk.X, padx=10, pady=6)
        table = self.frame(files_card)
        table.pack(fill=tk.BOTH, expand=True, padx=10)
        self.tree = ttk.Treeview(table, columns=("name", "size", "modified", "midi"),
                                 show="headings", selectmode="browse", style="Conversion.Treeview", height=5)
        for key, title, width in (("name", "File name", 220), ("size", "Size", 80),
                                  ("modified", "Modified", 145), ("midi", "MIDI", 95)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=50, stretch=key == "name")
        self.scroll = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview,
                                    style="Conversion.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.path_field(files_card, self.source).pack(fill=tk.X, padx=10, pady=(4, 6))

        model_card = self.card(3)
        self.label("PIANO MODEL", parent=model_card, foreground="MUTED_TEXT_COLOR").pack(
            fill=tk.X, padx=10, pady=(6, 0))
        self.path_field(model_card, self.model).pack(fill=tk.X, padx=10, pady=(2, 0))
        models = self.frame(model_card)
        models.pack(fill=tk.X, padx=10, pady=(4, 6))
        self.button(models, config.CONVERSION_BUTTONS["model"], self.choose_model).pack(side=tk.LEFT, padx=(0, 6))
        self.button(models, config.CONVERSION_BUTTONS["download"], self.redownload).pack(side=tk.LEFT)

        status_card = self.card(4)
        self.progress = ttk.Progressbar(status_card, mode="indeterminate",
                                        style="Conversion.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.label(variable=self.info, parent=status_card).pack(fill=tk.X, padx=10, pady=(0, 4))
        actions = self.frame(status_card)
        actions.pack(fill=tk.X, padx=10, pady=(0, 8))
        self.button(actions, config.CONVERSION_BUTTONS["convert"], self.convert, accent=True).pack(side=tk.LEFT)
        self.button(actions, config.CONVERSION_BUTTONS["cancel"], self.cancel, busy_enabled=True).pack(side=tk.RIGHT)
        self.apply_theme(ui_theme.current())
        self.unsubscribe = ui_theme.subscribe(self.apply_theme)
        self.window.bind("<Destroy>", self._destroyed, add="+")
        self.refresh()

    def frame(self, parent, background="CARD_COLOR", **options):
        widget = tk.Frame(parent, bg=getattr(ui_theme.current(), background), **options)
        self._colours.append((widget, {"bg": background}))
        return widget

    def card(self, row):
        card = self.frame(self.window)
        card.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.frame(card, "ACCENT_COLOR", height=2).pack(fill=tk.X)
        return card

    def label(self, text=None, variable=None, *, parent=None, background="CARD_COLOR",
              foreground="TEXT_COLOR", font=config.UI_FONT):
        widget = tk.Label(parent or self.window, text=text, textvariable=variable,
                          bg=getattr(ui_theme.current(), background),
                          fg=getattr(ui_theme.current(), foreground), font=font,
                          anchor="w", justify=tk.LEFT, wraplength=600)
        widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(1, event.width)))
        self._colours.append((widget, {"bg": background, "fg": foreground}))
        return widget

    def path_field(self, parent, variable):
        # Selectable, single-line paths cannot grow the cards beyond the window.
        widget = tk.Entry(parent, textvariable=variable, state="readonly", relief=tk.FLAT,
                          bd=0, highlightthickness=0, font=config.UI_FONT)
        self._colours.append((widget, {"readonlybackground": "CARD_COLOR",
                                      "fg": "MUTED_TEXT_COLOR",
                                      "selectbackground": "SELECTION_COLOR",
                                      "selectforeground": "TEXT_COLOR"}))
        return widget

    def button(self, parent, text, command, busy_enabled=False, *, accent=False):
        button = ui_theme.button(parent, text, command, accent=accent)
        self._buttons.append((button, accent))
        if not busy_enabled:
            self.controls.append(button)
        return button

    def _destroyed(self, event):
        if event.widget is self.window:
            self.unsubscribe()

    def apply_theme(self, theme):
        self.window.configure(bg=theme.BACKGROUND_COLOR)
        for widget, colours in self._colours:
            widget.configure(**{option: getattr(theme, role) for option, role in colours.items()})
        for button, accent in self._buttons:
            ui_theme.style_button(button, accent=accent)
        style = ttk.Style(self.window)
        # Windows' native tree field ignores fieldbackground. Clone only these
        # elements from clam so the conversion table is dark without retheming
        # the existing app's combobox or playback controls.
        if "Conversion.Treeview.field" not in style.element_names():
            style.element_create("Conversion.Treeview.field", "from", "clam", "Treeview.field")
            style.element_create("Conversion.Treeheading.cell", "from", "clam", "Treeheading.cell")
        style.layout("Conversion.Treeview", [("Conversion.Treeview.field", {
            "sticky": "nswe", "children": [("Treeview.padding", {
                "sticky": "nswe", "children": [("Treeview.treearea", {"sticky": "nswe"})]})]})])
        style.layout("Conversion.Treeview.Heading", [("Conversion.Treeheading.cell", {
            "sticky": "nswe", "children": [("Treeheading.padding", {
                "sticky": "nswe", "children": [("Treeheading.text", {"sticky": "we"})]})]})])
        style.configure("Conversion.Treeview", background=theme.PANEL_COLOR,
                        fieldbackground=theme.PANEL_COLOR, foreground=theme.TEXT_COLOR,
                        bordercolor=theme.SEPARATOR_COLOR, font=config.UI_FONT, rowheight=24)
        style.configure("Conversion.Treeview.Heading", background=theme.BUTTON_COLOR,
                        foreground=theme.BUTTON_TEXT_COLOR, font=config.UI_FONT,
                        bordercolor=theme.SEPARATOR_COLOR, lightcolor=theme.BUTTON_COLOR,
                        darkcolor=theme.BUTTON_COLOR)
        style.map("Conversion.Treeview", background=[("selected", theme.SELECTION_COLOR)],
                  foreground=[("selected", theme.TEXT_COLOR)])
        style.map("Conversion.Treeview.Heading", background=[("active", theme.HOVER_COLOR)])
        for name, source in (("Conversion.Progressbar.trough", "Progressbar.trough"),
                             ("Conversion.Progressbar.pbar", "Progressbar.pbar"),
                             ("Conversion.Scrollbar.trough", "Scrollbar.trough"),
                             ("Conversion.Scrollbar.thumb", "Scrollbar.thumb"),
                             ("Conversion.Scrollbar.uparrow", "Scrollbar.uparrow"),
                             ("Conversion.Scrollbar.downarrow", "Scrollbar.downarrow")):
            if name not in style.element_names():
                style.element_create(name, "from", "clam", source)
        style.layout("Conversion.Horizontal.TProgressbar", [("Conversion.Progressbar.trough", {
            "sticky": "nswe", "children": [("Conversion.Progressbar.pbar", {"side": "left", "sticky": "ns"})]})])
        style.configure("Conversion.Horizontal.TProgressbar", troughcolor=theme.SEPARATOR_COLOR,
                        background=theme.ACCENT_COLOR, bordercolor=theme.SEPARATOR_COLOR,
                        lightcolor=theme.ACCENT_COLOR, darkcolor=theme.ACCENT_COLOR)
        style.layout("Conversion.Vertical.TScrollbar", [("Conversion.Scrollbar.trough", {
            "sticky": "ns", "children": [
                ("Conversion.Scrollbar.uparrow", {"side": "top", "sticky": ""}),
                ("Conversion.Scrollbar.downarrow", {"side": "bottom", "sticky": ""}),
                ("Conversion.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Conversion.Vertical.TScrollbar", troughcolor=theme.PANEL_COLOR,
                        background=theme.BUTTON_COLOR, arrowcolor=theme.BUTTON_TEXT_COLOR,
                        bordercolor=theme.SEPARATOR_COLOR, lightcolor=theme.BUTTON_COLOR,
                        darkcolor=theme.BUTTON_COLOR)
        style.map("Conversion.Vertical.TScrollbar", background=[("active", theme.HOVER_COLOR),
                                                               ("pressed", theme.ACCENT_COLOR)])

    def refresh(self):
        self.scan_token = uuid.uuid4().hex
        self.owner.service.scan(self.folder.get(), self.scan_token,
                                fallback_dir=self.owner.settings.get("converted_output_dir"))

    def change_folder(self):
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.folder.get() or None)
        if folder:
            self.owner.set_audio_folder(folder)

    def browse(self):
        initial = self.folder.get() or self.owner.settings.get("last_audio_dir") or None
        path = filedialog.askopenfilename(parent=self.window, initialdir=initial,
                filetypes=[("Audio files", " ".join("*" + ext for ext in config.SUPPORTED_AUDIO_EXTS)), ("All files", "*.*")])
        if path:
            self.tree.selection_remove(*self.tree.selection())
            self.source.set(path)
            self.owner.save({"last_audio_dir": str(Path(path).parent)})

    def select(self, event=None):
        if self.owner.busy:
            return
        selected = self.tree.selection()
        if selected and selected[0] in self.rows:
            path = self.rows[selected[0]]["path"]
            self.source.set(path)
            self.owner.save({"last_audio_dir": str(Path(path).parent)})

    def choose_model(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=[("Piano checkpoint", "*.pth"), ("All files", "*.*")])
        if path:
            self.begin({"operation": "model", "checkpoint_path": path})

    def approve_download(self):
        return messagebox.askyesno("Download piano model", f"Download approximately {config.CHECKPOINT_EXPECTED_BYTES / 1_000_000:.0f} MB to:\n"
                f"{model_destination().parent}\n\nAudio stays on this computer. App-downloaded models may be replaced; user-provided files will be kept.", parent=self.window)

    def redownload(self):
        if self.approve_download():
            self.begin({"operation": "model", "allow_download": True, "force_download": True})

    def convert(self):
        if not self.source.get():
            self.info.set("Choose an audio file first.")
            return
        self.begin({"source": self.source.get(), "checkpoint_path": self.owner.settings.get("checkpoint_path"),
                    "fallback_dir": self.owner.settings.get("converted_output_dir"), "operation": "convert"})

    def begin(self, request):
        if self.owner.busy or self.owner.closing:
            return
        self.task_token = uuid.uuid4().hex
        self.dispatched = False
        self.started = time.monotonic()
        self.transcribe_started = self.estimate = None
        self.stage = "Checking selected files…"
        self.owner.set_busy(True)
        for control in self.controls:
            control.config(state=tk.DISABLED)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.owner.service.preflight({**request, "_token": self.task_token})

    def finish(self):
        self.owner.set_busy(False)
        self.started = self.transcribe_started = None
        self.progress.stop()
        for control in self.controls:
            control.config(state=tk.NORMAL)
        if self.close_when_done:
            self.close()

    def cancel(self):
        if not self.owner.busy:
            self.close()
            return
        self.owner.service.cancel()
        self.info.set("Cancelling…")
        self.stage = "Cancelling…"
        if not self.dispatched:
            self.task_token = uuid.uuid4().hex
            self.finish()
            self.info.set("Conversion cancelled.")

    def close(self):
        if self.owner.busy:
            self.close_when_done = True
            self.cancel()
        else:
            self.owner.dialog = None
            self.unsubscribe()
            self.window.destroy()

    def tick(self):
        if self.started is None:
            return
        elapsed = time.monotonic() - (self.transcribe_started or self.started)
        estimate = f" · Estimate ~{self.estimate:.0f} s (not a deadline)" if self.estimate else ""
        self.info.set(f"{self.stage} · Elapsed {elapsed:.0f} s{estimate}")

    def handle(self, event):
        kind = event["type"]
        if kind == "scan" and event["token"] == self.scan_token:
            self.tree.delete(*self.tree.get_children())
            self.rows = {}
            for index, row in enumerate(event["rows"]):
                key = str(index)
                self.rows[key] = row
                self.tree.insert("", tk.END, iid=key, values=(row["name"], f"{row['size'] / 1024:.1f} KB",
                        datetime.fromtimestamp(row["modified"]).strftime("%Y-%m-%d %H:%M"), "MIDI exists" if row["midi"] else ""))
            if not self.owner.busy:
                self.info.set("Choose a file and click Convert." if self.rows else config.CONVERSION_EMPTY_TEXT)
        elif kind == "scan_error" and event["token"] == self.scan_token:
            self.tree.delete(*self.tree.get_children())
            self.rows = {}
            self.info.set(f"Cannot read audio folder: {event['message']}. Use Change folder…")
        elif kind == "preflight":
            request = dict(event["request"])
            if request.pop("_token") != self.task_token or not self.owner.busy:
                return
            if not event["model_exists"] and request.get("operation") == "convert" and not request.get("allow_download"):
                if not self.approve_download():
                    self.finish()
                    self.info.set("Download cancelled. Choose model file… to use an offline checkpoint.")
                    return
                if self.owner.closing or not self.owner.busy:
                    return
                request.update(allow_download=True, force_download=False, checkpoint_path=None)
            self.dispatched = True
            self.owner.service.start(request)
        elif kind == "preflight_error":
            if event.get("token") != self.task_token or not self.owner.busy:
                return
            self.finish()
            self.info.set(event["message"])
            messagebox.showerror(config.CONVERSION_TITLE, event["message"], parent=self.window)
        elif kind == "stage":
            self.stage = config.CONVERSION_STAGES.get(event["stage"], event["stage"])
            self.owner.set_status(self.stage)
            if event["stage"] != "downloading":
                self.progress.stop()
                self.progress.configure(mode="indeterminate")
                self.progress.start()
            if event["stage"] == "transcribing":
                self.transcribe_started = event["started"]
                self.estimate = event["estimate"]
        elif kind == "download":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=event["total"], value=event["bytes"])
            self.stage = f"Downloading model: {event['bytes'] / 1_000_000:.1f} / {event['total'] / 1_000_000:.1f} MB"
        elif kind == "model_ready":
            self.model.set(event["path"])
        elif kind in ("success", "model_success"):
            self.info.set(f"Saved: {event['path']}" if kind == "success" else "Model validated and ready.")
            self.started = None
            if kind == "success":
                self.refresh()
        elif kind in ("error", "cancelled", "warning"):
            if kind != "warning":
                self.started = None
            self.info.set(event["message"])
            self.owner.set_status(event["message"])
            if kind == "error":
                messagebox.showerror(config.CONVERSION_TITLE,
                        event["message"] + "\n\nFor model problems, use Re-download model or Choose model file…", parent=self.window)
        elif kind == "finished":
            self.finish()
