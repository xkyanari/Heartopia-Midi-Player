"""Six player designs, independent of Tk and persisted settings."""
from types import SimpleNamespace

import app_config as config

DEFAULT_THEME = "Midnight Blue (current)"
COLOR_ROLES = (
    "BACKGROUND_COLOR", "PANEL_COLOR", "CARD_COLOR", "BUTTON_COLOR",
    "HOVER_COLOR", "BUTTON_TEXT_COLOR", "ACCENT_COLOR", "ACCENT_HOVER_COLOR",
    "ACCENT_TEXT_COLOR", "TEXT_COLOR", "MUTED_TEXT_COLOR", "FOOTER_TEXT_COLOR",
    "SEPARATOR_COLOR", "SELECTION_COLOR",
)
SECTIONS = ("song", "instrument", "transport", "modes", "playlist")


def blend(color, target, amount=0.18):
    channels = [round(int(color[i:i + 2], 16) * (1 - amount) +
                      int(target[i:i + 2], 16) * amount) for i in (1, 3, 5)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def draft(name, colors, *, order=SECTIONS, columns=3, padding=10, title_size=13):
    bg, panel, button, text, muted, line, accent, on_accent, selected = colors.split()
    return SimpleNamespace(
        name=name, sections=order, columns=columns, padding=padding,
        title_size=title_size, labelled=True,
        BACKGROUND_COLOR=bg, PANEL_COLOR=panel, CARD_COLOR=panel,
        BUTTON_COLOR=button, HOVER_COLOR=blend(button, text),
        BUTTON_TEXT_COLOR=text, TEXT_COLOR=text, MUTED_TEXT_COLOR=muted,
        FOOTER_TEXT_COLOR=muted, SEPARATOR_COLOR=line, ACCENT_COLOR=accent,
        ACCENT_HOVER_COLOR=blend(accent, text), ACCENT_TEXT_COLOR=on_accent,
        SELECTION_COLOR=selected,
    )


THEMES = {
    DEFAULT_THEME: SimpleNamespace(
        name=DEFAULT_THEME, sections=SECTIONS, columns=6, padding=10,
        title_size=13, labelled=False,
        **{role: getattr(config, role) for role in COLOR_ROLES}),
    "Midnight Teal": draft("Midnight Teal",
        "#0c141e #14202d #1e3040 #eef5fb #aabbca #324759 #72e1ce #102a26 #203d46"),
    "Paper Sage": draft("Paper Sage",
        "#fafbf8 #ffffff #eff3ee #26362e #52665a #d0dacf #2c674a #ffffff #e6f1e8",
        padding=16, title_size=18),
    "Studio Amber": draft("Studio Amber",
        "#17191d #202329 #2b3038 #f2f3f5 #bac0ca #434a56 #f0bf68 #30230c #3a3329",
        order=("instrument", "song", "transport", "modes", "playlist"),
        columns=2, title_size=16),
    "Soft Plum": draft("Soft Plum",
        "#211c2c #2c2639 #3a314b #f7f1ff #c6b9d8 #574765 #d5b1ff #2c1842 #453454",
        order=("song", "transport", "instrument", "modes", "playlist")),
    "Graphite Blue": draft("Graphite Blue",
        "#11171f #1b232e #273242 #f1f5fc #b6c4d8 #3b4c63 #a0c5ff #112e54 #2b405e",
        order=("playlist", "song", "instrument", "transport", "modes")),
}

DRAFT_BUTTONS = {
    **config.PLAYBACK_BUTTONS,
    "previous": "⏮ Previous", "play_selected": "▶ Play", "next": "⏭ Next",
    "pause_resume": "⏸ Pause", "stop": "⏹ Stop", "play_playlist": "▶▶ Play Playlist",
}


def resolve(name):
    return THEMES.get(name, THEMES[DEFAULT_THEME]) if isinstance(name, str) else THEMES[DEFAULT_THEME]


def playback_labels(theme):
    return DRAFT_BUTTONS if theme.labelled else config.PLAYBACK_BUTTONS
