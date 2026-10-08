# Five player UI drafts

Open [index.html](index.html) in a browser. It works offline, without installing
anything. Use the numbered buttons to focus on one draft or **All five** to
compare. Browser printing also works for the visible drafts.

These are design previews for choosing a direction, not changes to the Tkinter
player. The preview controls are illustrations, not clickable playback controls.
Only the draft selector is interactive. All five preserve the existing actions:
previous, play selected song, play playlist, pause/resume, stop, next, loop,
Musical Chairs, instrument selection, load MIDI, delete and Convert Audio.
The displayed playing state uses **Pause**; the implemented control would still
resume after pausing. The progress bar is a read-only indicator.

| Draft | Design choice | Best suited to |
| --- | --- | --- |
| 1 · Midnight Teal | Dark teal, separated sections, player first | A familiar upgrade; recommended starting point |
| 2 · Paper Sage | Light background, green accent, more breathing room | Daytime use and a lighter appearance |
| 3 · Studio Amber | Instrument first, rectangular panels, two-column controls | Scanning explicit labels and changing instruments |
| 4 · Soft Plum | Softer panels, wider Play, separate Play playlist row | A playful style with a clear main action |
| 5 · Graphite Blue | Playlist first, playback dock below | Frequent song selection and file management |

Each uses the supplied screenshot's single song, version and credits. Long file
names wrap, playback icons have visible labels, and the draft selector supports
keyboard navigation with a visible focus outline. There are no added search,
volume, shuffle, seeking or artwork features. No fonts, packages or external
resources are downloaded.

The layouts express design direction rather than promise an exact 480×560 fit.
After a choice, verify the actual Tkinter window's minimum size, font rendering,
control focus order, hover/disabled states and long filenames. The playlist must
still expand and scroll; the conversion dialog should use the selected palette.
