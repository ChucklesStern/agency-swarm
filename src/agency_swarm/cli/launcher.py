"""Launcher and template-init logic for the `agency-swarm` CLI.

Three entry points:

- :func:`run_launcher` — bare ``agency-swarm`` invocation. If no entrypoint
  exists in cwd, scaffold the one-Assistant starter and open the TUI.
- :func:`init_minimal` — explicit form of bare invocation, dispatched by
  ``agency-swarm init minimal``. Same behavior as :func:`run_launcher`.
- :func:`init_openswarm` — ``agency-swarm init openswarm``. Vendored
  scaffold + onboarding wizard + TUI.

TUI launch is delegated to :func:`agency_swarm.cli.run_tui.run_tui` in all
cases.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.resources as resources
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator
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

# ---------------------------------------------------------------------------
# OpenSwarm scaffold
# ---------------------------------------------------------------------------

_OPENSWARM_PACKAGE = "agency_swarm._templates.openswarm"

# Friendly-but-not-exhaustive dep gate. The full [openswarm] extra is ~40
# packages; we sample three that span distinct clusters (wizard, data agents,
# media agents) so a missing extras-install is caught before any disk write.
_OPENSWARM_DEP_CANARIES: tuple[str, ...] = ("questionary", "pandas", "fal_client")

# Top-level files inside the template that are renamed at scaffold time.
_OPENSWARM_RENAMES: dict[str, str] = {"swarm.py": "agency.py"}

# Top-level files inside the template that stay in the package and are NOT
# copied to user cwd. The developer-facing vendor manifest belongs only in
# the installed agency-swarm distribution.
_OPENSWARM_SKIP_TOP_LEVEL: frozenset[str] = frozenset({"NOTICE.md"})

_OPENSWARM_DEP_HELP = (
    "OpenSwarm dependencies appear to be missing (could not import: {name}).\n"
    "`agency-swarm init openswarm` requires the [openswarm] extras.\n"
    "Install them with:\n"
    '    pip install "agency-swarm-custom[openswarm]"\n'
    "(or, from a clone of this repo, `pip install .[openswarm]`)"
)


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


@contextlib.contextmanager
def _openswarm_template_root() -> Iterator[Path]:
    """Yield an on-disk :class:`Path` for the vendored OpenSwarm template tree.

    Uses :func:`importlib.resources.as_file` so the lookup is correct for
    editable installs, regular wheel installs, and zip-imported wheels. The
    yielded path is only guaranteed to exist for the duration of the
    ``with`` block — do not store it and reference it later.
    """
    pkg = resources.files(_OPENSWARM_PACKAGE)
    with resources.as_file(pkg) as root:
        yield Path(root)


def _iter_openswarm_manifest(root: Path) -> Iterable[tuple[Path, Path]]:
    """Yield ``(source_path, relative_dest_path)`` for every file to copy.

    Walks *root* recursively. The top-level ``swarm.py`` is renamed to
    ``agency.py`` at the destination. The top-level developer-facing
    ``NOTICE.md`` is excluded. Everything else preserves its relative path.
    """
    for source in sorted(root.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(root)
        # Skip Python bytecode caches anywhere in the tree — these are local
        # artifacts from imports of the vendored copy, not part of the scaffold.
        if "__pycache__" in rel.parts:
            continue
        if len(rel.parts) == 1 and rel.parts[0] in _OPENSWARM_SKIP_TOP_LEVEL:
            continue
        if len(rel.parts) == 1 and rel.parts[0] in _OPENSWARM_RENAMES:
            yield (source, Path(_OPENSWARM_RENAMES[rel.parts[0]]))
            continue
        yield (source, rel)


def _preflight_openswarm_destinations(cwd: Path, manifest: Iterable[tuple[Path, Path]]) -> list[Path]:
    """Return the subset of per-file destinations that already exist in *cwd*.

    ``.env`` is never in the manifest so it is never reported as a conflict.
    """
    return [cwd / rel for _, rel in manifest if (cwd / rel).exists()]


def _dep_check_openswarm() -> None:
    """Try-import each :data:`_OPENSWARM_DEP_CANARIES`.

    On the first failure, prints the install hint (including the offending
    module name) and raises :class:`SystemExit` with exit code 1.
    """
    for name in _OPENSWARM_DEP_CANARIES:
        try:
            importlib.import_module(name)
        except ImportError:
            print(_OPENSWARM_DEP_HELP.format(name=name), file=sys.stderr)
            raise SystemExit(1) from None


def _scaffold_openswarm(cwd: Path, manifest: list[tuple[Path, Path]]) -> None:
    """Copy each manifest entry into *cwd*.

    Preconditions: dep check has passed and the preflight returned no
    conflicts. Each individual write still re-checks ``Path.exists`` as a
    belt-and-suspenders guard against a race between preflight and copy —
    on conflict, we abort mid-walk without overwriting.

    Emits one stdout line per top-level destination entry as it is first
    written, so the user sees what was created.
    """
    announced: set[str] = set()
    for source, rel in manifest:
        dest = cwd / rel
        if dest.exists():
            print(
                f"Refusing to overwrite ./{rel} — it appeared between preflight and copy.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        top = rel.parts[0]
        if top not in announced:
            announced.add(top)
            suffix = "/" if len(rel.parts) > 1 else ""
            print(f"  created {top}{suffix}")


def _run_onboarding_wizard(cwd: Path) -> bool:
    """Run the OpenSwarm onboarding wizard as a subprocess.

    Invokes ``python onboard.py`` in *cwd*. The wizard owns its own UX
    (questionary prompts for provider, key, and add-ons) and writes a
    ``.env`` file directly. Returns ``True`` iff that file is present
    after the subprocess completes.

    Catches :class:`KeyboardInterrupt` so a user Ctrl-C during the wizard
    returns ``False`` cleanly instead of unwinding through the launcher.
    The caller is responsible for the post-condition (no TUI launch on
    ``False``).
    """
    try:
        subprocess.run([sys.executable, "onboard.py"], cwd=cwd, check=False)
    except KeyboardInterrupt:
        return False
    return (cwd / ".env").exists()


def run_launcher() -> None:
    """Bare-command launcher: ensure the minimal entrypoint, then run the TUI."""
    _ensure_minimal_agency(Path.cwd())
    run_tui(None)


def init_minimal() -> None:
    """Explicit form of :func:`run_launcher`, dispatched by `agency-swarm init minimal`."""
    run_launcher()


def init_openswarm() -> None:
    """Scaffold the vendored OpenSwarm agency, run the wizard, then launch the TUI.

    Flow:

    1. Dep gate (canary imports). Exits early with install hint if missing.
    2. Open the template-root context. Build the manifest.
    3. Preflight: abort if any destination file already exists in cwd.
    4. Copy the manifest into cwd (``swarm.py`` → ``agency.py``).
    5. If no ``.env`` exists in cwd, run the onboarding wizard. Abort if the
       wizard fails to leave a ``.env`` behind.
    6. Hand off to :func:`run_tui`.
    """
    cwd = Path.cwd()
    _dep_check_openswarm()

    with _openswarm_template_root() as root:
        manifest = list(_iter_openswarm_manifest(root))
        conflicts = _preflight_openswarm_destinations(cwd, manifest)
        if conflicts:
            print(
                "Refusing to scaffold OpenSwarm — these paths already exist in this directory:",
                file=sys.stderr,
            )
            for path in conflicts:
                print(f"    ./{path.relative_to(cwd)}", file=sys.stderr)
            print(
                "Move them out of the way or pick a fresh directory and try again.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        print("Scaffolding OpenSwarm agency into the current directory...")
        _scaffold_openswarm(cwd, manifest)

    if not (cwd / ".env").exists():
        if not _run_onboarding_wizard(cwd):
            print(
                "Wizard did not complete. No `.env` was written, so the TUI is "
                "not launching. Re-run `agency-swarm init openswarm` after "
                "you've resolved the issue.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    run_tui(None)
