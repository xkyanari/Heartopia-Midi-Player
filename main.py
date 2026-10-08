import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import multiprocessing
import os
import random
import math
import mido
from playback_timing import PlaybackClock, format_time
import ui_theme
from themes import playback_labels
from ui_theme import MidiVisualizer, button, style_combobox

from app_storage import (
    load_settings,
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
    APP_CREDIT,
    APP_TITLE,
    APP_VERSION,
    DEFAULT_INSTRUMENT,
    DEFAULT_LAYOUT,
    DEFAULT_STATUS,
    FILE_BUTTONS,
    FOCUS_CHECK_INTERVAL_MS,
    HEARTOPIA_WINDOW_TITLES,
    KEY_HOLD_MS,
    MUSICAL_CHAIRS_MAX_SECONDS,
    MUSICAL_CHAIRS_MIN_SECONDS,
    PLAYLIST_FONT,
    PAUSE_POLL_INTERVAL_MS,
    PLAYBACK_BUTTONS,
    PLAYBACK_SPEED,
    PLAYBACK_START_DELAY_MS,
    SETTINGS_SAVE_WARNING,
    SONG_END_BUFFER_SECONDS,
    TITLE_FONT,
    TRANSPORT_FONT,
    UI_FONT,
    WINDOW_SIZE,
)

# App state
player = None
conversion_ui = None
playlist = []
current_index = None
current_layout = DEFAULT_LAYOUT
current_instrument = DEFAULT_INSTRUMENT
loop_mode = "none"  # "none", "one", or "all"
is_paused = False
focus_check_id = None
now_playing_label = None
visualizer = None
time_label = None
progress_bar = None
playback_clock = None
time_update_id = None
playlist_box = status_label = None
settings_window = None
midi_folder = ""


def resize_progress(event=None):
    clock = playback_clock
    fraction = clock.position() / clock.duration if clock and clock.duration else 0
    progress_bar.coords("played", 0, 0, progress_bar.winfo_width() * fraction, 4)


def update_playback_time(schedule=True):
    global time_update_id
    if schedule:
        time_update_id = None
    if time_label is None:
        return
    clock = playback_clock
    position = clock.position() if clock else 0
    duration = clock.duration if clock else 0
    remaining = math.ceil(clock.remaining()) if clock else 0
    time_label.config(text=f"{format_time(position)} / {format_time(duration)}  ·  {format_time(remaining)} left")
    resize_progress()
    if schedule and clock and clock.remaining() > 0:
        time_update_id = root.after(200, update_playback_time)


def append_playlist_song(path):
    # Invalid files stay removable in the library and report errors when played.
    try:
        duration = mido.MidiFile(path).length
    except Exception:
        duration = None
    name = os.path.basename(path)
    playlist.append({"name": name, "path": path, "duration": duration})
    length = format_time(duration) if duration is not None else "--:--"
    playlist_box.insert(tk.END, f"{name}  ·  {length}")


def activate_playlist_song(event=None):
    on_playlist_select(event)
    if playlist_box.curselection():
        play_selected()
    return "break"


def schedule_song_end(seconds, callback):
    """Keep queue/loop transitions on the same pause-aware clock as the UI."""
    clock = playback_clock
    generation = playback_gen

    def check():
        if generation != playback_gen or clock is None:
            return
        remaining = seconds - clock.elapsed()
        if is_paused or remaining > 0:
            delay = PAUSE_POLL_INTERVAL_MS if is_paused else max(1, math.ceil(remaining * 1000))
            playback_after_ids.append(root.after(delay, check))
        else:
            callback()

    check()

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

def set_now_playing(name=None):
    if now_playing_label is not None:
        now_playing_label.config(text=name or "Nothing playing")


def highlight_keys(keys):
    if visualizer is not None:
        visualizer.show_keys([] if is_paused else keys,
                             list(player.note_map.values()) if player else [])

# Playback control (no threads): scheduled via tkinter `after`
playback_active = False
playback_after_ids = []
pressed_keys = []
playback_gen = 0
musical_chairs_run_id = 0
def cancel_playback():
    global playback_active, playback_after_ids, pressed_keys, focus_check_id
    global playback_clock, time_update_id
    if time_update_id is not None:
        root.after_cancel(time_update_id)
        time_update_id = None
    playback_clock = None
    update_playback_time()
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
    set_now_playing()
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
    append_playlist_song(path)
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

