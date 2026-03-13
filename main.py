import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import json
import mido
import keyboard

from midi_parser import parse_midi
from keyboard_player import KeyboardPlayer, MidiInputPlayer, INSTRUMENTS, note_to_midi_value

# Paths
PLAYLIST_FILE = "playlist.json"
LAYOUT_FILE = "layout.json"

# App state
player = None
midi_input = None
playlist = []
current_index = None
midi_mode = False
current_layout = "22"
current_instrument = "piano"  # Default instrument
loop_mode = "none"  # "none", "one", or "all"
is_paused = False
pause_time = 0.0

# Tk setup
root = tk.Tk()
root.title("Heartopia MIDI Player")
root.geometry("360x600")
root.configure(bg="#1e1e1e")

# Helpers
def set_status(text):
    status_label.config(text=text)

# Placeholder for visual highlight (visual keyboard removed)
def highlight_keys(keys):
    return

# Playback control (no threads): scheduled via tkinter `after`
playback_active = False
playback_after_ids = []
pressed_keys = set()
playback_gen = 0
KEY_HOLD_MS = 250  # Duration to hold each key (ms). Adjust if notes are missed or timing feels off.
PLAYBACK_SPEED = 1.0  # Tempo multiplier: increase (1.5, 2.0) to slow down; decrease (0.8) to speed up.

def cancel_playback():
    global playback_active, playback_after_ids, pressed_keys
    playback_active = False
    global playback_gen
    playback_gen += 1
    for aid in list(playback_after_ids):
        try:
            root.after_cancel(aid)
        except Exception:
            pass
    playback_after_ids.clear()
    for k in list(pressed_keys):
        try:
            keyboard.release(k)
        except Exception:
            pass
    pressed_keys.clear()
    try:
        highlight_keys([])
    except Exception:
        pass

def start_playback(events, speed=1.0, on_key_press=None):
    """Play `events` (list of (delay, notes)) using tkinter `after` scheduling.
    This avoids background threads and can be cancelled with `cancel_playback()`.
    """
    global playback_active, playback_after_ids, pressed_keys
    cancel_playback()
    playback_active = True
    playback_after_ids = []
    pressed_keys = set()
    global playback_gen
    playback_gen += 1
    my_gen = playback_gen

    def release_keys(keys):
        for k in keys:
            try:
                keyboard.release(k)
            except Exception:
                pass
            pressed_keys.discard(k)
        if on_key_press:
            on_key_press([])

    def calculate_sustain_time(notes):
        """Calculate sustain time based on instrument and notes."""
        if current_instrument != "violin":
            return KEY_HOLD_MS

        if not note or len(note) < 3:
            return KEY_HOLD_MS

        duration_ms = note[2]
        if duration_ms <= 0:
            return KEY_HOLD_MS
        
        # Use average MIDI value if multiple notes
        avg_midi = sum(midi_values) / len(midi_values)
        
        # C4 (MIDI 60) = max sustain (600ms)
        # C6 (MIDI 84) = min sustain (250ms)
        # Linear interpolation
        min_midi = 60  # C4
        max_midi = 84  # C6
        min_sustain = 250
        max_sustain = 600
        
        # Clamp avg_midi to range
        clamped = max(min_midi, min(max_midi, avg_midi))
        
        # Lower MIDI value = higher sustain (inverted)
        sustain = max_sustain - (clamped - min_midi) * (max_sustain - min_sustain) / (max_midi - min_midi)
        return int(sustain)

    def play_note_index(i):
        if not playback_active or i >= len(events):
            return
        delay, notes = events[i]

        def do_notes():
            if not playback_active:
                return

            # If paused, do not progress; keep checking until resumed.
            if is_paused:
                rid = root.after(100, do_notes)
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
                    keyboard.press(key)
                    pressed_keys.add(key)
                except Exception:
                    pass

                sustain_ms = calculate_sustain_time(note)
                rid = root.after(sustain_ms, lambda k=key: release_keys([k]))
                playback_after_ids.append(rid)

            if on_key_press:
                on_key_press(keys)
            
            # Calculate sustain time based on instrument and notes
            sustain_ms = calculate_sustain_time(notes)
            rid = root.after(sustain_ms, lambda: release_keys(keys))
            playback_after_ids.append(rid)
            # schedule next note
            if my_gen == playback_gen and playback_active:
                play_note_index(i+1)

        rid = root.after(int(delay * 1000 / PLAYBACK_SPEED), do_notes)
        playback_after_ids.append(rid)

    # initial delay before playback (3s)
    rid = root.after(5000, lambda: play_note_index(0))
    playback_after_ids.append(rid)

