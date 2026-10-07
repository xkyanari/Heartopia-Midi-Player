"""Fallback ownership and worker recording without optional conversion packages."""
from contextlib import ExitStack, nullcontext
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import audio_converter as converter
import conversion_files as files
from conversion_service import scan_audio_folder
from transcribe_worker import run_conversion


class FallbackIndexTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.source = self.folder / "source"
        self.other = self.folder / "other"
        self.fallback = self.folder / "fallback"
        for folder in (self.source, self.other, self.fallback):
            folder.mkdir()
        lock = patch.object(files, "state_file_lock", side_effect=nullcontext)
        lock.start()
        self.addCleanup(lock.stop)

    def test_recorded_numbered_case_insensitive_output_belongs_only_to_source_folder(self):
        for folder in (self.source, self.other):
            (folder / "song.wav").touch()
        midi = self.fallback / "SONG (12).MID"
        midi.touch()
        files.record_fallback_output(midi, self.source / "song.wav")
        self.assertTrue(scan_audio_folder(self.source, self.fallback)[0]["midi"])
        self.assertFalse(scan_audio_folder(self.other, self.fallback)[0]["midi"])
        self.assertEqual(files.fallback_sources(self.fallback),
                         {"song (12).mid": os.path.normcase(os.path.abspath(self.source))})

    def test_missing_corrupt_and_invalid_indexes_do_not_claim_midi(self):
        (self.source / "song.wav").touch()
        (self.fallback / "song.mid").touch()
        index = self.fallback / ".heartopia-sources.json"
        self.assertFalse(scan_audio_folder(self.source, self.fallback)[0]["midi"])
        for contents in ("broken JSON", "[]", '{"song.mid": 3}', "\ufffd"):
            with self.subTest(contents=contents):
                index.write_text(contents, encoding="utf-8")
                self.assertEqual(files.fallback_sources(self.fallback), {})
                self.assertFalse(scan_audio_folder(self.source, self.fallback)[0]["midi"])

    def test_recording_merges_entries_and_replace_failure_preserves_index(self):
        midi = self.fallback / "song.mid"
        files.record_fallback_output(midi, self.source / "song.wav")
        original = files.fallback_sources(self.fallback)
        with patch.object(files.os, "replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                files.record_fallback_output(self.fallback / "other.mid", self.other / "other.wav")
        self.assertEqual(files.fallback_sources(self.fallback), original)
        self.assertFalse((self.fallback / ".heartopia-sources.json.tmp").exists())
        files.record_fallback_output(self.fallback / "other.mid", self.other / "other.wav")
        self.assertEqual(set(files.fallback_sources(self.fallback)), {"song.mid", "other.mid"})

    def run_worker(self, output, cleanup_error=None, recording_error=None):
        source = self.source / "song.wav"
        temporary = output.parent / "temporary.part"
        output.touch()
        messages = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(converter, "require_dependencies", return_value={
                "piano_transcription_inference": SimpleNamespace(sample_rate=1)}))
            stack.enter_context(patch.object(converter, "decode_audio", return_value=[0]))
            stack.enter_context(patch.object(converter, "prepare_model", return_value=(Mock(), "checkpoint")))
            stack.enter_context(patch.object(converter, "output_temporary", return_value=temporary))
            stack.enter_context(patch.object(converter, "publish_midi", return_value=str(output)))
            stack.enter_context(patch.object(files, "forget_temp", side_effect=cleanup_error))
            record = stack.enter_context(patch.object(files, "record_fallback_output",
                side_effect=recording_error, wraps=None if recording_error else files.record_fallback_output))
            stack.enter_context(patch("transcribe_worker.threading.Thread"))
            run_conversion({"source": str(source), "job_id": "job", "parent": {}}, messages)
        events = [call.args[0] for call in messages.put.call_args_list]
        self.assertNotIn("error", [event["type"] for event in events])
        messages.close.assert_called_once()
        return next(event for event in events if event["type"] == "success"), record

    def test_worker_records_output_in_fallback(self):
        output = self.fallback / "song.mid"
        success, record = self.run_worker(output)
        record.assert_called_once_with(str(output), str(self.source / "song.wav"))
        self.assertIsNone(success["warning"])
        self.assertEqual(files.fallback_sources(self.fallback)["song.mid"],
                         os.path.normcase(os.path.abspath(self.source)))

    def test_worker_does_not_record_output_beside_source(self):
        success, record = self.run_worker(self.source / "song.mid")
        record.assert_not_called()
        self.assertIsNone(success["warning"])

    def test_worker_recording_failure_warns_and_preserves_cleanup_warning(self):
        for cleanup_error in (None, OSError("registry locked")):
            with self.subTest(cleanup_error=cleanup_error):
                success, _ = self.run_worker(self.fallback / "song.mid", cleanup_error, OSError("index locked"))
                self.assertIn("index locked", success["warning"])
                if cleanup_error:
                    self.assertIn("registry locked", success["warning"])
                self.assertTrue(Path(success["path"]).is_file())
