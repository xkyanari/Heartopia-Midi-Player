import ctypes

from app_config import HEARTOPIA_WINDOW_TITLES


def switch_to_heartopia():
    try:
        for title in HEARTOPIA_WINDOW_TITLES:
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if hwnd:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                return True
        return False
    except Exception:
        return False


def switch_to_window(hwnd):
    try:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def get_foreground_window_title():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 256)
        return buffer.value
    except Exception:
        return ""
