import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import multiprocessing
import os
import random
from ui_theme import button, style_combobox

from app_storage import (
    load_layout_settings,
    load_playlist_paths,
    save_layout_settings,
    save_playlist_paths,
)
from midi_parser import parse_midi
from keyboard_player import KeyboardPlayer, INSTRUMENTS
from keyboard_layout import press_key, release_key
from window_focus import get_foreground_window_title, switch_to_heartopia, switch_to_window
from app_config import (
    ACCENT_COLOR,
    APP_CREDIT,
    APP_TITLE,
    APP_VERSION,
    BACKGROUND_COLOR,
    CARD_COLOR,
    DEFAULT_INSTRUMENT,
    DEFAULT_LAYOUT,
    DEFAULT_STATUS,
    DISPLAY_FONT,
    FILE_BUTTONS,
    FOCUS_CHECK_INTERVAL_MS,
    FOOTER_TEXT_COLOR,
    HEARTOPIA_WINDOW_TITLES,
    KEY_HOLD_MS,
    MUSICAL_CHAIRS_MAX_SECONDS,
    MUSICAL_CHAIRS_MIN_SECONDS,
    MUTED_TEXT_COLOR,
    PANEL_COLOR,
    PLAYLIST_FONT,
    PAUSE_POLL_INTERVAL_MS,
    PLAYBACK_BUTTONS,
    PLAYBACK_SPEED,
    PLAYBACK_START_DELAY_MS,
    SELECTION_COLOR,
    SEPARATOR_COLOR,
    SETTINGS_SAVE_WARNING,
    SONG_END_BUFFER_SECONDS,
    TEXT_COLOR,
    TITLE_FONT,
    TRANSPORT_FONT,
    UI_FONT,
    WINDOW_SIZE,
)

# App state
player = None
playlist = []
current_index = None
current_layout = DEFAULT_LAYOUT
current_instrument = DEFAULT_INSTRUMENT
loop_mode = "none"  # "none", "one", or "all"
is_paused = False
focus_check_id = None

def switch_to_player():
    """Switch focus to the MIDI player window."""
    switch_to_window(root.winfo_id())

def check_heartopia_focus():
    """Check if Heartopia is still the active window, pause if not."""
    global focus_check_id
    if playback_active and not is_paused:
        title = get_foreground_window_title()
        if HEARTOPIA_WINDOW_TITLES[0] not in title:
            pause_resume()
    # Continue checking if still active
    if playback_active:
        focus_check_id = root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)
    else:
        focus_check_id = None

# Helpers
def set_status(text):
    status_label.config(text=text)

# Placeholder for visual highlight (visual keyboard removed)
def highlight_keys(keys):
    return

# Playback control (no threads): scheduled via tkinter `after`
playback_active = False
playback_after_ids = []
pressed_keys = []
playback_gen = 0
musical_chairs_run_id = 0
def cancel_playback():
    global playback_active, playback_after_ids, pressed_keys, focus_check_id
    playback_active = False
    global playback_gen
    playback_gen += 1
    for aid in list(playback_after_ids):
        try:
            root.after_cancel(aid)
        except Exception:
            pass
    playback_after_ids.clear()
    if focus_check_id:
        try:
            root.after_cancel(focus_check_id)
        except Exception:
            pass
        focus_check_id = None
    for k in list(pressed_keys):
        try:
            release_key(k)
        except Exception:
            pass
    pressed_keys.clear()
    try:
        highlight_keys([])
    except Exception:
        pass

def is_playback_fully_stopped():
    """Ignore stale IDs and playback_active after natural completion."""
    if is_paused or pressed_keys:
        return False
    pending = set(root.tk.splitlist(root.tk.call("after", "info")))
    return not pending.intersection(playback_after_ids)


def add_converted_midi(path):
    global current_index
    idle = is_playback_fully_stopped()
    playlist.append({"name": os.path.basename(path), "path": path})
    playlist_box.insert(tk.END, os.path.basename(path))
    if idle:
        current_index = len(playlist) - 1
        playlist_box.select_clear(0, tk.END)
        playlist_box.select_set(current_index)
        playlist_box.activate(current_index)
        playlist_box.see(current_index)
    try:
        save_playlist()
    except OSError as exc:
        set_status(f"MIDI saved: {path}. Playlist could not be saved: {exc}")
        return
    set_status(f"{'Converted' if idle else 'Added to playlist'}: {path}")


def close_app():
    stop()
    conversion_ui.shutdown()