def start_playback(events, speed=PLAYBACK_SPEED, on_key_press=None, song_name=None, duration=None):
    """Play `events` (list of (delay, notes)) using tkinter `after` scheduling.
    This avoids background threads and can be cancelled with `cancel_playback()`.
    """
    global playback_active, playback_after_ids, pressed_keys
    global playback_clock
    cancel_playback()
    playback_active = True
    playback_after_ids = []
    pressed_keys = []
    if duration is None:
        onset = 0
        duration = 0
        for delay, notes in events:
            onset += delay
            duration = max(duration, onset + max((note[2] / 1000 for note in notes), default=0))
    playback_clock = PlaybackClock(duration, speed=speed, delay=PLAYBACK_START_DELAY_MS / 1000)
    update_playback_time()
    set_now_playing(song_name if events else None)
    all_notes_played = False
    global playback_gen
    playback_gen += 1
    my_gen = playback_gen
    clock = playback_clock
    event_time = 0.0

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
            on_key_press(list(pressed_keys))
        if all_notes_played and not pressed_keys:
            set_now_playing()

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
        nonlocal event_time
        if not playback_active or i >= len(events):
            return
        delay, notes = events[i]
        event_time += delay / speed
        target_time = event_time

        def do_notes():
            nonlocal all_notes_played
            if not playback_active:
                return

            # If paused, do not progress; keep checking until resumed.
            if is_paused:
                rid = root.after(PAUSE_POLL_INTERVAL_MS, do_notes)
                playback_after_ids.append(rid)
                return

            # Pausing during a gap must preserve the remaining note delay.
            remaining = target_time - clock.elapsed()
            if remaining > 0.001:
                rid = root.after(max(1, math.ceil(remaining * 1000)), do_notes)
                playback_after_ids.append(rid)
                return

            for note in notes:
                # Note is (name, octave, duration_ms)
                key = player.get_playable_key((note[0], note[1]))
                if not key:
                    continue

                try:
                    press_key(key)
                    pressed_keys.append(key)
                except Exception:
                    pass

                sustain_ms = calculate_sustain_time(note)
                rid = root.after(sustain_ms, lambda k=key: release_keys([k]))
                playback_after_ids.append(rid)

            if on_key_press:
                on_key_press(list(pressed_keys))
            if i == len(events) - 1:
                all_notes_played = True
                if not pressed_keys:
                    set_now_playing()
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
    files = filedialog.askopenfilenames(initialdir=midi_folder or None, filetypes=[("MIDI Files", "*.mid *.midi")])
    if not files:
        return
    for path in files:
        append_playlist_song(path)
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
    start_playback(events, on_key_press=highlight_keys,
                   song_name=playlist[current_index]["name"], duration=duration)
    if switch_to_heartopia():  # Switch to Heartopia window for key presses
        root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)
    
    # If loop one is enabled, schedule replay after song ends
    if loop_mode == "one":
        schedule_song_end(duration + SONG_END_BUFFER_SECONDS, play_selected)

def play_playlist():
    global loop_mode
    stop()
    def play_next(idx):
        global current_index
        if idx >= len(playlist):
            if loop_mode == "all" and playlist:
                play_next(0)  # Loop back to start
            else:
                set_status("Playlist finished")
            return
        
        current_index = idx
        playlist_box.select_clear(0, tk.END)
        playlist_box.select_set(idx)
        playlist_box.activate(idx)
        playlist_box.see(idx)
        try:
            events, duration = parse_midi(playlist[idx]["path"])
        except Exception as e:
            messagebox.showerror("MIDI Error", str(e))
            play_next(idx+1)
            return
        set_status(f"Playing: {playlist[idx]['name']}")
        start_playback(events, on_key_press=highlight_keys, song_name=playlist[idx]["name"], duration=duration)
        if switch_to_heartopia():  # Switch to Heartopia window for key presses
            root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)
        # Schedule next song with duration + 6 second buffer
        schedule_song_end(duration + SONG_END_BUFFER_SECONDS, lambda: play_next(idx+1))
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
        start_playback(excerpt_events, on_key_press=highlight_keys,
                       song_name=playlist[current_index]["name"], duration=excerpt_duration)
        if switch_to_heartopia():
            root.after(FOCUS_CHECK_INTERVAL_MS, check_heartopia_focus)

        def finish_musical_chairs():
            if run_id == musical_chairs_run_id:
                cancel_playback()
                set_status("Musical Chairs finished")

        schedule_song_end(excerpt_duration, finish_musical_chairs)

    play_excerpt()

