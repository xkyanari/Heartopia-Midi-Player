"""Local conversion primitives, called only from the spawned worker. No Tk."""
import hashlib
from contextlib import nullcontext
import importlib
import json
import multiprocessing
import os
import re
from pathlib import Path
import time
import urllib.request
import uuid

from app_config import (
    CHECKPOINT_DOWNLOAD_CHUNK_BYTES, CHECKPOINT_DOWNLOAD_TIMEOUT_SECONDS,
    CHECKPOINT_EXPECTED_BYTES, CHECKPOINT_FILE, CHECKPOINT_FOLDER, CHECKPOINT_MIN_BYTES,
    CHECKPOINT_OWNERSHIP_FILE,
    CHECKPOINT_SHA256, CHECKPOINT_STALL_TIMEOUT_SECONDS, CHECKPOINT_URL,
    CONVERSION_CPU_THREADS, CONVERSION_INSTALL_COMMAND, CONVERSION_MAX_AUDIO_SECONDS,
    CONVERTED_OUTPUT_FOLDER, SUPPORTED_AUDIO_EXTS,
)
from conversion_files import app_data_dir, forget_temp, registered_temp
from app_storage import state_file_lock


class ConversionError(Exception):
    pass


def require_dependencies():
    try:
        return {name: importlib.import_module(name) for name in
                ("av", "numpy", "torch", "audioread", "psutil", "piano_transcription_inference")}
    except (ImportError, OSError) as exc:
        raise ConversionError(
            f"Conversion dependencies are missing or cannot load. Run: {CONVERSION_INSTALL_COMMAND}. {exc}"
        ) from exc


def decode_audio(path, sample_rate):
    """Bound decoding by actual sample count, not just potentially false metadata."""
    import av
    import numpy as np
    path = Path(path)
    if not path.is_file():
        raise ConversionError("The selected audio file no longer exists.")
    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
        raise ConversionError("Unsupported audio file. Choose WAV, FLAC, MP3, OGG or M4A.")
    limit = int(CONVERSION_MAX_AUDIO_SECONDS * sample_rate)
    chunks, count = [], 0
    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise ConversionError("The selected file has no audio stream.")
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=sample_rate)
            def append(frames):
                nonlocal count
                for frame in frames:
                    values = frame.to_ndarray().reshape(-1)
                    count += len(values)
                    if count > limit:
                        raise ConversionError(f"Audio exceeds the {CONVERSION_MAX_AUDIO_SECONDS / 60:g}-minute limit.")
                    chunks.append(values)
            for frame in container.decode(stream):
                append(resampler.resample(frame))
            append(resampler.resample(None))
        if not count:
            raise ConversionError("The selected file contains zero-length audio.")
        audio = np.concatenate(chunks).astype(np.float32, copy=False)
        if not np.all(np.isfinite(audio)):
            raise ConversionError("The audio contains invalid samples.")
        if not np.any(audio):
            raise ConversionError("The selected audio is silent.")
        return audio
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Cannot decode audio; the file may be unreadable or corrupt. {exc}") from exc


def default_checkpoint():
    return app_data_dir() / CHECKPOINT_FOLDER / CHECKPOINT_FILE


def _checkpoint_identity(path):
    stat = Path(path).stat()
    return {"inode": stat.st_ino,
            "birth_time": getattr(stat, "st_birthtime", stat.st_ctime if os.name == "nt" else None)}


def _record_checkpoint_owner(path, *, locked=False):
    marker = _checkpoint_marker(path)
    with nullcontext() if locked else state_file_lock():
        temporary = marker.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps(_checkpoint_identity(path)), encoding="utf-8")
            os.replace(temporary, marker)
        finally:
            temporary.unlink(missing_ok=True)


def _owned_checkpoint_identity(path):
    """Ownership requires both the app folder and a matching file identity."""
    path = Path(path).resolve()
    if path.parent != default_checkpoint().parent.resolve():
        return None
    try:
        identity = _checkpoint_identity(path)
        if json.loads(_checkpoint_marker(path).read_text(encoding="utf-8")) == identity:
            return identity
    except (OSError, ValueError):
        pass
    return None


def _cleanup_old_checkpoints(target):
    # Called with the publication lock held so simultaneous recoveries cannot
    # delete each other's newly published files.
    candidates = [target.parent / CHECKPOINT_FILE]
    try:
        candidates.extend(target.parent.glob("piano-*.pth"))
    except OSError:
        pass
    for path in candidates:
        try:
            if path == target or (path.name != CHECKPOINT_FILE and
                                 not re.fullmatch(r"piano-[0-9a-f]{32}\.pth", path.name)):
                continue
            identity = _owned_checkpoint_identity(path)
            if identity is not None:
                _remove_owned_corrupt_checkpoint(path, identity, locked=True)
        except OSError:
            pass  # One inaccessible file must not prevent cleaning the others.


