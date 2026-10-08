# Heartopia MIDI Player

A Python script that allows you to play music inside **Heartopia** (PC only).

⚠️ **Warning:** According to the Heartopia Discord mods, any third-party software is against the ToS. Use this at your own risk there’s a chance you could get banned.

Personally, I believe this tool is harmless and mainly helps players enjoy the game.. It does **not** give any in-game advantage. Tools like this are common in social games with instrument systems.

<img width="362" height="632" alt="image" src="https://github.com/user-attachments/assets/4aa2eca2-4f78-4771-bd05-3d0c225b2883" />

## UI design drafts

The **five player UI drafts** are in [docs/ui-drafts/index.html](docs/ui-drafts/index.html),
with a [comparison guide](docs/ui-drafts/README.md). These are design previews for
choosing a look; they do not change the player.

To view them, clone or download this repository, then double-click
`docs/ui-drafts/index.html` to open it in your browser. No installation is needed,
and it works offline. Use **All five** to compare or a numbered button to view one
draft. On GitHub, the HTML link shows source code; open the downloaded file locally
to see the designs.

---

## Features

* Play **MIDI files** directly in the game
* **Multi-instrument support** (Piano, Lute, Wooden Bass, Recorder, Violin, Cello)
* Supports **15-key** and **22-key** layouts
* Playlist persistence (remembers loaded MIDI files and instrument selection between sessions)
* Simple GUI with playback controls
* **Local solo-piano audio to MIDI conversion** (optional source dependencies or the conversion-enabled EXE)
* **Musical Chairs mode**: randomly plays one bounded 15-25 second excerpt, then stops without an end buffer
* **Auto-focus** to Heartopia window on play
* **Auto-pause** when switching away from Heartopia
* **Window switching** on pause/resume for seamless control
* **Keypress duration follows MIDI note length** for Violin & Cello (capped to max hold time)

---

## MIDI Playback Enhancements

The player supports MIDI file processing for better in-game playback:

### Note Folding (Octave Shifting)
- **Automatic octave wrapping**: Notes outside the instrument's range are shifted by full octaves (12 semitones) until they fit
- **Preserves musical structure**: Deep bass notes become playable mid-range notes instead of being dropped
- **Works with all instruments**: Piano, lute, violin, cello, etc. all benefit from this

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
* **MIDI timing**: Leading silence is trimmed so playback starts with the first note

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

* Python **3.12** (does not support 3.13+)
* Packages (install via pip):

```bash
pip install mido keyboard
```

## Convert solo piano audio to MIDI

Use **Convert Audio** to open the **Convert Piano Audio to MIDI…** dialog.
This works best with **solo piano recordings**; mixed songs, vocals and other
instruments give poor results. Audio stays on your computer.

The dialog lists WAV, FLAC, MP3, OGG and M4A files in the `audio` folder next to
the app (next to `main.py` when running from source). It creates this folder if
missing. **Change folder…** saves another location; **Browse…** picks a file
anywhere. The list is non-recursive and marks matching `.mid` files.
Use **Refresh** after adding or removing audio; nothing converts automatically.

Select one file and click **Convert**. CPU transcription takes roughly 1–2×
the song length, plus library/model startup time. The bar is indeterminate
during transcription, with elapsed time and an approximate 1.5× estimate.
**Cancel** stops the worker during decoding, model loading/downloading or
transcription. Closing the app also stops it and cleans its temporary files.
The default maximum input length is 20 minutes.

The MIDI is saved beside the source, adding ` (1)`, ` (2)`, etc. on collisions.
If that directory is not writable, output falls back to
`%LOCALAPPDATA%\Heartopia-Midi-Player\converted` (or the `converted_output_dir`
setting). It is added to the playlist; automatic selection happens only when
playback is fully stopped, including no paused session or queued transition.
Sustain pedal **CC64 is preserved in the MIDI**, but is **not audible during
in-app/game playback**.

### Model download and offline use

