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
5. Find the checkpoint download URL and its expected size/hash **in the package source**. Don't hard-code a URL from memory. Inspect and report exactly how the package downloads and validates its checkpoint, including whether it shells out to `wget` and whether it relies on a size threshold. Always pass an explicit, app-verified `checkpoint_path` to `PianoTranscription`; never let the package initiate its own download.
   - If upstream publishes no hash, **report that gap**. Don't invent or self-compute a "trusted" hash. In that case, validate by expected file size plus a successful model load, and state that limitation in the report.

If step 2 or 3 fails, stop and report. **Fallback:** Basic Pitch, only after it passes the same isolated install and inference test (Basic Pitch's dependency config selects TensorFlow on Windows/Python 3.12; ONNX is only auto-selected below Python 3.11). Choose the engine **only after** one has passed.

---

## 1. Feature summary

- A **"Convert Piano Audio to MIDI…"** action in the existing UI, placed where the Pop2Piano entry was planned.
- "Convert Piano Audio to MIDI…" opens a Convert dialog. The user can pick the source audio two ways:
  - **Browse…** — a standard file dialog filtered to `.wav .flac .mp3 .ogg .m4a` (plus an "All files" option). It opens in the audio folder below if one is set, otherwise in the last-used directory.
  - **Audio folder list** — if an audio folder is set, the dialog lists the supported audio files in it (non-recursive, sorted by name), showing file name, size and modified date. It also marks files that already have a matching `<stem>.mid` beside them ("MIDI exists"). The user selects one and clicks Convert.
- **Default audio folder:** use the `audio` directory next to the app: next to `main.py` for source runs (`E:\GIT\Heartopia-Midi-Player\audio` in this workspace), or next to the EXE for frozen builds, not its temporary extraction directory. Create this default directory if missing. List its supported files in the Convert dialog. A saved `audio_input_folder` overrides the default; **Change folder…** selects and saves that override. If creating or reading the directory fails, show a clear message and offer another folder.
- Include a **Change folder…** button (folder picker) and a **Refresh** button. Re-scan when the dialog opens and when Refresh is clicked. No background folder watching.
- Rescan only the audio folder's top level, ignore hidden/system files, and show "No audio files found" if it's empty. If the saved folder no longer exists or can't be read, show a clear message and offer to choose another. Never crash.
- The file list is for picking only. Nothing converts automatically; one file per conversion (batch stays out of scope).
- The chosen file is re-checked at the moment **Convert** is clicked (still exists, readable), since the list may be stale.
- During conversion the dialog shows progress and a **Cancel** button.
- **Progress:** `transcribe()` has no progress callback. Either (a) feed audio to the model in segments and report real per-segment percentage, only after verifying that this produces identical output to the single-call §0 MIDI output, or (b) use an indeterminate progress bar with elapsed time and an estimate of approximately 1.5× song length. If equivalence for (a) is not verified, use (b).
- The dialog warns that conversion takes roughly **1–2× the song length on CPU**.
- On success the `.mid` file is saved (location rules in §5), added to the playlist and selected (§6).
- The dialog states the scope: *"Works best on solo piano recordings. Other instruments or full mixes give poor results."*

---

## 2. Model / checkpoint handling

- The checkpoint (~165 MB) is **not bundled**. On first use, show a one-time prompt covering size and destination, then download it with progress and cancel.
- Store it in the per-user app data directory, not next to the EXE.
- Always pass an explicit, app-verified `checkpoint_path` to `PianoTranscription`. The app owns checkpoint acquisition and validation; never trigger the package's built-in download. Confirm its actual download and validity-check behavior from package source during §0.
- Verify size/hash after download. If an **app-owned download** is partial or corrupt, delete it and show an error.
- Also let the user choose an existing checkpoint file manually, for offline machines.
- Offer **Re-download model** alongside **Choose model file…**, including after a bad/unowned cached checkpoint fails. Re-download to a new file, validate its size and model load, and only then switch the saved checkpoint path. Never delete or overwrite the previous unowned file.
- Apply the defensive `os.system`/`wget` guard only while loading the model inside the spawned worker process. Never patch `os.system` in the main app process.
- **Checkpoint ownership:** the app deletes only files it downloaded itself (partial or corrupt downloads in its own app data dir). A **user-selected checkpoint is never deleted, moved or modified**. If it fails validation (size/hash where available, or a failed model load), reject it with a clear error, keep the previously saved path unchanged, and leave the file where it is.
- **Settings persistence:** the current settings writer saves only layout and instrument, and it replaces the whole JSON file. Extend it to do a **read-merge-write**: load the existing JSON, update only the keys being changed, keep unknown keys, and write atomically (temp file + rename). Hold the same exclusive cross-process file lock used for the temp-file registry around the entire settings read-merge-write, including the atomic replace, so concurrent instances cannot lose each other's updates. Store the checkpoint path under a new key. Existing layout/instrument saves must also go through the merge, so neither path clobbers the other. A missing or corrupt settings file falls back to defaults and is not overwritten until the next intentional save.
- Store `audio_input_folder` and `last_audio_dir` through the merged settings writer (same lock and read-merge-write rules as the checkpoint path).
- Resolve `audio_input_folder` to the saved override, or to the app-adjacent `audio` directory by default. Creating the missing default directory is allowed. After that, the audio folder is only read unless the §5 output location resolves to it (output still goes beside the source file per §5). Test format copies belong in an ignored test folder, never in `audio/`.

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
- **Temp files:** write to a temp path in the output directory. Validate that temporary MIDI as specified in §5 before publishing it under the final filename. Only then perform the collision-safe atomic rename.
- **Stale-file cleanup has to be scoped.** Output can sit beside any source file, so never scan folders or delete by pattern. Instead:
  - Keep a small app-owned registry (a JSON file in the app data dir) of in-progress temp files. Record the path, the owning PID, the process start time and the creation time before writing each file. Remove the entry after the rename or delete.
  - At startup, delete only registered files whose owner process is no longer alive (check PID + start time, to guard against PID reuse). Skip entries owned by a live process, which could be another running instance.
  - Temp names use an app-specific prefix/suffix and a random component, so they never collide with user files.
  - **Registry concurrency:** hold an exclusive cross-process **file lock around the entire read-modify-write**, and write the new contents with an **atomic replace** (temp + rename) while still holding the lock. Atomic replace alone prevents partial JSON but still lets two instances overwrite each other's updates, so the lock is required. Use this same cross-process file lock for settings read-merge-write operations (§2).
- **Timeout:** configurable, default = max(10 min, 3× audio duration). It covers **transcription only**. The checkpoint download has its own timeout and stall detection.
- Allow only one conversion at a time. Disable the menu action while one is running.

---

## 5. Output

- Default location: next to the source file, named `<source-stem>.mid`. Add a numeric suffix on collision and never overwrite.
- **The final rename must be collision-safe across instances.** Checking whether the name exists and then renaming is a race. On Windows, prefer direct `os.rename(temp, final)`, which fails if the target exists and avoids exposing an empty placeholder MIDI. On `FileExistsError`, try the next numeric suffix and retry. Use exclusive-create reservation (`O_CREAT | O_EXCL`) only as a fallback if direct rename proves unreliable; document the evidence for using that fallback. Never use `os.replace` (or anything else that overwrites) onto a name this process hasn't claimed.
- If exclusive creation reserves a final filename before publication, record that reservation in the app-owned cleanup registry before creating it. Remove an unfilled reservation on cancellation, failure or shutdown, and include it in stale-file recovery. Never delete a successfully published MIDI as reservation cleanup.
- If that folder isn't writable, fall back to a configurable output folder.
- **Validate the result before publication:** the temporary file must parse (mido) and contain at least one `note_on` with **`velocity > 0`**. A `note_on` with velocity 0 is a note release and doesn't count. Otherwise treat it as a failure (*"No piano notes detected"*) and delete the temporary file.
- **Sustain pedal:** keep CC64 events in the written MIDI file. The existing playback parser ignores pedal events, and **adding audible pedal support to Heartopia playback is out of scope**. Don't change the parser for this feature, and don't claim pedal is audible in the UI or docs.

---

## 6. Playlist integration (see Codex finding #4)

- Add the new MIDI through the existing playlist helpers.
- When selecting it programmatically, **also set `current_index`** to the new row so Play targets the new file.
- **Auto-select only when playback is fully stopped:** nothing playing, **no paused session**, and **no pending playlist transition** (e.g. a queued `root.after` advance to the next track). In every other state, don't interrupt anything and don't move `current_index` or the selection. Just append the new row and show a non-modal "Added to playlist" notice.
- **Don't trust the existing flags as-is.** `playback_active` currently stays `True` after a song finishes naturally, and the stored `root.after` callback IDs aren't cleared when those callbacks fire. So neither "`playback_active` is True" nor "the callback list isn't empty" means playback is actually in progress.
- Add one helper, e.g. `is_playback_fully_stopped()`, that works out the real state. It may check which stored callback IDs are **still pending** (e.g. via `root.tk.call('after', 'info')`, or by tracking IDs as they fire) and the paused state. Explicitly allowed: minimal changes so callbacks remove their own ID when they run, and so natural completion leaves an accurate state. These changes must not alter audible playback behavior (§7a). Use the helper only for the auto-select decision.
- If playlist persistence fails, the MIDI file still stays on disk. Show a warning that includes the file path. Don't roll back the conversion.

---

## 7. Dependencies and packaging (see Codex finding #3)

- Conversion dependencies are **optional** for source installs. Put them in a separate requirements file (e.g. `requirements-convert.txt`) and pin the versions verified in §0.
- Source users: when the deps are missing, the menu action shows install instructions instead of crashing. Lazy-import them inside the conversion code path.
- **EXE:** installing packages with `pip` never adds features to an already-built EXE, and lazy imports don't reliably keep packages out of PyInstaller builds. So produce **two builds from clean venvs**:
  - **Standard:** no torch/PyAV. Add explicit `excludes` in the spec as a safety net. The menu item reads "requires the conversion-enabled build".
  - **Conversion-enabled:** CPU torch + PyAV + the transcription package. The checkpoint is still downloaded at runtime.
- Report the size of both builds.
- **Keep the existing PyInstaller version-bump logic unchanged.** It increments the version every time it runs, so running both builds one after the other in the same checkout would bump twice. Required approach:
  - Build each variant in its **own isolated copy** of the source tree (a separate temp directory or git worktree), with both copies containing the **same completed, reviewed source snapshot**, including the conversion implementation, and starting from the **same version value**. If using git worktrees, the selected commit must include the completed implementation; do not build an older commit merely because it has the desired version.
  - Each copy runs the unchanged bump logic once, so both builds end up with the **same resulting version**.
  - Record that one version for the release: write it back to the main checkout once and put it in the CHANGELOG. Discard the bumps inside the isolated copies. Artifact names add a variant suffix (e.g. `-standard`, `-convert`) and share the version.
  - Changing release orchestration (e.g. a wrapper script that drives both builds) is allowed if it's needed to do the above. Don't modify the bump logic itself. If none of this is possible without changing the bump logic, stop and report instead.

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
9. Output with no `note_on` where velocity > 0 is rejected before publication. Cancellation or failure leaves no temporary MIDI or unfilled final-name reservation; successfully published MIDI files remain intact.
10. The first-run checkpoint download works, can be cancelled cleanly, and a corrupt download is detected. Choosing a checkpoint manually works offline.
11. The standard EXE contains no torch (check the build output and size). The conversion EXE works on a clean Windows machine.
12. No Pop2Piano code, config keys or strings remain.
13. The app starts and behaves as before after the `main.py` restructuring, and spawning the worker doesn't open a second window (source and EXE).
14. Saving the checkpoint path keeps layout/instrument settings and any unknown keys, and saving layout/instrument keeps the checkpoint path.
15. Startup cleanup deletes only registered temp files from dead owner processes. With two instances running, one never deletes the other's in-progress files, and concurrent registry updates from both instances are all kept (no lost entries).
16. Existing PyInstaller version-bump logic is unchanged. A release run builds both variants from the **same completed source snapshot** with the **same** version, and the recorded version advances by exactly one bump. README and CHANGELOG are updated as described in §7a.
17. Two instances converting the **same source file at the same time** both succeed, and both outputs survive under distinct names (e.g. `song.mid` and `song (1).mid`). Neither overwrites the other.
18. After a song **finishes naturally** (no Stop pressed), a conversion that completes afterwards auto-selects the new row and sets `current_index`. A conversion completing while a queued next-track callback is still pending does not.
19. Choosing an invalid checkpoint manually is rejected with a clear error. The file is left untouched on disk, and the previously saved checkpoint path is kept.
20. Browse… converts a file from any location. The dialog starts in the audio folder when one is set, otherwise in the last-used directory.
21. With an audio folder set, the dialog lists only supported audio files from that folder, marks ones with an existing .mid, and Refresh picks up files added or removed while the dialog is open.
22. A missing or unreadable audio folder shows a clear message and lets the user choose a new one. An empty folder shows "No audio files found".
23. A listed file deleted before Convert is clicked gives a clear error, not a crash.
24. The audio folder and last-used directory persist across restarts without affecting other settings. With no saved override, the app uses and, if necessary, creates its adjacent `audio` folder; **Change folder…** persists an override.

---

## Out of scope (for now)

Full-song / mixed-audio input (source separation with Demucs etc.), guitar or other instruments, GPU acceleration, batch conversion, and audible sustain-pedal support in Heartopia playback.

## Approved implementation phases

Section 0 is approved. Use piano_transcription_inference with the versions recorded in SECTION0-VERIFICATION.md, including audioread==3.1.0 in requirements-convert.txt. Stop for review after each phase:

1. main.py entry-point restructure and settings read-merge-write; preserve behavior and verify startup.
2. Worker process, decoding, checkpoint acquisition/validation, temp registry, output validation and collision-safe rename, with tests.
3. Convert dialog and playlist integration, including is_playback_fully_stopped().
4. Two-build packaging/version handling, README and CHANGELOG.

After phase 1 is approved, delete the SECTION0-*.mid files and generated test audio copies. Keep SECTION0-VERIFICATION.md. Do not delete the source audio or cached checkpoint.