def start_playback(events, speed=PLAYBACK_SPEED, on_key_press=None):
    """Play `events` (list of (delay, notes)) using tkinter `after` scheduling.
    This avoids background threads and can be cancelled with `cancel_playback()`.
    """
    global playback_active, playback_after_ids, pressed_keys
    cancel_playback()
    playback_active = True
    playback_after_ids = []
    pressed_keys = []
    global playback_gen
    playback_gen += 1
    my_gen = playback_gen

    def release_keys(keys):
        for k in keys:
            try:
                release_key(k)
            except Exception:
                pass
            try:
                pressed_keys.remove(k)
            except ValueError:
                pass
        if on_key_press:
            on_key_press([])

    def calculate_sustain_time(note):
        """Calculate sustain time for a single note based on MIDI duration.

        Violin and cello should hold keys as long as the MIDI note lasts,
        capped at the game's maximum sustain value.
        """
        if current_instrument == "violin":
            max_sustain = 4500
        elif current_instrument == "cello":
            max_sustain = 5000
        else:
            return KEY_HOLD_MS

        if not note or len(note) < 3:
            return KEY_HOLD_MS

        duration_ms = note[2]
        if duration_ms <= 0:
            return KEY_HOLD_MS

        return min(max_sustain, duration_ms)

    def play_note_index(i):
        if not playback_active or i >= len(events):
            return
        delay, notes = events[i]

        def do_notes():
            if not playback_active:
                return

            # If paused, do not progress; keep checking until resumed.
            if is_paused:
                rid = root.after(PAUSE_POLL_INTERVAL_MS, do_notes)
                playback_after_ids.append(rid)
                return

            active_press_keys = []
            for note in notes:
                # Note is (name, octave, duration_ms)
                key = player.get_playable_key((note[0], note[1]))
                if not key:
                    continue

                active_press_keys.append(key)
                try:
                    press_key(key)
                    pressed_keys.append(key)
                except Exception:
                    pass

                sustain_ms = calculate_sustain_time(note)
                rid = root.after(sustain_ms, lambda k=key: release_keys([k]))
                playback_after_ids.append(rid)

            if on_key_press:
                on_key_press(active_press_keys)
            # schedule next note
            if my_gen == playback_gen and playback_active:
                play_note_index(i+1)

        rid = root.after(int(delay * 1000 / speed), do_notes)
        playback_after_ids.append(rid)

    rid = root.after(PLAYBACK_START_DELAY_MS, lambda: play_note_index(0))
    playback_after_ids.append(rid)

def create_random_excerpt(events, duration):
    """Return a random 20-25 second excerpt as relative-delay events."""
    excerpt_duration = min(
        duration,
        random.uniform(MUSICAL_CHAIRS_MIN_SECONDS, MUSICAL_CHAIRS_MAX_SECONDS),
    )
    start_time = 0.0
    if duration > excerpt_duration:
        start_time = random.uniform(0.0, duration - excerpt_duration)
    end_time = start_time + excerpt_duration

    excerpt_events = []
    absolute_time = 0.0
    previous_time = start_time
    for delay, notes in events:
        absolute_time += delay
        if start_time <= absolute_time <= end_time:
            excerpt_events.append((absolute_time - previous_time, notes))
            previous_time = absolute_time

    return excerpt_events, excerpt_duration

def on_playlist_select(event):
    global current_index
    sel = playlist_box.curselection()
    if sel:
        current_index = sel[0]

def update_status_wrap(event=None):
    # Toplevel bindings also receive child Configure events.
    status_label.config(wraplength=max(120, status_label.winfo_width()))

# Playback controls
def stop():
    global is_paused, musical_chairs_run_id
    musical_chairs_run_id += 1
    cancel_playback()
    if player:
        player.stop()
    is_paused = False
    set_status("Stopped")

def load_midi():
    files = filedialog.askopenfilenames(filetypes=[("MIDI Files", "*.mid *.midi")])
    if not files:
        return
    for path in files:
        playlist.append({"name": os.path.basename(path), "path": path})
        playlist_box.insert(tk.END, os.path.basename(path))
    set_status(f"{len(playlist)} files loaded")
    save_playlist()

def delete_selected():
    global current_index
    sel = playlist_box.curselection()
    if not sel:
        return
    idx = sel[0]
    playlist_box.delete(idx)
    playlist.pop(idx)
    if playlist:
        current_index = min(idx, len(playlist)-1)
        playlist_box.select_set(current_index)
    else:
        current_index = None
        set_status("No files loaded")
    save_playlist()

