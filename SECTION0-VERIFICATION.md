# Section 0 verification report

Status: **installation, imports, explicit-checkpoint CPU loading, and full-file MP3/WAV/M4A inference passed on this machine.** No UI or application code was changed. This verifies the engine path; it does not verify GUI behavior, packaging, or musical accuracy.

## Environment and verified versions

- Windows 11 x64, Python 3.12.10; isolated venv: `build/verification-piano/venv`.
- CPU: AMD Ryzen 7 3700X 8-Core Processor (8 cores / 16 logical processors).
- Installed RAM reported by Windows: 31.92 GiB.
- Each transcription ran sequentially in its own process, with four PyTorch CPU threads.
- CPU PyTorch came from `https://download.pytorch.org/whl/cpu`; CUDA build is null and CUDA unavailable.
- `pip check` passed. All import probes passed after explicitly adding `audioread`.

| Package | Verified version |
| --- | --- |
| piano_transcription_inference | 0.0.6 |
| torch | 2.14.0+cpu |
| torchlibrosa | 0.1.0 |
| av | 18.1.0 |
| numpy | 2.5.3 |
| librosa | 1.0.0 |
| mido | 1.3.3 |
| psutil | 7.2.2 |
| audioread | 3.1.0 |

Initial import failure: `piano_transcription_inference/utilities.py:3` imports audioread at module level, but package 0.0.6 does not directly declare it. Installing `audioread==3.1.0` fixed the failure. No package-source patches or other missing-dependency repairs were needed. Bypassing `load_audio` alone does not avoid that import.

Engine selected for the next implementation phase: **piano_transcription_inference 0.0.6 (ByteDance), CPU-only PyTorch**. Basic Pitch was not needed or tested.

## Checkpoint acquisition and package behavior

The URL was extracted from the installed package's `inference.py`, not recalled:

```text
https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1
```

Downloaded with Python `requests` to:

```text
C:\Users\Sophia\AppData\Local\Heartopia-Midi-Player\models\note_F1=0.9677_pedal_F1=0.9186.pth
```

- Actual file size: **171,966,578 bytes**, matching HTTP Content-Length (171966578); exceeds the 160,000,000-byte threshold.
- Initial download wall time: 90.84 s.
- Initial CPU model load: **PASS**, 16.70 s; 42,946,305 model parameters.
- All model loads passed an explicit `checkpoint_path` and `device='cpu'`. An `os.system` guard would fail any attempted package shell call; every load recorded zero calls.
- **Hash gap:** the package source publishes no trusted hash or exact expected size. Validation used the size threshold plus successful model load; Content-Length was an additional transfer-length check, not an integrity hash. No self-computed hash is presented as trusted. Separately hosted upstream checksum metadata was not audited.

Actual package behavior (`inference.py:27-35,53-54`): if no path is supplied, it picks a home-directory default. For any path, including an explicit one, if the file is absent or below 160,000,000 bytes, it creates the directory and runs `wget -O` via `os.system`. It ignores the command's return code and checks no hash or exact size after download, then calls `torch.load` and `load_state_dict(..., strict=False)`. An explicit path alone does not suppress downloads: the verified file must still exist and meet the threshold when the constructor checks it.

## Input and format coverage

Original user-selected pedal sample:

```text
E:\GIT\Heartopia-Midi-Player\audio\YTDown.com_YouTube_Media__OjyfdPQ2Jw_Britney-Spears-Baby-One-More-Time-Piano-Cover-by-Pianella-Piano_009_128k.mp3
```

Full decoded duration: **227.694875 seconds**; no trimming or synthetic input. The user designated this recording as the pedal sample.

PyAV decoded to mono float32 at the package's 16,000 Hz sample rate. It also created two test copies under the ignored `build/verification-piano/` directory:

- `pedal-format-copy.wav`: mono 16 kHz float32 PCM.
- `pedal-format-copy.m4a`: mono 16 kHz AAC, requested 128 kbit/s encoding.

The original MP3 was not modified. These are format-coverage copies of the same performance, not independent recordings. Each copy was decoded afresh with PyAV before transcription. No external ffmpeg executable or package `load_audio` was used.

## Full-file CPU inference results

Wall and CPU times below cover `transcribe()` including MIDI writing, excluding imports, decoding, and model loading. CPU time sums the process's threads. Wall/audio below 1 means faster than real time. These are single-run measurements on this machine, not performance guarantees.

