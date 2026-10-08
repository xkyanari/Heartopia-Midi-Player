# Brief: Local Piano Audio → MIDI Conversion

**Scope change:** Pop2Piano is cancelled. Remove every reference to it (the Hugging Face Space, uploads, bearer tokens, the external-service notice). In its place we add **local transcription of solo piano recordings to MIDI**, similar to Eldoraudio. Audio never leaves the machine.

Treat this brief as the spec. Where it conflicts with the repo, trust the repo and flag the conflict. Don't guess.

---

## 0. Verify before building (blocking)

Do this in an **isolated venv** on the target setup (Windows, Python 3.12) and report back **before** touching any UI code:

1. Install `piano_transcription_inference` (ByteDance high-resolution piano transcription, PyTorch) plus the **CPU-only** torch wheel.
2. Confirm it installs and imports cleanly on Python 3.12. Record the exact versions that work.
3. Transcribe one solo piano WAV and one M4A (decoded as described in §3). Confirm the MIDI output has notes, sensible velocities and sustain pedal (CC64) events.
4. Record wall-clock time against audio length on CPU, and peak RAM.
5. Find the checkpoint download URL and its expected size/hash **in the package source**. Don't hard-code a URL from memory.

If step 2 or 3 fails, stop and report. **Fallback:** Basic Pitch, only after it passes the same isolated install and inference test (see Codex's note: TensorFlow is selected on Windows/Py 3.12). Choose the engine **only after** one has passed.

---

## 1. Feature summary

- A **"Convert Piano Audio to MIDI…"** action in the existing UI, placed where the Pop2Piano entry was planned.
- The user picks an audio file (`.wav .flac .mp3 .ogg .m4a`), then a dialog shows progress and a **Cancel** button.
- On success the `.mid` file is saved (location rules in §5), added to the playlist and selected (§6).
- The dialog states the scope: *"Works best on solo piano recordings. Other instruments or full mixes give poor results."*

---

## 2. Model / checkpoint handling

- The checkpoint (~165 MB) is **not bundled**. On first use, show a one-time prompt covering size and destination, then download it with progress and cancel.
- Store it in the per-user app data directory, not next to the EXE.
- Verify size/hash after download. If the file is partial or corrupt, delete it and show an error.
- Also let the user choose an existing checkpoint file manually, for offline machines. Save that path in the existing config structure.

---

## 3. Audio decoding (no system ffmpeg)

- Decode with **PyAV** (it ships its own FFmpeg libs) to **mono float32 at the model's sample rate** (read the constant from the package, expected 16 kHz). Pass the array straight to the transcriber and **bypass the package's `load_audio`**, which relies on librosa/audioread and so on system ffmpeg.
- Reject these with a clear message:
  - unreadable or corrupt files
  - no audio stream
  - zero-length audio or pure silence
  - clips over a configurable max duration (default 20 min)

---

## 4. Execution model, cancellation, shutdown

- Run transcription in a **child process** (`multiprocessing`, spawn), not a thread. That makes Cancel real: terminate the process.
- Call `multiprocessing.freeze_support()` in the entry point so the frozen EXE works.
- Send progress and results to the UI over a queue, polled with `root.after(...)` (the pattern the app already uses). Never touch Tk from the worker.
- **Cancel stops the conversion.** It terminates the child and deletes the temp output. It does not just close the dialog.
- **App exit during conversion:** terminate the child, wait briefly for it to finish, then delete the temp files in the parent's shutdown path. Don't rely on a daemon thread with `finally`.
- **Temp files:** write to a temp path in the output directory, then do an atomic rename to the final name on success. Delete stale temp files at startup.
- **Timeout:** configurable, default = max(10 min, 3× audio duration). It covers **transcription only**. The checkpoint download has its own timeout and stall detection.
- Allow only one conversion at a time. Disable the menu action while one is running.

---

## 5. Output

- Default location: next to the source file, named `<source-stem>.mid`. Add a numeric suffix on collision and never overwrite.
- If that folder isn't writable, fall back to a configurable output folder.
- **Validate the result:** the file must parse (mido) and contain at least one note_on. Otherwise treat it as a failure (*"No piano notes detected"*) and delete the file.

---

## 6. Playlist integration (see Codex finding #4)

- Add the new MIDI through the existing playlist helpers.
- When selecting it programmatically, **also set `current_index`** to the new row so Play targets the new file.
- **If playback is active when conversion finishes:** don't interrupt it and don't move `current_index`. Append the new row and show a non-modal "Added to playlist" notice. Only auto-select when nothing is playing.
- If playlist persistence fails, the MIDI file still stays on disk. Show a warning that includes the file path. Don't roll back the conversion.

---

## 7. Dependencies and packaging (see Codex finding #3)

- Conversion dependencies are **optional** for source installs. Put them in a separate requirements file (e.g. `requirements-convert.txt`) and pin the versions verified in §0.
- Source users: when the deps are missing, the menu action shows install instructions instead of crashing. Lazy-import them inside the conversion code path.
- **EXE:** installing packages with `pip` never adds features to an already-built EXE, and lazy imports don't reliably keep packages out of PyInstaller builds. So produce **two builds from clean venvs**:
  - **Standard:** no torch/PyAV. Add explicit `excludes` in the spec as a safety net. The menu item reads "requires the conversion-enabled build".
  - **Conversion-enabled:** CPU torch + PyAV + the transcription package. The checkpoint is still downloaded at runtime.
- Report the size of both builds.

---

## 8. Acceptance criteria

1. The §0 verification report exists and names the chosen engine and pinned versions.
2. A solo piano WAV and M4A convert on a machine **without system ffmpeg**, and the MIDI plays in the app.
3. Sustain pedal events are present in the output for a recording that uses pedal.
4. Each of these gives a clear error, leaves no stray files and doesn't crash:
   - a non-audio file
   - a zero-length file
   - a silent file
   - a video file with no audio track
   - a corrupt file
5. Cancel during transcription stops the worker within about 2 s and leaves no temp files.
6. Closing the app mid-conversion leaves no orphan process or temp files.
7. A conversion finishing during playback doesn't change what's playing, and the next Play/Next behaves correctly (`current_index` stays in sync).
8. Forced playlist-save failure: the MIDI is kept and a warning is shown.
9. Output with no notes is rejected as failed.
10. The first-run checkpoint download works, can be cancelled cleanly, and a corrupt download is detected. Choosing a checkpoint manually works offline.
11. The standard EXE contains no torch (check the build output and size). The conversion EXE works on a clean Windows machine.
12. No Pop2Piano code, config keys or strings remain.

---

## Out of scope (for now)

Full-song / mixed-audio input (source separation with Demucs etc.), guitar or other instruments, GPU acceleration, and batch conversion.
