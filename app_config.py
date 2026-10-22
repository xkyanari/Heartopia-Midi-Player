APP_TITLE = "Heartopia MIDI Player"
APP_VERSION = "v0.4.10"
APP_CREDIT = "By yukiokoito, Modified by Kyanari"

WINDOW_SIZE = "480x560"
BACKGROUND_COLOR = "#090e18"
PANEL_COLOR = "#101a2b"
CARD_COLOR = "#131e30"
BUTTON_COLOR = "#23324a"
HOVER_COLOR = "#344966"
BUTTON_TEXT_COLOR = "#e8f0ff"
ACCENT_COLOR = "#55dfcf"
ACCENT_HOVER_COLOR = "#8aefe3"
ACCENT_TEXT_COLOR = "#092622"
SEPARATOR_COLOR = "#2a3b54"
TEXT_COLOR = "#e8f0ff"
MUTED_TEXT_COLOR = "#a6b6d0"
FOOTER_TEXT_COLOR = "#8194b1"
SELECTION_COLOR = "#254b61"
UI_FONT = ("Segoe UI", 9)
TITLE_FONT = ("Segoe UI", 12, "bold")
PLAYLIST_FONT = ("Segoe UI", 10)
DISPLAY_FONT = ("Segoe UI", 13, "bold")
TRANSPORT_FONT = ("Segoe UI", 13)

PLAYLIST_FILE = "playlist.json"
LAYOUT_FILE = "layout.json"
APP_DATA_FOLDER = "Heartopia-Midi-Player"
STATE_LOCK_FILE = "state.lock"
STATE_LOCK_TIMEOUT_SECONDS = 5
STATE_LOCK_POLL_SECONDS = 0.05
SETTINGS_SAVE_WARNING = "Settings not saved: another instance is busy. Changes are kept for this session."

DEFAULT_LAYOUT = "22"
DEFAULT_INSTRUMENT = "piano"
DEFAULT_STATUS = "No Files Loaded"

KEY_HOLD_MS = 250
PLAYBACK_SPEED = 1.0
PLAYBACK_START_DELAY_MS = 0
FOCUS_CHECK_INTERVAL_MS = 500
PAUSE_POLL_INTERVAL_MS = 100
SONG_END_BUFFER_SECONDS = 6
MUSICAL_CHAIRS_MIN_SECONDS = 15
MUSICAL_CHAIRS_MAX_SECONDS = 25

HEARTOPIA_WINDOW_TITLES = ("Heartopia", "Heartopia.exe", "Heartopia Game")

FILE_BUTTONS = {
    "load_midi": "Load MIDI",
    "delete_selected": "Delete",
}

PLAYBACK_BUTTONS = {
    "previous": "⏮",
    "play_selected": "▶ Play",
    "play_playlist": "▶▶",
    "musical_chairs": "Musical Chairs",
    "pause_resume": "⏯",
    "stop": "⏹",
    "next": "⏭",
    "loop": "↻ Loop",
}
