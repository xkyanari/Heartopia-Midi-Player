import json
import os

from app_config import DEFAULT_INSTRUMENT, DEFAULT_LAYOUT, LAYOUT_FILE, PLAYLIST_FILE


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


def save_layout_settings(layout, instrument):
    with open(LAYOUT_FILE, "w") as f:
        json.dump({"layout": layout, "instrument": instrument}, f)


def load_layout_settings():
    if not os.path.exists(LAYOUT_FILE):
        return DEFAULT_LAYOUT, DEFAULT_INSTRUMENT
    try:
        with open(LAYOUT_FILE, "r") as f:
            data = json.load(f)
        return (
            data.get("layout", DEFAULT_LAYOUT),
            data.get("instrument", DEFAULT_INSTRUMENT),
        )
    except Exception:
        return DEFAULT_LAYOUT, DEFAULT_INSTRUMENT
