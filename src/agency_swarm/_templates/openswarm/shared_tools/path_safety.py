"""Shared path-safety helpers for the local text-file toolset.

Used by ReadTextFile, ListProjectFiles, and SearchTextFiles to keep local
filesystem reads inside the user's project workspace. Paths outside the
allowed roots are blocked, and files that look like secrets (`.env`,
private keys, etc.) are refused even when they are inside an allowed root.

Allowed roots, resolved at call time:

1. The current working directory (the user's project root).
2. ``./mnt`` under that project root, if it resolves.
3. ``OPENSWARM_PROJECT_FOLDER`` (single path), if set.
4. ``OPENSWARM_ALLOWED_READ_DIRS`` (os.pathsep-separated), if set.

Symlinks are followed when resolving the candidate path, so symlink-escape
attempts cannot smuggle reads outside the real allowed tree.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path

# Extensions the local text tools will open. Anything else is rejected.
READABLE_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".csv",
        ".py",
        ".toml",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".ts",
    }
)

# Filenames that look sensitive even when the extension would otherwise be text-like.
SENSITIVE_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".envrc",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "authorized_keys",
        "known_hosts",
        "credentials",
        "credentials.json",
    }
)

# Suffixes that look like keys, certs, or other secrets.
SENSITIVE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".gpg",
        ".asc",
        ".crt",
        ".cer",
        ".pkcs12",
        ".keystore",
        ".jks",
    }
)

# Filename prefixes that flag dotenv variants like ".env.local" or ".env.prod".
SENSITIVE_PREFIXES: tuple[str, ...] = (".env.",)

# Directory names that mark credential trees. A path is refused if any
# ancestor directory in its resolved form matches one of these names.
# ``.config`` is deliberately omitted: many projects use it for lint / build
# config trees (`.config/ruff.toml`, etc.), so blocking it by default would
# produce too many false positives. Users with sensitive ``.config`` data
# should keep it outside the project workspace.
SENSITIVE_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {
        ".ssh",
        ".aws",
        ".gcloud",
        ".azure",
        ".gnupg",
        ".kube",
    }
)

# Directory names pruned at walk time during recursive list/search to keep
# results focused on the user's authored project content. Reading an
# individual file inside one of these via an explicit ReadTextFile path is
# still allowed (subject to the other safety checks); the prune only stops
# noisy/heavy recursive descents.
EXCLUDED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".playwright-browsers",
    }
)

# Max bytes a single ReadTextFile / SearchTextFiles read will accept.
# Larger files require chunked reads via start_line / max_lines.
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB

# How many leading bytes we sniff to detect binary content.
BINARY_SNIFF_BYTES = 8 * 1024

# Control bytes that strongly suggest binary content if they appear in the sniff.
_BINARY_CONTROL_BYTES: frozenset[int] = frozenset(
    b for b in range(0x00, 0x20) if b not in (0x09, 0x0A, 0x0D)
)


class PathNotAllowedError(Exception):
    """Raised when a tool is asked to touch a path outside the allowed roots."""


def _normalize_mnt_input(raw: str) -> str:
    """Mirror CopyFile's ``/mnt → ./mnt`` normalization on Windows non-docker runs.

    Linux-style ``/mnt/...`` paths emitted by agents resolve to ``<drive>:\\mnt\\...``
    on Windows, which is not the repo-local ``./mnt`` folder. Normalize so users
    on Windows see the same tree as agents do in containers.
    """
    if not raw:
        return raw
    if os.name != "nt":
        return raw
    if Path("/.dockerenv").is_file():
        return raw
    if raw.startswith("/mnt/") or raw == "/mnt":
        mnt = (Path(__file__).resolve().parents[1] / "mnt").resolve()
        suffix = raw[len("/mnt/") :] if raw.startswith("/mnt/") else ""
        return str(mnt / suffix)
    return raw


def _split_env_paths(raw: str | None) -> list[Path]:
    if not raw:
        return []
    out: list[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(Path(part).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
    return out


def get_allowed_roots() -> list[Path]:
    """Return the resolved directories the local text tools may touch.

    Order is informational; membership is what matters. Duplicates are removed
    after each entry is resolved (so two env vars pointing at the same place
    only show up once).
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except (OSError, RuntimeError):
            return
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    _add(Path.cwd())
    _add(Path.cwd() / "mnt")

    project = os.getenv("OPENSWARM_PROJECT_FOLDER")
    if project:
        _add(Path(project))

    for extra in _split_env_paths(os.getenv("OPENSWARM_ALLOWED_READ_DIRS")):
        _add(extra)

    return roots


