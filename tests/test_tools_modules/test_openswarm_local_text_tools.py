"""Tests for the OpenSwarm local text-file toolset (ReadTextFile, ListProjectFiles, SearchTextFiles).

These cover the user-facing contract from the "fix Markdown file reading" task:
- Reads must work on Markdown / text under the project root and ./mnt subtree.
- Reads outside allowed roots, of secret-looking files, of binary files, and of
  oversized files must be refused.
- The acceptance flow (user pastes an absolute path under ./mnt) must succeed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from shared_tools import ListProjectFiles, ReadTextFile, SearchTextFiles
from shared_tools.path_safety import (
    DEFAULT_MAX_BYTES,
    PathNotAllowedError,
    get_allowed_roots,
    is_binary_bytes,
    is_sensitive_filename,
    read_text_with_fallback,
    resolve_allowed_path,
)

# ---------------------------------------------------------------------------
# path_safety helpers
# ---------------------------------------------------------------------------


def test_is_sensitive_filename_blocks_dotenv_and_variants() -> None:
    """All .env / dotenv-* / *.pem / id_rsa patterns must be flagged as sensitive."""
    assert is_sensitive_filename(".env")
    assert is_sensitive_filename(".env.local")
    assert is_sensitive_filename(".env.production")
    assert is_sensitive_filename("id_rsa")
    assert is_sensitive_filename("id_ed25519")
    assert is_sensitive_filename("cert.pem")
    assert is_sensitive_filename("private.key")
    assert is_sensitive_filename("creds.p12")


def test_is_sensitive_filename_does_not_block_normal_text() -> None:
    """Normal Markdown / text / source file names must not be flagged."""
    assert not is_sensitive_filename("hello.md")
    assert not is_sensitive_filename("notes.txt")
    assert not is_sensitive_filename("config.toml")
    assert not is_sensitive_filename("README.md")
    assert not is_sensitive_filename("script.py")


def test_is_binary_bytes_detects_nul_and_control_density() -> None:
    """NUL bytes always flag; high control-byte density flags; plain text doesn't."""
    assert is_binary_bytes(b"hello\x00world")
    assert is_binary_bytes(bytes(range(0, 32)) * 4)  # mostly control bytes
    assert not is_binary_bytes(b"")
    assert not is_binary_bytes(b"# heading\n\nsome **markdown** content here.\n")


def test_read_text_with_fallback_returns_utf8_with_replacement_on_bad_bytes(
    tmp_path: Path,
) -> None:
    """Garbled bytes decode with replacement and the encoding label reports the fallback."""
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"valid \xff\xfe trailing")
    text, label = read_text_with_fallback(bad)
    assert "valid" in text and "trailing" in text
    assert label == "utf-8 (with replacement)"


def test_resolve_allowed_path_accepts_paths_inside_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paths inside the project root (cwd) resolve cleanly."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "hello.md"
    target.write_text("hello world\n", encoding="utf-8")
    resolved = resolve_allowed_path(str(target))
    assert resolved == target.resolve()


def test_resolve_allowed_path_accepts_paths_inside_mnt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """./mnt/<anything> resolves to an allowed root, even if it didn't exist at startup."""
    monkeypatch.chdir(tmp_path)
    mnt_file = tmp_path / "mnt" / "persistent_cat" / "hello_world.md"
    mnt_file.parent.mkdir(parents=True)
    mnt_file.write_text("# greeting\nhello from cat\n", encoding="utf-8")

    resolved = resolve_allowed_path(str(mnt_file))
    assert resolved == mnt_file.resolve()


def test_resolve_allowed_path_blocks_paths_outside_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute path outside the project tree must raise PathNotAllowedError."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere" / "secret.md"
    outside.parent.mkdir()
    outside.write_text("nope\n", encoding="utf-8")

    monkeypatch.chdir(project)

    with pytest.raises(PathNotAllowedError):
        resolve_allowed_path(str(outside))