def play_selected():
    global loop_mode
    stop()
    if current_index is None:
        messagebox.showwarning("Play", "Select a MIDI file first")
        return
    try:
        events, duration = parse_midi(playlist[current_index]["path"])
    except Exception as e:
        messagebox.showerror("MIDI Error", str(e))
        return
    set_status(f"Playing: {playlist[current_index]['name']}")
    start_playback(events, on_key_press=highlight_keys)
    if switch_to_heartopia():  # Switch to Heartopia window for key presses
        root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)
    
    # If loop one is enabled, schedule replay after song ends
    if loop_mode == "one":
        wait_time = int((duration + SONG_END_BUFFER_SECONDS) * 1000)
        aid = root.after(wait_time, lambda: play_selected())
        playback_after_ids.append(aid)

def play_playlist():
    global loop_mode
    stop()
    def play_next(idx):
        if idx >= len(playlist):
            if loop_mode == "all":
                play_next(0)  # Loop back to start
            else:
                set_status("Playlist finished")
            return
        
        playlist_box.select_clear(0, tk.END)
        playlist_box.select_set(idx)
        playlist_box.activate(idx)
        try:
            events, duration = parse_midi(playlist[idx]["path"])
        except Exception as e:
            messagebox.showerror("MIDI Error", str(e))
            play_next(idx+1)
            return
        set_status(f"Playing: {playlist[idx]['name']}")
        start_playback(events, on_key_press=highlight_keys)
        if switch_to_heartopia():  # Switch to Heartopia window for key presses
            root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)
        # Schedule next song with duration + 6 second buffer
        wait_time = int((duration + SONG_END_BUFFER_SECONDS) * 1000)
        aid = root.after(wait_time, lambda: play_next(idx+1))
        playback_after_ids.append(aid)
    play_next(current_index or 0)

def play_musical_chairs():
    """Play one bounded excerpt from one random playlist song."""
    global current_index, musical_chairs_run_id
    stop()
    musical_chairs_run_id += 1
    run_id = musical_chairs_run_id
    if not playlist:
        messagebox.showwarning("Musical Chairs", "Load at least one MIDI file first")
        return

    def play_excerpt():
        global current_index
        if run_id != musical_chairs_run_id or not playlist:
            return
        if is_paused:
            aid = root.after(PAUSE_POLL_INTERVAL_MS, play_excerpt)
            playback_after_ids.append(aid)
            return
        cancel_playback()

        current_index = random.randrange(len(playlist))
        playlist_box.select_clear(0, tk.END)
        playlist_box.select_set(current_index)
        playlist_box.activate(current_index)

        try:
            events, duration = parse_midi(playlist[current_index]["path"])
        except Exception as e:
            messagebox.showerror("MIDI Error", str(e))
            return

        excerpt_events, excerpt_duration = create_random_excerpt(events, duration)
        set_status(f"Playing: {playlist[current_index]['name']}")
        start_playback(excerpt_events, on_key_press=highlight_keys)
        if switch_to_heartopia():
            root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)

        wait_time = int(excerpt_duration * 1000) + PLAYBACK_START_DELAY_MS
        def finish_musical_chairs():
            if run_id == musical_chairs_run_id:
                cancel_playback()
                set_status("Musical Chairs finished")

        aid = root.after(wait_time, finish_musical_chairs)
        playback_after_ids.append(aid)

    play_excerpt()

def pause_resume():
    global is_paused
    if not playback_active:
        messagebox.showinfo("Pause", "No playback to pause")
        return
    is_paused = not is_paused
    if is_paused:
        set_status("Paused")
        switch_to_player()  # Switch to player window when paused
    else:
        set_status("Resumed")
        switch_to_heartopia()  # Switch back to Heartopia when resumed

def skip_next():
    global current_index
    if current_index is None:
        messagebox.showwarning("Skip", "No playlist loaded")
        return
    if len(playlist) == 0:
        return
    current_index = (current_index + 1) % len(playlist)
    playlist_box.select_clear(0, tk.END)
    playlist_box.select_set(current_index)
    playlist_box.activate(current_index)
    play_selected()

def skip_previous():
    global current_index
    if current_index is None:
        messagebox.showwarning("Skip", "No playlist loaded")
        return
    if len(playlist) == 0:
        return
    current_index = (current_index - 1) % len(playlist)
    playlist_box.select_clear(0, tk.END)
    playlist_box.select_set(current_index)
    playlist_box.activate(current_index)
    play_selected()

def toggle_loop_one():
    global loop_mode
    stop()
    if loop_mode == "one":
        loop_mode = "none"
        set_status("Loop: Off")
    else:
        loop_mode = "one"
        set_status("Loop: One Song")

def toggle_loop_all():
    global loop_mode
    stop()
    if loop_mode == "all":
        loop_mode = "none"
        set_status("Loop: Off")
    else:
        loop_mode = "all"
        set_status("Loop: All Songs")

