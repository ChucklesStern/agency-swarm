"""List files inside an allowed project directory."""

from __future__ import annotations

from pydantic import Field

from agency_swarm.tools import BaseTool
from shared_tools.path_safety import (
    PathNotAllowedError,
    is_sensitive_filename,
    resolve_allowed_path,
)

DEFAULT_MAX_RESULTS = 200
HARD_MAX_RESULTS = 2000


class ListProjectFiles(BaseTool):  # type: ignore[metaclass]
    """
    List files inside an allowed project directory.

    Walks only inside allowed project roots (current project root, ./mnt, and any
    explicitly configured project folder via OPENSWARM_PROJECT_FOLDER or
    OPENSWARM_ALLOWED_READ_DIRS). Sensitive entries such as .env files and private
    keys are omitted; directories are skipped (file paths only).

    Use this when the user asks what's in a project subdirectory or under ./mnt before
    deciding which file to read with ReadTextFile or grep with SearchTextFiles.
    """

    directory: str = Field(
        default=".",
        description=(
            "Directory to list. Defaults to the project root (cwd). Accepts absolute "
            "paths and '/mnt/...' paths (normalized to './mnt/...' on Windows)."
        ),
    )
    pattern: str = Field(
        default="*",
        description="Glob pattern applied to file names (e.g. '*.md', 'hello_*.txt').",
    )
    recursive: bool = Field(
        default=False,
        description="If True, recurse into subdirectories.",
    )
    max_results: int = Field(
        default=DEFAULT_MAX_RESULTS,
        ge=1,
        le=HARD_MAX_RESULTS,
        description=(
            f"Maximum number of file paths to return. Defaults to {DEFAULT_MAX_RESULTS}; "
            f"hard cap {HARD_MAX_RESULTS}."
        ),
    )

    def run(self) -> str:
        try:
            resolved = resolve_allowed_path(self.directory)
        except PathNotAllowedError as exc:
            return f"Error: {exc}"
        except FileNotFoundError:
            return f"Error: Directory not found: {self.directory}"

        if not resolved.is_dir():
            return f"Error: Path is not a directory: {resolved}"

        try:
            iterator = (
                resolved.rglob(self.pattern) if self.recursive else resolved.glob(self.pattern)
            )
        except (OSError, ValueError) as exc:
            return f"Error: Failed to list {resolved}: {exc}"

        results: list[str] = []
        skipped_sensitive = 0
        skipped_outside = 0
        truncated = False

        for entry in iterator:
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue
            if is_sensitive_filename(entry.name):
                skipped_sensitive += 1
                continue
            # Re-validate each entry to defend against symlink-escape during traversal.
            try:
                resolve_allowed_path(str(entry))
            except (PathNotAllowedError, FileNotFoundError):
                skipped_outside += 1
                continue
            results.append(str(entry))
            if len(results) >= self.max_results:
                truncated = True
                break

        results.sort()

        header_parts = [
            f"directory: {resolved}",
            f"pattern: {self.pattern}",
            f"recursive: {self.recursive}",
            f"matches: {len(results)}",
        ]
        if skipped_sensitive:
            header_parts.append(f"skipped_sensitive: {skipped_sensitive}")
        if skipped_outside:
            header_parts.append(f"skipped_outside_roots: {skipped_outside}")
        if truncated:
            header_parts.append(
                f"truncated: True (raise max_results above {self.max_results} for more)"
            )
        else:
            header_parts.append("truncated: False")

        header = "\n".join(header_parts)
        body = "\n".join(results) if results else "(no matches)"
        return f"{header}\n---\n{body}"
