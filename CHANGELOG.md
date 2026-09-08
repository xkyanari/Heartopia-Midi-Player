# Changelog

All notable changes to Heartopia MIDI Player are documented here.

## 2026-09-08

### Added
- Added Musical Chairs playback with a random 15-25 second excerpt from one playlist song.
- Added automatic executable versioning for PyInstaller builds.
- Added Windows executable version metadata and synchronized UI version display.
- Added a 300x500 minimum window size and responsive wrapping for active song status text.

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
