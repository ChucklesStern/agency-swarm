"""Launcher and template-init logic for the `agency-swarm` CLI.

Three entry points:

- :func:`run_launcher` — bare ``agency-swarm`` invocation. If no entrypoint
  exists in cwd, scaffold the one-Assistant starter and open the TUI.
- :func:`init_minimal` — explicit form of bare invocation, dispatched by
  ``agency-swarm init minimal``. Same behavior as :func:`run_launcher`.
- :func:`init_openswarm` — ``agency-swarm init openswarm``. Vendored
  scaffold + onboarding wizard + TUI. Implemented in a later phase;
  currently raises :class:`NotImplementedError`.

TUI launch is delegated to :func:`agency_swarm.cli.run_tui.run_tui` in all
cases.
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


def _ensure_minimal_agency(cwd: Path) -> None:
    """Write the one-Assistant starter ``agency.py`` to *cwd* if no entrypoint exists.

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
    """Bare-command launcher: ensure the minimal entrypoint, then run the TUI."""
    _ensure_minimal_agency(Path.cwd())
    run_tui(None)


def init_minimal() -> None:
    """Explicit form of :func:`run_launcher`, dispatched by `agency-swarm init minimal`."""
    run_launcher()


def init_openswarm() -> None:
    """Scaffold the vendored OpenSwarm agency and launch the TUI.

    Stub: implemented in the next phase. Argparse already routes here so
    the CLI surface is stable across the rest of the rollout.
    """
    raise NotImplementedError("`agency-swarm init openswarm` will be implemented in the next phase.")
