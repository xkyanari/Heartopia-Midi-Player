"""Checkpoint publication and verification without optional conversion libraries."""
import hashlib
from contextlib import contextmanager, nullcontext
import io
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
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
    if os.name != "nt":
        # The application's shared lock uses msvcrt; isolate it on POSIX CI.
        monkeypatch.setattr(converter, "state_file_lock", nullcontext)
        monkeypatch.setattr(files, "state_file_lock", nullcontext)
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
    with patch.object(converter, "load_model", return_value="model-object"):
        _, result = converter.prepare_model("after-cleanup")
    assert Path(result) == target


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
                record[change] = (record[change] or 0) + 1
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


def test_stat_without_birthtime_is_supported(checkpoint_env):
    stat = SimpleNamespace(st_size=5, st_mtime_ns=2, st_ino=3,
                           st_ctime=4, st_ctime_ns=4_000_000_000)
    with patch.object(Path, "stat", return_value=stat):
        record = converter._checkpoint_verification(checkpoint_env)
        identity = converter._checkpoint_identity(checkpoint_env)
    assert record["birth_time"] is None
    assert identity == {"inode": 3, "birth_time": 4 if os.name == "nt" else None}
    if os.name != "nt":
        assert record["ctime_ns"] == stat.st_ctime_ns


def test_hash_does_not_hold_shared_state_lock(checkpoint_env, monkeypatch):
    target = checkpoint_env
    target.write_bytes(b"model")
    locked = False

    @contextmanager
    def lock():
        nonlocal locked
        assert not locked
        locked = True
        try:
            yield
        finally:
            locked = False

    real_digest = hashlib.file_digest
    def hash_file(source, algorithm):
        assert not locked
        return real_digest(source, algorithm)

    monkeypatch.setattr(converter, "state_file_lock", lock)
    with patch.object(converter.hashlib, "file_digest", side_effect=hash_file):
        converter._validate_checkpoint(target)


def test_file_changed_during_hash_is_not_recorded(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"model")
    real_digest = hashlib.file_digest

    def hash_then_change(source, algorithm):
        digest = real_digest(source, algorithm)
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return digest

    with patch.object(converter.hashlib, "file_digest", side_effect=hash_then_change):
        with pytest.raises(converter.ConversionError, match="changed during verification"):
            converter._validate_checkpoint(target)
    assert converter._read_checkpoint_verifications() == {}


def test_verification_transfer_failure_does_not_fail_publication(checkpoint_env):
    target = checkpoint_env
    original = converter._checkpoint_verification

    def verification(path):
        if Path(path) == target:
            raise OSError("temporarily unavailable")
        return original(path)

    def load(path):
        converter._validate_checkpoint(path)
        return "model-object"

    with patch.object(converter.urllib.request, "urlopen", return_value=io.BytesIO(b"model")), \
         patch.object(converter, "load_model", side_effect=load), \
         patch.object(converter, "_checkpoint_verification", side_effect=verification), \
         patch.object(converter, "_cleanup_old_checkpoints", wraps=converter._cleanup_old_checkpoints) as cleanup:
        model, result = converter.prepare_model("transfer", allow_download=True, force_download=True)
    assert model == "model-object"
    assert Path(result).read_bytes() == b"model"
    assert converter._owned_checkpoint_identity(result) is not None
    cleanup.assert_called_once_with(target)


def test_cleanup_continues_after_inaccessible_candidate(checkpoint_env):
    default = checkpoint_env
    default.write_bytes(b"model")
    converter._record_checkpoint_owner(default)
    old = default.with_name(f"piano-{'d' * 32}.pth")
    old.write_bytes(b"model")
    converter._record_checkpoint_owner(old)
    target = default.with_name(f"piano-{'e' * 32}.pth")
    original = converter._owned_checkpoint_identity

    def identity(path):
        if Path(path) == default:
            raise OSError("inaccessible default")
        return original(path)

    with patch.object(converter, "_owned_checkpoint_identity", side_effect=identity):
        with converter.state_file_lock():
            converter._cleanup_old_checkpoints(target)
    assert default.exists()
    assert not old.exists()


def test_newest_owned_checkpoint_is_discovered_without_download(checkpoint_env):
    default = checkpoint_env
    owned = default.with_name(f"piano-{'f' * 32}.pth")
    older = default.with_name(f"piano-{'a' * 32}.pth")
    for path in (older, owned):
        path.write_bytes(b"model")
        converter._record_checkpoint_owner(path)
    stat = owned.stat()
    os.utime(older, ns=(stat.st_atime_ns, stat.st_mtime_ns - 1_000_000_000))
    unowned = default.with_name(f"piano-{'b' * 32}.pth")
    unowned.write_bytes(b"model")
    os.utime(unowned, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    with patch.object(converter, "load_model", return_value="model-object") as load, \
         patch.object(converter.urllib.request, "urlopen") as download:
        model, result = converter.prepare_model("discover")
    assert model == "model-object"
    assert Path(result) == owned
    load.assert_called_once_with(owned)
    download.assert_not_called()


@pytest.mark.skipif(os.name == "nt", reason="POSIX ctime detects restored-mtime edits")
def test_posix_ctime_detects_corruption_with_restored_mtime(checkpoint_env):
    target = checkpoint_env
    target.write_bytes(b"model")
    converter._validate_checkpoint(target)
    stat = target.stat()
    target.write_bytes(b"wrong")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(converter.ConversionError, match="checksum"):
        converter._validate_checkpoint(target)
