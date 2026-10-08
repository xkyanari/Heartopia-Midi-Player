# Brief: Local Piano Audio → MIDI Conversion

**Scope change:** Pop2Piano is cancelled. Remove every reference to it (the Hugging Face Space, uploads, bearer tokens, the external-service notice). In its place we add **local transcription of solo piano recordings to MIDI**, similar to Eldoraudio. Audio never leaves the machine.

Treat this brief as the spec. Where it conflicts with the repo, trust the repo and flag the conflict. Don't guess.

---

## 0. Verify before building (blocking)

Do this in an **isolated venv** on the target setup (Windows, Python 3.12) and report back **before** touching any UI code:

1. Install `piano_transcription_inference` (ByteDance high-resolution piano transcription, PyTorch) plus the **CPU-only** torch wheel.
2. Confirm it installs and imports cleanly on Python 3.12. Record the exact versions that work.
3. Transcribe one solo piano WAV and one M4A (decoded as described in §3). Confirm the MIDI output has notes, sensible velocities and sustain pedal (CC64) events.
   - **Test samples:** use at least one recording that clearly uses the sustain pedal. If no suitable samples exist in the repo, ask for them. Don't substitute synthetic audio for the pedal test.
4. Record wall-clock time against audio length on CPU, and peak RAM.
5. Find the checkpoint download URL and its expected size/hash **in the package source**. Don't hard-code a URL from memory.
   - If upstream publishes no hash, **report that gap**. Don't invent or self-compute a "trusted" hash. In that case, validate by expected file size plus a successful model load, and state that limitation in the report.

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
- Also let the user choose an existing checkpoint file manually, for offline machines.
- **Settings persistence:** the current settings writer saves only layout and instrument, and it replaces the whole JSON file. Extend it to do a **read-merge-write**: load the existing JSON, update only the keys being changed, keep unknown keys, and write atomically (temp file + rename). Store the checkpoint path under a new key. Existing layout/instrument saves must also go through the merge, so neither path clobbers the other. A missing or corrupt settings file falls back to defaults and is not overwritten until the next intentional save.

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
- **Startup restructuring is in scope.** `main.py` currently creates Tk and calls `mainloop()` at module level. With spawn, each child re-imports the main module and would recreate the UI. So:
  - Move UI creation into a `main()` function.
  - Call it only from `if __name__ == "__main__":`, with `multiprocessing.freeze_support()` as the first line inside that guard.
  - Put the worker function in a separate module (e.g. `transcribe_worker.py`) that imports nothing from the UI or Tk.
  - Keep this refactor behavior-neutral: the app must start and behave exactly as before, in both source and EXE builds.
- Send progress and results to the UI over a queue, polled with `root.after(...)` (the pattern the app already uses). Never touch Tk from the worker.
- **Cancel stops the conversion.** It terminates the child and deletes the temp output. It does not just close the dialog.
- **App exit during conversion:** terminate the child, wait briefly for it to finish, then delete the temp files in the parent's shutdown path. Don't rely on a daemon thread with `finally`.
- **Temp files:** write to a temp path in the output directory, then do an atomic rename to the final name on success.
- **Stale-file cleanup has to be scoped.** Output can sit beside any source file, so never scan folders or delete by pattern. Instead:
  - Keep a small app-owned registry (a JSON file in the app data dir) of in-progress temp files. Record the path, the owning PID, the process start time and the creation time before writing each file. Remove the entry after the rename or delete.
  - At startup, delete only registered files whose owner process is no longer alive (check PID + start time, to guard against PID reuse). Skip entries owned by a live process, which could be another running instance.
  - Temp names use an app-specific prefix/suffix and a random component, so they never collide with user files.
  - Update the registry with a file lock or atomic replace so two instances don't corrupt it.
- **Timeout:** configurable, default = max(10 min, 3× audio duration). It covers **transcription only**. The checkpoint download has its own timeout and stall detection.
- Allow only one conversion at a time. Disable the menu action while one is running.

---

## 5. Output

- Default location: next to the source file, named `<source-stem>.mid`. Add a numeric suffix on collision and never overwrite.
- If that folder isn't writable, fall back to a configurable output folder.
- **Validate the result:** the file must parse (mido) and contain at least one `note_on` with **`velocity > 0`**. A `note_on` with velocity 0 is a note release and doesn't count. Otherwise treat it as a failure (*"No piano notes detected"*) and delete the file.
- **Sustain pedal:** keep CC64 events in the written MIDI file. The existing playback parser ignores pedal events, and **adding audible pedal support to Heartopia playback is out of scope**. Don't change the parser for this feature, and don't claim pedal is audible in the UI or docs.

