import keyboard


# IBM PC/AT set-1 scan codes for a US QWERTY keyboard layout.
# Keeping these explicit avoids translating through the active Windows layout.
US_SCAN_CODES = {
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    "-": 12,
    "=": 13,
    "q": 16,
    "w": 17,
    "e": 18,
    "r": 19,
    "t": 20,
    "y": 21,
    "u": 22,
    "i": 23,
    "o": 24,
    "p": 25,
    "[": 26,
    "]": 27,
    "a": 30,
    "s": 31,
    "d": 32,
    "f": 33,
    "g": 34,
    "h": 35,
    "j": 36,
    "k": 37,
    "l": 38,
    ";": 39,
    "'": 40,
    "`": 41,
    "\\": 43,
    "z": 44,
    "x": 45,
    "c": 46,
    "v": 47,
    "b": 48,
    "n": 49,
    "m": 50,
    ",": 51,
    ".": 52,
    "/": 53,
}


def create_key_descriptor(key_name):
    """Return a layout-independent key descriptor for a US keyboard key."""
    try:
        scan_code = US_SCAN_CODES[key_name]
    except KeyError as exc:
        raise ValueError(f"No US scan code configured for key: {key_name}") from exc
    return {"name": key_name, "scan_code": scan_code}


def create_scan_code_note_map(note_to_key):
    return {
        note: create_key_descriptor(key_name)
        for note, key_name in note_to_key.items()
    }


def press_key(descriptor):
    keyboard.send(_scan_code_for(descriptor), do_press=True, do_release=False)


def release_key(descriptor):
    keyboard.send(_scan_code_for(descriptor), do_press=False, do_release=True)


def _scan_code_for(descriptor):
    if isinstance(descriptor, dict):
        return descriptor["scan_code"]
    return US_SCAN_CODES[descriptor]
