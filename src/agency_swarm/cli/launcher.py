"""First-boot launcher for `agency-swarm` invoked without a subcommand.

If neither ``agency.py`` nor ``run.py`` exists in the current directory, a
quick-start ``agency.py`` is written so the TUI has something to load. The
side effect is announced on stdout. Discovery and TUI launch are then
delegated to :func:`agency_swarm.cli.run_tui.run_tui`, which is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from .run_tui import DEFAULT_ENTRYPOINT_FILES, run_tui

_DEFAULT_AGENCY_TEMPLATE = """\
from agency_swarm import Agency, Agent

assistant = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
)

agency = Agency(assistant)
"""


def _ensure_agency_file(cwd: Path) -> None:
    """Write a starter ``agency.py`` to *cwd* if no conventional entrypoint exists.

    Searches for any name in :data:`DEFAULT_ENTRYPOINT_FILES`. If at least one
    exists, returns silently. Otherwise prints two stdout lines and writes
    ``agency.py`` with :data:`_DEFAULT_AGENCY_TEMPLATE`.
    """
    for name in DEFAULT_ENTRYPOINT_FILES:
        if (cwd / name).exists():
            return

    target = cwd / "agency.py"
    print(f"No {' or '.join(DEFAULT_ENTRYPOINT_FILES)} found. Creating ./agency.py quick-start template...")
    target.write_text(_DEFAULT_AGENCY_TEMPLATE, encoding="utf-8")
    print("Created agency.py — edit it any time to customize your agency.")


def run_launcher() -> None:
    """First-boot launcher: ensure an entrypoint file exists, then run the TUI."""
    _ensure_agency_file(Path.cwd())
    run_tui(None)
