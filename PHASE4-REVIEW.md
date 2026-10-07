# Phase 4 review

Phase 4 is complete and stopped before commit/tag. Workspace version is **v0.4.9**.

Builds came from one identical source snapshot in separate clean Python 3.12
environments. The existing spec version-bump block was left unchanged; each
copy bumped 0.4.8 to 0.4.9, and the workspace version was recorded once after
both artifacts passed checks.

| EXE | Size | SHA-256 |
| --- | ---: | --- |
| [main-0.4.9-standard.exe](/E:/GIT/Heartopia-Midi-Player/dist/main-0.4.9-standard.exe) | 13,914,106 bytes | `8299883b8ea061c543859fef6713797c583dfa7fe0b80e8498160c2cc8875d68` |
| [main-0.4.9-convert.exe](/E:/GIT/Heartopia-Midi-Player/dist/main-0.4.9-convert.exe) | 293,025,644 bytes | `8fb891079e127e30946cc1782be9588170839240dba49a553e02653e16cf956f` |

Frozen checks ran outside any venv. Standard startup preserved settings, showed
“Conversion requires the conversion-enabled build,” and its archive contained
no torch or PyAV. The conversion build reused the cached 171,966,578-byte model;
it did not bundle or redownload the checkpoint.

The full 227.7-second song converted in **327.0 seconds**, producing 1,860
positive note-ons and 534 CC64 events. Cancel stopped its worker in **1.06 s**.
Closing during transcription shut down in **5.63 s**. Both left no worker,
conversion temporary file or registered temp entry.

Verification:

- Entry-point test: 3/3 runs passed.
- Full suite: 44/44 passed.
- The earlier requested 20-run entry-point gate had already passed 20/20 before
  the leaner rerun request; no further repetition was made.

README and CHANGELOG now document conversion, the model/offline workflow,
optional source dependencies, pedal CC64 behavior, and the two EXE variants.
No commit or tag was created.
