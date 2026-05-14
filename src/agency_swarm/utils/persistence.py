"""File-based persistence helper for Agency Swarm conversations."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

_SAFE_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_filename(chat_id: str) -> str:
    """Validate chat_id and return it as a safe filename component.

    Raises ValueError if the chat_id contains characters outside
    letters, digits, underscores, and hyphens.
    """
    if not chat_id or not _SAFE_CHAT_ID.fullmatch(chat_id):
        raise ValueError(
            f"chat_id {chat_id!r} is invalid: must contain only letters, "
            "numbers, underscores, and hyphens"
        )
    return chat_id


class FileSystemPersistence:
    """File-based persistence for Agency Swarm conversations.

    Stores each chat session as a JSON file inside a user-designated directory.
    The directory is created automatically on instantiation.

    Each ``chat_id`` maps to a single ``{chat_id}.json`` file inside the
    directory.  Chat IDs must contain only letters, digits, underscores, and
    hyphens; anything else raises ``ValueError`` immediately.

    Writes are atomic: data is written to a temp file in the same directory
    and then renamed into place so a crash or interruption never leaves a
    partial file.

    .. note::
        ``AGENCY_SWARM_CHATS_DIR`` is a separate environment variable that
        controls the internal cache directory (conversation-starter cache,
        etc.).  It does **not** configure this helper.

    Usage::

        persistence = FileSystemPersistence(".agency_swarm/threads")
        agency = Agency(agent, **persistence.callbacks("user_session_42"))
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, chat_id: str) -> Path:
        return self.directory / f"{_safe_filename(chat_id)}.json"

    def load(self, chat_id: str) -> list[dict[str, Any]]:
        """Return stored messages for *chat_id*, or ``[]`` if none exist."""
        path = self._path(chat_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, messages: list[dict[str, Any]], chat_id: str) -> None:
        """Atomically persist *messages* for *chat_id*."""
        target = self._path(chat_id)
        data = json.dumps(messages, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def callbacks(self, chat_id: str = "default") -> dict[str, Callable[..., Any]]:
        """Return keyword arguments to unpack directly into ``Agency(...)``.

        Example::

            agency = Agency(agent, **persistence.callbacks("session-123"))
        """
        return {
            "load_threads_callback": lambda: self.load(chat_id),
            "save_threads_callback": lambda messages: self.save(messages, chat_id),
        }