def pause_resume():
    global is_paused
    if not playback_active:
        messagebox.showinfo("Pause", "No playback to pause")
        return
    is_paused = not is_paused
    if playback_clock is not None:
        if is_paused:
            playback_clock.pause()
        else:
            playback_clock.resume()
    highlight_keys(pressed_keys)
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
    playlist_box.see(current_index)
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
    playlist_box.see(current_index)
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
        append_playlist_song(path)
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


def load_player_settings():
    global midi_folder
    try:
        settings = load_settings()
    except OSError:
        settings = {}
    ui_theme.set_theme(settings.get("theme"))
    folder = settings.get("midi_input_folder", "")
    midi_folder = folder if isinstance(folder, str) else ""


def apply_theme(name):
    previous = ui_theme.current()
    ui_theme.set_theme(name)
    if ui_theme.current() is not previous:
        build_player_ui()
    # The existing IO service uses app_storage.save_settings off the Tk thread,
    # so waiting for another instance's settings lock cannot stall MIDI notes.
    conversion_ui.save({"theme": ui_theme.current().name})


def scan_midi_folder():
    """Import only immediate MIDI files, in name order, preserving the queue."""
    if not midi_folder:
        return
    normalize = lambda path: os.path.normcase(os.path.realpath(os.path.abspath(path)))
    known = {normalize(song["path"]) for song in playlist}
    try:
        with os.scandir(midi_folder) as entries:
            paths = sorted((entry.path for entry in entries if entry.is_file() and
                            os.path.splitext(entry.name)[1].lower() in (".mid", ".midi")),
                           key=lambda path: (os.path.basename(path).casefold(), path))
    except OSError as error:
        set_status(f"Cannot read MIDI folder: {error}")
        return
    added = 0
    for path in paths:
        key = normalize(path)
        if key not in known:
            append_playlist_song(path)
            known.add(key)
            added += 1
    if added:
        try:
            save_playlist()
        except OSError as error:
            set_status(f"Playlist not saved: {error}")
            return
        set_status(f"Added {added} MIDI files from folder")


def set_midi_folder(folder):
    global midi_folder
    midi_folder = folder
    scan_midi_folder()
    conversion_ui.save({"midi_input_folder": folder})


def open_settings():
    global settings_window
    if settings_window is not None and settings_window.window.winfo_exists():
        settings_window.window.lift()
        return
    from settings_ui import SettingsWindow
    settings_window = SettingsWindow(root, apply_theme, lambda: midi_folder,
                                     set_midi_folder, conversion_ui)


def playback_commands():
    return {
        "previous": skip_previous, "play_selected": play_selected,
        "play_playlist": play_playlist, "pause_resume": pause_resume,
        "stop": stop, "next": skip_next,
    }


