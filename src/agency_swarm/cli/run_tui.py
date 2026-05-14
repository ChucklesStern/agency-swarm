"""Discovery and launch logic for `agency-swarm tui`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agency_swarm import Agency

# Conventional entry-point filenames searched in order when no FILE is given.
_DEFAULT_FILES = ("agency.py", "run.py")


def load_module(file_path: Path) -> ModuleType:
    """Import *file_path* as a fresh module without permanently mutating sys.path or sys.modules.

    The file's parent directory is prepended to sys.path for the duration of
    the import so that relative sibling imports inside the user's file work.
    It is removed again in a finally block whether the import succeeds or not.

    A unique module name is derived from the path so that repeated calls with
    different files never collide in sys.modules. The temporary entry is
    removed from sys.modules after execution.
    """
    parent = str(file_path.parent.resolve())
    # Unique name avoids stale-module collisions across multiple calls.
    module_name = f"_agency_swarm_tui_entry_{file_path.stem}_{id(file_path)}"

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {file_path}: importlib could not build a module spec.")

    module = importlib.util.module_from_spec(spec)

    sys.path.insert(0, parent)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        sys.path[:] = [p for p in sys.path if p != parent]
        sys.modules.pop(module_name, None)

    return module


def find_agency(module: ModuleType, source_path: Path) -> "Agency":
    """Discover an Agency instance inside *module* using a deterministic priority order.

    Discovery order:
      1. ``create_agency()`` — if defined and callable, call it; must return an Agency.
      2. ``agency`` — if a global with that name exists, it must be an Agency.
      3. Scan all globals for exactly one Agency instance.

    Raises SystemExit with a descriptive message if no single Agency is found.
    """
    from agency_swarm import Agency  # local import; avoids circular at module level

    label = str(source_path)

    # 1. Factory function
    factory = getattr(module, "create_agency", None)
    if callable(factory):
        result = factory()
        if not isinstance(result, Agency):
            raise SystemExit(
                f"create_agency() in {label} must return an Agency instance, "
                f"got {type(result).__name__}."
            )
        return result

    # 2. Conventional global name
    named = getattr(module, "agency", None)
    if named is not None:
        if not isinstance(named, Agency):
            raise SystemExit(
                f"Global 'agency' in {label} is not an Agency instance "
                f"(got {type(named).__name__})."
            )
        return named

    # 3. Scan for exactly one instance
    instances = [v for v in vars(module).values() if isinstance(v, Agency)]
    if len(instances) == 1:
        return instances[0]
    if not instances:
        raise SystemExit(
            f"No Agency instance found in {label}. "
            "Define `agency = Agency(...)` or `def create_agency() -> Agency: ...`."
        )
    raise SystemExit(
        f"Multiple Agency instances found in {label} ({len(instances)}). "
        "Define `def create_agency() -> Agency: ...` or name exactly one instance 'agency'."
    )


def resolve_entrypoint(file_arg: str | None) -> Path:
    """Return the resolved Path to the entrypoint file.

    If *file_arg* is given, that path must exist.
    Otherwise, search for the first matching name in _DEFAULT_FILES under cwd.
    Raises SystemExit with a clear message if nothing is found.
    """
    if file_arg is not None:
        path = Path(file_arg).resolve()
        if not path.exists():
            raise SystemExit(f"File not found: {file_arg}")
        return path

    cwd = Path.cwd()
    for name in _DEFAULT_FILES:
        candidate = cwd / name
        if candidate.exists():
            return candidate

    searched = ", ".join(_DEFAULT_FILES)
    raise SystemExit(
        f"No entrypoint file found in {cwd}. "
        f"Searched: {searched}. "
        "Pass an explicit path: agency-swarm tui path/to/file.py"
    )


def run_tui(file_arg: str | None) -> None:
    """Discover an Agency from *file_arg* (or cwd defaults) and call .tui()."""
    path = resolve_entrypoint(file_arg)
    module = load_module(path)
    agency = find_agency(module, path)
    agency.tui()