def _remove_owned_corrupt_checkpoint(path, expected_identity, *, locked=False):
    """Never infer ownership merely from a filename or directory."""
    marker = _checkpoint_marker(path)
    with nullcontext() if locked else state_file_lock():
        try:
            identity = json.loads(marker.read_text(encoding="utf-8"))
            if identity != expected_identity or identity != _checkpoint_identity(path):
                return False
        except (OSError, ValueError):
            return False
        try:
            Path(path).unlink()
            marker.unlink(missing_ok=True)
        except OSError:
            return False  # Keep locked files and their ownership proof for later.
        return True


def _checkpoint_marker(path):
    path = Path(path)
    return (path.parent / CHECKPOINT_OWNERSHIP_FILE if path.name == CHECKPOINT_FILE
            else path.with_suffix(".owner.json"))


def checkpoint_valid_size(path):
    # The exact audited model size prevents accepting larger partial/foreign files.
    path = Path(path)
    return path.is_file() and path.stat().st_size == CHECKPOINT_EXPECTED_BYTES


def _checkpoint_verification(path):
    stat = Path(path).stat()
    record = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
              "inode": stat.st_ino, "birth_time": getattr(stat, "st_birthtime", None),
              "sha256": CHECKPOINT_SHA256}
    if os.name != "nt":
        record["ctime_ns"] = stat.st_ctime_ns
    return record


def _read_checkpoint_verifications():
    path = app_data_dir() / CHECKPOINT_FOLDER / "verified-checkpoints.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return records if isinstance(records, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_checkpoint_verifications(records):
    # Caller holds the state lock. Verification is an optimization, not ownership.
    path = app_data_dir() / CHECKPOINT_FOLDER / "verified-checkpoints.json"
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(records), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass  # A read-only cache still permits fully verified model loading.
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _move_checkpoint_verification(temporary, target):
    # Rename preserves identity; reuse the digest checked before publication.
    try:
        records = _read_checkpoint_verifications()
        previous = records.pop(str(Path(temporary).resolve()), None)
        current = _checkpoint_verification(target)
        if isinstance(previous, dict) and "ctime_ns" in current:
            # POSIX rename itself changes ctime, without changing the contents.
            previous["ctime_ns"] = current["ctime_ns"]
        if previous == current:
            records[str(Path(target).resolve())] = current
            _write_checkpoint_verifications(records)
    except OSError:
        pass  # Bookkeeping cannot fail an already-published download.


def _validate_checkpoint(path):
    if not checkpoint_valid_size(path) or Path(path).stat().st_size < CHECKPOINT_MIN_BYTES:
        raise ConversionError("Checkpoint size is invalid. Choose the verified piano checkpoint or download it again.")
    if CHECKPOINT_SHA256 is not None:
        path = Path(path).resolve()
        with state_file_lock():
            current = _checkpoint_verification(path)
            records = _read_checkpoint_verifications()
            if records.get(str(path)) == current:
                return
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != CHECKPOINT_SHA256:
            raise ConversionError("Checkpoint checksum is invalid.")
        with state_file_lock():
            if _checkpoint_verification(path) != current:
                raise ConversionError("The checkpoint changed during verification; retry.")
            records = _read_checkpoint_verifications()
            records[str(path)] = current
            _write_checkpoint_verifications(records)


def load_model(path):
    if multiprocessing.parent_process() is None:
        raise ConversionError("Model loading is restricted to the spawned conversion worker.")
    import torch
    from piano_transcription_inference import PianoTranscription
    from unittest.mock import patch
    _validate_checkpoint(path)
    torch.set_num_threads(min(CONVERSION_CPU_THREADS, os.cpu_count() or 1))
    # Defense against a deletion/size race between our verification and its
    # constructor: the pinned package must never call its wget branch.
    with patch("os.system", side_effect=ConversionError("The checkpoint changed before loading; retry.")):
        return PianoTranscription(checkpoint_path=str(Path(path).resolve()), device="cpu")


