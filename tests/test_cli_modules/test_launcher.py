"""Tests for the bare `agency-swarm` no-subcommand launcher."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agency_swarm.cli import launcher
from agency_swarm.cli.run_tui import find_agency, load_module


def test_ensure_minimal_agency_creates_default_when_missing_in_empty_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Empty cwd → agency.py is created with the template body and two stdout lines print."""
    launcher._ensure_minimal_agency(tmp_path)

    target = tmp_path / "agency.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == launcher._DEFAULT_AGENCY_TEMPLATE

    out = capsys.readouterr().out
    assert "No agency.py or run.py found" in out
    assert "Created agency.py" in out


def test_ensure_minimal_agency_creates_default_when_missing_in_nonempty_dir(
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

    launcher._ensure_minimal_agency(tmp_path)

    target = tmp_path / "agency.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == launcher._DEFAULT_AGENCY_TEMPLATE

    # Existing files untouched
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# project\n"
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "requests\n"
    assert (tools_dir / "foo.py").read_text(encoding="utf-8") == "x = 1\n"

    out = capsys.readouterr().out
    assert "Creating ./agency.py" in out


def test_ensure_minimal_agency_skips_when_agency_py_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Pre-existing agency.py → file is not modified and no stdout is emitted."""
    existing = "# my custom agency\nx = 1\n"
    (tmp_path / "agency.py").write_text(existing, encoding="utf-8")

    launcher._ensure_minimal_agency(tmp_path)

    assert (tmp_path / "agency.py").read_text(encoding="utf-8") == existing
    assert capsys.readouterr().out == ""


def test_ensure_minimal_agency_skips_when_run_py_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Pre-existing run.py (no agency.py) → no agency.py is created and no stdout."""
    existing = "# my run script\n"
    (tmp_path / "run.py").write_text(existing, encoding="utf-8")

    launcher._ensure_minimal_agency(tmp_path)

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

    monkeypatch.setattr(launcher, "_ensure_minimal_agency", fake_ensure)
    monkeypatch.setattr(launcher, "run_tui", fake_run_tui)

    launcher.run_launcher()

    assert calls == [f"ensure:{tmp_path}", "run_tui:None"]


def test_init_minimal_delegates_to_run_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`agency-swarm init minimal` and bare `agency-swarm` share the same code path."""
    monkeypatch.chdir(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(launcher, "_ensure_minimal_agency", lambda cwd: calls.append(f"ensure:{cwd}"))
    monkeypatch.setattr(launcher, "run_tui", lambda f: calls.append(f"run_tui:{f!r}"))

    launcher.init_minimal()

    assert calls == [f"ensure:{tmp_path}", "run_tui:None"]


# ---------------------------------------------------------------------------
# OpenSwarm scaffold (phase 3)
# ---------------------------------------------------------------------------


def _stub_openswarm_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `_dep_check_openswarm` with a no-op for tests that go past dep gating."""
    monkeypatch.setattr(launcher, "_dep_check_openswarm", lambda: None)


def test_dep_check_openswarm_passes_when_all_canaries_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """When every canary imports cleanly, the gate is silent."""
    monkeypatch.setattr(launcher.importlib, "import_module", lambda _name: None)

    launcher._dep_check_openswarm()  # no exception


def test_dep_check_openswarm_fails_on_first_missing_canary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A single missing canary exits with code 1 and surfaces the install hint + module name."""

    def fake_import(name: str) -> None:
        if name == "pandas":
            raise ImportError(f"No module named '{name}'")
        return None

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)

    with pytest.raises(SystemExit) as exc_info:
        launcher._dep_check_openswarm()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "could not import: pandas" in err
    assert "[openswarm]" in err


def test_openswarm_template_root_yields_a_directory_containing_swarm_py() -> None:
    """`importlib.resources` finds the vendored template under both editable + wheel installs."""
    with launcher._openswarm_template_root() as root:
        assert root.is_dir()
        assert (root / "swarm.py").is_file()
        assert (root / "orchestrator").is_dir()


def test_iter_openswarm_manifest_renames_swarm_py_and_skips_notice() -> None:
    """The manifest renames swarm.py → agency.py and excludes the developer-facing NOTICE.md."""
    with launcher._openswarm_template_root() as root:
        manifest = list(launcher._iter_openswarm_manifest(root))

    dests = [rel for _, rel in manifest]
    dest_names = [str(rel) for rel in dests]

    assert "agency.py" in dest_names
    assert "swarm.py" not in dest_names
    assert "NOTICE.md" not in dest_names  # developer-facing manifest stays in package
    assert "OPENSWARM_NOTICE.md" in dest_names  # user-facing attribution comes along
    assert "OPENSWARM_LICENSE" in dest_names
    assert any(str(rel).startswith("orchestrator/") for rel in dests)
    assert any(str(rel).startswith("patches/") for rel in dests)


def test_preflight_returns_existing_paths(tmp_path: Path) -> None:
    """Pre-create some destinations; preflight reports them as conflicts."""
    (tmp_path / "agency.py").write_text("custom\n", encoding="utf-8")
    (tmp_path / "orchestrator").mkdir()
    (tmp_path / "orchestrator" / "orchestrator.py").write_text("custom\n", encoding="utf-8")

    with launcher._openswarm_template_root() as root:
        manifest = list(launcher._iter_openswarm_manifest(root))

    conflicts = launcher._preflight_openswarm_destinations(tmp_path, manifest)
    conflict_names = {p.relative_to(tmp_path).as_posix() for p in conflicts}

    assert "agency.py" in conflict_names
    assert "orchestrator/orchestrator.py" in conflict_names


def test_preflight_returns_empty_for_clean_cwd(tmp_path: Path) -> None:
    """Empty cwd → no conflicts."""
    with launcher._openswarm_template_root() as root:
        manifest = list(launcher._iter_openswarm_manifest(root))

    conflicts = launcher._preflight_openswarm_destinations(tmp_path, manifest)

    assert conflicts == []


def test_preflight_does_not_flag_env(tmp_path: Path) -> None:
    """An existing `.env` is NOT a scaffold conflict — only manifest paths matter."""
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    with launcher._openswarm_template_root() as root:
        manifest = list(launcher._iter_openswarm_manifest(root))

    conflicts = launcher._preflight_openswarm_destinations(tmp_path, manifest)

    assert conflicts == []


def test_init_openswarm_aborts_when_preflight_finds_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pre-existing agency.py blocks the scaffold; nothing else runs."""
    _stub_openswarm_deps(monkeypatch)
    (tmp_path / "agency.py").write_text("preexisting\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    wizard_calls: list[str] = []
    run_tui_calls: list[str] = []
    monkeypatch.setattr(launcher, "_run_onboarding_wizard", lambda cwd: wizard_calls.append("wizard") or True)
    monkeypatch.setattr(launcher, "run_tui", lambda f: run_tui_calls.append(f"run_tui:{f!r}"))

    with pytest.raises(SystemExit) as exc_info:
        launcher.init_openswarm()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Refusing to scaffold OpenSwarm" in err
    assert "./agency.py" in err
    assert wizard_calls == []
    assert run_tui_calls == []
    # The pre-existing file is untouched.
    assert (tmp_path / "agency.py").read_text(encoding="utf-8") == "preexisting\n"


def test_init_openswarm_dep_check_exits_before_any_disk_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the canary check fails, scaffold runs zero file writes."""

    def fake_import(_name: str) -> None:
        raise ImportError("simulated missing extra")

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)
    monkeypatch.chdir(tmp_path)

    scaffold_calls: list[str] = []
    monkeypatch.setattr(launcher, "_scaffold_openswarm", lambda cwd, manifest: scaffold_calls.append("scaffold"))

    with pytest.raises(SystemExit) as exc_info:
        launcher.init_openswarm()

    assert exc_info.value.code == 1
    assert scaffold_calls == []
    # No files should appear in cwd.
    assert list(tmp_path.iterdir()) == []


def test_scaffold_openswarm_copies_tree_and_renames_swarm_py(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: bare cwd → agency.py written, swarm.py absent, all 8 agent dirs present.

    Wizard is stubbed (.env pre-written so the wizard branch short-circuits).
    `run_tui` is stubbed.
    """
    _stub_openswarm_deps(monkeypatch)
    monkeypatch.chdir(tmp_path)

    # Pre-write .env so the wizard step short-circuits cleanly.
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-not-real\n", encoding="utf-8")

    run_tui_calls: list[str] = []
    monkeypatch.setattr(launcher, "run_tui", lambda f: run_tui_calls.append(f"run_tui:{f!r}"))

    launcher.init_openswarm()

    # Renamed entrypoint.
    assert (tmp_path / "agency.py").is_file()
    assert not (tmp_path / "swarm.py").exists()
    # Eight agent directories.
    for d in (
        "orchestrator",
        "virtual_assistant",
        "deep_research",
        "data_analyst_agent",
        "slides_agent",
        "docs_agent",
        "image_generation_agent",
        "video_generation_agent",
    ):
        assert (tmp_path / d).is_dir()
    # Support directories + key files.
    assert (tmp_path / "shared_tools").is_dir()
    assert (tmp_path / "patches").is_dir()
    assert (tmp_path / "shared_instructions.md").is_file()
    assert (tmp_path / "OPENSWARM_LICENSE").is_file()
    assert (tmp_path / "OPENSWARM_NOTICE.md").is_file()
    # Developer-facing manifest does NOT end up in user cwd.
    assert not (tmp_path / "NOTICE.md").exists()
    # TUI was launched.
    assert run_tui_calls == ["run_tui:None"]
    # Stdout summarized what happened.
    out = capsys.readouterr().out
    assert "Scaffolding OpenSwarm" in out
    assert "created agency.py" in out
    assert "created orchestrator/" in out


def test_init_openswarm_skips_wizard_when_env_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An existing `.env` means the wizard is skipped entirely (not even called)."""
    _stub_openswarm_deps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    wizard_calls: list[str] = []
    monkeypatch.setattr(launcher, "_run_onboarding_wizard", lambda cwd: wizard_calls.append("wizard") or True)
    monkeypatch.setattr(launcher, "run_tui", lambda f: None)

    launcher.init_openswarm()

    assert wizard_calls == []


def test_init_openswarm_aborts_when_wizard_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the wizard returns False (no .env left behind), abort before TUI launch."""
    _stub_openswarm_deps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    # No .env yet, and the wizard returns False (still no .env after).
    monkeypatch.setattr(launcher, "_run_onboarding_wizard", lambda cwd: False)

    tui_calls: list[str] = []
    monkeypatch.setattr(launcher, "run_tui", lambda f: tui_calls.append("ran"))

    with pytest.raises(SystemExit) as exc_info:
        launcher.init_openswarm()

    assert exc_info.value.code == 1
    assert tui_calls == []
    err = capsys.readouterr().err
    assert "Wizard did not complete" in err


def test_run_onboarding_wizard_invokes_subprocess_with_correct_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wizard subprocess gets `[sys.executable, "onboard.py"]` with cwd=cwd."""
    recorded: dict[str, object] = {}

    def fake_run(argv, cwd, check):  # type: ignore[no-untyped-def]
        recorded["argv"] = argv
        recorded["cwd"] = cwd
        recorded["check"] = check
        # Simulate the wizard writing .env.
        (Path(cwd) / ".env").write_text("OPENAI_API_KEY=ok\n", encoding="utf-8")
        return None  # launcher ignores the return value; check=False keeps run() silent

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    result = launcher._run_onboarding_wizard(tmp_path)

    assert result is True
    assert recorded["argv"] == [sys.executable, "onboard.py"]
    assert recorded["cwd"] == tmp_path
    assert recorded["check"] is False


def test_run_onboarding_wizard_returns_false_when_env_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subprocess returns non-zero and writes no .env → wizard reported as failed."""

    def fake_run(argv, cwd, check):  # type: ignore[no-untyped-def]
        return None  # subprocess "ran" but didn't write .env

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert launcher._run_onboarding_wizard(tmp_path) is False


def test_run_onboarding_wizard_swallows_keyboard_interrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl-C during the wizard returns False instead of propagating."""

    def fake_run(argv, cwd, check):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    # Should not raise — must return False since no .env was written.
    assert launcher._run_onboarding_wizard(tmp_path) is False


def test_init_openswarm_runs_wizard_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When `.env` is absent, init_openswarm() calls the wizard subprocess."""
    _stub_openswarm_deps(monkeypatch)
    monkeypatch.chdir(tmp_path)

    wizard_invocations: list[Path] = []

    def fake_run(argv, cwd, check):  # type: ignore[no-untyped-def]
        wizard_invocations.append(Path(cwd))
        # Simulate successful wizard completion.
        (Path(cwd) / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
        return None  # launcher ignores the return value; check=False keeps run() silent

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher, "run_tui", lambda f: None)

    launcher.init_openswarm()

    assert wizard_invocations == [tmp_path]
    assert (tmp_path / ".env").is_file()


def test_scaffolded_agency_py_is_discoverable_by_run_tui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical: the scaffolded agency.py loads through run_tui.load_module/find_agency.

    This validates that the swarm.py → agency.py rename is safe and that the OpenSwarm
    patches + agent imports don't break on the current agency-swarm version.

    Offline-safety: a fake .env is pre-written so dotenv-loading inside the agency
    succeeds without prompting. The TUI is never launched (run_tui at the launcher
    boundary is mocked). The agency import is NOT mocked — this is the whole point
    of the test.

    Skipped if the [openswarm] extras aren't installed in the test environment;
    in that case the test would fail at agency import for unrelated reasons.
    """
    pytest.importorskip("questionary")
    pytest.importorskip("pandas")
    pytest.importorskip("fal_client")
    pytest.importorskip("composio")
    pytest.importorskip("matplotlib")

    from agency_swarm import Agency

    _stub_openswarm_deps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("DEFAULT_MODEL", "gpt-5.4")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test-not-a-real-key\nDEFAULT_MODEL=gpt-5.4\n",
        encoding="utf-8",
    )

    # Mock run_tui at the launcher boundary so the TUI never opens.
    monkeypatch.setattr(launcher, "run_tui", lambda f: None)

    launcher.init_openswarm()

    agency_py = tmp_path / "agency.py"
    assert agency_py.is_file()

    # Real load_module + find_agency — no mocks here.
    module = load_module(agency_py)
    result = find_agency(module, agency_py)

    assert isinstance(result, Agency)
    assert len(result.agents) >= 8
