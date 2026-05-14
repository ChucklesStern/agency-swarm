"""Tests for Agency.project_folder and Agency.enable_project_shell."""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.tools.built_in import PersistentShellTool
from tests.deterministic_model import DeterministicModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETUP_MODULE = "agency_swarm.agency.setup"


def _make_agent(name: str = "TestAgent") -> Agent:
    return Agent(
        name=name,
        instructions="You are a test agent.",
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )


def _make_agency(tmp_path: Path, **kwargs) -> Agency:
    """Create an Agency with project_folder pointing at tmp_path.

    _apply_files_folder is patched to avoid OpenAI calls.
    """
    return Agency(_make_agent(), **kwargs)


def _agency_tool_types(agency: Agency) -> set[type]:
    """Collect all tool types across every agent in the agency."""
    types: set[type] = set()
    for agent in agency.agents.values():
        for tool in agent.tools:
            types.add(type(tool))
    return types


def _has_shell_tool(agency: Agency) -> bool:
    return any(
        (inspect.isclass(t) and issubclass(t, PersistentShellTool))
        or isinstance(t, PersistentShellTool)
        or getattr(t, "name", None) == "PersistentShellTool"
        for agent in agency.agents.values()
        for t in agent.tools
    )


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    def test_directory_created(self, tmp_path: Path) -> None:
        """project_folder directory is created on Agency init."""
        target = tmp_path / "workspace"
        assert not target.exists()
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            _make_agency(tmp_path, project_folder=target)
        assert target.is_dir()

    def test_existing_directory_not_cleared(self, tmp_path: Path) -> None:
        """Pre-existing files inside project_folder are not deleted."""
        (tmp_path / "keep.txt").write_text("important")
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            _make_agency(tmp_path, project_folder=tmp_path)
        assert (tmp_path / "keep.txt").read_text() == "important"

    def test_no_project_folder_no_directory_created(self, tmp_path: Path) -> None:
        """Without project_folder, no unexpected directory is created."""
        before = set(tmp_path.iterdir())
        _make_agency(tmp_path)
        assert set(tmp_path.iterdir()) == before

    def test_accepts_absolute_path(self, tmp_path: Path) -> None:
        """Absolute project_folder path is stored as-is (resolved)."""
        target = tmp_path / "abs_workspace"
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = _make_agency(tmp_path, project_folder=target)
        assert agency.project_folder == target
        assert agency.project_folder.is_absolute()


# ---------------------------------------------------------------------------
# Vector store ingestion
# ---------------------------------------------------------------------------


class TestVectorStoreIngestion:
    def test_ingestion_called_with_resolved_path(self, tmp_path: Path) -> None:
        """_apply_files_folder is called with the resolved absolute path."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder") as mock_ingest:
            agency = _make_agency(tmp_path, project_folder=tmp_path)
        mock_ingest.assert_called_once()
        call_path = mock_ingest.call_args[0][1]  # second positional arg
        assert call_path == tmp_path
        assert call_path.is_absolute()

    def test_ingestion_not_called_without_project_folder(self, tmp_path: Path) -> None:
        """_apply_files_folder is NOT called when project_folder is omitted."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder") as mock_ingest:
            _make_agency(tmp_path)
        # May be called for shared_files_folder, but project_folder path should not appear
        for call in mock_ingest.call_args_list:
            assert call[0][1] != tmp_path

    def test_both_project_and_shared_files_ingest_independently(self, tmp_path: Path) -> None:
        """Both project_folder and shared_files_folder trigger separate ingestion calls."""
        shared = tmp_path / "shared"
        shared.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        with patch(f"{_SETUP_MODULE}._apply_files_folder") as mock_ingest:
            Agency(
                _make_agent(),
                project_folder=project,
                shared_files_folder=str(shared),
            )
        paths_ingested = {call[0][1] for call in mock_ingest.call_args_list}
        assert project in paths_ingested
        assert shared in paths_ingested

    def test_dry_run_skips_ingestion_but_creates_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With DRY_RUN enabled, ingestion is skipped but the directory is still created."""
        monkeypatch.setenv("DRY_RUN", "1")
        target = tmp_path / "dry_workspace"
        with patch(f"{_SETUP_MODULE}._apply_files_folder") as mock_ingest:
            _make_agency(tmp_path, project_folder=target)
        assert target.is_dir()
        # _apply_files_folder should not have been called for the project folder
        # (dry_run guard is inside apply_project_folder, before calling _apply_files_folder)
        for call in mock_ingest.call_args_list:
            assert call[0][1] != target


# ---------------------------------------------------------------------------
# Shell access (opt-in)
# ---------------------------------------------------------------------------


class TestShellAccess:
    def test_shell_not_added_by_default(self, tmp_path: Path) -> None:
        """PersistentShellTool is NOT added without enable_project_shell=True."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = _make_agency(tmp_path, project_folder=tmp_path)
        assert not _has_shell_tool(agency)

    def test_shell_added_when_opted_in(self, tmp_path: Path) -> None:
        """PersistentShellTool appears in all agents' tools when enable_project_shell=True."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = _make_agency(tmp_path, project_folder=tmp_path, enable_project_shell=True)
        assert _has_shell_tool(agency)

    def test_shell_without_project_folder_raises(self) -> None:
        """enable_project_shell=True without project_folder raises ValueError."""
        with pytest.raises(ValueError, match="project_folder"):
            Agency(_make_agent(), enable_project_shell=True)

    def test_shell_tool_not_duplicated(self, tmp_path: Path) -> None:
        """If PersistentShellTool is already in shared_tools, it is not added twice."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = Agency(
                _make_agent(),
                project_folder=tmp_path,
                enable_project_shell=True,
                shared_tools=[PersistentShellTool],
            )
        shell_count = sum(
            1
            for agent in agency.agents.values()
            for t in agent.tools
            if isinstance(t, PersistentShellTool) or getattr(t, "name", None) == "PersistentShellTool"
        )
        assert shell_count == len(agency.agents), "exactly one shell tool per agent"