def toggle_loop():
    global loop_mode
    stop()
    if loop_mode == "none":
        loop_mode = "one"
        set_status("Loop: One Song")
    elif loop_mode == "one":
        loop_mode = "all"
        set_status("Loop: All Songs")
    else:  # loop_mode == "all"
        loop_mode = "none"
        set_status("Loop: Off")

def on_instrument_change(event=None):
    global current_instrument, player
    current_instrument = instrument_var.get()
    if player:
        player.instrument = current_instrument
        player.set_layout_and_instrument(current_layout, current_instrument)
    set_status(f"Instrument: {current_instrument}")
    save_instrument()

# Saving songs
def save_playlist():
    save_playlist_paths([p["path"] for p in playlist])

def load_saved_playlist():
    for path in load_playlist_paths():
        playlist.append({"name": os.path.basename(path), "path": path})
        playlist_box.insert(tk.END, os.path.basename(path))
    if playlist:
        set_status(f"{len(playlist)} files loaded")

def save_layout():
    try:
        save_layout_settings(current_layout, current_instrument)
    except TimeoutError:
        set_status(SETTINGS_SAVE_WARNING)

def load_layout():
    global current_layout, current_instrument
    current_layout, current_instrument = load_layout_settings()
    instrument_var.set(current_instrument)

def save_instrument():
    save_layout()  # Save both layout and instrument together


