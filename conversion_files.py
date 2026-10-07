"""App-owned temporary files. No model, audio, or Tk imports."""
import json
import os
from pathlib import Path
import time
import uuid

from app_config import (
    APP_DATA_FOLDER, CONVERSION_REGISTRY_FILE, CONVERSION_TEMP_PREFIX,
    CONVERSION_TEMP_SUFFIX,
)
from app_storage import state_file_lock


def app_data_dir():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_DATA_FOLDER


def process_identity():
    import psutil
    return {"pid": os.getpid(), "start_time": psutil.Process().create_time()}


def owner_alive(entry):
    import psutil
    try:
        process = psutil.Process(entry["pid"])
        return process.is_running() and process.create_time() == entry["start_time"]
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True  # Uncertain ownership must never authorize deletion.


def _read_registry():
    path = app_data_dir() / CONVERSION_REGISTRY_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Invalid conversion temporary-file registry")
    return data


def _write_registry(data):
    path = app_data_dir() / CONVERSION_REGISTRY_FILE
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def registered_temp(directory, job_id):
    """Register before creating; creation and registration share the state lock."""
    directory = Path(directory).resolve()
    name = f"{CONVERSION_TEMP_PREFIX}{uuid.uuid4().hex}{CONVERSION_TEMP_SUFFIX}"
    path = directory / name
    entry = dict(process_identity(), path=str(path), job_id=job_id, created=time.time())
    with state_file_lock():
        data = _read_registry()
        data[str(path)] = entry
        _write_registry(data)
        try:
            with path.open("xb"):
                pass
        except BaseException:
            data.pop(str(path))
            _write_registry(data)
            raise
    return path


def forget_temp(path, delete=False):
    path = Path(path).resolve()
    with state_file_lock():
        data = _read_registry()
        entry = data.get(str(path))
        if entry is None:
            return
        identity = process_identity()
        if any(entry[key] != identity[key] for key in ("pid", "start_time")):
            raise PermissionError("Cannot remove another process's temporary file")
        if delete:
            path.unlink(missing_ok=True)
        data.pop(str(path))
        _write_registry(data)


def cleanup_stale(job_id=None):
    """Delete only registered app temps with a confirmed dead owner.

    Return paths that could not be deleted for a non-modal cleanup warning.
    The same lock is used by settings saves and all registry operations.
    """
    failed = []
    with state_file_lock():
        data = _read_registry()
        for key, entry in list(data.items()):
            if job_id is not None and entry.get("job_id") != job_id:
                continue
            path = Path(entry["path"])
            if (not path.is_absolute() or str(path) != key or
                    not path.name.startswith(CONVERSION_TEMP_PREFIX) or
                    not path.name.endswith(CONVERSION_TEMP_SUFFIX)):
                failed.append(str(path))
                continue
            if owner_alive(entry):
                continue
            try:
                path.unlink(missing_ok=True)
                data.pop(key)
            except OSError:
                failed.append(str(path))
        _write_registry(data)
    return failed
