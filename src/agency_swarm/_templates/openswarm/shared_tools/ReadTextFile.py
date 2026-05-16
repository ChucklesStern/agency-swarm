"""Read a small UTF-8 text file from inside the project workspace."""

from __future__ import annotations

from pydantic import Field

from agency_swarm.tools import BaseTool
from shared_tools.path_safety import (
    BINARY_SNIFF_BYTES,
    DEFAULT_MAX_BYTES,
    READABLE_TEXT_EXTENSIONS,
    PathNotAllowedError,
    is_binary_bytes,
    is_sensitive_path,
    read_text_with_fallback,
    resolve_allowed_path,
)

DEFAULT_MAX_LINES = 2000
HARD_MAX_LINES = 20000


class ReadTextFile(BaseTool):  # type: ignore[metaclass]
    """
    Read a UTF-8 text file from inside the project workspace.

    Supports .md, .txt, .json, .yaml/.yml, .csv, .py, .toml, .xml, .html, .css, .js, .ts.
    Reads only inside the allowed project roots (current project root, ./mnt, and any
    explicitly configured project folder via OPENSWARM_PROJECT_FOLDER or
    OPENSWARM_ALLOWED_READ_DIRS). Rejects binary content, oversized files, and
    secret-looking files such as .env or private keys.

    Use this whenever the user gives a path to a local Markdown or text file under the
    project workspace or its ./mnt subtree. Do not ask the user to paste, upload, or
    convert the file first.

    For long files, page through by adjusting start_line; the response always reports
    whether the slice was truncated and what start_line to use next.
    """

    file_path: str = Field(
        ...,
        description=(
            "Absolute or project-relative path to the text file. May start with "
            "'/mnt/' (normalized to './mnt/' on Windows non-docker runs)."
        ),
    )
    start_line: int = Field(
        default=1,
        ge=1,
        description="1-indexed line number to start reading from. Defaults to 1.",
    )
    max_lines: int = Field(
        default=DEFAULT_MAX_LINES,
        ge=1,
        le=HARD_MAX_LINES,
        description=(
            f"Maximum number of lines to return from start_line. "
            f"Defaults to {DEFAULT_MAX_LINES}; hard cap {HARD_MAX_LINES}. "
            "For longer files, call again with start_line set to the next unread line."
        ),
    )

    def run(self) -> str:
        try:
            resolved = resolve_allowed_path(self.file_path)
        except PathNotAllowedError as exc:
            return f"Error: {exc}"
        except FileNotFoundError:
            return f"Error: File not found: {self.file_path}"

        if resolved.is_dir():
            return f"Error: Path is a directory, not a file: {resolved}"
        if not resolved.is_file():
            return f"Error: Path is not a regular file: {resolved}"

        if is_sensitive_path(resolved):
            return (
                f"Error: Refusing to read sensitive path: {resolved}. "
                "Files such as .env and private keys, and anything under "
                ".ssh / .aws / .gcloud / .azure / .gnupg / .kube, are blocked."
            )

        suffix = resolved.suffix.lower()
        if suffix not in READABLE_TEXT_EXTENSIONS:
            allowed = ", ".join(sorted(READABLE_TEXT_EXTENSIONS))
            return (
                f"Error: Extension {suffix!r} is not in the allowed text extensions. "
                f"Allowed: {allowed}."
            )

        try:
            size = resolved.stat().st_size
        except OSError as exc:
            return f"Error: Could not stat {resolved}: {exc}"

        if size > DEFAULT_MAX_BYTES:
            mb = DEFAULT_MAX_BYTES / (1024 * 1024)
            return (
                f"Error: File is {size} bytes; refusing to read more than "
                f"{mb:g} MiB at once. Use ListProjectFiles + chunked reads instead."
            )

        try:
            with resolved.open("rb") as fh:
                sample = fh.read(BINARY_SNIFF_BYTES)
            if is_binary_bytes(sample):
                return f"Error: File appears to be binary, not text: {resolved}"
            text, encoding_label = read_text_with_fallback(resolved)
        except OSError as exc:
            return f"Error: Failed to read {resolved}: {exc}"

        # splitlines() drops the trailing newline (if any); 1-indexed line numbers
        # match what users see in editors.
        all_lines = text.splitlines()
        total = len(all_lines)

        if total == 0:
            header = "\n".join(
                [
                    f"path: {resolved}",
                    "lines: 0-0 of 0",
                    f"encoding: {encoding_label}",
                    "truncated: False",
                ]
            )
            return f"{header}\n---\n"

        if self.start_line > total:
            return (
                f"Error: start_line {self.start_line} is past the end of file "
                f"({total} lines)."
            )

        start_idx = self.start_line - 1
        end_idx = min(start_idx + self.max_lines, total)
        slice_ = all_lines[start_idx:end_idx]
        truncated = end_idx < total

        header_parts = [
            f"path: {resolved}",
            f"lines: {start_idx + 1}-{end_idx} of {total}",
            f"encoding: {encoding_label}",
        ]
        if truncated:
            header_parts.append(
                f"truncated: True (call again with start_line={end_idx + 1} for the next slice)"
            )
        else:
            header_parts.append("truncated: False")

        header = "\n".join(header_parts)
        body = "\n".join(slice_)
        return f"{header}\n---\n{body}"
