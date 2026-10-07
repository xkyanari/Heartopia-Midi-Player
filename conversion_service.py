"""Parent-side IO and job threads. No Tk imports or model construction."""
import importlib.util
import os
from pathlib import Path
import queue
import re
import stat
import sys
import threading

import app_config as config
from app_storage import load_settings, save_settings
from conversion_files import app_data_dir, cleanup_stale, fallback_sources
from conversion_job import ConversionJob


def default_audio_folder():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / config.DEFAULT_AUDIO_FOLDER


def model_destination():
    return app_data_dir() / config.CHECKPOINT_FOLDER / config.CHECKPOINT_FILE


def missing_dependencies():
    return [name for name in ("av", "numpy", "torch", "audioread", "psutil", "piano_transcription_inference")
            if importlib.util.find_spec(name) is None]


def scan_audio_folder(folder, fallback_dir=None):
    rows = []
    midi_stems = set()

    def record_midi(entry):
        path = Path(entry.name)
        if path.suffix.lower() == ".mid" and entry.is_file(follow_symlinks=False):
            stem = path.stem.casefold()
            midi_stems.add(stem)
            numbered = re.fullmatch(r"(.+) \([1-9][0-9]*\)", stem)
            if numbered:
                midi_stems.add(numbered.group(1))

    with os.scandir(folder) as entries:
        for entry in entries:
            record_midi(entry)
            if not entry.is_file(follow_symlinks=False) or Path(entry.name).suffix.lower() not in config.SUPPORTED_AUDIO_EXTS:
                continue
            metadata = entry.stat(follow_symlinks=False)
            if entry.name.startswith(".") or getattr(metadata, "st_file_attributes", 0) & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM):
                continue
            path = Path(entry.path)
            rows.append({"path": str(path.resolve()), "name": entry.name, "size": metadata.st_size,
                         "modified": metadata.st_mtime})
    fallback = Path(fallback_dir) if fallback_dir else app_data_dir() / config.CONVERTED_OUTPUT_FOLDER
    source_folder = os.path.normcase(os.path.abspath(folder))
    if os.path.normcase(os.path.abspath(fallback)) != source_folder:
        sources = fallback_sources(fallback)
        try:
            with os.scandir(fallback) as entries:
                for entry in entries:
                    if sources.get(entry.name.casefold()) == source_folder:
                        record_midi(entry)
        except OSError:
            pass  # The fallback may not exist yet or may be temporarily unavailable.
    for row in rows:
        row["midi"] = Path(row["name"]).stem.casefold() in midi_stems
    return sorted(rows, key=lambda row: (row["name"].casefold(), row["name"]))


class ConversionService:
    def __init__(self):
        self.events = queue.Queue()
        self.io_commands = queue.Queue()
        self.job_commands = queue.Queue()
        self.cancel_event = threading.Event()
        self.closing = threading.Event()
        self.closed = threading.Event()
        self.io_thread = threading.Thread(target=self._io_loop, name="conversion-io", daemon=False)
        self.job_thread = threading.Thread(target=self._job_loop, name="conversion-controller", daemon=False)
        self.io_thread.start()
        self.job_thread.start()
        self.io_commands.put(("initialize", {}))

    def scan(self, folder, token, fallback_dir=None):
        self.io_commands.put(("scan", {"folder": folder, "token": token, "fallback_dir": fallback_dir}))

    def save(self, updates):
        self.io_commands.put(("save", updates))

    def preflight(self, request):
        self.cancel_event.clear()
        self.io_commands.put(("preflight", request))

    def start(self, request):
        # Do not clear a cancellation requested while preflight/start was queued.
        self.job_commands.put(request)

    def cancel(self):
        self.cancel_event.set()

    def shutdown(self):
        self.closing.set()
        self.cancel_event.set()

    def _io_loop(self):
        try:
            while True:
                action, data = self.io_commands.get()
                if action == "stop":
                    return
                try:
                    if action == "initialize":
                        settings = load_settings()
                        folder = settings.get("audio_input_folder") or str(default_audio_folder())
                        warning = None
                        if not settings.get("audio_input_folder"):
                            try:
                                Path(folder).mkdir(parents=True, exist_ok=True)
                            except OSError as exc:
                                warning = f"Cannot create audio folder: {exc}. Choose another folder."
                        self.events.put({"type": "initialized", "settings": settings, "folder": folder,
                                         "missing": missing_dependencies(), "warning": warning})
                        # Skip dependency-free cleanup only when there is no registry.
                        try:
                            failed = cleanup_stale()
                            if failed:
                                self.events.put({"type": "warning", "message": f"Temporary cleanup needs retry: {failed}"})
                        except Exception as exc:
                            self.events.put({"type": "warning", "message": f"Temporary cleanup deferred: {exc}"})
                    elif action == "scan":
                        self.events.put({"type": "scan", **data,
                                         "rows": scan_audio_folder(data["folder"], data.get("fallback_dir"))})
                    elif action == "save":
                        save_settings(data)
                    elif action == "preflight":
                        missing = missing_dependencies()
                        if missing:
                            raise RuntimeError(config.CONVERSION_STANDARD_BUILD_TEXT if getattr(sys, "frozen", False)
                                               else f"Install conversion dependencies first:\n{config.CONVERSION_INSTALL_COMMAND}")
                        source = data.get("source")
                        if data.get("operation", "convert") == "convert":
                            if not source or not Path(source).is_file():
                                raise ValueError("The selected audio file no longer exists or is unreadable.")
                            with open(source, "rb") as audio:
                                audio.read(1)
                        checkpoint = data.get("checkpoint_path") or str(model_destination())
                        self.events.put({"type": "preflight", "request": data,
                                         "model_exists": Path(checkpoint).is_file()})
                except Exception as exc:
                    kind = "scan_error" if action == "scan" else "preflight_error" if action == "preflight" else "warning"
                    token = data.get("token") if action == "scan" else data.get("_token")
                    message = config.SETTINGS_SAVE_WARNING if action == "save" and isinstance(exc, TimeoutError) else str(exc)
                    self.events.put({"type": kind, "message": message, "token": token})
                    if action == "initialize":
                        self.events.put({"type": "initialized", "settings": {}, "folder": str(default_audio_folder()),
                                         "missing": missing_dependencies(), "warning": str(exc)})
        finally:
            self.closed.set()

    def _job_loop(self):
        job = ConversionJob()
        try:
            while not self.closing.is_set():
                try:
                    request = self.job_commands.get(timeout=config.CONVERSION_SERVICE_POLL_SECONDS)
                except queue.Empty:
                    request = None
                if request is not None:
                    if self.cancel_event.is_set():
                        self.events.put({"type": "cancelled", "message": "Conversion cancelled."})
                        self.events.put({"type": "finished"})
                    else:
                        try:
                            job.start(**request)
                        except Exception as exc:
                            self.events.put({"type": "error", "message": str(exc)})
                            self.events.put({"type": "finished"})
                if self.cancel_event.is_set():
                    job.cancel()
                for event in job.poll():
                    if event["type"] == "model_ready":
                        # Only the worker can produce this after a successful load.
                        self.save({"checkpoint_path": event["path"]})
                    self.events.put(event)
        except Exception as exc:
            self.events.put({"type": "error", "message": f"Conversion service failed: {exc}"})
            self.events.put({"type": "finished"})
        finally:
            try:
                for event in job.shutdown():
                    self.events.put(event)
            finally:
                self.io_commands.put(("stop", {}))
