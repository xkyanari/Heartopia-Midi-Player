"""Conversion lifecycle regressions without a transcription environment."""
import pickle
import queue
import unittest
from unittest.mock import Mock, patch

from conversion_job import ConversionJob


class ConversionJobTests(unittest.TestCase):
    def setUp(self):
        self.job = ConversionJob()
        self.process = Mock()
        self.process.is_alive.return_value = True
        self.process.terminate.side_effect = lambda: setattr(self.process.is_alive, "return_value", False)
        self.messages = Mock()
        self.messages.get_nowait.side_effect = queue.Empty
        self.job.process = self.process
        self.job.messages = self.messages
        self.job.job_id = "test-job"
        cleanup = patch("conversion_job.cleanup_stale", return_value=[])
        self.cleanup = cleanup.start()
        self.addCleanup(cleanup.stop)

    def test_cancel_after_queued_success_reports_saved(self):
        success = {"type": "success", "path": "piano.mid"}
        for reason in ("Conversion cancelled.", "Transcription timed out."):
            with self.subTest(reason=reason):
                self.job.process = self.process
                self.job.messages = self.messages
                self.job.terminal = False
                self.process.is_alive.return_value = True
                self.messages.get_nowait.side_effect = [success, queue.Empty]
                self.job.cancel(reason)
                events = self.job.poll()
                self.assertEqual(events, [success, {"type": "finished"}])
                self.assertTrue(self.job.terminal)
                self.assertFalse(self.job.active)
        self.process.join.assert_called_with(timeout=0)
        self.cleanup.assert_called_with("test-job")

    def test_broken_queue_after_terminate_does_not_raise(self):
        for error in (EOFError(), OSError(), pickle.UnpicklingError(), ValueError(), RuntimeError()):
            with self.subTest(error=type(error).__name__):
                self.job.process = self.process
                self.job.messages = self.messages
                self.process.is_alive.return_value = True
                self.messages.get_nowait.side_effect = error
                self.job.cancel()
                events = self.job.poll()
                self.assertEqual([event["type"] for event in events], ["cancelled", "finished"])
                self.assertFalse(self.job.active)
                self.messages.close.assert_called()
                self.process.close.assert_called()

    def test_success_before_corrupt_frame_is_preserved(self):
        success = {"type": "success", "path": "piano.mid"}
        self.messages.get_nowait.side_effect = [success, pickle.UnpicklingError()]
        self.job.cancel()
        self.assertEqual(self.job.poll(), [success, {"type": "finished"}])

    def test_cancelled_live_worker_is_not_drained(self):
        self.process.terminate.side_effect = None
        self.job.cancel()
        self.assertEqual(self.job.poll(), [])
        self.messages.get_nowait.assert_not_called()
        self.process.join.assert_not_called()
        self.assertTrue(self.job.active)

    def test_cancel_after_terminal_event_does_nothing(self):
        self.job.terminal = True
        self.job.cancel()
        self.process.terminate.assert_not_called()
        self.assertIsNone(self.job.cancel_reason)

    def test_shutdown_bounds_joins_and_handles_broken_queue(self):
        self.process.terminate.side_effect = None
        self.process.kill.side_effect = lambda: setattr(self.process.is_alive, "return_value", False)
        self.messages.get_nowait.side_effect = EOFError
        self.assertEqual([event["type"] for event in self.job.shutdown()], ["cancelled", "finished"])
        self.assertEqual([call.kwargs["timeout"] for call in self.process.join.call_args_list], [1, 1, 0])
        self.process.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