# Title
title_frame = tk.Frame(root, bg="#1e1e1e")
title_frame.pack(pady=(10, 2))

tk.Label(title_frame, text="Heartopia MIDI Player", fg="white",
         bg="#1e1e1e", font=("Arial", 20, "bold")).pack()
tk.Label(title_frame, text="by yukiokoito, modified by Kyanari", fg="#bbbbbb",
         bg="#1e1e1e", font=("Arial", 10)).pack()

# Playlist
playlist_box = tk.Listbox(root, bg="#2e2e2e", fg="white",
                          selectbackground="#555555", font=("Arial", 12))
playlist_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

def on_playlist_select(event):
    global current_index
    sel = playlist_box.curselection()
    if sel:
        current_index = sel[0]

playlist_box.bind("<<ListboxSelect>>", on_playlist_select)

# Status
status_label = tk.Label(root, text="No files loaded", bg="#1e1e1e",
                        fg="white", font=("Arial", 12))
status_label.pack(pady=(0, 10))

# Playback controls
def stop():
    global midi_mode, is_paused
    # Cancel scheduled playback and stop any player/input
    cancel_playback()
    if player:
        player.stop()
    if midi_mode and midi_input:
        midi_input.stop()
    midi_mode = False
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
    global midi_mode, loop_mode
    stop()
    midi_mode = False
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
    
    # If loop one is enabled, schedule replay after song ends
    if loop_mode == "one":
        wait_time = int((duration + 6) * 1000)
        aid = root.after(wait_time, lambda: play_selected())
        playback_after_ids.append(aid)

def play_playlist():
    global midi_mode, loop_mode
    stop()
    midi_mode = False
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
        # Schedule next song with duration + 6 second buffer
        wait_time = int((duration + 6) * 1000)
        aid = root.after(wait_time, lambda: play_next(idx+1))
        playback_after_ids.append(aid)
    play_next(current_index or 0)

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

# MIDI keyboard
device_frame = tk.Frame(root, bg="#1e1e1e")
device_frame.pack(pady=5, padx=10, fill=tk.X)

tk.Label(device_frame, text="MIDI Device:", bg="#1e1e1e", fg="white").pack(anchor="w")

midi_device_var = tk.StringVar()
device_box = ttk.Combobox(device_frame, textvariable=midi_device_var, width=35)
device_box.pack(fill=tk.X, pady=(2, 5))

# Instrument selection
instrument_frame = tk.Frame(root, bg="#1e1e1e")
instrument_frame.pack(pady=5, padx=10, fill=tk.X)

tk.Label(instrument_frame, text="Instrument:", bg="#1e1e1e", fg="white").pack(anchor="w")

instrument_var = tk.StringVar(value="piano")
instrument_box = ttk.Combobox(instrument_frame, textvariable=instrument_var, width=35, 
                               values=list(INSTRUMENTS.keys()), state="readonly")
instrument_box.pack(fill=tk.X, pady=(2, 5))

def on_instrument_change(event=None):
    global current_instrument, player, midi_input
    current_instrument = instrument_var.get()
    if player:
        player.instrument = current_instrument
        player.set_layout_and_instrument(current_layout, current_instrument)
    set_status(f"Instrument: {current_instrument}")
    save_instrument()

instrument_box.bind("<<ComboboxSelected>>", on_instrument_change)

