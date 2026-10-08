# Phase 2: backend ready for review

Phase 1's timeout and frozen follow-up checks passed; the user's conditional
approval authorized cleanup and this phase. Stop here before phase 3.

## Standard EXE delivered

`dist/main-0.4.9-standard.exe` — 13,236,698 bytes (12.62 MiB).

SHA-256: `BD2201E39EDC0F42B0AFF1C68C136116D30993C8E7AE1D98AF59B5E606CD97A4`.

Built with PyInstaller 6.22.3 / Python 3.12.10 from the phase-1 app with the
timeout warning. The unchanged `main-current.spec` ran in an isolated source
copy. Frozen startup and spawn passed; the test child exited 0 with no second
window, and seeded settings stayed byte-identical. The build copy and its version
bump were discarded. The workspace version is still v0.4.8.

The user subsequently requested an EXE to keep, so this verified artifact was
retained. It is the **standard phase-1 app**, without a Convert dialog or bundled
conversion dependencies. It is not a phase-4 conversion-enabled release.

## Backend changes

- `audio_converter.py`: lazy optional imports, PyAV mono float32 decoding at the
  model's sample rate, actual decoded-duration cap (20 minutes), silence and
  invalid-input rejection, checkpoint download/validation and CPU loading, output
  directory fallback, MIDI validation, Windows no-overwrite rename with suffixes.
- `conversion_files.py`: shared registry under per-user app data, using the exact
  settings lock. Registers random temp paths before creation and stores PID,
  process start time, creation time and job ID. Cleanup touches only registered
  app-temp paths whose owners are demonstrably dead; PID reuse is handled and
  inaccessible owner processes are treated as alive. Live instances are preserved.
- `transcribe_worker.py`: independent spawn target with no Tk/UI imports. Reports
  stages/results via a queue, passes an explicit checkpoint path, invokes the
  unchanged single-call transcriber, validates before final publication, and
  watches for parent death. Worker errors become queue messages.
- `conversion_job.py`: parent-owned one-at-a-time lifecycle, cancellation, bounded
  shutdown, crash detection and dead-worker cleanup. Independent download and
  transcription deadlines; the latter is max(600 seconds, 3x decoded duration).
  Cancellation never drains a queue that may have been interrupted while writing.
- `requirements-convert.txt`: exact section-0 environment pins, including
  **audioread==3.1.0** and an explicit Windows/Python-3.12 CPU torch wheel URL.
  Base requirements.txt is unchanged.
- `app_config.py`: conversion paths, limits, timeout and checkpoint constants.
- `tests/test_conversion.py`: backend failure, concurrency and lifecycle tests.

No phase-3 widgets, playlist integration, playback-state changes, phase-4 spec
changes, README or CHANGELOG updates have been introduced.

## Checkpoint and progress decisions

- New downloads require explicit `allow_download=True`; no implicit network use.
- Downloads use Python urllib with read-stall and overall deadlines, progress
  messages, a registered partial file, fsync, size validation and successful model
  loading before publication. Failed new download candidates are deleted.
- The audited checkpoint is exactly 171,966,578 bytes, exceeding the package's
  160,000,000-byte trigger threshold. No trusted hash was found in package source;
  validation is size plus CPU model load. The SHA-256 constant remains None.
- An os.system guard prevents the package from invoking wget even if the explicit
  file changes between prevalidation and constructor execution.
- User-selected checkpoints are never modified or deleted; settings changes are
  deferred to the UI only after validation succeeds. An existing bad shared cache
  without ownership evidence is kept and produces a clear error. New app downloads record file identity under the shared lock; a later corrupt owned checkpoint is deleted only if that identity still matches, protecting manual replacements and other instances.
- Choose progress option **(b)**: elapsed time, estimated 1.5x song length, and an
  indeterminate bar in phase 3. No manual model segmentation or unverified percent
  progress is introduced. Download byte progress is independently measurable.

## Validation

- **8 base-app tests passed** in the environment without conversion dependencies,
  including the real five-second settings lock timeout, non-modal warning,
  retained in-memory settings and unchanged on-disk settings.
- **17 backend tests passed** in the conversion environment: invalid/silent/empty
  or missing audio, no audio stream, duration limit, manual checkpoint preservation,
  explicit download approval, failed-download cleanup, progress, stall/total
  deadline, no-notes MIDI, permission fallback, collision-safe concurrent outputs,
  live-owner preservation, PID reuse, worker crash, cancellation and shutdown.
- Two spawned processes produced `same.mid` and `same (1).mid` concurrently with
  valid contents, no overwrite, and no lost registry entries.
- **Real spawned-worker conversion passed** on a ten-second excerpt of the
  approved source (15-25 seconds). This is an integration check, not a replacement
  for the full-song quality/format verification in section 0. Total job time was
  21.14 seconds including imports, decode and loading. Output validates with mido.
- **Real transcription cancellation passed in 0.25 seconds** from cancellation
  request through worker exit and cleanup; no registered temp files remained.
- `git diff --check` passed. No playback/parser/keyboard module changes.

Commands:

```powershell
build\phase1\venv\Scripts\python.exe -m unittest discover -s tests -v
build\verification-piano\venv\Scripts\python.exe -m unittest discover -s tests -p test_conversion.py -v
build\verification-piano\venv\Scripts\python.exe -u build\phase2\real_smoke.py
```

Local evidence: `build/phase1/frozen-results.json` and
`build/phase2/real-smoke-results.json`. Test fixture/output stays in ignored
`build/phase2/`. Network failure tests use controlled responses; this phase did
not redownload the full checkpoint, already downloaded and loaded in section 0.

## Phase-3 integration obligations

Call lifecycle/registry operations from a parent service thread (they perform IO
and can wait for the shared lock). Deliver resulting messages to Tk via its own
polled queue; never block Tk while waiting on registry/worker cleanup. Keep Cancel
available during download, decoding, loading and transcription. Call shutdown on
application exit and cleanup_stale at startup. These backend entry points have
been tested but are intentionally not wired into the UI in this phase.

The known pre-existing Configure/teardown error is documented in PHASE1-REVIEW.md
and remains untouched. The three SECTION0 MIDI files and generated WAV/M4A copies
were deleted after the approval gates. Source audio, the cached checkpoint,
SECTION0-VERIFICATION.md and all unrelated user changes remain intact.
