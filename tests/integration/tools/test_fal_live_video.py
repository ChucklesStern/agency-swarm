"""Opt-in live FAL.AI video-generation tests.

These tests make real HTTP calls to fal.ai and cost real money. They are skipped
by default. Two gates must BOTH be set to run them:

    export FAL_KEY=<your key>
    export RUN_FAL_LIVE_TESTS=1
    pytest tests/integration/tools/test_fal_live_video.py -v

The endpoint chosen here is the cheapest verified video model in the catalog
(`fal:hailuo-02-standard-t2v`) to keep the spend per CI run minimal. A real call
takes roughly one minute and produces a single 6-second 768p MP4.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fal_client")

# Mirror the openswarm template's top-level import contract, as the live image
# test does. The integration conftest does not inject the path itself.
_OPENSWARM_ROOT = Path(__file__).resolve().parents[3] / "src" / "agency_swarm" / "_templates" / "openswarm"
if _OPENSWARM_ROOT.is_dir():
    path_str = str(_OPENSWARM_ROOT)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

pytestmark = pytest.mark.skipif(
    not (os.getenv("FAL_KEY") and os.getenv("RUN_FAL_LIVE_TESTS") == "1"),
    reason="FAL live tests are opt-in. Set FAL_KEY and RUN_FAL_LIVE_TESTS=1 to enable.",
)


from shared_tools.fal_adapter import get_fal_video_spec, invoke_fal_video  # noqa: E402


def test_hailuo_standard_live_single_video(tmp_path):
    """One real Hailuo Standard T2V call returns a non-empty local MP4 path."""
    import asyncio

    # Use a unique product directory so we don't collide with any local state.
    product_name = f"_live_test_{tmp_path.name}"
    spec = get_fal_video_spec("fal:hailuo-02-standard-t2v")
    output_path = asyncio.run(
        invoke_fal_video(
            spec,
            prompt="A small ceramic mug on a wooden table, soft natural light, gentle camera push-in.",
            seconds=6,
            size="1280x720",
            name="live_smoke_clip",
            product_name=product_name,
        )
    )
    assert isinstance(output_path, str)
    assert output_path.endswith("live_smoke_clip.mp4")
    assert Path(output_path).exists()
    assert Path(output_path).stat().st_size > 0
