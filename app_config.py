APP_TITLE = "Heartopia MIDI Player"
APP_VERSION = "v0.4.9"
APP_CREDIT = "by yukiokoito, modified by Kyanari"

WINDOW_SIZE = "430x440"
BACKGROUND_COLOR = "#292b3d"
PANEL_COLOR = "#080e0b"
CARD_COLOR = "#3c4056"
BUTTON_COLOR = "#b2b5c3"
HOVER_COLOR = "#d1d4df"
BUTTON_TEXT_COLOR = "#161925"
ACCENT_COLOR = "#b6ed74"
ACCENT_HOVER_COLOR = "#d0ff96"
ACCENT_TEXT_COLOR = "#15210b"
SEPARATOR_COLOR = "#71778e"
TEXT_COLOR = "#b6ed74"
MUTED_TEXT_COLOR = "#d4d7e2"
FOOTER_TEXT_COLOR = "#9299ae"
SELECTION_COLOR = "#30492a"
UI_FONT = ("Tahoma", 9)
TITLE_FONT = ("Tahoma", 9, "bold")
PLAYLIST_FONT = ("Consolas", 10)
DISPLAY_FONT = ("Consolas", 12, "bold")
TRANSPORT_FONT = ("Segoe UI", 11)

PLAYLIST_FILE = "playlist.json"
LAYOUT_FILE = "layout.json"
APP_DATA_FOLDER = "Heartopia-Midi-Player"
STATE_LOCK_FILE = "state.lock"
STATE_LOCK_TIMEOUT_SECONDS = 5
STATE_LOCK_POLL_SECONDS = 0.05
SETTINGS_SAVE_WARNING = "Settings not saved: another instance is busy. Changes are kept for this session."

SUPPORTED_AUDIO_EXTS = (".wav", ".flac", ".mp3", ".ogg", ".m4a")
CONVERTED_OUTPUT_FOLDER = "converted"
CONVERSION_REGISTRY_FILE = "conversion-temps.json"
CONVERSION_TEMP_PREFIX = "heartopia-convert-"
CONVERSION_TEMP_SUFFIX = ".part"
CONVERSION_MAX_AUDIO_SECONDS = 20 * 60
CONVERSION_MIN_TIMEOUT_SECONDS = 10 * 60
CONVERSION_TIMEOUT_AUDIO_FACTOR = 3
CONVERSION_ESTIMATE_AUDIO_FACTOR = 1.5
CONVERSION_CPU_THREADS = 4
CONVERSION_PARENT_POLL_SECONDS = 0.2
CHECKPOINT_FOLDER = "models"
CHECKPOINT_FILE = "note_F1=0.9677_pedal_F1=0.9186.pth"
CHECKPOINT_OWNERSHIP_FILE = "checkpoint-owner.json"
# Audited from piano_transcription_inference 0.0.6, inference.py:31-35.
CHECKPOINT_URL = "https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
CHECKPOINT_MIN_BYTES = 160_000_000
CHECKPOINT_EXPECTED_BYTES = 171_966_578
# SHA-256 of the exact-size checkpoint from CHECKPOINT_URL.
CHECKPOINT_SHA256 = "c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141"
CHECKPOINT_DOWNLOAD_TIMEOUT_SECONDS = 600
CHECKPOINT_STALL_TIMEOUT_SECONDS = 15
CHECKPOINT_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
CONVERSION_INSTALL_COMMAND = "python -m pip install -r requirements-convert.txt"
DEFAULT_AUDIO_FOLDER = "audio"
CONVERSION_UI_POLL_MS = 100
CONVERSION_SERVICE_POLL_SECONDS = 0.05
CONVERSION_DIALOG_SIZE = "760x570"
CONVERSION_TITLE = "Convert Piano Audio to MIDI…"
CONVERSION_SCOPE_TEXT = "Works best on solo piano recordings. Other instruments or full mixes give poor results."
CONVERSION_CPU_TEXT = "Conversion takes roughly 1–2× the song length on CPU."
CONVERSION_EMPTY_TEXT = "No audio files found"
CONVERSION_BUTTONS = {
    "browse": "Browse…", "folder": "Change folder…", "refresh": "Refresh",
    "model": "Choose model file…", "download": "Re-download model",
    "convert": "Convert", "cancel": "Cancel",
}
CONVERSION_STAGES = {
    "dependencies": "Loading conversion libraries…", "decoding": "Decoding audio…",
    "checkpoint": "Checking model…", "downloading": "Downloading model…",
    "loading_model": "Validating model…", "transcribing": "Transcribing…",
    "validating": "Validating MIDI…",
}
CONVERSION_STANDARD_BUILD_TEXT = "Conversion requires the conversion-enabled build."

DEFAULT_LAYOUT = "22"
DEFAULT_INSTRUMENT = "piano"
DEFAULT_STATUS = "No files loaded"

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
    "convert_audio": "Convert Audio",
}

PLAYBACK_BUTTONS = {
    "previous": "⏮",
    "play_selected": "▶",
    "play_playlist": "▶▶",
    "musical_chairs": "Musical Chairs",
    "pause_resume": "⏯",
    "stop": "⏹",
    "next": "⏭",
    "loop": "↻ Loop",
}
