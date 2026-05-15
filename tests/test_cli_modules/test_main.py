from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agency_swarm.cli import launcher as cli_launcher, main as cli_main


def test_main_dispatches_migrate_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_migrate(settings_file: str, output_dir: str) -> int:
        calls.append((settings_file, output_dir))
        return 7

    monkeypatch.setattr(cli_main, "migrate_agent_command", fake_migrate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agency-swarm", "migrate-agent", "settings.json", "--output-dir", "out"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 7
    assert calls == [("settings.json", "out")]


def test_main_dispatches_import_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, str, bool]] = []

    def fake_import(tool_name: str | None, directory: str, list_tools: bool) -> int:
        calls.append((tool_name, directory, list_tools))
        return 3

    monkeypatch.setattr(cli_main, "import_tool_command", fake_import)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agency-swarm", "import-tool", "IPythonInterpreter", "--directory", "./dest", "--list"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 3
    assert calls == [("IPythonInterpreter", "./dest", True)]


def test_main_create_agent_template_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    def fake_create_agent_template(**kwargs: object) -> bool:
        captured_kwargs.update(kwargs)
        return True

    monkeypatch.setattr(cli_main, "create_agent_template", fake_create_agent_template)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agency-swarm",
            "create-agent-template",
            "Data Analyst",
            "--description",
            "Analyzes data",
            "--model",
            "gpt-5.4-mini",
            "--reasoning",
            "high",
            "--max-tokens",
            "100",
            "--temperature",
            "0.2",
            "--instructions",
            "Be concise",
            "--use-txt",
            "--path",
            "./agents",
        ],
    )

    cli_main.main()

    assert captured_kwargs == {
        "agent_name": "Data Analyst",
        "agent_description": "Analyzes data",
        "model": "gpt-5.4-mini",
        "reasoning": "high",
        "max_tokens": 100,
        "temperature": 0.2,
        "instructions": "Be concise",
        "use_txt": True,
        "path": "./agents",
    }


def test_main_create_agent_template_failure_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "create_agent_template", lambda **_kwargs: False)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Writer"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1


def test_main_create_agent_template_exception_prints_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(**_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "create_agent_template", explode)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Writer"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert "ERROR: boom" in capsys.readouterr().err


def test_main_no_args_dispatches_to_run_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare `agency-swarm` invokes the no-subcommand launcher and skips argparse's help."""
    calls: list[str] = []

    def fake_run_launcher() -> None:
        calls.append("launcher")

    monkeypatch.setattr(cli_launcher, "run_launcher", fake_run_launcher)

    def fail_if_called(_self: argparse.ArgumentParser) -> None:
        raise AssertionError("parser.print_help should not be called when no subcommand is given")

    monkeypatch.setattr(argparse.ArgumentParser, "print_help", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["agency-swarm"])

    cli_main.main()

    assert calls == ["launcher"]


def test_main_help_flag_does_not_call_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """`agency-swarm --help` short-circuits in argparse before our dispatch runs."""
    called: list[str] = []
    monkeypatch.setattr(cli_launcher, "run_launcher", lambda: called.append("launcher"))
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 0
    assert called == []


def test_main_short_help_flag_does_not_call_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """`agency-swarm -h` short-circuits in argparse before our dispatch runs."""
    called: list[str] = []
    monkeypatch.setattr(cli_launcher, "run_launcher", lambda: called.append("launcher"))
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "-h"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 0
    assert called == []


def test_main_unknown_command_does_not_call_launcher_and_does_not_scaffold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An invalid subcommand makes argparse exit; the launcher is not called and no file is written."""
    called: list[str] = []
    monkeypatch.setattr(cli_launcher, "run_launcher", lambda: called.append("launcher"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "not-a-real-command"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    # argparse exits with code 2 for invalid arguments
    assert exc_info.value.code == 2
    assert called == []
    assert not (tmp_path / "agency.py").exists()


def test_main_internal_else_branch_handles_unknown_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The internal `else` branch in main() prints a fallback message if dispatch sees an unknown command.

    This bypasses argparse to exercise the dispatch fallback directly (defensive code path).
    """
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(command="custom-command"),
    )

    cli_main.main()

    assert "Unknown command: custom-command" in capsys.readouterr().out


def test_main_tui_subcommand_does_not_call_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """`agency-swarm tui` routes to run_tui directly, not through the no-arg launcher."""
    called: list[str] = []
    monkeypatch.setattr(cli_launcher, "run_launcher", lambda: called.append("launcher"))

    run_tui_calls: list[str | None] = []

    def fake_run_tui(file_arg: str | None) -> None:
        run_tui_calls.append(file_arg)

    monkeypatch.setattr(cli_main, "run_tui", fake_run_tui)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "tui"])

    cli_main.main()

    assert called == []
    assert run_tui_calls == [None]


def test_module_entrypoint_executes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running `python -m agency_swarm.cli.main` with no args invokes the launcher."""
    called: list[str] = []
    monkeypatch.setattr(cli_launcher, "run_launcher", lambda: called.append("launcher"))
    monkeypatch.setattr(sys, "argv", ["agency-swarm"])
    monkeypatch.delitem(sys.modules, "agency_swarm.cli.main", raising=False)

    runpy.run_module("agency_swarm.cli.main", run_name="__main__")

    assert called == ["launcher"]
