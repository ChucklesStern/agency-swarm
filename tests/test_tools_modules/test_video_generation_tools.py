"""Tests for the FAL.AI integration inside GenerateVideo.

Adapter-level coverage lives in `test_fal_adapter_video.py`. These tests focus on
the tool-side wiring: Pydantic validators (legacy normalization, FAL duration
guard, asset_image_ref rejection), dispatch through `_run_fal`, and the
end-to-end tool output shape (including the cost-tier hint).
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fal_client")
pytest.importorskip("PIL")

from pydantic import ValidationError  # noqa: E402
from shared_tools.fal_adapter import FAL_VIDEO_CATALOG  # noqa: E402
from video_generation_agent.tools.GenerateVideo import GenerateVideo  # noqa: E402

from agency_swarm import ToolOutputText  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_video_utils(monkeypatch):
    """Replace the leaf video_utils module so unit tests don't need ffmpeg/moviepy."""
    real_path = "video_generation_agent.tools.utils.video_utils"
    fake = types.ModuleType(real_path)
    fake.extract_last_frame = MagicMock(return_value=None)
    fake.generate_spritesheet = MagicMock(return_value=None)
    fake.get_videos_dir = MagicMock(return_value="/tmp/test-videos")
    # Preserve the real symbols that GenerateVideo imports at module top —
    # the stub only needs to cover the leaf functions the adapter calls
    # function-locally.
    from video_generation_agent.tools.utils import video_utils as real

    for name in (
        "ensure_not_blank",
        "get_gemini_client",
        "is_veo_model",
        "is_sora_model",
        "resolve_input_reference",
        "validate_resolution",
        "save_video_with_metadata",
        "save_veo_video_with_metadata",
    ):
        setattr(fake, name, getattr(real, name))
    monkeypatch.setitem(sys.modules, real_path, fake)
    return fake


# ---------------------------------------------------------------------------
# Field Literal and drift
# ---------------------------------------------------------------------------


def test_generate_video_model_literal_includes_legacy_seedance_alias():
    """Backward compat: the legacy literal stays accepted for one release."""
    from typing import get_args

    values = set(get_args(GenerateVideo.model_fields["model"].annotation))
    assert "seedance-1.5-pro" in values


def test_generate_video_model_literal_includes_all_fal_catalog_keys():
    """Drift guard: every catalog key must be an accepted Literal value."""
    from typing import get_args

    values = set(get_args(GenerateVideo.model_fields["model"].annotation))
    for key in FAL_VIDEO_CATALOG:
        assert key in values, f"Catalog key {key!r} missing from GenerateVideo.model Literal"


# ---------------------------------------------------------------------------
# Legacy alias normalization
# ---------------------------------------------------------------------------


def test_legacy_seedance_literal_is_normalized_to_canonical(stub_video_utils):
    """`seedance-1.5-pro` becomes `fal:seedance-1.5-pro` after instantiation."""
    tool = GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="x",
        model="seedance-1.5-pro",
        seconds=5,
        size="1280x720",
    )
    assert tool.model == "fal:seedance-1.5-pro"


def test_canonical_seedance_literal_passes_through_unchanged(stub_video_utils):
    tool = GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="x",
        model="fal:seedance-1.5-pro",
        seconds=5,
        size="1280x720",
    )
    assert tool.model == "fal:seedance-1.5-pro"


# ---------------------------------------------------------------------------
# Validators: FAL duration guard
# ---------------------------------------------------------------------------


def test_kling_pro_rejects_unsupported_duration(stub_video_utils):
    """Kling Pro T2V duration set is {3..15}; 2 is outside."""
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="fal:kling-v3-pro-t2v",
            seconds=2,  # field min is 4, so this fails at the ge=4 constraint
            size="1280x720",
        )
    assert "seconds" in str(exc.value).lower() or "Duration" in str(exc.value)


def test_hailuo_standard_rejects_seconds_outside_supported_set(stub_video_utils):
    """Hailuo Standard accepts only 6s or 10s; 8 is rejected."""
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="fal:hailuo-02-standard-t2v",
            seconds=8,
            size="1280x720",
        )
    assert "Duration 8s" in str(exc.value)
    assert "fal:hailuo-02-standard-t2v" in str(exc.value)