---

## 6. Playlist integration (see Codex finding #4)

- Add the new MIDI through the existing playlist helpers.
- When selecting it programmatically, **also set `current_index`** to the new row so Play targets the new file.
- **Auto-select only when playback is fully stopped:** nothing playing, **no paused session**, and **no pending playlist transition** (e.g. a queued `root.after` advance to the next track). In every other state, don't interrupt anything and don't move `current_index` or the selection. Just append the new row and show a non-modal "Added to playlist" notice.
- Read the playback state from the app's existing state variables. If the repo doesn't expose a reliable "fully stopped" check, add one helper that does, and use it only here.
- If playlist persistence fails, the MIDI file still stays on disk. Show a warning that includes the file path. Don't roll back the conversion.

---

## 7. Dependencies and packaging (see Codex finding #3)

- Conversion dependencies are **optional** for source installs. Put them in a separate requirements file (e.g. `requirements-convert.txt`) and pin the versions verified in §0.
- Source users: when the deps are missing, the menu action shows install instructions instead of crashing. Lazy-import them inside the conversion code path.
- **EXE:** installing packages with `pip` never adds features to an already-built EXE, and lazy imports don't reliably keep packages out of PyInstaller builds. So produce **two builds from clean venvs**:
  - **Standard:** no torch/PyAV. Add explicit `excludes` in the spec as a safety net. The menu item reads "requires the conversion-enabled build".
  - **Conversion-enabled:** CPU torch + PyAV + the transcription package. The checkpoint is still downloaded at runtime.
- Report the size of both builds.
- **Keep the existing PyInstaller version-bump logic unchanged.** Both builds must go through it the same way the current build does. Don't bypass or duplicate it, and don't let the two builds bump the version twice for one release.

---

## 7a. Carried-over protections and deliverables

These carry over from the original brief and still apply:

- **Existing playback behavior is protected.** Play/pause/stop/next/previous, the `root.after(...)` scheduling, playlist order and `current_index` semantics must behave exactly as before, except for the one intended change in §6. No regressions to the existing layout, instrument settings or playlist helpers.
- **README:** document the feature, the "solo piano only" limitation, the first-run checkpoint download (size, location, manual/offline option), source-install steps using `requirements-convert.txt`, and the difference between the two EXE builds. State that pedal is kept in the MIDI file but isn't heard during in-app playback.
- **CHANGELOG:** add an entry covering the new conversion feature, the settings-writer change (merge instead of replace), the `main.py` entry-point restructuring, and the two-build packaging.

---

## 8. Acceptance criteria

1. The §0 verification report exists and names the chosen engine and pinned versions.
2. A solo piano WAV and M4A convert on a machine **without system ffmpeg**, and the MIDI plays in the app.
3. For the pedal sample, CC64 events are present in the written MIDI file (inspected with mido). Hearing the pedal in in-app playback is **not** required.
4. Each of these gives a clear error, leaves no stray files and doesn't crash:
   - a non-audio file
   - a zero-length file
   - a silent file
   - a video file with no audio track
   - a corrupt file
5. Cancel during transcription stops the worker within about 2 s and leaves no temp files.
6. Closing the app mid-conversion leaves no orphan process or temp files.
7. A conversion finishing while playing, **while paused**, or **during a pending track transition** doesn't change what's playing or selected, and the next Play/Resume/Next behaves correctly (`current_index` stays in sync). Auto-select happens only when playback is fully stopped.
8. Forced playlist-save failure: the MIDI is kept and a warning is shown.
9. Output with no `note_on` where velocity > 0 is rejected as failed.
10. The first-run checkpoint download works, can be cancelled cleanly, and a corrupt download is detected. Choosing a checkpoint manually works offline.
11. The standard EXE contains no torch (check the build output and size). The conversion EXE works on a clean Windows machine.
12. No Pop2Piano code, config keys or strings remain.
13. The app starts and behaves as before after the `main.py` restructuring, and spawning the worker doesn't open a second window (source and EXE).
14. Saving the checkpoint path keeps layout/instrument settings and any unknown keys, and saving layout/instrument keeps the checkpoint path.
15. Startup cleanup deletes only registered temp files from dead owner processes. With two instances running, one never deletes the other's in-progress files.
16. Existing PyInstaller version-bump behavior is unchanged. README and CHANGELOG are updated as described in §7a.

---

## Out of scope (for now)

Full-song / mixed-audio input (source separation with Demucs etc.), guitar or other instruments, GPU acceleration, batch conversion, and audible sustain-pedal support in Heartopia playback.
