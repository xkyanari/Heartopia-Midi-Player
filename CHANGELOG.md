# Changelog

All notable changes to Heartopia MIDI Player are documented here.

## 0.4.10 — 2026-10-07

### Added
- Added a "Now Playing:" line showing the current song name, resetting to "Nothing playing" on stop or when the song ends.
- Added a 12-bar visualizer that lights up for held notes and goes flat while paused.
- Added double-click or Enter on a playlist row to play that song.
- Added song lengths to each playlist row, showing `--:--` for unreadable files.
- Added a progress bar with elapsed / total / remaining time that freezes while paused; playlist and loop transitions also wait for paused time.

### Changed
- Updated the player with flat midnight-blue panels, cyan accents, a decorative record graphic, and Segoe UI typography.
- Updated the displayed version and Windows version metadata together; the title bar now also shows the version.

## 0.4.9 — 2026-09-28

### Added
- Local solo-piano audio-to-MIDI conversion using the section-0 pinned CPU engine, including `audioread==3.1.0`.
- Audio-folder list, Browse, Change folder, Refresh, model download/offline selection/re-download, elapsed-time progress and cancellation.
- Spawned conversion workers with bounded shutdown, registered temporary-file cleanup, output validation and collision-safe Windows publication.
- Separate `-standard` and `-convert` EXEs. Both build from the same snapshot in clean environments with one release-version increment.
- Conversion playlist integration that preserves active/paused playback and queued transitions. MIDI pedal CC64 is retained; audible pedal playback remains unsupported.

### Changed
- Restructured the main entry point for safe source and frozen multiprocessing startup.
- Settings now use locked, atomic read-merge-write updates, preserving unrelated keys across instances; save timeouts warn without losing session settings.
- Added release orchestration and source/conversion setup documentation. The existing spec version-bump logic is unchanged.

## 2026-09-08

### Added
- Added Musical Chairs playback with a random 15-25 second excerpt from one playlist song.
- Added automatic executable versioning for PyInstaller builds.
- Added Windows executable version metadata and synchronized UI version display.
- Added a 350x500 minimum window size and responsive wrapping for active song status text.

### Changed
- Removed the playback startup delay so songs begin immediately.
- Trimmed leading silence from MIDI playback.
- Updated build and runtime configuration modules.

### Fixed
- Musical Chairs now stops after its single excerpt instead of starting another song.
- Stale Musical Chairs callbacks are invalidated when playback is stopped or another mode starts.

Commits: `5dc8f87`, `1438a46`

## 2026-03-13

### Added
- Added note folding for MIDI file playback and live MIDI input.
- Added note merging and chord cleaning for MIDI input.
- Added pause/resume, automatic Heartopia focus handling, cello support, and sustain based on MIDI note duration.

### Fixed
- Removed duplicate sustain logic that caused playback errors.

Commits: `3e6337d`, `cc074eb`, `75097e2`, `8debf8b`, `ef6996b`, `8019b38`

## 2026-02-18

### Added
- Added multi-instrument support, including lute, wooden bass, recorder, violin, and cello configurations.

Commit: `4cc8ca5`

## 2026-02-05

### Changed
- Updated full piano mode and related playback behavior.
- Updated documentation for piano playback.

Commits: `fdd573a`, `dd49494`, `f4642ef`, `bf20f92`, `0d9cbb8`, `bd14d3f`

## 2026-01-12

### Added
- Added the 22-key piano option.
- Added playlist persistence and an application footer.

### Changed
- Improved MIDI parsing and documentation.

Commits: `40d53d7`, `28c7cf7`, `281971e`, `12e3f18`, `b7682bd`

## 2026-01-10

### Added
- Created the initial MIDI player application, parser, keyboard player, and requirements configuration.

Commits: `3a0d53b`, `105ae16`, `27df727`, `17c2f31`, `8509621`, `b4d9b39`