def build_player_ui():
    """Replace widgets only; playback callbacks always use the new globals."""
    global playlist_box, status_label, instrument_var, transport_buttons
    global now_playing_label, visualizer, time_label, progress_bar
    theme = ui_theme.current()
    selection = playlist_box.curselection() if playlist_box is not None else ()
    scroll = playlist_box.yview()[0] if playlist_box is not None else 0
    status = status_label.cget("text") if status_label is not None else DEFAULT_STATUS
    song = now_playing_label.cget("text") if now_playing_label is not None else "Nothing playing"
    for widget in root.winfo_children():
        if not isinstance(widget, tk.Toplevel):
            widget.destroy()
    root.configure(bg=theme.BACKGROUND_COLOR)
    if theme.labelled:
        root.minsize(480, 660)
    else:
        root.minsize(430, 460)
    style_combobox(root)

    header = tk.Frame(root, bg=theme.BACKGROUND_COLOR)
    header.pack(fill=tk.X, padx=16, pady=(12, 8))
    tk.Label(header, text="HEARTOPIA", bg=theme.BACKGROUND_COLOR,
             fg=theme.TEXT_COLOR, font=TITLE_FONT).pack(side=tk.LEFT)
    button(header, "⚙", open_settings, font=("Segoe UI", 12)).pack(side=tk.RIGHT, padx=(8, 0))
    tk.Label(header, text="MIDI PLAYER", bg=theme.BACKGROUND_COLOR,
             fg=theme.ACCENT_COLOR, font=UI_FONT).pack(side=tk.RIGHT)
    footer = tk.Frame(root, bg=theme.BACKGROUND_COLOR)
    footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(2, 6))
    tk.Label(footer, text=APP_CREDIT, fg=theme.FOOTER_TEXT_COLOR,
             bg=theme.BACKGROUND_COLOR, font=("Segoe UI", 8)).pack(side=tk.RIGHT)
    body = tk.Frame(root, bg=theme.BACKGROUND_COLOR)
    body.pack(fill=tk.BOTH, expand=True)
    deck = body if theme.labelled else tk.Frame(body, bg=theme.CARD_COLOR)
    if not theme.labelled:
        deck.pack(fill=tk.X, padx=12, pady=(0, 4))
        tk.Frame(deck, bg=theme.ACCENT_COLOR, height=2).pack(fill=tk.X)

    display = tk.Frame(deck, bg=theme.PANEL_COLOR)
    visualizer = MidiVisualizer(display)
    visualizer.pack(side=tk.LEFT, padx=(8, 10), pady=8)
    track_info = tk.Frame(display, bg=theme.PANEL_COLOR)
    track_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    tk.Label(track_info, text="Now Playing:", bg=theme.PANEL_COLOR,
             fg=theme.ACCENT_COLOR, font=UI_FONT, anchor="w").pack(fill=tk.X)
    now_playing_label = tk.Label(track_info, text=song, bg=theme.PANEL_COLOR,
                                fg=theme.TEXT_COLOR, font=("Segoe UI", theme.title_size, "bold"),
                                anchor="w", width=1)
    now_playing_label.pack(fill=tk.X, pady=(4, 0))
    status_label = tk.Label(track_info, text=status, bg=theme.PANEL_COLOR,
                            fg=theme.MUTED_TEXT_COLOR, font=UI_FONT, justify=tk.LEFT,
                            anchor="w", wraplength=260)
    status_label.pack(fill=tk.X, pady=(4, 0))
    time_label = tk.Label(track_info, bg=theme.PANEL_COLOR,
                         fg=theme.MUTED_TEXT_COLOR, font=UI_FONT, anchor="w")
    time_label.pack(fill=tk.X, pady=(4, 0))
    progress_bar = tk.Canvas(track_info, height=4, bg=theme.SEPARATOR_COLOR,
                             highlightthickness=0, bd=0)
    progress_bar.create_rectangle(0, 0, 0, 4, fill=theme.ACCENT_COLOR, outline="", tags="played")
    progress_bar.pack(fill=tk.X, pady=(3, 4))
    progress_bar.bind("<Configure>", resize_progress)
    root.bind("<Configure>", update_status_wrap)

    instrument_frame = tk.Frame(deck, bg=theme.CARD_COLOR)
    tk.Label(instrument_frame, text="INSTRUMENT", bg=theme.CARD_COLOR,
             fg=theme.MUTED_TEXT_COLOR).pack(side=tk.LEFT, padx=(0, 8))
    instrument_var = tk.StringVar(value=current_instrument)
    instrument_box = ttk.Combobox(instrument_frame, textvariable=instrument_var,
                                  width=1, values=list(INSTRUMENTS), state="readonly",
                                  style="Player.TCombobox", font=UI_FONT)
    instrument_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
    instrument_box.bind("<<ComboboxSelected>>", on_instrument_change)

    playback_frame = tk.Frame(deck, bg=theme.CARD_COLOR)
    labels = playback_labels(theme)
    callbacks = playback_commands()
    keys = ("previous", "play_selected", "play_playlist", "pause_resume", "stop", "next")
    if theme.labelled:
        keys = ("previous", "play_selected", "next", "pause_resume", "stop", "play_playlist")
    transport_buttons = {}
    for i, key in enumerate(keys):
        row, column = divmod(i, theme.columns)
        span = 1
        if theme.name == "Soft Plum":
            row, column, span = {
                "play_selected": (0, 0, 2), "pause_resume": (0, 2, 1),
                "previous": (1, 0, 1), "stop": (1, 1, 1), "next": (1, 2, 1),
                "play_playlist": (2, 0, 3),
            }[key]
        widget = button(playback_frame, labels[key], callbacks[key],
                        accent=key == "play_selected",
                        width=0 if theme.labelled or key == "play_selected" else 3,
                        font=UI_FONT if theme.labelled or key == "play_selected" else TRANSPORT_FONT)
        widget.grid(row=row, column=column, columnspan=span, sticky="ew", padx=2, pady=2)
        transport_buttons[key] = widget
    for column in range(theme.columns):
        playback_frame.columnconfigure(column, weight=1, uniform="transport")

    loop_frame = tk.Frame(deck, bg=theme.CARD_COLOR)
    button(loop_frame, PLAYBACK_BUTTONS["loop"], toggle_loop, width=8).grid(row=0, column=0, padx=4, pady=3)
    button(loop_frame, PLAYBACK_BUTTONS["musical_chairs"], play_musical_chairs,
           width=16).grid(row=0, column=1, padx=4, pady=3)

    playlist_card = tk.Frame(body, bg=theme.CARD_COLOR)
    tk.Label(playlist_card, text="YOUR PLAYLIST · Double-click or Enter to play",
             bg=theme.CARD_COLOR, fg=theme.MUTED_TEXT_COLOR,
             anchor="w", font=UI_FONT).pack(fill=tk.X, padx=10, pady=8)
    actions = tk.Frame(playlist_card, bg=theme.CARD_COLOR)
    actions.pack(side=tk.BOTTOM, pady=(0, 4))
    for i, (key, command) in enumerate((("load_midi", load_midi), ("delete_selected", delete_selected))):
        button(actions, FILE_BUTTONS[key], command, width=9).grid(row=0, column=i, padx=3, pady=2)
    convert_button = button(actions, FILE_BUTTONS["convert_audio"], conversion_ui.open, width=12)
    convert_button.grid(row=0, column=2, padx=3, pady=2)
    conversion_ui.attach_button(convert_button)
    library = tk.Frame(playlist_card, bg=theme.CARD_COLOR)
    library.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
    playlist_box = tk.Listbox(library, bg=theme.PANEL_COLOR, fg=theme.TEXT_COLOR,
                              selectbackground=theme.SELECTION_COLOR, selectforeground=theme.TEXT_COLOR,
                              font=PLAYLIST_FONT, exportselection=False, height=5,
                              highlightthickness=1, highlightbackground=theme.SEPARATOR_COLOR,
                              highlightcolor=theme.ACCENT_COLOR, bd=0, relief=tk.FLAT, activestyle="none")
    scrollbar = tk.Scrollbar(library, orient=tk.VERTICAL, command=playlist_box.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    playlist_box.config(yscrollcommand=scrollbar.set)
    playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    playlist_box.bind("<<ListboxSelect>>", on_playlist_select)
    playlist_box.bind("<Double-Button-1>", activate_playlist_song)
    playlist_box.bind("<Return>", activate_playlist_song)

    sections = {"song": display, "instrument": instrument_frame,
                "transport": playback_frame, "modes": loop_frame, "playlist": playlist_card}
    if theme.labelled:
        for row, name in enumerate(theme.sections):
            sections[name].grid(row=row, column=0, sticky="nsew" if name == "playlist" else "ew",
                                padx=theme.padding, pady=(0, theme.padding))
            body.rowconfigure(row, weight=1 if name == "playlist" else 0)
        body.columnconfigure(0, weight=1)
    else:
        display.pack(fill=tk.X, padx=10, pady=(10, 8))
        instrument_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        playback_frame.pack(pady=(0, 3))
        loop_frame.pack(pady=(0, 5))
        playlist_card.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
    for entry in playlist:
        duration = entry.get("duration")
        length = format_time(duration) if duration is not None else "--:--"
        playlist_box.insert(tk.END, f"{entry['name']}  ·  {length}")
    for index in selection:
        playlist_box.select_set(index)
        playlist_box.activate(index)
    playlist_box.yview_moveto(scroll)
    highlight_keys(pressed_keys)
    update_playback_time(schedule=False)
    # Measure the finished layout using the actual Tk fonts/DPI. A fixed height
    # can otherwise squeeze the playlist below its five requested rows.
    root.update_idletasks()
    minimum_width, minimum_height = root.minsize()
    root.minsize(minimum_width, max(minimum_height, root.winfo_reqheight()))


def main():
    global root, player, conversion_ui
    from conversion_ui import ConversionUI

    root = tk.Tk()
    root.title(f"{APP_TITLE} {APP_VERSION}")
    root.geometry(WINDOW_SIZE)
    root.option_add("*Font", UI_FONT)
    load_player_settings()
    conversion_ui = ConversionUI(root, add_converted_midi, set_status)
    build_player_ui()
    load_layout()
    instrument_var.set(current_instrument)
    player = KeyboardPlayer(layout=current_layout, instrument=current_instrument)
    load_saved_playlist()
    scan_midi_folder()
    root.protocol("WM_DELETE_WINDOW", close_app)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