def test_resolve_allowed_path_blocks_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink inside the project that points outside must be rejected post-resolve."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere" / "secret.md"
    outside.parent.mkdir()
    outside.write_text("nope\n", encoding="utf-8")

    link = project / "shortcut.md"
    link.symlink_to(outside)

    monkeypatch.chdir(project)
    with pytest.raises(PathNotAllowedError):
        resolve_allowed_path(str(link))


def test_resolve_allowed_path_honors_explicit_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENSWARM_ALLOWED_READ_DIRS extends the allowed-root set."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "external" / "ok.md"
    outside.parent.mkdir()
    outside.write_text("opted in\n", encoding="utf-8")

    monkeypatch.chdir(project)
    monkeypatch.setenv("OPENSWARM_ALLOWED_READ_DIRS", str(outside.parent))

    resolved = resolve_allowed_path(str(outside))
    assert resolved == outside.resolve()


def test_get_allowed_roots_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pointing OPENSWARM_PROJECT_FOLDER at cwd doesn't double-count the root."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENSWARM_PROJECT_FOLDER", str(tmp_path))
    roots = get_allowed_roots()
    assert roots.count(tmp_path.resolve()) == 1


# ---------------------------------------------------------------------------
# ReadTextFile
# ---------------------------------------------------------------------------


def test_read_text_file_reads_markdown_under_mnt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance flow: read a Markdown file from ./mnt and return the body."""
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "mnt" / "persistent_cat" / "hello_world.md"
    md.parent.mkdir(parents=True)
    md.write_text("# Hello World\n\nFrom the cat directory.\n", encoding="utf-8")

    result = ReadTextFile(file_path=str(md)).run()

    assert not result.startswith("Error")
    assert f"path: {md.resolve()}" in result
    assert "lines: 1-3 of 3" in result
    assert "encoding: utf-8" in result
    assert "truncated: False" in result
    assert "# Hello World" in result
    assert "From the cat directory." in result


def test_read_text_file_reports_truncation_and_next_start_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When max_lines is exceeded, the header reports the next start_line to resume from."""
    monkeypatch.chdir(tmp_path)
    long_file = tmp_path / "long.md"
    long_file.write_text("\n".join(f"line {i}" for i in range(1, 21)) + "\n", encoding="utf-8")

    result = ReadTextFile(file_path=str(long_file), start_line=1, max_lines=5).run()

    assert "lines: 1-5 of 20" in result
    assert "truncated: True" in result
    assert "start_line=6" in result
    assert "line 1" in result and "line 5" in result
    assert "line 6" not in result


def test_read_text_file_paginates_via_start_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start_line + max_lines slices midway through the file deterministically."""
    monkeypatch.chdir(tmp_path)
    long_file = tmp_path / "long.md"
    long_file.write_text("\n".join(f"L{i}" for i in range(1, 11)) + "\n", encoding="utf-8")

    result = ReadTextFile(file_path=str(long_file), start_line=6, max_lines=3).run()

    assert "lines: 6-8 of 10" in result
    assert "L6" in result and "L8" in result
    assert "L5" not in result
    assert "truncated: True" in result
    assert "start_line=9" in result


def test_read_text_file_blocks_path_outside_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absolute paths outside the project tree return a clear error, not contents."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere" / "secret.md"
    outside.parent.mkdir()
    outside.write_text("nope\n", encoding="utf-8")

    monkeypatch.chdir(project)
    result = ReadTextFile(file_path=str(outside)).run()

    assert result.startswith("Error:")
    assert "outside the allowed project roots" in result
    assert "nope" not in result


def test_read_text_file_blocks_sensitive_filenames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env (and look-alikes) must be refused even when they sit inside the project root."""
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=supersecret\n", encoding="utf-8")

    result = ReadTextFile(file_path=str(env_file)).run()
    assert result.startswith("Error:")
    assert "sensitive file" in result
    assert "supersecret" not in result