# ---------------------------------------------------------------------------
# Shell CWD seeding
# ---------------------------------------------------------------------------


class TestShellCwdSeeding:
    def test_shell_cwds_seeded_for_all_agents(self, tmp_path: Path) -> None:
        """user_context['shell_cwds'] contains project_folder for every agent."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = Agency(
                _make_agent("Alpha"),
                project_folder=tmp_path,
                enable_project_shell=True,
            )
        cwds = agency.user_context.get("shell_cwds", {})
        for name in agency.agents:
            assert cwds[name] == str(tmp_path)

    def test_user_supplied_cwd_wins_for_specific_agent(self, tmp_path: Path) -> None:
        """Explicit user_context shell_cwds entry wins; other agents get project default."""
        override = "/custom/path"
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = Agency(
                _make_agent("Alpha"),
                project_folder=tmp_path,
                enable_project_shell=True,
                user_context={"shell_cwds": {"Alpha": override}},
            )
        cwds = agency.user_context["shell_cwds"]
        assert cwds["Alpha"] == override  # user-supplied wins

    def test_non_dict_cwds_logged_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-dict shell_cwds in user_context logs a warning and does not raise."""
        import logging

        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            with caplog.at_level(logging.WARNING, logger="agency_swarm.agency.setup"):
                agency = Agency(
                    _make_agent(),
                    project_folder=tmp_path,
                    enable_project_shell=True,
                    user_context={"shell_cwds": "not-a-dict"},
                )
        assert any("shell_cwds" in msg for msg in caplog.messages)
        # shell_cwds left unchanged (not overwritten)
        assert agency.user_context["shell_cwds"] == "not-a-dict"

    def test_cwds_seeded_before_tool_wired(self, tmp_path: Path) -> None:
        """user_context['shell_cwds'] is populated before _apply_shared_tools is called.

        This verifies ordering: the shell CWD is available at the point the tool
        is wired to agents, so PersistentShellTool sees the project folder as its
        initial working directory from its very first invocation.
        """
        call_order: list[str] = []

        original_apply_shared_tools = __import__(
            "agency_swarm.agency.setup", fromlist=["_apply_shared_tools"]
        )._apply_shared_tools

        def recording_apply_shared_tools(agency: Agency) -> None:
            cwds = agency.user_context.get("shell_cwds", {})
            seeded = all(v == str(tmp_path) for v in cwds.values()) if cwds else False
            call_order.append(f"_apply_shared_tools:cwds_seeded={seeded}")
            original_apply_shared_tools(agency)

        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            with patch(f"{_SETUP_MODULE}._apply_shared_tools", side_effect=recording_apply_shared_tools):
                Agency(
                    _make_agent("Alpha"),
                    project_folder=tmp_path,
                    enable_project_shell=True,
                )

        # The call from apply_project_folder (the second call, after shared_resources)
        # must see cwds already seeded.
        project_folder_calls = [c for c in call_order if "cwds_seeded=True" in c]
        assert project_folder_calls, (
            "shell_cwds must be seeded before _apply_shared_tools is called "
            f"from apply_project_folder; call_order={call_order}"
        )

    def test_no_shell_no_cwds_seeded(self, tmp_path: Path) -> None:
        """Without enable_project_shell, shell_cwds is not seeded."""
        with patch(f"{_SETUP_MODULE}._apply_files_folder"):
            agency = _make_agency(tmp_path, project_folder=tmp_path)
        assert "shell_cwds" not in agency.user_context
