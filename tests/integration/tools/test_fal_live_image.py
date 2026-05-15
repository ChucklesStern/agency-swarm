"""Opt-in live FAL.AI image-generation tests.

These tests make real HTTP calls to fal.ai and cost real money. They are skipped
by default. Two gates must BOTH be set to run them:

    export FAL_KEY=<your key>
    export RUN_FAL_LIVE_TESTS=1
    pytest tests/integration/tools/test_fal_live_image.py -v

The endpoints chosen here are the cheapest in each capability bucket
(`fal:flux-schnell` for general T2I) to keep the spend per CI run minimal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fal_client")

# The openswarm template uses top-level imports like `from shared_tools.X`. Make
# its package roots importable for this test file. Mirrors the conftest setup in
# tests/test_tools_modules/.
_OPENSWARM_ROOT = Path(__file__).resolve().parents[3] / "src" / "agency_swarm" / "_templates" / "openswarm"
if _OPENSWARM_ROOT.is_dir():
    path_str = str(_OPENSWARM_ROOT)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

pytestmark = pytest.mark.skipif(
    not (os.getenv("FAL_KEY") and os.getenv("RUN_FAL_LIVE_TESTS") == "1"),
    reason=("FAL live tests are opt-in. Set FAL_KEY and RUN_FAL_LIVE_TESTS=1 to enable."),
)


from PIL import Image  # noqa: E402
from shared_tools.fal_adapter import (  # noqa: E402
    get_fal_t2i_spec,
    invoke_fal_image_sync,
)


def test_flux_schnell_live_single_variant():
    """One real Flux Schnell call must return a PIL Image with non-zero size."""
    spec = get_fal_t2i_spec("fal:flux-schnell")
    images = invoke_fal_image_sync(
        spec,
        prompt="A small ceramic mug on a wooden table, soft natural light.",
        aspect_ratio="1:1",
        num_variants=1,
    )
    assert len(images) == 1
    assert isinstance(images[0], Image.Image)
    assert images[0].width > 0 and images[0].height > 0
