import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app_storage


def write_settings(directory, worker, barrier):
    os.environ["LOCALAPPDATA"] = directory
    app_storage.LAYOUT_FILE = str(Path(directory) / "layout.json")
    barrier.wait(timeout=20)
    for index in range(12):
        app_storage.save_settings({f"worker_{worker}_{index}": index})


def hold_settings_lock(directory, ready, release):
    os.environ["LOCALAPPDATA"] = directory
    with app_storage.state_file_lock():
        ready.set()
        release.wait(timeout=20)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "layout.json"
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.location = patch.object(app_storage, "LAYOUT_FILE", str(self.path))
        self.location.start()
        self.addCleanup(self.location.stop)

    def test_round_trip_preserves_conversion_and_unknown_keys(self):
        original = {"unknown": {"nested": [1, 2]}, "layout": "15", "instrument": "piano"}
        self.path.write_text(json.dumps(original), encoding="utf-8")
        app_storage.save_settings({"checkpoint_path": "C:/models/piano.pth",
                                   "audio_input_folder": "C:/audio", "last_audio_dir": "C:/other"})
        app_storage.save_layout_settings("22", "violin")
        data = app_storage.load_settings()
        self.assertEqual(data["unknown"], original["unknown"])
        self.assertEqual(data["checkpoint_path"], "C:/models/piano.pth")
        self.assertEqual(data["audio_input_folder"], "C:/audio")
        self.assertEqual(data["last_audio_dir"], "C:/other")
        self.assertEqual(app_storage.load_layout_settings(), ("22", "violin"))

    def test_missing_or_corrupt_settings_are_not_rewritten_by_read(self):
        self.assertEqual(app_storage.load_layout_settings(), ("22", "piano"))
        self.assertFalse(self.path.exists())
        for text in ("{bad json", "[]", "null"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(app_storage.load_layout_settings(), ("22", "piano"))
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)
        app_storage.save_settings({"checkpoint_path": "valid"})
        self.assertEqual(app_storage.load_settings(), {"checkpoint_path": "valid"})

    def test_failed_replace_keeps_original_and_cleans_temporary_file(self):
        self.path.write_text('{"keep": 1}', encoding="utf-8")
        with patch.object(app_storage.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                app_storage.save_settings({"new": 2})
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"keep": 1}')
        self.assertEqual(list(self.path.parent.glob(".settings-*.tmp")), [])
        app_storage.save_settings({"after_failure": True})
        self.assertEqual(app_storage.load_settings(), {"keep": 1, "after_failure": True})

    def test_read_permission_failure_does_not_overwrite_unknown_settings(self):
        self.path.write_text('{"keep": 1}', encoding="utf-8")
        with patch.object(app_storage, "load_settings", side_effect=PermissionError("unreadable")):
            with self.assertRaises(PermissionError):
                app_storage.save_settings({"new": 2})
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"keep": 1}')

    def test_spawned_writers_do_not_lose_updates(self):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(4)
        children = [context.Process(target=write_settings, args=(self.directory.name, i, barrier))
                    for i in range(4)]
        try:
            for child in children:
                child.start()
            for child in children:
                child.join(timeout=30)
                self.assertEqual(child.exitcode, 0)
            data = app_storage.load_settings()
            self.assertEqual(len(data), 48)
            for worker in range(4):
                for index in range(12):
                    self.assertEqual(data[f"worker_{worker}_{index}"], index)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=5)

    def test_real_five_second_lock_timeout_keeps_disk_and_session_settings(self):
        import main
        import time

        original = '{"layout":"22","instrument":"piano","unknown":7}'
        self.path.write_text(original, encoding="utf-8")
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        child = context.Process(target=hold_settings_lock, args=(self.directory.name, ready, release))
        try:
            child.start()
            self.assertTrue(ready.wait(timeout=10))
            with patch.object(main, "current_layout", "15"), \
                 patch.object(main, "current_instrument", "violin"), \
                 patch.object(main, "set_status") as status, \
                 patch.object(main.messagebox, "showerror") as modal:
                started = time.monotonic()
                main.save_layout()
                elapsed = time.monotonic() - started
                self.assertGreaterEqual(elapsed, 5)
                self.assertLess(elapsed, 8)
                status.assert_called_once_with(main.SETTINGS_SAVE_WARNING)
                modal.assert_not_called()
                self.assertEqual((main.current_layout, main.current_instrument), ("15", "violin"))
            self.assertEqual(self.path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(self.path.parent.glob(".settings-*.tmp")), [])
        finally:
            release.set()
            child.join(timeout=5)
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
