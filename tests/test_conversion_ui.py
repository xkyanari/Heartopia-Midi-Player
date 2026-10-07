"""Phase 3 behavior checks with real Tk widgets and isolated filesystem state."""
import io
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import app_config as config
import app_storage
import audio_converter as converter
import conversion_service as service_module
from conversion_service import ConversionService, scan_audio_folder
from conversion_ui import ConversionUI
import main


class FakeService:
    def __init__(self):
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.scan = Mock()
        self.save = Mock()
        self.preflight = Mock()
        self.start = Mock()
        self.cancel = Mock()
        self.shutdown = Mock()


class DialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.service = FakeService()
        self.status, self.converted = Mock(), Mock()
        self.ui = ConversionUI(self.root, self.converted, self.status, self.service)
        self.ui.ready = True
        self.ui.folder = "C:/audio"
        self.ui.settings = {"checkpoint_path": "C:/old.pth", "instrument": "violin"}
        self.ui.open()
        self.dialog = self.ui.dialog

    def preflight_result(self, exists=True):
        request = self.service.preflight.call_args.args[0]
        self.dialog.handle({"type": "preflight", "request": request, "model_exists": exists})

    def test_browse_filters_and_start_directory(self):
        with patch("conversion_ui.filedialog.askopenfilename", return_value="D:/other/piano.mp3") as picker:
            self.dialog.browse()
        self.assertEqual(picker.call_args.kwargs["initialdir"], "C:/audio")
        self.assertIn("*.m4a", picker.call_args.kwargs["filetypes"][0][1])
        self.assertEqual(self.dialog.source.get(), "D:/other/piano.mp3")
        self.assertEqual(self.ui.settings["last_audio_dir"], "D:\\other")
        self.dialog.folder.set("")
        with patch("conversion_ui.filedialog.askopenfilename", return_value="") as picker:
            self.dialog.browse()
        self.assertEqual(picker.call_args.kwargs["initialdir"], "D:\\other")

    def test_folder_scan_refresh_empty_error_and_stale_reply(self):
        row = {"path": "C:/audio/piano.wav", "name": "piano.wav", "size": 2000, "modified": 0, "midi": True}
        self.dialog.handle({"type": "scan", "token": self.dialog.scan_token, "rows": [row]})
        self.assertEqual(self.dialog.tree.item("0", "values")[-1], "MIDI exists")
        old_token = self.dialog.scan_token
        self.dialog.refresh()
        self.dialog.handle({"type": "scan", "token": old_token, "rows": []})
        self.assertEqual(len(self.dialog.rows), 1)
        self.dialog.handle({"type": "scan", "token": self.dialog.scan_token, "rows": []})
        self.assertEqual(self.dialog.info.get(), config.CONVERSION_EMPTY_TEXT)
        self.dialog.handle({"type": "scan_error", "token": self.dialog.scan_token, "message": "Access denied"})
        self.assertIn("Change folder", self.dialog.info.get())
        with patch("conversion_ui.filedialog.askdirectory", return_value="D:/new"):
            self.dialog.change_folder()
        self.assertEqual(self.ui.settings["audio_input_folder"], "D:/new")
        self.assertEqual(self.ui.settings["instrument"], "violin")

    def test_refresh_passes_configured_output_folder(self):
        self.ui.settings["converted_output_dir"] = "D:/converted"
        self.dialog.refresh()
        self.service.scan.assert_called_with("C:/audio", self.dialog.scan_token, fallback_dir="D:/converted")

    def test_missing_model_prompt_decline_and_accept(self):
        self.dialog.source.set("C:/audio/piano.wav")
        self.dialog.convert()
        with patch.object(self.dialog, "approve_download", return_value=False):
            self.preflight_result(False)
        self.assertFalse(self.ui.busy)
        self.service.start.assert_not_called()
        self.dialog.convert()
        with patch.object(self.dialog, "approve_download", return_value=True):
            self.preflight_result(False)
        self.assertTrue(self.service.start.call_args.args[0]["force_download"])
        self.assertTrue(self.ui.busy)

    def test_redownload_and_manual_model_only_switch_after_validation(self):
        with patch.object(self.dialog, "approve_download", return_value=True):
            self.dialog.redownload()
        self.preflight_result()
        request = self.service.start.call_args.args[0]
        self.assertEqual(request["operation"], "model")
        self.assertTrue(request["force_download"])
        self.assertEqual(self.ui.settings["checkpoint_path"], "C:/old.pth")
        self.service.events.put({"type": "model_ready", "path": "C:/new.pth"})
        self.service.events.put({"type": "model_success", "path": "C:/new.pth"})
        self.service.events.put({"type": "finished"})
        self.ui._poll()
        self.assertEqual(self.ui.settings["checkpoint_path"], "C:/new.pth")
        with patch("conversion_ui.filedialog.askopenfilename", return_value="C:/bad.pth"):
            self.dialog.choose_model()
        self.preflight_result()
        with patch("conversion_ui.messagebox.showerror"):
            self.dialog.handle({"type": "error", "message": "Invalid model"})
        self.dialog.handle({"type": "finished"})
        self.assertEqual(self.ui.settings["checkpoint_path"], "C:/new.pth")

    def test_cancel_preflight_ignores_late_success_and_error(self):
        self.dialog.begin({"source": "missing.wav"})
        request = self.service.preflight.call_args.args[0]
        self.dialog.cancel()
        self.assertFalse(self.ui.busy)
        with patch("conversion_ui.messagebox.showerror") as error:
            self.dialog.handle({"type": "preflight_error", "token": request["_token"], "message": "missing"})
            self.dialog.handle({"type": "preflight", "request": request, "model_exists": True})
        error.assert_not_called()
        self.service.start.assert_not_called()

    def test_cancel_each_worker_stage_waits_until_cleanup(self):
        for stage in config.CONVERSION_STAGES:
            with self.subTest(stage=stage):
                self.dialog.begin({"source": "piano.wav"})
                self.preflight_result()
                self.dialog.handle({"type": "stage", "stage": stage, "started": time.monotonic(), "estimate": 15})
                self.dialog.tick()
                self.dialog.cancel()
                self.assertTrue(self.ui.busy)
                self.dialog.handle({"type": "cancelled", "message": "Conversion cancelled."})
                self.dialog.handle({"type": "finished"})
                self.assertFalse(self.ui.busy)
        self.assertEqual(self.service.cancel.call_count, len(config.CONVERSION_STAGES))

    def test_download_percentage_then_indeterminate_estimate(self):
        self.dialog.begin({"source": "piano.wav"})
        self.dialog.handle({"type": "download", "bytes": 50, "total": 100})
        self.assertEqual(str(self.dialog.progress["mode"]), "determinate")
        self.assertEqual(self.dialog.progress["value"], 50)
        self.dialog.handle({"type": "stage", "stage": "transcribing", "started": time.monotonic(), "estimate": 15})
        self.dialog.tick()
        self.assertEqual(str(self.dialog.progress["mode"]), "indeterminate")
        self.assertIn("Estimate ~15 s", self.dialog.info.get())

    def test_close_cancels_and_keeps_dialog_until_worker_finished(self):
        self.dialog.begin({"source": "piano.wav"})
        self.preflight_result()
        self.dialog.close()
        self.assertIs(self.ui.dialog, self.dialog)
        self.service.cancel.assert_called_once()
        self.dialog.handle({"type": "finished"})
        self.assertIsNone(self.ui.dialog)

    def test_missing_dependencies_show_instructions(self):
        self.ui.missing = ["torch"]
        with patch("conversion_ui.messagebox.showerror") as error:
            self.ui.open()
        self.assertIn("requirements-convert.txt", error.call_args.args[1])

    def test_settings_warning_retains_session_values_without_modal(self):
        self.ui.save({"audio_input_folder": "D:/session"})
        self.service.events.put({"type": "warning", "message": config.SETTINGS_SAVE_WARNING})
        with patch("conversion_ui.messagebox.showerror") as error:
            self.ui._poll()
        self.assertEqual(self.ui.settings["audio_input_folder"], "D:/session")
        self.status.assert_called_with(config.SETTINGS_SAVE_WARNING)
        error.assert_not_called()


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        for context in (patch.dict(os.environ, {"LOCALAPPDATA": self.directory.name}),
                        patch.object(app_storage, "LAYOUT_FILE", str(self.folder / "layout.json")),
                        patch.object(service_module, "default_audio_folder", return_value=self.folder / "audio")):
            context.start()
            self.addCleanup(context.stop)

    def event(self, service, kind):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            event = service.events.get(timeout=5)
            if event["type"] == kind:
                return event
        self.fail(f"No {kind} event")

    def start_service(self):
        service = ConversionService()
        def stop_service():
            service.shutdown()
            self.assertTrue(service.closed.wait(6))
            service.job_thread.join(1)
            service.io_thread.join(1)
        self.addCleanup(stop_service)
        return service

    def test_scan_supported_top_level_sorted_hidden_and_midi(self):
        for name in ("b.MP3", "A.wav", "c.flac", "d.ogg", "e.m4a", ".hidden.wav", "x.txt", "A.mid"):
            (self.folder / name).touch()
        nested = self.folder / "nested"
        nested.mkdir()
        (nested / "no.wav").touch()
        rows = scan_audio_folder(self.folder)
        self.assertEqual([row["name"] for row in rows], ["A.wav", "b.MP3", "c.flac", "d.ogg", "e.m4a"])
        self.assertTrue(rows[0]["midi"])
        import ctypes
        hidden = self.folder / "b.MP3"
        self.assertTrue(ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 2))
        try:
            self.assertNotIn("b.MP3", [row["name"] for row in scan_audio_folder(self.folder)])
        finally:
            ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 128)

    def test_default_creation_startup_cleanup_and_deleted_input(self):
        with patch.object(service_module, "cleanup_stale", return_value=[]) as cleanup, \
             patch.object(service_module, "missing_dependencies", return_value=[]):
            service = self.start_service()
            initialized = self.event(service, "initialized")
            service.preflight({"source": str(self.folder / "gone.wav"), "_token": "test"})
            result = self.event(service, "preflight_error")
            self.assertIn("no longer exists", result["message"])
            self.assertEqual(result["token"], "test")
            self.assertTrue(Path(initialized["folder"]).is_dir())
            cleanup.assert_called_once()

    def test_settings_save_timeout_is_nonmodal_and_does_not_stop_service(self):
        service = self.start_service()
        self.event(service, "initialized")
        with patch.object(service_module, "save_settings", side_effect=TimeoutError):
            service.save({"last_audio_dir": "kept in UI"})
            self.assertEqual(self.event(service, "warning")["message"], config.SETTINGS_SAVE_WARNING)
        self.assertFalse((self.folder / "layout.json").exists())
        service.save({"audio_input_folder": "override", "last_audio_dir": "elsewhere"})
        service.scan(self.folder, "barrier")
        self.event(service, "scan")
        self.assertEqual(app_storage.load_settings()["last_audio_dir"], "elsewhere")

    def test_service_scan_detects_configured_fallback_midi(self):
        fallback = self.folder / "output"
        fallback.mkdir()
        (self.folder / "name.wav").touch()
        (fallback / "name (1).mid").touch()
        service = self.start_service()
        self.event(service, "initialized")
        service.scan(self.folder, "fallback", fallback_dir=fallback)
        result = self.event(service, "scan")
        self.assertEqual(result["token"], "fallback")
        self.assertTrue(result["rows"][0]["midi"])

    def test_main_process_model_guard_never_patches_os_system(self):
        original = os.system
        with patch("unittest.mock.patch", side_effect=AssertionError("Main process patch")):
            with self.assertRaisesRegex(converter.ConversionError, "spawned conversion worker"):
                converter.load_model(self.folder / "anything.pth")
        self.assertIs(os.system, original)

    def test_redownload_preserves_unowned_cache_and_validates_before_publish(self):
        if service_module.importlib.util.find_spec("psutil") is None:
            self.skipTest("Requires conversion environment for registry process identity")
        target = converter.default_checkpoint()
        target.parent.mkdir(parents=True)
        target.write_bytes(b"unowned")
        def validate(path):
            self.assertEqual(target.read_bytes(), b"unowned")
            self.assertEqual(list(target.parent.glob("piano-*.pth")), [])
            return "model"
        with patch.object(converter.urllib.request, "urlopen", return_value=io.BytesIO(b"download")), \
             patch.object(converter, "load_model", side_effect=validate):
            _, path = converter.prepare_model("recovery", str(target), True, force_download=True)
        self.assertNotEqual(Path(path), target)
        self.assertEqual(Path(path).read_bytes(), b"download")
        self.assertEqual(target.read_bytes(), b"unowned")

    def test_saved_folder_override_is_loaded_without_creating_default(self):
        app_storage.save_settings({"audio_input_folder": str(self.folder / "missing"), "last_audio_dir": "D:/last"})
        service = self.start_service()
        initialized = self.event(service, "initialized")
        self.assertEqual(initialized["folder"], str(self.folder / "missing"))
        self.assertEqual(initialized["settings"]["last_audio_dir"], "D:/last")
        self.assertFalse((self.folder / "audio").exists())
        service.scan(initialized["folder"], "missing")
        self.assertEqual(self.event(service, "scan_error")["token"], "missing")


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        box = tk.Listbox(self.root, exportselection=False)
        box.insert(tk.END, "old.mid")
        box.select_set(0)
        for name, value in {"root": self.root, "playlist_box": box, "playlist": [{"name": "old.mid", "path": "old.mid"}],
                            "current_index": 0, "pressed_keys": [], "is_paused": False,
                            "playback_active": True, "playback_after_ids": ["expired-id"]}.items():
            context = patch.object(main, name, value, create=True)
            context.start()
            self.addCleanup(context.stop)
        self.status = patch.object(main, "set_status").start()
        self.addCleanup(patch.stopall)

    def test_natural_completion_selects_and_sets_index_despite_stale_flags(self):
        with patch.object(main, "save_playlist") as save:
            main.add_converted_midi("new.mid")
        self.assertEqual(main.current_index, 1)
        self.assertEqual(main.playlist_box.curselection(), (1,))
        save.assert_called_once()

    def test_paused_pressed_keys_and_pending_transition_preserve_selection(self):
        transition = self.root.after(10000, lambda: None)
        for state in ({"is_paused": True}, {"pressed_keys": ["a"]}, {"playback_after_ids": [transition]}):
            with self.subTest(state=state), patch.multiple(main, **state), patch.object(main, "save_playlist"):
                main.add_converted_midi("new.mid")
                self.assertEqual(main.current_index, 0)
                self.assertEqual(main.playlist_box.curselection(), (0,))
                self.assertIn("Added to playlist", self.status.call_args.args[0])

    def test_playlist_save_error_keeps_file_and_reports_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.mid"
            path.write_bytes(b"saved MIDI")
            with patch.object(main, "save_playlist", side_effect=PermissionError("read only")):
                main.add_converted_midi(str(path))
            self.assertTrue(path.exists())
            self.assertIn(str(path), self.status.call_args.args[0])
            self.assertEqual(len(main.playlist), 2)


if __name__ == "__main__":
    unittest.main()
