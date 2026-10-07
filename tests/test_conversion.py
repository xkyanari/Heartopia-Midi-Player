import io
import hashlib
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


class CheckpointTests(unittest.TestCase):
    """Checkpoint safety needs no conversion libraries or network access."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        for context in (
            patch.dict(os.environ, {"LOCALAPPDATA": directory.name}),
            patch.object(files, "process_identity", return_value={"pid": os.getpid(), "start_time": 1}),
            patch.object(converter.urllib.request, "urlopen", side_effect=lambda *a, **k: io.BytesIO(b"model")),
            patch.object(converter, "load_model", return_value="model-object"),
        ):
            context.start()
            self.addCleanup(context.stop)

    def checkpoint(self, name=None, owned=True):
        target = converter.default_checkpoint()
        target.parent.mkdir(parents=True, exist_ok=True)
        if name:
            target = target.with_name(name)
        target.write_bytes(b"old")
        if owned:
            converter._record_checkpoint_owner(target)
        return target

    def test_first_download_uses_default_name_and_registers_owner(self):
        _, path = converter.prepare_model("first", allow_download=True)
        target = converter.default_checkpoint()
        self.assertEqual(Path(path), target)
        self.assertEqual(target.read_bytes(), b"model")
        self.assertIsNotNone(converter._owned_checkpoint_identity(target))
        self.assertEqual(list(target.parent.glob("*.pth")), [target])
        self.assertEqual(files._read_registry(), {})

    def test_redownload_replaces_owned_default_and_cleans_owned_leftovers(self):
        target = self.checkpoint()
        old = self.checkpoint(f"piano-{'a' * 32}.pth")
        def validate(path):
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(Path(path).read_bytes(), b"model")
            self.assertIn(str(Path(path).resolve()), files._read_registry())
            return "model-object"
        with patch.object(converter, "load_model", side_effect=validate):
            for _ in range(2):
                _, path = converter.prepare_model("replace", str(target), True, force_download=True)
                self.assertEqual(Path(path), target)
                self.assertEqual(target.read_bytes(), b"model")
                self.assertIsNotNone(converter._owned_checkpoint_identity(target))
                self.assertEqual(list(target.parent.glob("*.pth")), [target])
                target.write_bytes(b"old")
        self.assertFalse(converter._checkpoint_marker(old).exists())
        self.assertEqual(files._read_registry(), {})

    def test_redownload_preserves_unowned_and_mismatched_files(self):
        target = self.checkpoint(owned=False)
        unowned = self.checkpoint(f"piano-{'b' * 32}.pth", owned=False)
        mismatch = self.checkpoint(f"piano-{'c' * 32}.pth")
        converter._checkpoint_marker(mismatch).write_text('{}', encoding="utf-8")
        _, path = converter.prepare_model("unowned", str(target), True, force_download=True)
        self.assertNotEqual(Path(path), target)
        for original in (target, unowned, mismatch):
            self.assertEqual(original.read_bytes(), b"old")
        self.assertIsNotNone(converter._owned_checkpoint_identity(path))

    def test_failed_redownload_keeps_previous_model_and_cleans_temp(self):
        target = self.checkpoint()
        with patch.object(converter, "load_model", side_effect=ValueError("bad model")):
            with self.assertRaises(converter.ConversionError):
                converter.prepare_model("bad", str(target), True, force_download=True)
        self.assertEqual(target.read_bytes(), b"old")
        self.assertIsNotNone(converter._owned_checkpoint_identity(target))
        self.assertEqual(list(target.parent.glob("*.pth")), [target])
        self.assertEqual(files._read_registry(), {})
        self.assertEqual(list(target.parent.glob("*.part")), [])

    def test_replacement_rechecks_ownership_after_model_validation(self):
        target = self.checkpoint()
        def validate(path):
            converter._checkpoint_marker(target).write_text('{}', encoding="utf-8")
            return "model-object"
        with patch.object(converter, "load_model", side_effect=validate):
            _, path = converter.prepare_model("changed-owner", allow_download=True, force_download=True)
        self.assertNotEqual(Path(path), target)
        self.assertEqual(target.read_bytes(), b"old")

    def test_saved_owned_corrupt_checkpoint_is_removed(self):
        for name in (None, f"piano-{'d' * 32}.pth"):
            with self.subTest(name=name):
                target = self.checkpoint(name)
                with patch.object(converter, "load_model", side_effect=ValueError("bad model")):
                    with self.assertRaisesRegex(converter.ConversionError, "removed.*Download it again"):
                        converter.prepare_model("saved", str(target))
                self.assertFalse(target.exists())
                self.assertFalse(converter._checkpoint_marker(target).exists())

    def test_selected_corrupt_files_without_app_ownership_are_kept(self):
        unowned = self.checkpoint(owned=False)
        outside = self.folder / "chosen.pth"
        outside.write_bytes(b"user")
        converter._record_checkpoint_owner(outside)
        mismatch = self.checkpoint(f"piano-{'e' * 32}.pth")
        converter._checkpoint_marker(mismatch).write_text('{}', encoding="utf-8")
        with patch.object(converter, "load_model", side_effect=ValueError("bad model")):
            for target in (unowned, outside, mismatch):
                with self.subTest(target=target), self.assertRaisesRegex(converter.ConversionError, "original file was kept"):
                    converter.prepare_model("chosen", str(target))
                self.assertTrue(target.exists())

    def test_checksum_rejects_same_size_corruption(self):
        target = self.checkpoint()
        with patch.object(converter, "CHECKPOINT_EXPECTED_BYTES", 3), \
             patch.object(converter, "CHECKPOINT_MIN_BYTES", 3), \
             patch.object(converter, "CHECKPOINT_SHA256", hashlib.sha256(b"old").hexdigest()):
            converter._validate_checkpoint(target)
            target.write_bytes(b"bad")
            with self.assertRaisesRegex(converter.ConversionError, "checksum"):
                converter._validate_checkpoint(target)


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
