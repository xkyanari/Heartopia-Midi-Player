"""Pause-aware playback time, independent of Tk and keyboard input."""
import time


def format_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class PlaybackClock:
    def __init__(self, duration, *, speed=1.0, delay=0.0, now=time.monotonic):
        self.duration = max(0.0, duration / speed)
        self.now = now
        self.started = now() + delay
        self.paused_at = None

    def elapsed(self):
        end = self.now() if self.paused_at is None else self.paused_at
        return max(0.0, end - self.started)

    def pause(self):
        if self.paused_at is None:
            self.paused_at = self.now()

    def resume(self):
        if self.paused_at is not None:
            self.started += self.now() - self.paused_at
            self.paused_at = None

    def position(self):
        return min(self.duration, self.elapsed())

    def remaining(self):
        return max(0.0, self.duration - self.elapsed())
