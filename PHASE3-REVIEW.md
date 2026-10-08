# Phase 3: ready for source review

Phase 2 was approved. Phase 3 is implemented; stop here for review before phase 4.
The workspace version remains **v0.4.8**. The deleted
`dist/main-0.4.9-standard.exe` is absent. No new EXE was built.

## Run it

From PowerShell:

```powershell
Set-Location E:\GIT\Heartopia-Midi-Player
& .\build\verification-piano\venv\Scripts\python.exe .\main.py
```

The existing conversion venv now also contains the app's base requirements
(`keyboard` and `tk`, alongside the already installed `mido`). Open **Convert
Audio** to use the **Convert Piano Audio to MIDI…** dialog.

## Changes

- `conversion_ui.py` provides the non-modal dialog: Browse, Change folder,
  Refresh, a sorted top-level audio list with size/date and “MIDI exists,”
  source/model paths, download byte progress, indeterminate transcription
  progress with elapsed time and a 1.5× estimate, and Cancel. The solo-piano
  scope and approximate 1–2× CPU-time warning are visible.
- The adjacent `audio/` directory is created if missing when there is no saved
  override. Hidden/system files and subdirectories are excluded. Missing,
  unreadable and empty folders have clear messages. Selection is rechecked
  before dispatch. Folder and last-used-directory updates use the merged
  settings writer. No background folder watching or batch conversion.
- `conversion_service.py` moves folder scans, settings writes, registry cleanup
  and worker lifecycle IO off Tk into parent service threads. Tk polls their
  event queue. Startup calls `cleanup_stale`; exit terminates/reaps the worker
  and finishes registry cleanup before destroying the window. Settings timeout
  warnings are non-modal and preserve session settings.
- Both **Choose model file…** and **Re-download model** are available, including
  after a model error. Manual choices are validated in a spawned worker before
  changing the saved path. Re-download requires confirmation of size/destination,
  writes a new uniquely named candidate, validates it, and only then switches
  the path. The previous unowned file is never deleted or overwritten.
- **Worker-only wget guard confirmed:** `audio_converter.load_model()` rejects
  execution when `multiprocessing.parent_process()` is absent, before importing
  the model or patching `os.system`. The guard surrounds only the constructor
  inside the spawned worker. Every constructor receives an explicit validated
  checkpoint path. The main process's `os.system` remained identical throughout
  the real UI conversion/cancellation/exit test.
- `main.py` adds the action and `is_playback_fully_stopped()`. It checks paused
  state, held keys and which stored playback callback IDs are actually pending;
  stale flags/expired IDs do not block idle auto-selection. Successful MIDI is
  appended and persisted; only an idle player selects it and changes
  `current_index`. Playing, paused and pending-transition states keep their
  selection/index. Playlist-save errors retain the MIDI and show its path.
  The playlist retains its selection when another widget takes focus.
- The existing single-call transcription algorithm, parser, keyboard mapping,
  playback callbacks and pedal behavior are unchanged. CC64 stays in the MIDI;
  this does not add audible pedal support to game playback.

## Verification

**44 automated tests passed** in the conversion venv: 6 settings, 17 backend,
19 Phase 3 dialog/service/playlist checks, and 2 entry-point tests.

```powershell
& .\build\verification-piano\venv\Scripts\python.exe -m unittest discover -s tests -v
```

The Phase 3 tests exercise real Tk widgets plus controlled service/network
responses: all worker-stage Cancel controls, preflight cancellation with late
messages, missing dependencies, first-download consent, manual-model rejection,
new-file recovery, settings timeout/session retention, default/override folders,
hidden files, Refresh, stale/deleted inputs and playlist selection/save failures.
The existing backend suite covers actual process termination, timeout, crash,
temp cleanup and concurrent Windows no-overwrite publication.

Full source-app smoke tests used isolated settings, playlist and app-data state
under ignored `build/phase3/`. The real conversion used the approved recording's
existing 10-second excerpt and the cached checkpoint:

| Check | Result |
| --- | --- |
| Complete GUI conversion, validation and playlist insertion | Passed; 24.56 s including imports, decoding and model load |
| Cancel during real transcription | Passed; 0.30 s through worker exit and cleanup |
| Close app during real transcription | Passed; 0.30 s through shutdown |
| Leftover worker / registered temporary files | None |
| Tk responsiveness during the real probe | Largest measured 20 ms heartbeat interval was 0.156 s |
| Base-only source startup | Passed; conversion action shows install instructions; no torch/PyAV/model imports |
| Main-process `os.system` identity | Unchanged |

Evidence: `build/phase3/conversion/results.json`,
`build/phase3/standard/results.json` and the local smoke script
`build/phase3/app_smoke.py`. Dialog screenshots were inspected; the file table
uses scoped dark styling without changing the main app's ttk theme.

One initial combined test run hit `WinError 6` in the spawned entry-point test's
result queue. The isolated test and a repeat of the complete 44-test suite passed;
the error was not reproduced by the full-app worker test. No cause is claimed.

The download/recovery tests use controlled responses; this phase did not fetch
another full checkpoint. Real checkpoint loading and transcription passed using
the cached section-0 model. The no-upstream-hash limitation still applies:
validation uses the audited size and successful model load.

## Review boundary

Please check the dialog and in-game playback from source. Packaging, two-build
release handling, README and CHANGELOG remain for phase 4 after approval.
No phase-3 frozen build has been tested yet.

The pre-existing Configure/teardown callback issue documented in
`PHASE1-REVIEW.md` remains out of scope. Automated full-app probes unbind that
callback only inside their test harness before teardown; production code does
not change it. Source audio, cached checkpoint and `SECTION0-VERIFICATION.md`
are retained. Tests write only to isolated temporary or ignored test folders;
the user's playlist is not used for test persistence.
