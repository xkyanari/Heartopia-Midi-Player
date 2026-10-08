"""Spawn target; never import UI modules or touch Tk."""
import contextlib
import os
from pathlib import Path
import threading
import time

from app_config import (
    CONVERSION_ESTIMATE_AUDIO_FACTOR, CONVERSION_MIN_TIMEOUT_SECONDS,
    CONVERSION_PARENT_POLL_SECONDS, CONVERSION_TIMEOUT_AUDIO_FACTOR,
)


def run_conversion(request, messages):
    from audio_converter import (
        ConversionError, decode_audio, output_temporary, prepare_model,
        publish_midi, require_dependencies,
    )
    temporary = None
    done = threading.Event()
    def emit(message):
        messages.put(message)
    def watch_parent():
        from conversion_files import owner_alive
        while not done.wait(CONVERSION_PARENT_POLL_SECONDS):
            if not owner_alive(request["parent"]):
                os._exit(1)  # Registry lets the next startup reclaim dead-worker temps.
    try:
        emit({"type": "stage", "stage": "dependencies"})
        dependencies = require_dependencies()
        threading.Thread(target=watch_parent, daemon=True).start()
        from conversion_files import forget_temp, record_fallback_output
        audio, duration = None, None
        if request.get("operation", "convert") == "convert":
            emit({"type": "stage", "stage": "decoding"})
            audio = decode_audio(request["source"], dependencies["piano_transcription_inference"].sample_rate)
            duration = len(audio) / dependencies["piano_transcription_inference"].sample_rate
        emit({"type": "stage", "stage": "checkpoint", "duration": duration})
        # The pinned package prints segment logs rather than offering a callback.
        # Keep its single-call behavior; UI phase 3 will use elapsed/estimated time.
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet):
            model, checkpoint = prepare_model(
                request["job_id"], request.get("checkpoint_path"),
                request.get("allow_download", False), emit, request.get("force_download", False),
            )
            emit({"type": "model_ready", "path": checkpoint})
            if request.get("operation") == "model":
                emit({"type": "model_success", "path": checkpoint})
                return
            temporary = output_temporary(request["source"], request["job_id"], request.get("fallback_dir"))
            emit({"type": "stage", "stage": "transcribing", "duration": duration,
                  "started": time.monotonic(),
                  "timeout": max(CONVERSION_MIN_TIMEOUT_SECONDS, CONVERSION_TIMEOUT_AUDIO_FACTOR * duration),
                  "estimate": CONVERSION_ESTIMATE_AUDIO_FACTOR * duration})
            model.transcribe(audio, str(temporary))
        emit({"type": "stage", "stage": "validating"})
        output = publish_midi(temporary, request["source"])
        # Cleanup problems cannot turn a successfully published MIDI into a loss.
        warning = None
        try:
            forget_temp(temporary)
            temporary = None
        except Exception as exc:
            warning = f"MIDI saved, but temporary registry cleanup needs retry: {exc}"
        if os.path.normcase(os.path.abspath(Path(output).parent)) != os.path.normcase(os.path.abspath(Path(request["source"]).parent)):
            try:
                record_fallback_output(output, request["source"])
            except Exception as exc:
                index_warning = f"MIDI saved, but fallback source recording needs retry: {exc}"
                warning = f"{warning}; {index_warning}" if warning else index_warning
        emit({"type": "success", "path": output, "checkpoint_path": checkpoint, "warning": warning})
    except Exception as exc:
        emit({"type": "error", "message": str(exc) if isinstance(exc, ConversionError)
              else f"Conversion failed: {exc}"})
    finally:
        done.set()
        if temporary is not None:
            try:
                from conversion_files import forget_temp
                forget_temp(temporary, delete=True)
            except Exception as exc:
                emit({"type": "warning", "message": f"Temporary cleanup needs retry: {exc}"})
        messages.close()
        messages.join_thread()