def refresh_devices():
    try:
        ports = mido.get_input_names()
    except Exception:
        ports = []
    if not ports:
        ports = ["No MIDI devices"]
    device_box["values"] = ports
    midi_device_var.set(ports[0])

def start_midi_keyboard():
    global midi_input, midi_mode
    stop()
    midi_mode = True
    port = midi_device_var.get()
    if not port or port == "No MIDI devices":
        messagebox.showerror("MIDI", "No MIDI device available")
        return
    midi_input = MidiInputPlayer(layout=current_layout, instrument=current_instrument)
    midi_input.start(port)
    set_status(f"MIDI Keyboard: {port}")

refresh_devices()

# Buttons
btn_frame = tk.Frame(root, bg="#1e1e1e")
btn_frame.pack(pady=5)

file_buttons = [
    ("📁 Load MIDI", load_midi),
    ("🗑 Delete", delete_selected),
    ("🎹 Keyboard", start_midi_keyboard),
]

for i, (text, cmd) in enumerate(file_buttons):
    tk.Button(btn_frame, text=text, command=cmd, bg="#333333", fg="white", width=14).grid(row=0, column=i, padx=4, pady=3)

# Playback controls frame
playback_frame = tk.Frame(root, bg="#1e1e1e")
playback_frame.pack(pady=5)

playback_buttons = [
    ("⏮", skip_previous),
    ("▶", play_selected),
    ("▶▶", play_playlist),
    ("⏸", pause_resume),
    ("⏹", stop),
    ("⏭", skip_next)
]

for i, (text, cmd) in enumerate(playback_buttons):
    tk.Button(playback_frame, text=text, command=cmd, bg="#333333", fg="white", width=6).grid(row=0, column=i, padx=2, pady=3)

# Loop controls frame
loop_frame = tk.Frame(root, bg="#1e1e1e")
loop_frame.pack(pady=5)

loop_buttons = [
    ("🔁", toggle_loop)
]

for i, (text, cmd) in enumerate(loop_buttons):
    tk.Button(loop_frame, text=text, command=cmd, bg="#333333", fg="white", width=6).grid(row=0, column=i, padx=2, pady=3)

# Footer
tk.Frame(root, bg="#444444", height=1).pack(fill=tk.X, pady=10)

footer = tk.Frame(root, bg="#1e1e1e")
footer.pack(fill=tk.X, padx=10)

tk.Label(footer, text="v0.2.0", fg="#aaaaaa", bg="#1e1e1e").pack(side=tk.LEFT)
# tk.Button(footer, text="Ko-fi", command=lambda: webbrowser.open("https://ko-fi.com/yukiokoito"),
#           bg="#333333", fg="white").pack(side=tk.RIGHT)

# Saving songs
def save_playlist():
    with open(PLAYLIST_FILE, "w") as f:
        json.dump([p["path"] for p in playlist], f)

def load_saved_playlist():
    if os.path.exists(PLAYLIST_FILE):
        try:
            with open(PLAYLIST_FILE, "r") as f:
                paths = json.load(f)
            for path in paths:
                if os.path.exists(path):
                    playlist.append({"name": os.path.basename(path), "path": path})
                    playlist_box.insert(tk.END, os.path.basename(path))
            if playlist:
                set_status(f"{len(playlist)} files loaded")
        except Exception:
            pass

def save_layout():
    with open(LAYOUT_FILE, "w") as f:
        json.dump({"layout": current_layout, "instrument": current_instrument}, f)

def load_layout():
    global current_layout, current_instrument
    if os.path.exists(LAYOUT_FILE):
        try:
            with open(LAYOUT_FILE, "r") as f:
                data = json.load(f)
                current_layout = data.get("layout", "22")
                current_instrument = data.get("instrument", "piano")
                instrument_var.set(current_instrument)
        except Exception:
            pass

def save_instrument():
    save_layout()  # Save both layout and instrument together

# Init
load_layout()
instrument_var.set(current_instrument)
player = KeyboardPlayer(layout=current_layout, instrument=current_instrument)
load_saved_playlist()

root.mainloop()

