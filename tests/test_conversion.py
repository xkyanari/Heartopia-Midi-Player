import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

import audio_converter as converter
import conversion_files as files
from conversion_job import ConversionJob
from conversion_service import scan_audio_folder


class OutputFolderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.fallback = self.folder / "fallback"

    def test_generic_oserror_uses_fallback(self):
        temporary = self.fallback / "output.part"
        with patch.object(converter, "registered_temp", side_effect=[OSError("disk full"), temporary]) as register:
            self.assertEqual(converter.output_temporary(self.folder / "name.wav", "job", self.fallback), temporary)
        self.assertTrue(self.fallback.is_dir())
        self.assertEqual(register.call_args_list[0].args, (self.folder, "job"))
        self.assertEqual(register.call_args_list[1].args, (self.fallback, "job"))

    def test_non_oserror_propagates_without_fallback(self):
        with patch.object(converter, "registered_temp", side_effect=ValueError("invalid registry")) as register:
            with self.assertRaisesRegex(ValueError, "invalid registry"):
                converter.output_temporary(self.folder / "name.wav", "job", self.fallback)
        register.assert_called_once()
        self.assertFalse(self.fallback.exists())

    def test_both_output_folders_fail_with_existing_message(self):
        with patch.object(converter, "registered_temp", side_effect=[OSError("disk full"), OSError("share unavailable")]):
            with self.assertRaisesRegex(converter.ConversionError,
                                        "Cannot write MIDI beside the source or in the fallback folder: share unavailable"):
                converter.output_temporary(self.folder / "name.wav", "job", self.fallback)

    def test_scan_detects_exact_numbered_and_fallback_midi_case_insensitively(self):
        self.fallback.mkdir()
        for name in ("exact.wav", "numbered.mp3", "saved.flac", "saved copy.ogg", "name.wav"):
            (self.folder / name).touch()
        for name in ("EXACT.MID", "NUMBERED (1).mid", "name2.mid", "name (0).mid", "name (-1).mid",
                     "name (x).mid", "name (1) extra.mid"):
            (self.folder / name).touch()
        (self.folder / "name (2).mid").mkdir()
        (self.fallback / "SAVED.mid").touch()
        (self.fallback / "SAVED COPY (12).MID").touch()
        with patch("conversion_service.os.scandir", wraps=os.scandir) as scan:
            rows = scan_audio_folder(self.folder, self.fallback)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual({row["name"]: row["midi"] for row in rows},
                         {"exact.wav": True, "numbered.mp3": True, "saved.flac": True,
                          "saved copy.ogg": True, "name.wav": False})

    def test_scan_uses_default_fallback(self):
        fallback = self.folder / converter.CONVERTED_OUTPUT_FOLDER
        fallback.mkdir()
        (self.folder / "name.wav").touch()
        (fallback / "name (1).mid").touch()
        with patch("conversion_service.app_data_dir", return_value=self.folder):
            self.assertTrue(scan_audio_folder(self.folder)[0]["midi"])

    def test_missing_or_unreadable_fallback_keeps_source_listing(self):
        (self.folder / "name.wav").touch()
        (self.folder / "name.mid").touch()
        self.assertTrue(scan_audio_folder(self.folder, self.fallback)[0]["midi"])
        scan = os.scandir
        def unavailable(folder):
            if Path(folder) == self.fallback:
                raise OSError("share unavailable")
            return scan(folder)
        with patch("conversion_service.os.scandir", side_effect=unavailable):
            self.assertTrue(scan_audio_folder(self.folder, self.fallback)[0]["midi"])

    def test_same_directory_is_listed_once(self):
        (self.folder / "name.wav").touch()
        (self.folder / "name (1).mid").touch()
        with patch("conversion_service.os.scandir", wraps=os.scandir) as scan:
            self.assertTrue(scan_audio_folder(self.folder, self.folder)[0]["midi"])
        scan.assert_called_once()


def make_midi(path, notes=True):
    import mido
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    if notes:
        track.append(mido.Message("note_on", note=60, velocity=80))
        track.append(mido.Message("control_change", control=64, value=127))
        track.append(mido.Message("note_off", note=60, time=100))
        track.append(mido.Message("control_change", control=64, value=0))
    else:
        track.append(mido.Message("note_on", note=60, velocity=0))
    midi.save(str(path))


def collision_writer(folder, barrier, results):
    os.environ["LOCALAPPDATA"] = folder
    temporary = files.registered_temp(folder, str(os.getpid()))
    make_midi(temporary)
    barrier.wait(timeout=10)
    results.put(converter.publish_midi(temporary, "same.wav"))
    files.forget_temp(temporary)