| Input | Audio (s) | Inference wall (s) | CPU (s) | Wall/audio | Inference peak RSS (MiB) | Process peak working set (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MP3 | 227.695 | 341.29 | 1117.25 | 1.499 | 999.0 | 999.0 |
| WAV | 227.695 | 326.27 | 1086.33 | 1.433 | 992.8 | 997.8 |
| M4A | 227.712 | 311.84 | 1054.58 | 1.369 | 999.0 | 1001.9 |

Inference peak RSS was sampled every 50 ms and may miss shorter spikes. The Windows process peak working set is the OS lifetime high-water mark, including imports, decoding, and loading. These are process memory measures, not total system RAM.

| Input | Decode (s) | Model load (s) |
| --- | ---: | ---: |
| MP3 | 0.82 | 5.47 |
| WAV | 0.22 | 5.94 |
| M4A | 0.23 | 5.64 |

## MIDI note, velocity, and pedal checks

| Input | MIDI duration (s) | Positive note-ons | MIDI note range | Velocity min-max (median) | CC64 total | Pedal down / up |
| --- | ---: | ---: | --- | --- | ---: | --- |
| MP3 | 221.171 | 1860 | [24, 84] | [37, 101] (76) | 534 | 267 / 267 |
| WAV | 221.171 | 1860 | [24, 84] | [37, 101] (76) | 534 | 267 / 267 |
| M4A | 221.181 | 1864 | [24, 84] | [37, 101] (76) | 524 | 262 / 262 |

- MP3: 57 distinct velocities; CC64 values [0, 127]; unmatched note-offs 0; unclosed notes 0; nonpositive note durations 0; note duration range [0.0078125, 2.9296875] seconds.

- WAV: 57 distinct velocities; CC64 values [0, 127]; unmatched note-offs 0; unclosed notes 0; nonpositive note durations 0; note duration range [0.0078125, 2.9296875] seconds.

- M4A: 59 distinct velocities; CC64 values [0, 127]; unmatched note-offs 0; unclosed notes 0; nonpositive note durations 0; note duration range [0.0078125, 2.9296875000000284] seconds.

These checks establish readable, nonempty MIDI with varied legal velocities and inferred pedal events. They do not establish note-for-note accuracy or accurate pedal timing against ground truth. No listening-based quality assessment or in-game playback test was performed. The existing playback parser ignores CC64; audible pedal support remains out of scope.

Outputs beside this report (ignored by Git):

- [SECTION0-mp3.mid](SECTION0-mp3.mid)
- [SECTION0-wav.mid](SECTION0-wav.mid)
- [SECTION0-m4a.mid](SECTION0-m4a.mid)

MP3 and WAV MIDI files are byte-identical: True.

## Scope and retained evidence

Only `TASK-audio-to-midi.md`, `.gitignore`, this report, and verification artifacts were changed for this work. No UI/app implementation, production dependency file, version bump, EXE build, or playlist write was performed. Existing user changes to `playlist.json` were left untouched.

`audio/` and `/SECTION0-*.mid` are now ignored; test copies, scripts, and raw JSON results are under the already-ignored `build/verification-piano/` folder. The brief now defaults to an app-adjacent audio folder, creates it if missing, and preserves a saved `audio_input_folder` override.

Evidence: `import-results.json`, `checkpoint-results.json`, `format-results.json`, `inference-mp3.json`, `inference-wav.json`, `inference-m4a.json`, `installed-versions.txt`, and the `check_imports.py`, `check_checkpoint.py`, `run_audio_checks.py` probes in that folder.

Reproduction (PowerShell, from repository root; existing MIDI outputs are deliberately not overwritten by the harness):

```powershell
$python = '.\build\verification-piano\venv\Scripts\python.exe'
& $python .\build\verification-piano\check_imports.py
& $python .\build\verification-piano\check_checkpoint.py
# run_audio_checks.py prepare <original MP3 path>
# run_audio_checks.py infer <input path> --label mp3|wav|m4a
```

## Complete verified environment snapshot

This is evidence for this test environment, not a new production requirements file. Install torch from its CPU index when reproducing the `+cpu` pin.

```text
audioread==3.1.0
av==18.1.0
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.1
cloudpickle==3.1.2
contourpy==1.4.0
cycler==0.12.1
decorator==5.3.1
filelock==3.32.3
fonttools==4.66.0
fsspec==2026.7.0
idna==3.20
Jinja2==3.1.6
joblib==1.6.0
kiwisolver==1.5.1
lazy-loader==0.6
librosa==1.0.0
llvmlite==0.49.0
MarkupSafe==3.0.3
matplotlib==3.11.2
mido==1.3.3
mpmath==1.3.0
msgpack==1.2.2
narwhals==2.26.0
networkx==3.6.1
numba==0.67.0
numpy==2.5.3
packaging==26.3
piano-transcription-inference==0.0.6
pillow==12.3.0
platformdirs==4.12.1
pooch==1.9.0
psutil==7.2.2
pycparser==3.0
pyparsing==3.3.3
python-dateutil==2.9.0.post0
requests==2.34.2
scikit-learn==1.9.1
scipy==1.18.1
setuptools==78.1.0
six==1.17.0
soundfile==0.14.0
soxr==1.1.0
sympy==1.14.0
threadpoolctl==3.7.0
torch==2.14.0+cpu
torchlibrosa==0.1.0
typing_extensions==4.16.0
urllib3==2.8.0
```

## Post-verification review and cleanup

The user approved section 0 and manually verified SECTION0-mp3.mid in-game with acceptable transcription quality. Following the phase-1 review gates, the three SECTION0 MIDI outputs and generated WAV/M4A test copies were deleted as authorized. Output links above are historical evidence, not retained files. The source MP3, cached checkpoint, this report and measurement JSON remain.
