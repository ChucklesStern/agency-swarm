"""Tests for agency_swarm.cli.run_tui (agency-swarm tui subcommand)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agency_swarm.cli.run_tui import find_agency, load_module, resolve_entrypoint, run_tui


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, src: str) -> Path:
    """Write *src* to *tmp_path/name* and return the path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return p


def _agency_src(var_name: str = "agency", agent_name: str = "TestAgent") -> str:
    """Return already-dedented source that creates an Agency instance bound to *var_name*."""
    return textwrap.dedent(f"""\
        from unittest.mock import patch
        from agents import ModelSettings
        from agency_swarm import Agency, Agent
        from tests.deterministic_model import DeterministicModel

        with patch("agency_swarm.agency.setup._apply_files_folder"):
            {var_name} = Agency(
                Agent(
                    name="{agent_name}",
                    instructions="test",
                    model=DeterministicModel(),
                    model_settings=ModelSettings(temperature=0.0),
                )
            )
        """)


# ---------------------------------------------------------------------------
# resolve_entrypoint
# ---------------------------------------------------------------------------


class TestResolveEntrypoint:
    def test_explicit_path_found(self, tmp_path: Path) -> None:
        """An explicit path that exists is returned resolved."""
        f = _write(tmp_path, "myagency.py", "x = 1\n")
        result = resolve_entrypoint(str(f))
        assert result == f.resolve()

    def test_invalid_explicit_path_error(self, tmp_path: Path) -> None:
        """A non-existent explicit path raises SystemExit."""
        with pytest.raises(SystemExit, match="not found"):
            resolve_entrypoint(str(tmp_path / "missing.py"))

    def test_default_agency_py_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """agency.py is preferred over run.py when both exist."""
        _write(tmp_path, "agency.py", "x = 1\n")
        _write(tmp_path, "run.py", "x = 2\n")
        monkeypatch.chdir(tmp_path)
        result = resolve_entrypoint(None)
        assert result.name == "agency.py"

    def test_default_run_py_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run.py is used when agency.py is absent."""
        _write(tmp_path, "run.py", "x = 1\n")
        monkeypatch.chdir(tmp_path)
        result = resolve_entrypoint(None)
        assert result.name == "run.py"

    def test_no_entrypoint_file_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No default file found → SystemExit with clear message."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit, match="No entrypoint file found"):
            resolve_entrypoint(None)


# ---------------------------------------------------------------------------
# find_agency
# ---------------------------------------------------------------------------


class TestFindAgency:
    def test_factory_create_agency(self, tmp_path: Path) -> None:
        """create_agency() factory takes priority and its return value is used."""
        src = _agency_src("_inner") + "\ndef create_agency():\n    return _inner\n"
        # _write calls textwrap.dedent; src is already dedented so this is a no-op.
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        from agency_swarm import Agency

        result = find_agency(module, f)
        assert isinstance(result, Agency)

    def test_factory_wrong_return_type_error(self, tmp_path: Path) -> None:
        """create_agency() returning a non-Agency raises SystemExit."""
        src = "def create_agency():\n    return 42\n"
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        with pytest.raises(SystemExit, match="create_agency\\(\\).*must return an Agency"):
            find_agency(module, f)

    def test_global_agency_name(self, tmp_path: Path) -> None:
        """A global named 'agency' is used when no factory exists."""
        f = _write(tmp_path, "agency.py", _agency_src("agency"))
        module = load_module(f)
        from agency_swarm import Agency

        result = find_agency(module, f)
        assert isinstance(result, Agency)

    def test_global_agency_wrong_type_error(self, tmp_path: Path) -> None:
        """Global 'agency' that is not an Agency raises SystemExit."""
        src = "agency = 'not an agency'\n"
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        with pytest.raises(SystemExit, match="Global 'agency'.*not an Agency"):
            find_agency(module, f)

    def test_single_anonymous_instance(self, tmp_path: Path) -> None:
        """Exactly one Agency instance with no conventional name is discovered."""
        src = _agency_src("my_special_name")
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        from agency_swarm import Agency

        result = find_agency(module, f)
        assert isinstance(result, Agency)

    def test_no_agency_found_error(self, tmp_path: Path) -> None:
        """A file with no Agency instance raises SystemExit with the file path."""
        src = "x = 1\n"
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        with pytest.raises(SystemExit, match="No Agency instance found"):
            find_agency(module, f)

    def test_multiple_agencies_error(self, tmp_path: Path) -> None:
        """Two Agency instances raises SystemExit mentioning the count."""
        src = _agency_src("a1", "Agent1") + _agency_src("a2", "Agent2")
        f = _write(tmp_path, "agency.py", src)
        module = load_module(f)
        with pytest.raises(SystemExit, match="Multiple Agency instances"):
            find_agency(module, f)


# ---------------------------------------------------------------------------
# load_module
# ---------------------------------------------------------------------------


class TestLoadModule:
    def test_sys_path_restored_after_success(self, tmp_path: Path) -> None:
        """sys.path is identical before and after a successful load."""
        _write(tmp_path, "simple.py", "x = 1\n")
        before = list(sys.path)
        load_module(tmp_path / "simple.py")
        assert sys.path == before

    def test_sys_path_restored_after_failure(self, tmp_path: Path) -> None:
        """sys.path is restored even when the module raises during import."""
        _write(tmp_path, "bad.py", "raise RuntimeError('boom')\n")
        before = list(sys.path)
        with pytest.raises(RuntimeError, match="boom"):
            load_module(tmp_path / "bad.py")
        assert sys.path == before

    def test_module_not_left_in_sys_modules(self, tmp_path: Path) -> None:
        """The temporary module name is cleaned up from sys.modules after load."""
        modules_before = set(sys.modules.keys())
        _write(tmp_path, "clean.py", "x = 1\n")
        load_module(tmp_path / "clean.py")
        new_keys = set(sys.modules.keys()) - modules_before
        assert not any("_agency_swarm_tui_entry_" in k for k in new_keys)

    def test_entrypoint_relative_imports_work_and_sys_path_restored(self, tmp_path: Path) -> None:
        """A sibling module imported from the entrypoint works and sys.path is restored.

        Structure:
            tmp_path/
                agency.py      # does `from helper import VALUE`
                helper.py      # exports VALUE = 42
        """
        _write(tmp_path, "helper.py", "VALUE = 42\n")
        _write(
            tmp_path,
            "agency.py",
            "from helper import VALUE\nassert VALUE == 42\n",
        )
        before = list(sys.path)
        module = load_module(tmp_path / "agency.py")
        assert sys.path == before
        assert module.VALUE == 42  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# run_tui (end-to-end with mocked .tui())
# ---------------------------------------------------------------------------


class TestRunTui:
    def test_tui_called_exactly_once(self, tmp_path: Path) -> None:
        """run_tui() calls .tui() exactly once on the discovered Agency."""
        f = _write(tmp_path, "agency.py", _agency_src("agency"))
        tui_mock = MagicMock()
        with patch("agency_swarm.agency.core.Agency.tui", tui_mock):
            run_tui(str(f))
        tui_mock.assert_called_once_with()

    def test_explicit_path_works(self, tmp_path: Path) -> None:
        """run_tui(explicit_path) loads that file."""
        f = _write(tmp_path, "myagency.py", _agency_src("agency"))
        tui_mock = MagicMock()
        with patch("agency_swarm.agency.core.Agency.tui", tui_mock):
            run_tui(str(f))
        tui_mock.assert_called_once()

    def test_default_agency_py_used(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_tui(None) finds ./agency.py by default."""
        _write(tmp_path, "agency.py", _agency_src("agency"))
        monkeypatch.chdir(tmp_path)
        tui_mock = MagicMock()
        with patch("agency_swarm.agency.core.Agency.tui", tui_mock):
            run_tui(None)
        tui_mock.assert_called_once()