def test_hailuo_pro_accepts_any_seconds_because_no_duration_field(stub_video_utils):
    """Hailuo Pro I2V has no duration field; tool-side validator is a no-op."""
    tool = GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="x",
        model="fal:hailuo-02-pro-i2v",
        seconds=12,
        size="1280x720",
        first_frame_ref="hero_image",
    )
    assert tool.seconds == 12


def test_luma_ray2_accepts_only_5_or_9_seconds(stub_video_utils):
    with pytest.raises(ValidationError):
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="fal:luma-ray-2-t2v",
            seconds=6,
            size="1280x720",
        )
    # 5 is fine
    GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="x",
        model="fal:luma-ray-2-t2v",
        seconds=5,
        size="1280x720",
    )


# ---------------------------------------------------------------------------
# Validators: asset_image_ref rejection
# ---------------------------------------------------------------------------


def test_fal_model_rejects_asset_image_ref(stub_video_utils):
    """All FAL models route image inputs through `first_frame_ref` only."""
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="fal:kling-v3-pro-t2v",
            seconds=5,
            size="1280x720",
            asset_image_ref="some_image",
        )
    assert "asset_image_ref" in str(exc.value)


def test_sora_still_rejects_asset_image_ref(stub_video_utils):
    """Existing Sora rejection rule preserved post-refactor."""
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="sora-2",
            seconds=4,
            size="1280x720",
            asset_image_ref="some_image",
        )
    assert "asset_image_ref" in str(exc.value)


# ---------------------------------------------------------------------------
# Direct-provider validators stay intact
# ---------------------------------------------------------------------------


def test_sora_still_enforces_4_8_12_seconds(stub_video_utils):
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="sora-2",
            seconds=5,
            size="1280x720",
        )
    assert "Sora" in str(exc.value)


def test_veo_still_enforces_4_6_8_seconds(stub_video_utils):
    with pytest.raises(ValidationError) as exc:
        GenerateVideo(
            product_name="p",
            prompt="a sunset",
            name="x",
            model="veo-3.1-generate-preview",
            seconds=12,
            size="1280x720",
        )
    assert "Veo" in str(exc.value)


# ---------------------------------------------------------------------------
# Dispatch to _run_fal
# ---------------------------------------------------------------------------


def test_run_dispatches_to_fal_and_includes_cost_tier_hint(monkeypatch, stub_video_utils):
    """When the model is a FAL video id, run() calls invoke_fal_video and adds the cost-tier hint."""
    mock_invoke = AsyncMock(return_value="/tmp/test-videos/x.mp4")
    monkeypatch.setattr(
        "video_generation_agent.tools.GenerateVideo.invoke_fal_video", mock_invoke
    )
    tool = GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="x",
        model="fal:kling-v3-pro-t2v",
        seconds=5,
        size="1280x720",
    )
    outputs = asyncio.run(tool.run())
    assert mock_invoke.called
    assert all(isinstance(o, ToolOutputText) for o in outputs)
    joined = "\n".join(o.text for o in outputs)
    assert "/tmp/test-videos/x.mp4" in joined
    assert "Estimated cost tier: premium" in joined  # Kling Pro is premium


def test_legacy_seedance_dispatch_calls_fal_with_canonical_id(monkeypatch, stub_video_utils):
    """`seedance-1.5-pro` literal must route to the FAL adapter with the canonical id."""
    captured_spec = []

    async def fake_invoke(spec, **kwargs):
        captured_spec.append(spec)
        return "/tmp/test-videos/clip.mp4"

    monkeypatch.setattr(
        "video_generation_agent.tools.GenerateVideo.invoke_fal_video", fake_invoke
    )
    tool = GenerateVideo(
        product_name="p",
        prompt="a sunset",
        name="clip",
        model="seedance-1.5-pro",  # legacy alias
        seconds=5,
        size="1280x720",
    )
    asyncio.run(tool.run())
    assert len(captured_spec) == 1
    assert captured_spec[0].user_id == "fal:seedance-1.5-pro"
