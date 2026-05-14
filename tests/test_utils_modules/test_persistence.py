"""Tests for agency_swarm.utils.persistence.FileSystemPersistence."""

import json
from pathlib import Path
from typing import Any

import pytest

from agency_swarm.utils.persistence import FileSystemPersistence, _safe_filename


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------


class TestSafeFilename:
    """Tests for the _safe_filename() validator."""

    @pytest.mark.parametrize(
        "chat_id",
        ["default", "demo_session", "user-session-42", "abc123", "A_B-C", "x"],
    )
    def test_valid_chat_ids_accepted(self, chat_id: str) -> None:
        """Alphanumeric, underscore, and hyphen IDs pass through unchanged."""
        assert _safe_filename(chat_id) == chat_id

    @pytest.mark.parametrize(
        "chat_id",
        [
            "",                 # empty
            "a/b",              # path separator
            "../escape",        # directory traversal
            "a b",              # space
            "session.json",     # dot
            "user@host",        # special char
            "ünïcödé",          # non-ASCII
        ],
    )
    def test_unsafe_chat_id_raises(self, chat_id: str) -> None:
        """IDs with unsafe characters raise ValueError immediately."""
        with pytest.raises(ValueError, match="chat_id"):
            _safe_filename(chat_id)


# ---------------------------------------------------------------------------
# FileSystemPersistence
# ---------------------------------------------------------------------------


class TestFileSystemPersistence:
    """Tests for FileSystemPersistence load/save/callbacks behaviour."""

    def test_directory_created_on_init(self, tmp_path: Path) -> None:
        """Constructor creates the target directory when it does not exist."""
        target = tmp_path / "nested" / "threads"
        FileSystemPersistence(target)
        assert target.is_dir()

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        """load() returns [] when no file exists for the given chat_id."""
        p = FileSystemPersistence(tmp_path)
        assert p.load("new-session") == []

    def test_save_then_load_roundtrip(self, tmp_path: Path) -> None:
        """save() followed by load() returns identical data."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        p = FileSystemPersistence(tmp_path)
        p.save(messages, "session-1")
        assert p.load("session-1") == messages

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        """Data saved by one instance is readable by a new instance pointing at the same dir."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": "remember this"}]
        FileSystemPersistence(tmp_path).save(messages, "shared")
        assert FileSystemPersistence(tmp_path).load("shared") == messages

    def test_json_file_created_with_trailing_newline(self, tmp_path: Path) -> None:
        """Saved JSON file ends with a newline (POSIX convention)."""
        p = FileSystemPersistence(tmp_path)
        p.save([{"role": "user", "content": "x"}], "nl-test")
        raw = (tmp_path / "nl-test.json").read_text(encoding="utf-8")
        assert raw.endswith("\n")

    def test_json_file_utf8_encoded(self, tmp_path: Path) -> None:
        """Saved file is valid UTF-8."""
        messages: list[dict[str, Any]] = [{"content": "café résumé naïve"}]
        p = FileSystemPersistence(tmp_path)
        p.save(messages, "utf8-test")
        path = tmp_path / "utf8-test.json"
        data = json.loads(path.read_bytes().decode("utf-8"))
        assert data == messages

    def test_atomic_write_uses_temp_then_replace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """save() writes via a .tmp file; no .tmp files remain after success."""
        p = FileSystemPersistence(tmp_path)
        p.save([{"role": "user", "content": "data"}], "atomic")
        # No leftover temp files
        assert list(tmp_path.glob("*.tmp")) == []
        # Target file exists
        assert (tmp_path / "atomic.json").exists()

    def test_multiple_chat_ids_isolated(self, tmp_path: Path) -> None:
        """Each chat_id gets its own file; saves don't overwrite each other."""
        p = FileSystemPersistence(tmp_path)
        p.save([{"id": "a"}], "session-a")
        p.save([{"id": "b"}], "session-b")
        assert p.load("session-a") == [{"id": "a"}]
        assert p.load("session-b") == [{"id": "b"}]

    # --- callbacks() ---

    def test_callbacks_returns_correct_keys(self, tmp_path: Path) -> None:
        """callbacks() dict has exactly the two Agency-compatible keys."""
        cbs = FileSystemPersistence(tmp_path).callbacks("default")
        assert set(cbs.keys()) == {"load_threads_callback", "save_threads_callback"}

    def test_callbacks_are_callable(self, tmp_path: Path) -> None:
        """Both callback values are callable."""
        cbs = FileSystemPersistence(tmp_path).callbacks("default")
        assert callable(cbs["load_threads_callback"])
        assert callable(cbs["save_threads_callback"])

    def test_callbacks_load_takes_no_args(self, tmp_path: Path) -> None:
        """load_threads_callback() accepts zero arguments and returns a list."""
        cbs = FileSystemPersistence(tmp_path).callbacks("cb-test")
        result = cbs["load_threads_callback"]()
        assert isinstance(result, list)

    def test_callbacks_save_takes_one_arg(self, tmp_path: Path) -> None:
        """save_threads_callback(messages) accepts one positional argument."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
        cbs = FileSystemPersistence(tmp_path).callbacks("cb-save")
        cbs["save_threads_callback"](messages)  # must not raise
        assert FileSystemPersistence(tmp_path).load("cb-save") == messages

    def test_callbacks_roundtrip(self, tmp_path: Path) -> None:
        """Saving via save_callback and loading via load_callback returns same data."""
        messages: list[dict[str, Any]] = [{"role": "assistant", "content": "done"}]
        cbs = FileSystemPersistence(tmp_path).callbacks("roundtrip")
        cbs["save_threads_callback"](messages)
        assert cbs["load_threads_callback"]() == messages

    def test_callbacks_unsafe_chat_id_raises(self, tmp_path: Path) -> None:
        """callbacks() with an unsafe chat_id raises ValueError on first use."""
        cbs = FileSystemPersistence(tmp_path).callbacks("bad/id")
        with pytest.raises(ValueError, match="chat_id"):
            cbs["load_threads_callback"]()