def test_read_text_file_blocks_disallowed_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extensions outside the allowed text-extension list are refused."""
    monkeypatch.chdir(tmp_path)
    bin_file = tmp_path / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\nbinary noise")

    result = ReadTextFile(file_path=str(bin_file)).run()
    assert result.startswith("Error:")
    assert "not in the allowed text extensions" in result


def test_read_text_file_blocks_binary_content_under_allowed_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file with a .txt extension but binary contents must still be refused."""
    monkeypatch.chdir(tmp_path)
    sneaky = tmp_path / "secret.txt"
    sneaky.write_bytes(b"hello\x00world\x00\x00")

    result = ReadTextFile(file_path=str(sneaky)).run()
    assert result.startswith("Error:")
    assert "binary" in result


def test_read_text_file_blocks_oversized_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files larger than DEFAULT_MAX_BYTES are refused with a chunked-read hint."""
    monkeypatch.chdir(tmp_path)
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (DEFAULT_MAX_BYTES + 1))

    result = ReadTextFile(file_path=str(big)).run()
    assert result.startswith("Error:")
    assert "refusing to read more than" in result


def test_read_text_file_returns_clear_error_for_missing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nonexistent paths return a user-facing error, not a traceback."""
    monkeypatch.chdir(tmp_path)
    result = ReadTextFile(file_path=str(tmp_path / "missing.md")).run()
    assert result.startswith("Error:")
    assert "not found" in result.lower() or "not allowed" in result.lower()


def test_read_text_file_rejects_directory_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing a directory path to ReadTextFile returns a clear error."""
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "subdir"
    d.mkdir()
    result = ReadTextFile(file_path=str(d)).run()
    assert result.startswith("Error:")
    assert "directory" in result.lower()


def test_read_text_file_falls_back_for_non_utf8_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garbled bytes decode with replacement and the encoding line says so."""
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "garbled.md"
    f.write_bytes(b"# title\n\xff\xfe trailing\n")
    result = ReadTextFile(file_path=str(f)).run()
    assert "encoding: utf-8 (with replacement)" in result
    assert "title" in result


# ---------------------------------------------------------------------------
# ListProjectFiles
# ---------------------------------------------------------------------------


def test_list_project_files_lists_top_level_glob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-recursive glob returns only top-level matches."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.md").write_text("deep", encoding="utf-8")

    result = ListProjectFiles(directory=str(tmp_path), pattern="*.md", recursive=False).run()
    assert "matches: 2" in result
    assert str(tmp_path / "a.md") in result
    assert str(tmp_path / "b.md") in result
    assert "deep.md" not in result


def test_list_project_files_recursive_walks_mnt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recursive listing under ./mnt finds files in nested project folders."""
    monkeypatch.chdir(tmp_path)
    mnt = tmp_path / "mnt" / "persistent_cat"
    mnt.mkdir(parents=True)
    (mnt / "hello_world.md").write_text("hi", encoding="utf-8")
    (mnt / "nested" / "deep.txt").parent.mkdir()
    (mnt / "nested" / "deep.txt").write_text("deep", encoding="utf-8")

    result = ListProjectFiles(directory=str(tmp_path / "mnt"), pattern="*", recursive=True).run()

    assert "matches: 2" in result
    assert "hello_world.md" in result
    assert "deep.txt" in result


def test_list_project_files_skips_sensitive_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env and private keys are not surfaced in listings."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("ok", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=zzz", encoding="utf-8")
    (tmp_path / "id_rsa").write_text("KEY", encoding="utf-8")

    result = ListProjectFiles(directory=str(tmp_path), pattern="*", recursive=False).run()
    assert "notes.md" in result
    assert ".env" not in result.split("---", 1)[1]
    assert "id_rsa" not in result.split("---", 1)[1]
    assert "skipped_sensitive: 2" in result


def test_list_project_files_blocks_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Listing a directory outside the allowed roots returns an error, not contents."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "leak.md").write_text("leak", encoding="utf-8")

    monkeypatch.chdir(project)
    result = ListProjectFiles(directory=str(outside), pattern="*", recursive=False).run()
    assert result.startswith("Error:")
    assert "outside the allowed project roots" in result


# ---------------------------------------------------------------------------
# SearchTextFiles
# ---------------------------------------------------------------------------


def test_search_text_files_finds_pattern_with_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches return file:line locations and optional surrounding context."""
    monkeypatch.chdir(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(
        "intro line\nneedle here\nanother line\nsecond needle line\nfinal\n",
        encoding="utf-8",
    )

    result = SearchTextFiles(
        pattern="needle",
        directory=str(tmp_path),
        context_lines=1,
        recursive=True,
    ).run()

    assert "matches: 2" in result
    assert f"{doc}:2" in result
    assert f"{doc}:4" in result
    assert "intro line" in result  # context before line 2
    assert "another line" in result  # context after line 2


def test_search_text_files_skips_sensitive_and_disallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hits inside .env or binary files don't surface, and the headers tally the skips."""
    monkeypatch.chdir(tmp_path)
    ok = tmp_path / "notes.md"
    ok.write_text("the secret token is hidden\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_TOKEN=abc\n", encoding="utf-8")
    (tmp_path / "bin.txt").write_bytes(b"SECRET_TOKEN\x00binary")

    result = SearchTextFiles(
        pattern="SECRET_TOKEN",
        directory=str(tmp_path),
        recursive=False,
    ).run()

    body = result.split("---", 1)[1]
    assert "abc" not in body
    assert "binary" not in body
    assert "skipped_sensitive_files: 1" in result
    assert "skipped_binary_files: 1" in result


def test_search_text_files_invalid_regex_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad regex returns a friendly error rather than raising."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.md").write_text("hi", encoding="utf-8")
    result = SearchTextFiles(pattern="(unclosed", directory=str(tmp_path)).run()
    assert result.startswith("Error:")
    assert "Invalid regex" in result


