"""Search text files under an allowed project directory."""

from __future__ import annotations

import re

from pydantic import Field

from agency_swarm.tools import BaseTool
from shared_tools.path_safety import (
    BINARY_SNIFF_BYTES,
    DEFAULT_MAX_BYTES,
    READABLE_TEXT_EXTENSIONS,
    PathNotAllowedError,
    excluded_dirs_note,
    is_binary_bytes,
    is_sensitive_path,
    iter_allowed_files,
    read_text_with_fallback,
    resolve_allowed_path,
)

DEFAULT_MAX_MATCHES = 100
HARD_MAX_MATCHES = 1000
DEFAULT_CONTEXT_LINES = 0
HARD_CONTEXT_LINES = 10


class SearchTextFiles(BaseTool):  # type: ignore[metaclass]
    """
    Search text files under an allowed project directory for a pattern.

    By default the pattern is matched as a **literal string** (so a dot, parentheses,
    plus, etc. are matched as themselves). Set ``regex=True`` to interpret the
    pattern as a Python regular expression.

    Walks only inside allowed project roots (current project root, ./mnt, and any
    explicitly configured project folder via OPENSWARM_PROJECT_FOLDER or
    OPENSWARM_ALLOWED_READ_DIRS). Skips sensitive paths (.env, private keys, and
    anything under .ssh / .aws / .gcloud / .azure / .gnupg / .kube), binary files,
    oversized files, files whose extension is not in the allowed text-extension
    list, and recursive descents into noisy/heavy directories (.git, .venv,
    node_modules, __pycache__, .pytest_cache, .mypy_cache, .ruff_cache, dist,
    build, .playwright-browsers). Set include_excluded_dirs=True to opt back in.

    Use this tool to grep through long project docs or source files before reading
    them in full with ReadTextFile.
    """

    pattern: str = Field(
        ...,
        description=(
            "Text to search for. Treated as a literal string by default (regex "
            "metacharacters are escaped). Set regex=True to interpret it as a "
            "Python regular expression."
        ),
    )
    directory: str = Field(
        default=".",
        description=(
            "Directory to search. Defaults to the project root (cwd). Accepts absolute "
            "paths and '/mnt/...' paths (normalized to './mnt/...' on Windows)."
        ),
    )
    recursive: bool = Field(
        default=True,
        description="If True (default), recurse into subdirectories.",
    )
    file_glob: str = Field(
        default="*",
        description="fnmatch pattern applied to file names before searching (e.g. '*.md', '*.py').",
    )
    regex: bool = Field(
        default=False,
        description=(
            "If False (default), treat 'pattern' as a literal string. "
            "If True, treat 'pattern' as a Python regular expression."
        ),
    )
    case_sensitive: bool = Field(
        default=False,
        description="If False (default), pattern matches are case-insensitive.",
    )
    include_excluded_dirs: bool = Field(
        default=False,
        description=(
            "If True, do NOT prune the default noisy/heavy directories "
            "(.git, .venv, node_modules, __pycache__, .pytest_cache, .mypy_cache, "
            ".ruff_cache, dist, build, .playwright-browsers). Use sparingly."
        ),
    )
    context_lines: int = Field(
        default=DEFAULT_CONTEXT_LINES,
        ge=0,
        le=HARD_CONTEXT_LINES,
        description=(
            f"Number of context lines to show before and after each match. "
            f"0 = match line only. Hard cap {HARD_CONTEXT_LINES}."
        ),
    )
    max_matches: int = Field(
        default=DEFAULT_MAX_MATCHES,
        ge=1,
        le=HARD_MAX_MATCHES,
        description=(
            f"Maximum number of match snippets to return across all files. "
            f"Default {DEFAULT_MAX_MATCHES}; hard cap {HARD_MAX_MATCHES}."
        ),
    )

    def run(self) -> str:
        try:
            resolved_dir = resolve_allowed_path(self.directory)
        except PathNotAllowedError as exc:
            return f"Error: {exc}"
        except FileNotFoundError:
            return f"Error: Directory not found: {self.directory}"

        if not resolved_dir.is_dir():
            return f"Error: Path is not a directory: {resolved_dir}"

        if is_sensitive_path(resolved_dir):
            return (
                f"Error: Refusing to search sensitive directory: {resolved_dir}. "
                "Directories under .ssh / .aws / .gcloud / .azure / .gnupg / .kube are blocked."
            )

        effective_pattern = self.pattern if self.regex else re.escape(self.pattern)
        flags = 0 if self.case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(effective_pattern, flags)
        except re.error as exc:
            return f"Error: Invalid regex pattern: {exc}"

        try:
            walker = iter_allowed_files(
                resolved_dir,
                pattern=self.file_glob,
                recursive=self.recursive,
                include_excluded_dirs=self.include_excluded_dirs,
            )
        except (OSError, ValueError) as exc:
            return f"Error: Failed to walk {resolved_dir}: {exc}"

        match_blocks: list[str] = []
        files_searched = 0
        files_skipped_sensitive = 0
        files_skipped_binary = 0
        files_skipped_large = 0
        truncated = False

        for entry in walker:
            if is_sensitive_path(entry):
                files_skipped_sensitive += 1
                continue
            if entry.suffix.lower() not in READABLE_TEXT_EXTENSIONS:
                continue
            # Re-validate each entry to defend against symlink-escape during traversal.
            try:
                resolve_allowed_path(str(entry))
            except (PathNotAllowedError, FileNotFoundError):
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if size > DEFAULT_MAX_BYTES:
                files_skipped_large += 1
                continue
            try:
                with entry.open("rb") as fh:
                    sniff = fh.read(BINARY_SNIFF_BYTES)
                if is_binary_bytes(sniff):
                    files_skipped_binary += 1
                    continue
                text, _ = read_text_with_fallback(entry)
            except OSError:
                continue

            files_searched += 1
            lines = text.splitlines()
            for idx, line in enumerate(lines):
                if not compiled.search(line):
                    continue
                lo = max(0, idx - self.context_lines)
                hi = min(len(lines), idx + self.context_lines + 1)
                snippet_lines = [
                    f"{'>' if j == idx else ' '} {j + 1}: {lines[j]}" for j in range(lo, hi)
                ]
                match_blocks.append(f"{entry}:{idx + 1}\n" + "\n".join(snippet_lines))
                if len(match_blocks) >= self.max_matches:
                    truncated = True
                    break
            if truncated:
                break

        header_parts = [
            f"directory: {resolved_dir}",
            f"pattern: {self.pattern!r}",
            f"regex: {self.regex}",
            f"case_sensitive: {self.case_sensitive}",
            f"recursive: {self.recursive}",
            f"file_glob: {self.file_glob}",
            f"context_lines: {self.context_lines}",
            f"files_searched: {files_searched}",
            f"matches: {len(match_blocks)}",
        ]
        if not self.include_excluded_dirs:
            header_parts.append(f"pruned_dir_names: {excluded_dirs_note()}")
        if files_skipped_sensitive:
            header_parts.append(f"skipped_sensitive_files: {files_skipped_sensitive}")
        if files_skipped_binary:
            header_parts.append(f"skipped_binary_files: {files_skipped_binary}")
        if files_skipped_large:
            header_parts.append(f"skipped_large_files: {files_skipped_large}")
        if truncated:
            header_parts.append(
                f"truncated: True (raise max_matches above {self.max_matches} for more)"
            )
        else:
            header_parts.append("truncated: False")

        header = "\n".join(header_parts)
        body = "\n\n".join(match_blocks) if match_blocks else "(no matches)"
        return f"{header}\n---\n{body}"
