"""Tests for the bare `agency-swarm` no-subcommand launcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency_swarm.cli import launcher
from agency_swarm.cli.run_tui import find_agency, load_module


def test_ensure_agency_file_creates_default_when_missing_in_empty_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Empty cwd → agency.py is created with the template body and two stdout lines print."""
    launcher._ensure_agency_file(tmp_path)

    target = tmp_path / "agency.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == launcher._DEFAULT_AGENCY_TEMPLATE

    out = capsys.readouterr().out
    assert "No agency.py or run.py found" in out
    assert "Created agency.py" in out


def test_ensure_agency_file_creates_default_when_missing_in_nonempty_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Populated cwd (no entrypoint) → agency.py is still created and existing files are untouched.

    This is a deliberate side effect of bare `agency-swarm`: the contract is "create when
    neither agency.py nor run.py exists" regardless of what else is in the directory.
    """
    (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "foo.py").write_text("x = 1\n", encoding="utf-8")

    launcher._ensure_agency_file(tmp_path)

    target = tmp_path / "agency.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == launcher._DEFAULT_AGENCY_TEMPLATE

    # Existing files untouched
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# project\n"
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "requests\n"
    assert (tools_dir / "foo.py").read_text(encoding="utf-8") == "x = 1\n"

    out = capsys.readouterr().out
    assert "Creating ./agency.py" in out


def test_ensure_agency_file_skips_when_agency_py_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Pre-existing agency.py → file is not modified and no stdout is emitted."""
    existing = "# my custom agency\nx = 1\n"
    (tmp_path / "agency.py").write_text(existing, encoding="utf-8")

    launcher._ensure_agency_file(tmp_path)

    assert (tmp_path / "agency.py").read_text(encoding="utf-8") == existing
    assert capsys.readouterr().out == ""


def test_ensure_agency_file_skips_when_run_py_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Pre-existing run.py (no agency.py) → no agency.py is created and no stdout."""
    existing = "# my run script\n"
    (tmp_path / "run.py").write_text(existing, encoding="utf-8")

    launcher._ensure_agency_file(tmp_path)

    assert not (tmp_path / "agency.py").exists()
    assert (tmp_path / "run.py").read_text(encoding="utf-8") == existing
    assert capsys.readouterr().out == ""


def test_default_template_is_discoverable_by_run_tui(tmp_path: Path) -> None:
    """The baked-in template loads cleanly and yields exactly one Agency via run_tui discovery.

    This guards against template-vs-discovery drift: if either the template's variable
    name or the discovery contract changes, this fails before users see a broken first boot.
    The real Node TUI is never launched.
    """
    from agency_swarm import Agency

    target = tmp_path / "agency.py"
    target.write_text(launcher._DEFAULT_AGENCY_TEMPLATE, encoding="utf-8")

    module = load_module(target)
    result = find_agency(module, target)

    assert isinstance(result, Agency)
    assert len(result.agents) == 1


def test_run_launcher_calls_ensure_then_run_tui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_launcher() ensures the file first, then delegates to run_tui(None)."""
    monkeypatch.chdir(tmp_path)
    calls: list[str] = []

    def fake_ensure(cwd: Path) -> None:
        calls.append(f"ensure:{cwd}")

    def fake_run_tui(file_arg: str | None) -> None:
        calls.append(f"run_tui:{file_arg!r}")

    monkeypatch.setattr(launcher, "_ensure_agency_file", fake_ensure)
    monkeypatch.setattr(launcher, "run_tui", fake_run_tui)

    launcher.run_launcher()

    assert calls == [f"ensure:{tmp_path}", "run_tui:None"]