def test_search_text_files_blocks_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory outside the project roots is refused even with a valid regex."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "leak.md").write_text("apikey 1234\n", encoding="utf-8")

    monkeypatch.chdir(project)
    result = SearchTextFiles(pattern="apikey", directory=str(outside)).run()
    assert result.startswith("Error:")
    assert "outside the allowed project roots" in result


# ---------------------------------------------------------------------------
# Acceptance scenario from the task description
# ---------------------------------------------------------------------------


def test_acceptance_user_pasted_mnt_path_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end shape of the acceptance flow:

    User runs the agency from a project directory and pastes an absolute path under
    ``./mnt/persistent_cat/hello_world.md``. ReadTextFile must:
      * confirm the path is inside the allowed project/persistent root, and
      * return the Markdown contents (not an error, not a "convert to PDF" deflection).
    """
    project = tmp_path / "my-first-swarm"
    project.mkdir()
    persistent = project / "mnt" / "persistent_cat"
    persistent.mkdir(parents=True)
    md = persistent / "hello_world.md"
    md.write_text("# Hello, world!\n\nThis is the cat doc.\n", encoding="utf-8")

    monkeypatch.chdir(project)

    result = ReadTextFile(file_path=str(md)).run()

    assert not result.startswith("Error")
    assert "Hello, world!" in result
    assert "This is the cat doc." in result
    assert "encoding: utf-8" in result
    # The header should record the resolved absolute path so the user can verify it.
    assert f"path: {md.resolve()}" in result


def test_acceptance_outside_mnt_is_refused_not_swallowed_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paths under ./mnt are allowed; paths above the project root are blocked."""
    project = tmp_path / "my-first-swarm"
    project.mkdir()
    monkeypatch.chdir(project)

    outside = tmp_path / "stranger" / "file.md"
    outside.parent.mkdir()
    outside.write_text("not yours\n", encoding="utf-8")

    result = ReadTextFile(file_path=str(outside)).run()
    assert result.startswith("Error:")
    # The message must point the user at the safe path rather than at a deflection.
    assert "allowed project roots" in result


# Skip the symlink-escape test on Windows where the test setup can't always create symlinks
# without elevated privileges.
if os.name == "nt":
    test_resolve_allowed_path_blocks_symlink_escape = pytest.mark.skip(  # type: ignore[assignment]
        reason="Windows symlink permissions are out of scope"
    )(test_resolve_allowed_path_blocks_symlink_escape)