The model is not bundled. First use asks before downloading approximately
**172 MB (164 MiB)** into
`%LOCALAPPDATA%\Heartopia-Midi-Player\models`. Download progress and Cancel are
available. Later conversions reuse the validated checkpoint.

**Choose model file…** validates an existing checkpoint for offline use.
**Re-download model** downloads to a new file, validates it, then changes the
saved path. Manually supplied/unowned files are never deleted or overwritten.
No trusted upstream hash was found in the package source; validation uses the
audited size plus a successful model load. Microsoft Store Python can redirect
app-data storage; when moving from source to an EXE, choose the existing cached
file from its actual location if it is not found automatically.

### Source installation with conversion

Use Windows x64 and Python 3.12. The pinned conversion dependencies include CPU
PyTorch, PyAV and `audioread==3.1.0`; no system FFmpeg or Hugging Face token is
needed.

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-convert.txt
& .\.venv\Scripts\python.exe .\main.py
```

For playback only, install just `requirements.txt`. The conversion action will
show installation instructions if its optional dependencies are absent.

### Windows EXE variants

| Artifact | Contents |
| --- | --- |
| `main-0.4.9-standard.exe` | MIDI playback; no torch or PyAV. Convert explains that it requires the conversion-enabled build. |
| `main-0.4.9-convert.exe` | MIDI playback plus local CPU transcription and bundled audio decoding. Model downloads separately on first use. |

Neither EXE needs Python, a venv or a system FFmpeg installation. Installing
packages with pip cannot add conversion to an already-built standard EXE.

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

To build both Windows variants from one source snapshot, use Windows Python
3.12 and run this from the project folder:

```powershell
python tools/build_release.py build
```

The wrapper creates two clean venvs and two identical isolated source copies
under `build/`. Each copy runs the spec's unchanged patch-version bump once;
both EXEs have the same resulting version and `-standard` / `-convert` suffixes.
Artifacts go to `dist/`; logs, source hashes, sizes and hashes go to the generated
`release.json`. After frozen checks, record that version in the workspace once:

```powershell
python tools/build_release.py record build/release-YYYYMMDD-HHMMSS/release.json
```

Update the CHANGELOG for that version. Running the spec directly still bumps
its checkout on every invocation, so use the wrapper for paired releases.

4. **Using the app:**

* **Load MIDI files:** Click `Load MIDI` and select `.mid` or `.midi` files.
* **Delete:** Remove selected MIDI files from the playlist.
* **Play Selected:** Plays the selected MIDI file (auto-focuses to Heartopia).
* **Play Playlist:** Plays all MIDI files in order.
* **Musical Chairs:** Plays one random 15-25 second excerpt from a playlist song (shorter songs play in full), then stops. No song-end buffer is added.
* **Pause/Resume:** ⏸ pauses playback, press again to resume (switches windows accordingly).
* **Stop:** ⏹ stops playback.
* **Skip:** ⏮ ⏭ navigate through playlist.
* **Instrument:** Choose from Piano, Lute, Wooden Bass, Recorder, Violin, or Cello.
* **Layout:** Automatically configured based on selected instrument (15-key or 22-key).
* **Loop:** 🔁 toggles loop mode (none/one/all).

> The app will remember loaded MIDI files and your instrument selection between sessions.

---

## Notes

* The app is intended for fun and personal use in **Heartopia** - use responsibly.
* Instrument preferences are automatically saved in `layout.json`.
* MIDI notes are automatically transposed to fit within each instrument's range.
* Playback starts instantly and auto-focuses to Heartopia window.
* Musical Chairs excerpts start immediately, are limited to 15-25 seconds, and stop after one song.
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

To run tests, install `pip install -r requirements-dev.txt`, then run `python -m pytest`.

Feel free to contribute! I built this in a few days, so there's plenty of room for improvement:

* Improve the visual keyboard mapping
* Add more playback options (speed, looping, etc.)
* Add more instruments

---

## License

This project is **open-source** and free to use.
