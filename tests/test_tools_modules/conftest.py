"""Test-collection scope: make the openswarm template importable.

The openswarm template at `src/agency_swarm/_templates/openswarm/` uses top-level
imports like `from shared_tools.X` and `from image_generation_agent.tools.Y` that
only resolve when the template root is on `sys.path`. The template runs that way
in production (after `agency-swarm init openswarm` copies it into a user's project,
the template root becomes the cwd). Tests in this directory need the same path
setup to exercise the template code directly.

## Why `sys.path` injection in conftest, not `monkeypatch.syspath_prepend`

The two PR 1 test files (`test_fal_adapter.py`, `test_image_generation_tools.py`)
import openswarm symbols at module top:

    from shared_tools.fal_adapter import FAL_T2I_CATALOG  # module-top import

These imports execute during pytest **collection**, before any fixture (including
`monkeypatch`) can run. By the time `monkeypatch.syspath_prepend(...)` would fire
inside a test function, the failed module-top imports have already aborted
collection. Conftest-level injection runs at collection time, which is the
correct timing.

## Why this doesn't shadow installed packages

The injected path adds template-internal names (`shared_tools`, `image_generation_agent`,
`video_generation_agent`, `slides_agent`, etc.) that are unique to the openswarm
template. None of them collide with pip-installed package names in this dev env
or in standard Python stdlib.

## Scope

The injection only affects tests collected under `tests/test_tools_modules/` and
its subdirectories. It is intentionally scoped here rather than at the repo root
to keep the rest of the test suite isolated from template imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

_OPENSWARM_ROOT = Path(__file__).resolve().parents[2] / "src" / "agency_swarm" / "_templates" / "openswarm"
if _OPENSWARM_ROOT.is_dir():
    path_str = str(_OPENSWARM_ROOT)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
