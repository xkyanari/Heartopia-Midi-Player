"""Queue failures stop draining while unexpected failures remain visible."""
import pickle
import queue
import unittest
from unittest.mock import Mock, patch

from conversion_job import ConversionJob


class DrainTests(unittest.TestCase):
    def test_expected_queue_errors_do_not_log(self):
        for error in (queue.Empty(), EOFError(), OSError(), pickle.UnpicklingError(), ValueError()):
            with self.subTest(error=type(error).__name__):
                job = ConversionJob()
                job.messages = Mock(get_nowait=Mock(side_effect=error))
                with self.assertNoLogs("conversion_job"):
                    self.assertEqual(job._drain(), [])

    def test_unexpected_error_logs_and_preserves_received_events(self):
        job = ConversionJob()
        success = {"type": "success", "path": "song.mid"}
        job.messages = Mock(get_nowait=Mock(side_effect=[success, RuntimeError("queue bug")]))
        with self.assertLogs("conversion_job", level="ERROR") as captured:
            self.assertEqual(job._drain(), [success])
        self.assertIn("RuntimeError: queue bug", captured.output[0])

    def test_unexpected_error_does_not_prevent_poll_cleanup(self):
        job = ConversionJob()
        process = Mock()
        process.is_alive.return_value = False
        messages = Mock(get_nowait=Mock(side_effect=RuntimeError("queue bug")))
        job.process, job.messages, job.job_id = process, messages, "job"
        with patch("conversion_job.cleanup_stale", return_value=[]) as cleanup, \
                self.assertLogs("conversion_job", level="ERROR"):
            self.assertEqual([event["type"] for event in job.poll()], ["error", "finished"])
        cleanup.assert_called_once_with("job")
        messages.close.assert_called_once()
        process.close.assert_called_once()
        self.assertFalse(job.active)
