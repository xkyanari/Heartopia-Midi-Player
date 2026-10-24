import json
import os
import tempfile
import time
from contextlib import contextmanager

from app_config import (
    APP_DATA_FOLDER, DEFAULT_INSTRUMENT, DEFAULT_LAYOUT, DURATION_CACHE_FILE, LAYOUT_FILE,
    PLAYLIST_FILE,
    STATE_LOCK_FILE, STATE_LOCK_POLL_SECONDS, STATE_LOCK_TIMEOUT_SECONDS,
)


@contextmanager
def state_file_lock():
    """Shared cross-process lock for settings and the future temp-file registry."""
    import msvcrt

    app_data = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_DATA_FOLDER
    )
    os.makedirs(app_data, exist_ok=True)
    # Lock a separate, persistent file: replacing a JSON file must not replace
    # the lock itself. Never unlink this file while another instance may use it.
    with open(os.path.join(app_data, STATE_LOCK_FILE), "a+b") as lock:
        deadline = time.monotonic() + STATE_LOCK_TIMEOUT_SECONDS
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another app instance is saving settings. Try again.")
                time.sleep(STATE_LOCK_POLL_SECONDS)
        try:
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"\0")
                lock.flush()
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def load_settings():
    """Read settings without creating or repairing a missing/corrupt file."""
    try:
        with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def save_settings(updates):
    """Merge only supplied keys under the shared lock, then publish atomically."""
    with state_file_lock():
        data = load_settings()
        data.update(updates)
        destination = os.path.abspath(LAYOUT_FILE)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(destination),
                prefix=".settings-", suffix=".tmp", delete=False,
            ) as f:
                temporary = f.name
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)


def save_playlist_paths(paths):
    with open(PLAYLIST_FILE, "w") as f:
        json.dump(paths, f)


def load_playlist_paths():
    if not os.path.exists(PLAYLIST_FILE):
        return []
    try:
        with open(PLAYLIST_FILE, "r") as f:
            return [path for path in json.load(f) if os.path.exists(path)]
    except Exception:
        return []


def load_duration_cache():
    """{normalized path: {"size", "mtime_ns", "duration"}}; empty when missing or corrupt."""
    try:
        with open(DURATION_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_duration_cache(cache):
    """Best effort: the cache only speeds up startup, so write failures are ignored."""
    temporary = DURATION_CACHE_FILE + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(temporary, DURATION_CACHE_FILE)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def write_m3u(path, songs):
    """Winamp-style extended M3U (UTF-8). songs: dicts with name, path and duration.

    Paths are written relative to the playlist when possible, so a folder of
    songs plus its playlist can be moved together.
    """
    folder = os.path.dirname(os.path.abspath(path))
    lines = ["#EXTM3U"]
    for song in songs:
        seconds = -1 if song.get("duration") is None else round(song["duration"])
        try:
            location = os.path.relpath(song["path"], folder)
        except ValueError:  # Different drive on Windows.
            location = os.path.abspath(song["path"])
        lines += [f"#EXTINF:{seconds},{song['name']}", location]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def read_m3u(path):
    """[(absolute song path, seconds or None)] from an M3U/M3U8 playlist."""
    folder = os.path.dirname(os.path.abspath(path))
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = [line.strip() for line in f]
    songs, seconds = [], None
    for line in lines:
        if line.upper().startswith("#EXTINF:"):
            try:
                value = int(line[8:].split(",", 1)[0])
                seconds = value if value >= 0 else None
            except ValueError:
                seconds = None
        elif line and not line.startswith("#"):
            songs.append((os.path.normpath(os.path.join(folder, line)), seconds))
            seconds = None
    return songs


def save_layout_settings(layout, instrument):
    save_settings({"layout": layout, "instrument": instrument})


def load_layout_settings():
    try:
        data = load_settings()
    except OSError:
        return DEFAULT_LAYOUT, DEFAULT_INSTRUMENT
    return (
        data.get("layout", DEFAULT_LAYOUT),
        data.get("instrument", DEFAULT_INSTRUMENT),
    )
