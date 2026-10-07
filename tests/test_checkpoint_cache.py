"""Checkpoint publication and verification without optional conversion libraries."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
from unittest.mock import patch

import pytest

import audio_converter as converter
import conversion_files as files


@pytest.fixture
def checkpoint_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(files, "process_identity", lambda: {"pid": os.getpid(), "start_time": 1})
    monkeypatch.setattr(converter, "CHECKPOINT_EXPECTED_BYTES", 5)
    monkeypatch.setattr(converter, "CHECKPOINT_MIN_BYTES", 1)
    monkeypatch.setattr(converter, "CHECKPOINT_SHA256", hashlib.sha256(b"model").hexdigest())
    target = converter.default_checkpoint()
    target.parent.mkdir(parents=True)
    return target


def test_locked_redownload_keeps_new_owned_model(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"older")
    converter._record_checkpoint_owner(target)
    real_replace, real_rename, real_unlink = os.replace, os.rename, Path.unlink
    renamed = []

    def replace(source, destination):
        if Path(destination) == target:
            raise PermissionError("model open in another window")
        return real_replace(source, destination)

    def rename(source, destination):
        assert Path(source).read_bytes() == b"model"
        renamed.append(Path(source))
        return real_rename(source, destination)

    def unlink(path, *args, **kwargs):
        if path == target:
            raise PermissionError("still open")
        return real_unlink(path, *args, **kwargs)

    def load(path):
        converter._validate_checkpoint(path)
        return "model-object"

    with patch.object(converter.urllib.request, "urlopen", return_value=io.BytesIO(b"model")), \
         patch.object(converter, "load_model", side_effect=load), \
         patch.object(converter.os, "replace", side_effect=replace), \
         patch.object(converter.os, "rename", side_effect=rename), \
         patch.object(Path, "unlink", unlink), \
         patch.object(converter.hashlib, "file_digest", wraps=hashlib.file_digest) as digest:
        model, result = converter.prepare_model("locked", allow_download=True, force_download=True)
        new_target = Path(result)
        converter._validate_checkpoint(new_target)
        assert digest.call_count == 1  # Publication carries verification to the final name.
    assert model == "model-object"
    assert re.fullmatch(r"piano-[0-9a-f]{32}\.pth", new_target.name)
    assert new_target.read_bytes() == b"model"
    assert converter._owned_checkpoint_identity(new_target) is not None
    assert target.read_bytes() == b"older"
    assert converter._checkpoint_marker(target).exists()
    assert len(renamed) == 1
    assert not renamed[0].exists()
    assert files._read_registry() == {}


@pytest.mark.parametrize("error", [PermissionError, OSError])
def test_cleanup_leaves_locked_file_and_marker(checkpoint_env, error):
    target = checkpoint_env
    old = target.with_name(f"piano-{'a' * 32}.pth")
    old.write_bytes(b"model")
    converter._record_checkpoint_owner(old)
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == old:
            raise error("locked")
        return real_unlink(path, *args, **kwargs)

    with patch.object(Path, "unlink", unlink):
        with converter.state_file_lock():
            converter._cleanup_old_checkpoints(target)
    assert old.exists()
    assert converter._owned_checkpoint_identity(old) is not None


def test_cleanup_includes_owned_default_and_preserves_unowned(checkpoint_env):
    default = checkpoint_env
    default.write_bytes(b"model")
    converter._record_checkpoint_owner(default)
    target = default.with_name(f"piano-{'b' * 32}.pth")
    target.write_bytes(b"model")
    converter._record_checkpoint_owner(target)
    unowned = default.with_name(f"piano-{'c' * 32}.pth")
    unowned.write_bytes(b"model")
    with converter.state_file_lock():
        converter._cleanup_old_checkpoints(target)
    assert not default.exists()
    assert not converter._checkpoint_marker(default).exists()
    assert target.exists()
    assert unowned.exists()


def test_unchanged_checkpoint_is_hashed_once_without_granting_ownership(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"model")
    with patch.object(converter.hashlib, "file_digest", wraps=hashlib.file_digest) as digest:
        converter._validate_checkpoint(target)
        converter._validate_checkpoint(target)
    assert digest.call_count == 1
    assert converter._owned_checkpoint_identity(target) is None
    records = json.loads((target.parent / "verified-checkpoints.json").read_text())
    assert records[str(target.resolve())] == converter._checkpoint_verification(target)


@pytest.mark.parametrize("change", ["mtime", "size", "inode", "birth_time"])
def test_changed_checkpoint_is_hashed_again(checkpoint_env, change):
    target = checkpoint_env
    target.write_bytes(b"model")
    with patch.object(converter.hashlib, "file_digest", wraps=hashlib.file_digest) as digest:
        converter._validate_checkpoint(target)
        if change == "mtime":
            stat = target.stat()
            os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        elif change == "size":
            target.write_bytes(b"models")
            # Isolate the size comparison from changes to the expected digest.
            digest.return_value = hashlib.sha256(b"model")
            with patch.object(converter, "CHECKPOINT_EXPECTED_BYTES", 6):
                converter._validate_checkpoint(target)
        else:
            # Hold bytes, size and mtime constant while replacing the file identity.
            original = converter._checkpoint_verification
            def changed_identity(path):
                record = original(path)
                record[change] += 1
                return record
            with patch.object(converter, "_checkpoint_verification", side_effect=changed_identity):
                converter._validate_checkpoint(target)
        if change == "mtime":
            converter._validate_checkpoint(target)
        assert digest.call_count == 2


@pytest.mark.parametrize("contents", ["invalid json", "[]", '{"wrong": null}'])
def test_corrupt_verification_cache_is_rehashed(checkpoint_env, contents):
    target = checkpoint_env
    target.write_bytes(b"model")
    (target.parent / "verified-checkpoints.json").write_text(contents)
    with patch.object(converter.hashlib, "file_digest", wraps=hashlib.file_digest) as digest:
        converter._validate_checkpoint(target)
    assert digest.call_count == 1


def test_same_size_corruption_is_not_cached(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"model")
    converter._validate_checkpoint(target)
    target.write_bytes(b"wrong")
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    with pytest.raises(converter.ConversionError, match="checksum"):
        converter._validate_checkpoint(target)


def test_size_is_checked_even_with_verification_record(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"model")
    converter._validate_checkpoint(target)
    target.write_bytes(b"partial")
    with patch.object(converter.hashlib, "file_digest") as digest:
        with pytest.raises(converter.ConversionError, match="size"):
            converter._validate_checkpoint(target)
    digest.assert_not_called()