def idle_worker(request, messages):
    temporary = files.registered_temp(request["source"], request["job_id"])
    temporary.write_bytes(b"partial")
    messages.put({"type": "stage", "stage": "transcribing", "started": time.monotonic(),
                  "timeout": .1 if request.get("fallback_dir") == "timeout" else 600,
                  "path": str(temporary)})
    time.sleep(30)


def dead_worker(request, messages):
    files.registered_temp(request["source"], request["job_id"])
    os._exit(9)


def stalled_download_worker(request, messages):
    files.registered_temp(request["source"], request["job_id"])
    messages.put({"type": "stage", "stage": "downloading", "started": time.monotonic(), "timeout": .1})
    time.sleep(30)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        try:
            import av, numpy, psutil
        except ImportError:
            self.skipTest("Run conversion tests in the requirements-convert environment")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def audio(self, name="sample.wav", silent=False):
        import numpy as np
        path = self.folder / name
        values = np.zeros(1600, dtype="int16") if silent else (np.sin(np.arange(1600) * .1) * 5000).astype("int16")
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(values.tobytes())
        return path

    def test_decoding_and_bad_inputs(self):
        audio = converter.decode_audio(self.audio(), 16000)
        self.assertEqual((str(audio.dtype), audio.shape), ("float32", (1600,)))
        bad = self.folder / "bad.wav"
        bad.write_bytes(b"not audio")
        empty = self.folder / "empty.wav"
        empty.touch()
        for path in (bad, empty, self.audio("silent.wav", True), self.folder / "missing.wav"):
            with self.subTest(path=path), self.assertRaises(converter.ConversionError):
                converter.decode_audio(path, 16000)
        with patch.object(converter, "CONVERSION_MAX_AUDIO_SECONDS", .01):
            with self.assertRaisesRegex(converter.ConversionError, "limit"):
                converter.decode_audio(self.audio(), 16000)

    def test_no_audio_stream(self):
        from unittest.mock import MagicMock
        container = MagicMock()
        container.__enter__.return_value.streams.audio = []
        with patch("av.open", return_value=container):
            with self.assertRaisesRegex(converter.ConversionError, "no audio stream"):
                converter.decode_audio(self.audio(), 16000)

    def test_invalid_manual_checkpoint_is_untouched(self):
        path = self.folder / "manual.pth"
        path.write_bytes(b"original")
        with self.assertRaises(converter.ConversionError):
            converter.prepare_model("manual", str(path), True)
        self.assertEqual(path.read_bytes(), b"original")

    def test_download_requires_approval(self):
        with patch.object(converter.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(converter.ConversionError, "approval"):
                converter.prepare_model("no-consent")
            network.assert_not_called()

    def test_partial_download_is_deleted(self):
        with patch.object(converter.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")), \
             patch.object(converter, "load_model", side_effect=ValueError("bad checkpoint")):
            with self.assertRaises(converter.ConversionError):
                converter.prepare_model("partial", allow_download=True)
        self.assertFalse(converter.default_checkpoint().exists())
        self.assertEqual(files._read_registry(), {})
        self.assertEqual(list(files.app_data_dir().rglob("*.part")), [])

    def test_download_loads_before_publishing_and_reports_progress(self):
        events = []
        def verify(path):
            self.assertFalse(converter.default_checkpoint().exists())
            self.assertEqual(Path(path).read_bytes(), b"model")
            return "model-object"
        with patch.object(converter.urllib.request, "urlopen", return_value=io.BytesIO(b"model")), \
             patch.object(converter, "load_model", side_effect=verify):
            model, path = converter.prepare_model("download", allow_download=True, progress=events.append)
        self.assertEqual(model, "model-object")
        self.assertEqual(Path(path).read_bytes(), b"model")
        self.assertEqual(next(event["bytes"] for event in events if event["type"] == "download"), 5)
        self.assertEqual(files._read_registry(), {})

    def test_network_stall_error_cleans_temp(self):
        with patch.object(converter.urllib.request, "urlopen", side_effect=TimeoutError("stalled")):
            with self.assertRaisesRegex(converter.ConversionError, "stalled"):
                converter.prepare_model("stall", allow_download=True)
        self.assertEqual(files._read_registry(), {})

    def test_corrupt_owned_cache_removed_but_unowned_cache_kept(self):
        target = converter.default_checkpoint()
        target.parent.mkdir(parents=True)
        target.write_bytes(b"corrupt")
        with patch.object(converter, "load_model", side_effect=ValueError("bad model")):
            with self.assertRaises(converter.ConversionError):
                converter.prepare_model("unowned")
            self.assertTrue(target.exists())
            converter._record_checkpoint_owner(target)
            with self.assertRaisesRegex(converter.ConversionError, "removed"):
                converter.prepare_model("owned")
            self.assertFalse(target.exists())

    def test_output_rejects_empty_notes_and_preserves_existing(self):
        temporary = files.registered_temp(self.folder, "output")
        make_midi(temporary, False)
        with self.assertRaisesRegex(converter.ConversionError, "No piano notes"):
            converter.publish_midi(temporary, "source.wav")
        self.assertFalse((self.folder / "source.mid").exists())
        make_midi(temporary)
        (self.folder / "source.mid").write_bytes(b"keep")
        result = converter.publish_midi(temporary, "source.wav")
        self.assertEqual(Path(result).name, "source (1).mid")
        self.assertEqual((self.folder / "source.mid").read_bytes(), b"keep")
        files.forget_temp(temporary)

    def test_output_permission_fallback(self):
        real = files.registered_temp
        fallback = self.folder / "fallback"
        def register(directory, job):
            if Path(directory) == self.folder:
                raise PermissionError("read-only source directory")
            return real(directory, job)
        with patch.object(converter, "registered_temp", side_effect=register):
            path = converter.output_temporary(self.folder / "source.wav", "fallback", fallback)
        self.assertEqual(path.parent, fallback)
        files.forget_temp(path, delete=True)

    def test_stale_cleanup_preserves_live_owners_and_pid_reuse(self):
        live = files.registered_temp(self.folder, "live")
        dead = files.registered_temp(self.folder, "dead")
        with files.state_file_lock():
            data = files._read_registry()
            data[str(dead)]["start_time"] -= 100  # Same PID, different process incarnation.
            files._write_registry(data)
        unrelated = self.folder / "user.txt"
        unrelated.write_text("keep")
        self.assertEqual(files.cleanup_stale(), [])
        self.assertTrue(live.exists())
        self.assertFalse(dead.exists())
        self.assertTrue(unrelated.exists())
        files.forget_temp(live, delete=True)

    def test_two_instances_publish_distinct_names(self):
        context = multiprocessing.get_context("spawn")
        barrier, result = context.Barrier(2), context.Queue()
        children = [context.Process(target=collision_writer, args=(str(self.folder), barrier, result)) for _ in range(2)]
        try:
            for child in children:
                child.start()
            outputs = [result.get(timeout=15), result.get(timeout=15)]
            for child in children:
                child.join(timeout=10)
                self.assertEqual(child.exitcode, 0)
            self.assertEqual({Path(path).name for path in outputs}, {"same.mid", "same (1).mid"})
            for path in outputs:
                converter.validate_midi(path)
            self.assertEqual(files._read_registry(), {})
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=5)
            result.close()

    def run_fake_job(self, target, reason):
        job = ConversionJob()
        with patch("conversion_job.run_conversion", target):
            job.start(self.folder, fallback_dir="timeout" if reason == "timeout" else None)
        events = []
        try:
            deadline = time.monotonic() + 10
            while job.active and time.monotonic() < deadline:
                batch = job.poll()
                events.extend(batch)
                if any(event.get("stage") == "transcribing" for event in batch):
                    if reason == "cancel":
                        started = time.monotonic()
                        job.cancel()
                    elif reason == "shutdown":
                        started = time.monotonic()
                        events.extend(job.shutdown())
                time.sleep(.02)
            self.assertFalse(job.active)
            self.assertEqual(files._read_registry(), {})
            self.assertEqual(list(self.folder.glob("*.part")), [])
            if reason in ("cancel", "shutdown"):
                self.assertLess(time.monotonic() - started, 2)
            return events
        finally:
            job.shutdown()

    def test_cancel_kills_worker_and_cleans_registered_files(self):
        events = self.run_fake_job(idle_worker, "cancel")
        self.assertTrue(any(event["type"] == "cancelled" for event in events))

    def test_shutdown_leaves_no_worker_or_files(self):
        self.run_fake_job(idle_worker, "shutdown")

    def test_timeout_applies_to_transcription(self):
        events = self.run_fake_job(idle_worker, "timeout")
        self.assertTrue(any("timed out" in event.get("message", "") for event in events))

    def test_crash_cleanup_and_error(self):
        events = self.run_fake_job(dead_worker, "crash")
        self.assertTrue(any(event["type"] == "error" for event in events))

    def test_download_total_deadline_kills_stalled_worker(self):
        events = self.run_fake_job(stalled_download_worker, "download")
        self.assertTrue(any("Checkpoint download timed out" in event.get("message", "") for event in events))


if __name__ == "__main__":
    unittest.main()