def prepare_model(job_id, checkpoint_path=None, allow_download=False, progress=None, force_download=False):
    progress = progress or (lambda message: None)
    target = default_checkpoint()
    if checkpoint_path and not force_download:
        if _owned_checkpoint_identity(checkpoint_path) is not None:
            target = Path(checkpoint_path).resolve()
        else:
            # User-selected files are never modified or removed, even if invalid.
            try:
                return load_model(checkpoint_path), str(Path(checkpoint_path).resolve())
            except Exception as exc:
                raise ConversionError(f"Cannot load the selected checkpoint; the original file was kept. {exc}") from exc
    if not checkpoint_path and not force_download and not target.exists():
        with state_file_lock():
            newest = None
            for candidate in target.parent.glob("piano-*.pth"):
                try:
                    if (re.fullmatch(r"piano-[0-9a-f]{32}\.pth", candidate.name) and
                            _owned_checkpoint_identity(candidate) is not None):
                        modified = candidate.stat().st_mtime_ns
                        if newest is None or modified > newest[0]:
                            newest = (modified, candidate)
                except OSError:
                    continue
            if newest is not None:
                target = newest[1]
    if target.exists() and not force_download:
        cache_identity = _checkpoint_identity(target)
        try:
            return load_model(target), str(target)
        except Exception as exc:
            if _remove_owned_corrupt_checkpoint(target, cache_identity):
                raise ConversionError(f"The corrupt app-downloaded checkpoint was removed. Download it again. {exc}") from exc
            # Pre-existing/manual caches without proof of ownership are preserved.
            raise ConversionError(f"The cached checkpoint cannot load. Choose a valid checkpoint. {exc}") from exc
    if not allow_download:
        raise ConversionError("Checkpoint download approval is required, or choose an existing checkpoint.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = registered_temp(target.parent, job_id)
    started = time.monotonic()
    try:
        progress({"type": "stage", "stage": "downloading", "started": started,
                  "timeout": CHECKPOINT_DOWNLOAD_TIMEOUT_SECONDS})
        with urllib.request.urlopen(CHECKPOINT_URL, timeout=CHECKPOINT_STALL_TIMEOUT_SECONDS) as response:
            received = 0
            with temporary.open("wb") as output:
                while True:
                    if time.monotonic() - started > CHECKPOINT_DOWNLOAD_TIMEOUT_SECONDS:
                        raise ConversionError("Checkpoint download timed out. Try again.")
                    chunk = response.read(CHECKPOINT_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > CHECKPOINT_EXPECTED_BYTES:
                        raise ConversionError("Checkpoint download has an unexpected size.")
                    output.write(chunk)
                    progress({"type": "download", "bytes": received, "total": CHECKPOINT_EXPECTED_BYTES})
                output.flush()
                os.fsync(output.fileno())
        progress({"type": "stage", "stage": "loading_model"})
        model = load_model(temporary)  # Includes size validation and actual load.
        try:
            with state_file_lock():
                if force_download:
                    # Recheck ownership under the lock before replacing any file.
                    if target.exists() and _owned_checkpoint_identity(target) is None:
                        target = target.with_name(f"piano-{uuid.uuid4().hex}.pth")
                        os.rename(temporary, target)
                    else:
                        try:
                            os.replace(temporary, target)
                        except PermissionError:
                            target = target.with_name(f"piano-{uuid.uuid4().hex}.pth")
                            os.rename(temporary, target)
                else:
                    os.rename(temporary, target)  # Windows: never overwrite a concurrent download.
                _record_checkpoint_owner(target, locked=True)
                _move_checkpoint_verification(temporary, target)
                if force_download:
                    _cleanup_old_checkpoints(target)
        except FileExistsError:
            # Another instance won; verify the shared winner rather than replace it.
            model = load_model(target)
        return model, str(target)
    except Exception as exc:
        raise ConversionError(f"Checkpoint download or validation failed. {exc}") from exc
    finally:
        forget_temp(temporary, delete=True)


def output_temporary(source, job_id, fallback_dir=None):
    directories = [Path(source).resolve().parent,
                   Path(fallback_dir) if fallback_dir else app_data_dir() / CONVERTED_OUTPUT_FOLDER]
    last_error = None
    for index, directory in enumerate(directories):
        try:
            if index:
                directory.mkdir(parents=True, exist_ok=True)
            return registered_temp(directory, job_id)
        except OSError as exc:
            last_error = exc
    raise ConversionError(f"Cannot write MIDI beside the source or in the fallback folder: {last_error}")


def validate_midi(path):
    import mido
    try:
        midi = mido.MidiFile(str(path))
        if not any(message.type == "note_on" and message.velocity > 0
                   for track in midi.tracks for message in track):
            raise ConversionError("No piano notes detected.")
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"The generated MIDI is invalid. {exc}") from exc


def publish_midi(temporary, source):
    """Windows no-clobber rename; validate before making a final name visible."""
    if os.name != "nt":
        raise ConversionError("Collision-safe publication is currently supported on Windows only.")
    validate_midi(temporary)
    temporary = Path(temporary)
    stem = Path(source).stem
    index = 0
    while True:
        name = f"{stem}.mid" if index == 0 else f"{stem} ({index}).mid"
        final = temporary.parent / name
        try:
            os.rename(temporary, final)
            return str(final)
        except FileExistsError:
            index += 1
