# Heartopia MIDI Player

A Python script that allows you to play music inside **Heartopia** (PC only).

⚠️ **Warning:** According to the Heartopia Discord mods, any third-party software is against the ToS. Use this at your own risk there’s a chance you could get banned.

Personally, I believe this tool is harmless and mainly helps players enjoy the game.. It does **not** give any in-game advantage. Tools like this are common in social games with instrument systems.

---

## Features

* Play **MIDI files** directly in the game
* **Multi-instrument support** (Piano, Lute, Wooden Bass, Recorder, Violin, Cello)
* Use a **physical MIDI keyboard** (currently only white keys supported)
* Supports **15-key** and **22-key** layouts
* Playlist persistence (remembers loaded MIDI files and instrument selection between sessions)
* Simple GUI with playback controls
* **Auto-focus** to Heartopia window on play
* **Auto-pause** when switching away from Heartopia
* **Window switching** on pause/resume for seamless control
* **Keypress duration follows MIDI note length** for Violin & Cello (capped to max hold time)

---

## Multi-Instrument Support

You can now select different instruments when playing MIDI files. Each instrument has its own range of notes:

| Instrument | Note Range | Keys | Description |
|---|---|---|---|
| **Piano** | C3 to C6 | 22 (with sharps/flats) | DEFAULT - Full chromatic range |
| **Lute** | C3 to C5 | 15 (white keys only) | Warm, mellow tone |
| **Wooden Bass** | C2 to C4 | 15 (white keys only) | Deep, resonant bass |
| **Recorder** | C5 to C7 | 15 (white keys only) | Bright, flute-like tone |
| **Violin** | C4 to C6 | 15 (white keys only) | Elegant, stringed sound with variable sustain |
| **Cello** | C2 to C4 | 15 (white keys only) | Deep, rich tone with variable sustain |

### Using Instruments in the UI
1. Look for the **"Instrument:"** dropdown in the player interface
2. Click to select any of the 6 available instruments
3. The selected instrument will be used for playback of MIDI files
4. Your selection is automatically saved and restored when you restart the app

### How It Works
- **15-key instruments** use only white keys (no sharps/flats) mapped to the same keyboard layout. Sharps/flats are transposed to the nearest white key (e.g., C# → C, D# → E).
- **Piano** uses the full 22-key layout with both white and black keys
- **Violin & Cello** use MIDI note duration for sustain (capped at 4.5s and 5s respectively)
- When MIDI notes fall outside the selected instrument's range, the player automatically transposes them to the nearest available octave

---

## New in v0.2.5

* **Pause/Resume now works**: Press ⏸ to pause playback mid-song, resume with another press
* **Auto-focus on play**: Automatically switches to Heartopia window when starting playback
* **Auto-pause on focus loss**: Pauses automatically if you switch away from Heartopia during playback
* **Window switching**: Pause brings focus back to the player, resume switches back to Heartopia
* **Instant playback**: Removed 5-second delay, starts playing immediately
* **Cello instrument**: Added with C2-C4 range and variable sustain (up to 5 seconds)
* **Code cleanup**: Removed unused code and imports

---

## Requirements

* Python **3.10+**
* Packages (install via pip):

```bash
pip install mido python-rtmidi keyboard
```

> `python-rtmidi` is required to use a physical MIDI keyboard.

---

## How to Run

1. Clone or download this repository:

```bash
git clone https://github.com/yourusername/Heartopia-Midi-Player.git
cd Heartopia-Midi-Player
```

2. Install required packages:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python main.py
```

4. **Using the app:**

* **Load MIDI files:** Click `Load MIDI` and select `.mid` or `.midi` files.
* **Delete:** Remove selected MIDI files from the playlist.
* **Play Selected:** Plays the selected MIDI file (auto-focuses to Heartopia).
* **Play Playlist:** Plays all MIDI files in order.
* **Pause/Resume:** ⏸ pauses playback, press again to resume (switches windows accordingly).
* **Stop:** ⏹ stops playback.
* **Skip:** ⏮ ⏭ navigate through playlist.
* **Instrument:** Choose from Piano, Lute, Wooden Bass, Recorder, Violin, or Cello.
* **Layout:** Automatically configured based on selected instrument (15-key or 22-key).
* **MIDI Keyboard:** Connect a MIDI keyboard and select it from the dropdown to play live.
* **Loop:** 🔁 toggles loop mode (none/one/all).

> The app will remember loaded MIDI files and your instrument selection between sessions.

---

## Notes

* The app is intended for fun and personal use in **Heartopia** - use responsibly.
* Instrument preferences are automatically saved in `layout.json`.
* MIDI notes are automatically transposed to fit within each instrument's range.
* Playback starts instantly and auto-focuses to Heartopia window.
* Pause works mid-song and switches focus back to the player for control.
* If you switch away from Heartopia during playback, it auto-pauses.

### ⚠️ Limitations & Disclaimer
This player does **not** perform advanced MIDI processing like key signature adjustments, complex chord voicings, or dynamic expression. Heartopia's instruments have very limited functionality compared to real instruments or professional MIDI software. As a result:

- MIDI files may not play exactly as intended
- Some notes or chords might sound off due to the game's instrument constraints
- Complex arrangements may require manual simplification in your MIDI editor
- The player only handles basic note-on/note-off events and simple transposition

For best results, use simple MIDI files designed for the specific instrument you're playing in-game.

---

## Contributing

Feel free to contribute! I built this in a few days, so there's plenty of room for improvement:

* Improve the visual keyboard mapping
* Add more playback options (speed, looping, etc.)
* Add more instruments

---

## License

This project is **open-source** and free to use.
