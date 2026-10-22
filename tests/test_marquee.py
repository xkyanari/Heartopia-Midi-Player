"""Marquee timing checks run without Tk; widget checks skip without a display."""
from contextlib import ExitStack
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from ui_theme import MarqueeLabel


class MarqueeTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.font = Mock()
        self.font.measure.side_effect = lambda text: len(text) * 10
        self.font.metrics.return_value = 20
        stack.enter_context(patch("ui_theme.tkfont.Font", return_value=self.font))
        stack.enter_context(patch.object(tk.Canvas, "__init__", return_value=None))
        for name in ("bind", "coords", "itemconfigure"):
            stack.enter_context(patch.object(tk.Canvas, name))
        stack.enter_context(patch.object(tk.Canvas, "create_text", return_value=1))
        stack.enter_context(patch.object(tk.Canvas, "winfo_width", return_value=104))
        self.pending = {}
        self.delays = []
        self.next_id = 0

        def schedule(widget, delay, callback):
            self.next_id += 1
            timer = f"timer-{self.next_id}"
            self.pending[timer] = callback
            self.delays.append(delay)
            return timer

        def cancel(widget, timer):
            del self.pending[timer]

        stack.enter_context(patch.object(tk.Canvas, "after", schedule))
        stack.enter_context(patch.object(tk.Canvas, "after_cancel", cancel))
        self.widget = MarqueeLabel(None, text="short", font=("Segoe UI", 13, "bold"),
                                   bg="#000000", fg="#ffffff")

    def tick(self):
        self.assertEqual(len(self.pending), 1)
        callback = self.pending.pop(self.widget._timer)
        callback()

    def test_fitting_text_and_nothing_playing_stay_still(self):
        self.widget._restart()
        self.widget.config(text="ten letters"[:10])  # Exactly the available width.
        self.assertFalse(self.pending)
        self.widget.config(text="Nothing Playing")  # Even at a narrow width.
        self.assertFalse(self.pending)
        self.assertEqual(self.widget._offset, 0)

    def test_long_text_scrolls_and_pauses_at_both_ends(self):
        self.widget.config(text="longer title")
        self.assertEqual(self.widget._limit, 20)
        self.assertEqual(self.delays[-1], 1500)
        for _ in range(10):
            self.tick()
        self.assertEqual(self.widget._offset, 20)
        self.assertEqual(self.widget._direction, -1)
        self.assertEqual(self.delays[-1], 1500)
        self.tick()
        self.assertEqual(self.widget._offset, 18)
        self.assertEqual(self.delays[-1], 35)
        for _ in range(9):
            self.tick()
        self.assertEqual(self.widget._offset, 0)
        self.assertEqual(self.widget._direction, 1)
        self.assertEqual(self.delays[-1], 1500)
        self.tick()
        self.assertEqual(self.widget._offset, 2)

    def test_text_change_and_resize_restart_with_one_timer(self):
        self.widget.config(text="longer title")
        self.tick()
        previous = self.widget._timer
        self.widget.config(text="another long title")
        self.assertEqual(self.widget.cget("text"), "another long title")
        self.assertEqual(self.widget._offset, 0)
        self.assertNotIn(previous, self.pending)
        self.assertEqual(len(self.pending), 1)
        self.tick()
        self.widget._restart(SimpleNamespace(width=106))
        self.assertEqual(self.widget._offset, 0)
        self.assertEqual(self.widget._direction, 1)
        self.assertEqual(len(self.pending), 1)
        self.widget._restart(SimpleNamespace(width=300))
        self.assertFalse(self.pending)

    def test_destroy_cancels_timer_and_stops_callbacks(self):
        self.widget.config(text="longer title")
        callback = self.pending[self.widget._timer]
        self.widget._on_destroy(SimpleNamespace(widget=self.widget))
        self.assertFalse(self.pending)
        self.assertIsNone(self.widget._timer)
        callback()
        self.widget._restart()
        self.assertFalse(self.pending)


class MarqueeWidgetTests(unittest.TestCase):
    def test_parent_destruction_cancels_real_tk_timer(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(root.destroy)
        frame = tk.Frame(root, width=100, height=40)
        frame.pack()
        frame.pack_propagate(False)
        widget = MarqueeLabel(frame, text="long song title " * 20,
                              font=("Segoe UI", 13, "bold"), bg="#000000", fg="#ffffff")
        widget.pack(fill=tk.X)
        root.update()
        timer = widget._timer
        self.assertIsNotNone(timer)
        frame.destroy()
        self.assertIsNone(widget._timer)
        self.assertNotIn(timer, root.tk.call("after", "info"))
        root.update()
