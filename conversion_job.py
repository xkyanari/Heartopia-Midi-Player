"""Parent-owned conversion lifecycle; UI integration is deliberately separate."""
import multiprocessing
import time
import uuid

from conversion_files import cleanup_stale, process_identity
from transcribe_worker import run_conversion


class ConversionJob:
    """One job at a time per controller. Drain poll() from the UI/service loop.

    cancel() signals termination without waiting on a child; poll() reaps and
    cleans once it is dead. shutdown() is the bounded application-exit path.
    Final registry IO may wait for the state lock; phase 3 must do that IO in a
    parent service thread, delivering messages to Tk through its UI queue.
    """
    def __init__(self):
        self.process = None
        self.messages = None
        self.job_id = None
        self.deadline = None
        self.timeout_message = "Transcription timed out."
        self.terminal = False
        self.cancel_reason = None

    @property
    def active(self):
        return self.process is not None

    def start(self, source=None, checkpoint_path=None, allow_download=False, fallback_dir=None,
              force_download=False, operation="convert"):
        if self.active:
            raise RuntimeError("A conversion is already running.")
        cleanup_stale()
        self.job_id = uuid.uuid4().hex
        self.deadline = None
        self.terminal = False
        self.cancel_reason = None
        context = multiprocessing.get_context("spawn")
        self.messages = context.Queue()
        request = {"source": str(source) if source is not None else None, "checkpoint_path": checkpoint_path,
                   "allow_download": allow_download, "fallback_dir": fallback_dir,
                   "force_download": force_download, "operation": operation,
                   "job_id": self.job_id, "parent": process_identity()}
        self.process = context.Process(target=run_conversion, args=(request, self.messages))
        try:
            self.process.start()
            # Parent only receives. Closing its extra writer prevents a dead
            # child leaving a half-written queue frame waiting forever for EOF.
            self.messages._writer.close()
        except BaseException:
            self.process = None
            self.messages.close()
            self.messages = None
            raise

    def cancel(self, reason="Conversion cancelled."):
        if self.process is not None and not self.terminal:
            self.cancel_reason = reason
            if self.process.is_alive():
                self.process.terminate()

    def _drain(self):
        events = []
        while True:
            try:
                message = self.messages.get_nowait()
            except Exception:
                # A terminated writer can leave an incomplete or corrupt frame.
                break
            if message["type"] == "stage":
                if message["stage"] in ("transcribing", "downloading"):
                    self.deadline = message["started"] + message["timeout"]
                    self.timeout_message = ("Checkpoint download timed out." if message["stage"] == "downloading"
                                            else "Transcription timed out.")
                else:
                    self.deadline = None
            if message["type"] in ("success", "model_success", "error"):
                self.terminal = True
            events.append(message)
        return events

    def poll(self):
        if not self.active:
            return []
        # Wait until a cancelled writer is dead before reading partial frames.
        events = [] if self.cancel_reason else self._drain()
        if self.deadline and time.monotonic() >= self.deadline and not self.terminal:
            self.cancel(self.timeout_message)
        if self.process.is_alive():
            return events
        self.process.join(timeout=0)
        events.extend(self._drain())
        if not self.terminal:
            events.append({"type": "cancelled" if self.cancel_reason else "error",
                           "message": self.cancel_reason or f"Conversion worker exited unexpectedly ({self.process.exitcode})."})
        try:
            failed = cleanup_stale(self.job_id)
            if failed:
                events.append({"type": "warning", "message": f"Could not remove temporary files: {failed}"})
        except Exception as exc:
            events.append({"type": "warning", "message": f"Temporary cleanup needs retry: {exc}"})
        self.messages.cancel_join_thread()
        self.messages.close()
        self.process.close()
        self.process = self.messages = None
        events.append({"type": "finished"})
        return events

    def shutdown(self):
        """Terminate, bound the wait, then clean only this dead worker's files."""
        if not self.active:
            return []
        self.cancel("Application closed during conversion.")
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
        return self.poll()