def is_sensitive_filename(name: str) -> bool:
    """Return True if *name* matches the secret-file block list."""
    if not name:
        return False
    lname = name.lower()
    if lname in SENSITIVE_FILENAMES:
        return True
    if any(lname.startswith(prefix) for prefix in SENSITIVE_PREFIXES):
        return True
    if Path(lname).suffix in SENSITIVE_SUFFIXES:
        return True
    return False


def is_sensitive_path(path: Path) -> bool:
    """Return True if *path* is sensitive by filename OR by any path segment.

    Works for both files and directories: if any component of the resolved
    path (the leaf or any ancestor) matches ``SENSITIVE_DIRECTORY_NAMES``,
    the path is refused. This means a file like ``~/.ssh/notes.md`` and the
    directory ``~/.aws`` are both blocked.
    """
    if is_sensitive_filename(path.name):
        return True
    for part in path.parts:
        if part in SENSITIVE_DIRECTORY_NAMES:
            return True
    return False


def resolve_allowed_path(raw_path: str, *, must_exist: bool = True) -> Path:
    """Resolve *raw_path*, confirm it sits inside an allowed root, and return it.

    Raises :class:`PathNotAllowedError` when the path is empty, unresolvable,
    or escapes the allowed roots. Raises :class:`FileNotFoundError` when
    ``must_exist`` is True and the path does not exist on disk.
    """
    if not raw_path or not raw_path.strip():
        raise PathNotAllowedError("Path is empty.")

    candidate_raw = _normalize_mnt_input(raw_path.strip())
    candidate = Path(candidate_raw).expanduser()

    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError:
        raise
    except (OSError, RuntimeError) as exc:
        raise PathNotAllowedError(f"Could not resolve path: {candidate} ({exc!r})") from exc

    roots = get_allowed_roots()
    for root in roots:
        try:
            if resolved == root or resolved.is_relative_to(root):
                return resolved
        except ValueError:
            continue

    pretty_roots = ", ".join(str(r) for r in roots) or "(no allowed roots configured)"
    raise PathNotAllowedError(
        f"Path {resolved} is outside the allowed project roots: {pretty_roots}"
    )


def is_binary_bytes(sample: bytes) -> bool:
    """Heuristic: a non-empty sample is binary if it contains NUL or many control bytes."""
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    control_hits = sum(1 for b in sample if b in _BINARY_CONTROL_BYTES)
    return control_hits / len(sample) > 0.30


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    """Read *path* as UTF-8, falling back to UTF-8 with replacement on decode errors.

    Returns ``(text, encoding_label)`` so callers can surface any fidelity loss
    instead of silently corrupting non-UTF-8 input.
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), "utf-8 (with replacement)"


def iter_allowed_files(
    root: Path,
    *,
    pattern: str = "*",
    recursive: bool = True,
    include_excluded_dirs: bool = False,
) -> Iterator[Path]:
    """Walk *root* in name-sorted order, yielding files whose basename matches *pattern*.

    Heavy / noisy directories (``EXCLUDED_DIRECTORY_NAMES``) are pruned at walk
    time so recursive list / search never descends into ``.git``, ``.venv``,
    ``node_modules``, etc. Pass ``include_excluded_dirs=True`` to opt back in.

    Pattern matching is filename-only via :func:`fnmatch.fnmatch` (e.g.
    ``"*.md"``, ``"hello_*.txt"``). Callers are responsible for any further
    filtering — sensitive-path checks, extension allow-lists, binary sniffs,
    etc. — and for re-validating each yielded entry against
    :func:`resolve_allowed_path` to defend against symlink-escape during walk.
    """
    for current, dirs, files in os.walk(root):
        if include_excluded_dirs:
            dirs.sort()
        else:
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRECTORY_NAMES)
        if not recursive:
            dirs.clear()
        for fname in sorted(files):
            if fnmatch.fnmatch(fname, pattern):
                yield Path(current) / fname


def excluded_dirs_note() -> str:
    """One-line summary of the pruned directory names, for inclusion in tool responses."""
    return ", ".join(sorted(EXCLUDED_DIRECTORY_NAMES))