def main():
    global root, playlist_box, status_label, instrument_var, player, conversion_ui
    from conversion_ui import ConversionUI

    # Tk setup
    root = tk.Tk()
    root.title(f"{APP_TITLE} {APP_VERSION}")
    root.geometry(WINDOW_SIZE)
    root.minsize(430, 440)
    root.configure(bg=BACKGROUND_COLOR)
    root.option_add("*Font", UI_FONT)
    style_combobox(root)

    title_frame = tk.Frame(root, bg=BACKGROUND_COLOR)
    title_frame.pack(fill=tk.X, padx=16, pady=(12, 8))
    tk.Label(title_frame, text="HEARTOPIA", fg=TEXT_COLOR,
             bg=BACKGROUND_COLOR, font=TITLE_FONT).pack(side=tk.LEFT)
    tk.Label(title_frame, text="MIDI PLAYER", fg=ACCENT_COLOR,
             bg=BACKGROUND_COLOR, font=UI_FONT).pack(side=tk.RIGHT)

    # A flat player card with a decorative record beside the current status.
    deck = tk.Frame(root, bg=CARD_COLOR, bd=0)
    deck.pack(fill=tk.X, padx=12, pady=(0, 4))
    tk.Frame(deck, bg=ACCENT_COLOR, height=2).pack(fill=tk.X)
    display = tk.Frame(deck, bg=PANEL_COLOR, bd=0)
    display.pack(fill=tk.X, padx=10, pady=(10, 8))
    record = tk.Canvas(display, width=72, height=72, bg=PANEL_COLOR,
                       highlightthickness=0, bd=0)
    record.pack(side=tk.LEFT, padx=(8, 10), pady=8)
    for inset in (2, 9, 16, 23):
        record.create_oval(inset, inset, 72 - inset, 72 - inset,
                           fill=BACKGROUND_COLOR, outline=SEPARATOR_COLOR)
    record.create_oval(27, 27, 45, 45, fill=ACCENT_COLOR, outline=ACCENT_COLOR)
    record.create_oval(34, 34, 38, 38, fill=PANEL_COLOR, outline=PANEL_COLOR)
    track_info = tk.Frame(display, bg=PANEL_COLOR)
    track_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    tk.Label(track_info, text="NOW PLAYING", bg=PANEL_COLOR,
             fg=ACCENT_COLOR, font=UI_FONT, anchor="w").pack(fill=tk.X)
    status_label = tk.Label(track_info, text=DEFAULT_STATUS, bg=PANEL_COLOR,
                            fg=TEXT_COLOR, font=DISPLAY_FONT, justify=tk.LEFT,
                            anchor="w", wraplength=260)
    status_label.pack(fill=tk.X, pady=(4, 0))

    root.bind("<Configure>", update_status_wrap)

    # Instrument selection
    instrument_frame = tk.Frame(deck, bg=CARD_COLOR)
    instrument_frame.pack(pady=(0, 4), padx=8, fill=tk.X)

    tk.Label(instrument_frame, text="INSTRUMENT", bg=CARD_COLOR,
             fg=MUTED_TEXT_COLOR).pack(side=tk.LEFT, padx=(0, 8))

    instrument_var = tk.StringVar(value=DEFAULT_INSTRUMENT)
    instrument_box = ttk.Combobox(instrument_frame, textvariable=instrument_var, width=35,
                                   values=list(INSTRUMENTS.keys()), state="readonly",
                                   style="Player.TCombobox", font=UI_FONT)
    instrument_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

    instrument_box.bind("<<ComboboxSelected>>", on_instrument_change)

    conversion_ui = ConversionUI(root, add_converted_midi, set_status)

    # Playback controls frame
    playback_frame = tk.Frame(deck, bg=CARD_COLOR)
    playback_frame.pack(pady=(0, 3))

    playback_buttons = [
        (PLAYBACK_BUTTONS["previous"], skip_previous),
        (PLAYBACK_BUTTONS["play_selected"], play_selected),
        (PLAYBACK_BUTTONS["play_playlist"], play_playlist),
        (PLAYBACK_BUTTONS["pause_resume"], pause_resume),
        (PLAYBACK_BUTTONS["stop"], stop),
        (PLAYBACK_BUTTONS["next"], skip_next),
    ]

    for i, (text, cmd) in enumerate(playback_buttons):
        button(playback_frame, text, cmd, accent=cmd is play_selected,
               width=3, font=TRANSPORT_FONT).grid(row=0, column=i, padx=2, pady=2)

    # Loop controls frame
    loop_frame = tk.Frame(deck, bg=CARD_COLOR)
    loop_frame.pack(pady=(0, 5))

    loop_buttons = [
        (PLAYBACK_BUTTONS["loop"], toggle_loop)
    ]

    for i, (text, cmd) in enumerate(loop_buttons):
        button(loop_frame, text, cmd, width=8).grid(row=0, column=i, padx=4, pady=3)

    button(loop_frame, PLAYBACK_BUTTONS["musical_chairs"], play_musical_chairs,
           width=16).grid(row=0, column=1, padx=4, pady=3)

    # Library card grows with the window while transport stays at the top.
    playlist_card = tk.Frame(root, bg=CARD_COLOR, bd=0)
    playlist_card.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
    tk.Label(playlist_card, text="YOUR PLAYLIST", bg=CARD_COLOR, anchor="w",
             fg=MUTED_TEXT_COLOR, font=UI_FONT).pack(fill=tk.X, padx=10, pady=8)
    playlist_box = tk.Listbox(playlist_card, bg=PANEL_COLOR, fg=TEXT_COLOR,
                              selectbackground=SELECTION_COLOR, selectforeground=TEXT_COLOR,
                              font=PLAYLIST_FONT, exportselection=False, height=5,
                              highlightthickness=1, highlightbackground=SEPARATOR_COLOR,
                              highlightcolor=ACCENT_COLOR, bd=0, relief=tk.FLAT, activestyle="none")
    playlist_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
    playlist_box.bind("<<ListboxSelect>>", on_playlist_select)

    btn_frame = tk.Frame(playlist_card, bg=CARD_COLOR)
    btn_frame.pack(pady=(0, 4))
    file_buttons = [
        (FILE_BUTTONS["load_midi"], load_midi),
        (FILE_BUTTONS["delete_selected"], delete_selected),
    ]
    for i, (text, cmd) in enumerate(file_buttons):
        button(btn_frame, text, cmd, width=9).grid(row=0, column=i, padx=3, pady=2)
    convert_button = button(btn_frame, FILE_BUTTONS["convert_audio"], conversion_ui.open, width=12)
    convert_button.grid(row=0, column=2, padx=3, pady=2)
    conversion_ui.attach_button(convert_button)

    # Footer
    footer = tk.Frame(root, bg=BACKGROUND_COLOR)
    footer.pack(fill=tk.X, padx=10, pady=(2, 6))

    tk.Label(footer, text=APP_VERSION, fg=FOOTER_TEXT_COLOR, bg=BACKGROUND_COLOR).pack(side=tk.LEFT)
    tk.Label(footer, text=APP_CREDIT, fg=FOOTER_TEXT_COLOR,
             bg=BACKGROUND_COLOR, font=("Segoe UI", 8)).pack(side=tk.RIGHT)
    # tk.Button(footer, text="Ko-fi", command=lambda: webbrowser.open("https://ko-fi.com/yukiokoito"),
    #           bg="#333333", fg="white").pack(side=tk.RIGHT)

    # Init
    load_layout()
    instrument_var.set(current_instrument)
    player = KeyboardPlayer(layout=current_layout, instrument=current_instrument)
    load_saved_playlist()

    root.protocol("WM_DELETE_WINDOW", close_app)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
