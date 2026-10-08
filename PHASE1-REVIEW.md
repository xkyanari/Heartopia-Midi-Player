# Phase 1: approved after follow-up checks

The initial phase-1 review is preserved below. Follow-up checks and conditional approval are recorded at the end; phase 2 has its own review report.

## Changes

- `TASK-audio-to-midi.md`: added the progress choice, required segment-equivalence
  check, indeterminate elapsed-time/1.5x estimate fallback, and the 1-2x CPU-time
  warning. Recorded section 0 approval, pinned-engine requirement (including
  audioread 3.1.0), phase review gates, and deferred test-audio cleanup.
- `main.py`: moved window creation, widget wiring, initialization, and mainloop
  into `main()`. Added the guarded entry point with `freeze_support()` first.
  Existing callback function ASTs are identical to the pre-change file.
- `app_storage.py`: added general settings load/save helpers. Saves hold a
  cross-process Windows byte lock for the entire read-merge-write, fsync a
  temporary file in the destination directory, then atomically replace the JSON.
  Layout/instrument saves use this same path and preserve unknown/conversion keys.
  Missing/corrupt/non-object settings return defaults without rewriting on read.
  Unreadable files are not treated as safe-to-overwrite empty settings.
- `app_config.py`: constants for the app-data directory and shared lock file,
  timeout and retry interval. The persistent lock lives under
  `%LOCALAPPDATA%/Heartopia-Midi-Player/state.lock`; phase 2's registry must reuse
  `state_file_lock()`. A contended lock times out after five seconds.
- `tests/test_app_storage.py`, `tests/test_entrypoint.py`: settings durability,
  concurrent writers, and import/spawn regressions.

## Validation

Created `build/phase1/venv` with Python 3.12 and **only requirements.txt** installed.
No conversion dependencies were needed or imported.

```powershell
build\phase1\venv\Scripts\python.exe -m unittest discover -s tests -v
build\phase1\venv\Scripts\python.exe build\phase1\smoke.py
git diff --check
```

- **7 unit/integration tests passed.** Four concurrent spawned writers preserved
  all 48 independent settings updates. Failed atomic replacement preserved the
  original JSON, removed its temp file, and released the lock for a subsequent save.
- Importing `main` in both parent and spawned child created no Tk window.
- **Real Tk startup/event-loop smoke comparison passed** against the pre-change
  source snapshot. Widget tree and requested dimensions match. Load/delete,
  selection, play/pause/resume/stop, next/previous, playlist playback, loop,
  Musical Chairs, instrument changes, settings preservation, and scheduled note
  press/release callbacks were exercised with identical outcomes.
- All pre-existing callback ASTs match the baseline; the parser, keyboard modules,
  requirements.txt, version value and PyInstaller specs were not changed.
- `git diff --check` passed.

The GUI probe uses hidden real Tk windows and temporary app-data/settings, with
OS keyboard injection and window focus mocked. It therefore verifies startup,
controls and scheduling, **not audible in-game playback**. Frozen EXE validation
is deferred to phase 4. The probe clears the Configure binding before destroying
its test windows to avoid a teardown callback error observed in the baseline.

Smoke evidence: `build/phase1/smoke-results.json`. Baseline snapshot:
`build/phase1-main-before.py`. These local verification files are ignored by Git.

## Original review boundary (before conditional approval)

Stop here for phase 1 review. All three `SECTION0-*.mid` files and both generated
WAV/M4A test copies remain present. Delete them only after phase 1 approval;
retain `SECTION0-VERIFICATION.md`, original source audio, and the cached checkpoint.

The pre-existing playlist.json changes were not edited. The earlier `.gitignore`
audio/output protections remain. No worker, conversion dialog, production
requirements-convert.txt, packaging, README or CHANGELOG implementation is included
in this phase; the approved audioread pin is recorded in the brief for that work.

## Follow-up requested after manual review

The user manually verified in-game playback after phase 1 and reported unchanged behavior. The user also played SECTION0-mp3.mid in-game and found transcription quality acceptable.

Settings lock timeout handling is now explicit: after five seconds, main.save_layout catches TimeoutError and shows a non-modal status-bar warning. In-memory layout/instrument values remain selected; no settings JSON or temporary settings output is written. A real competing-process test covers the full five-second timeout. Eight regression tests pass.

Known issue (pre-existing, out of scope): the root Configure callback can run during window teardown after the status label has been destroyed, raising TclError (invalid command name). This was observed in the pre-change baseline. It has not been fixed. The test harness unbinds Configure only during its own cleanup.

Frozen follow-up PASS: the unchanged main-current.spec built the standard EXE with PyInstaller 6.22.3/Python 3.12.10 in an isolated source copy. The EXE started with a Heartopia MIDI Player window and test settings stayed byte-for-byte intact. An external parent used the same EXE's frozen spawn entry point with a stdlib test target: child exit code 0, no child windows. Evidence: build/phase1/frozen-results.json. The isolated version bump and build tree were discarded; workspace APP_VERSION stays v0.4.8. At the user's subsequent request for an EXE, the verified 13,236,698-byte artifact was retained as dist/main-0.4.9-standard.exe (phase-1 standard app, no conversion UI).

All phase-1 follow-up gates passed. Under the user's conditional approval, the three SECTION0 MIDI outputs and the generated WAV/M4A copies were deleted. SECTION0-VERIFICATION.md, source audio and the cached checkpoint were kept. Phase 2 is authorized; phase 3 remains gated on its review.
