"""Invocation-side unit tests for the FAL.AI video adapter (Tier B).

Companion to `test_fal_adapter_video.py` (Tier A catalog tests). Covers
endpoint selection, per-family request builders, response parsing, the
mocked-end-to-end `invoke_fal_video` flow, the GenerateVideo Literal drift
test, and `cost_tier_hint` umbrella coverage.

Mirrors the same offline, mocked-at-the-boundary discipline as the image-side
tests: `fal_client.SyncClient` and `httpx.AsyncClient` are patched, no real
HTTP calls happen. Live calls are exercised opt-in via
`tests/integration/tools/test_fal_live_video.py`.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import get_args
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fal_client")
pytest.importorskip("httpx")

from shared_tools.fal_adapter import (  # noqa: E402
    FAL_VIDEO_CATALOG,
    SEEDANCE_LEGACY_ALIAS,
    cost_tier_hint,
    get_fal_video_spec,
    invoke_fal_video,
)
from shared_tools.fal_adapter._video_invoke import (  # noqa: E402
    _build_hailuo_request,
    _build_kling_request,
    _build_luma_ray2_request,
    _build_seedance_request,
    _build_wan_request,
    _parse_video_response,
    _select_endpoint,
)

# ---------------------------------------------------------------------------
# Endpoint selection (modality routing)
# ---------------------------------------------------------------------------


def test_select_endpoint_uses_t2v_when_no_first_frame_for_t2v_only_id():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    assert _select_endpoint(spec, has_first_frame=False) == spec.endpoint_t2v


def test_select_endpoint_rejects_first_frame_on_t2v_only_id():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    with pytest.raises(ValueError) as exc:
        _select_endpoint(spec, has_first_frame=True)
    assert "T2V-only" in str(exc.value)


def test_select_endpoint_uses_i2v_when_first_frame_for_i2v_only_id():
    spec = get_fal_video_spec("fal:hailuo-02-pro-i2v")
    assert _select_endpoint(spec, has_first_frame=True) == spec.endpoint_i2v


def test_select_endpoint_rejects_missing_first_frame_on_i2v_only_id():
    spec = get_fal_video_spec("fal:hailuo-02-pro-i2v")
    with pytest.raises(ValueError) as exc:
        _select_endpoint(spec, has_first_frame=False)
    assert "I2V-only" in str(exc.value)


def test_select_endpoint_auto_routes_seedance():
    """Seedance is the dual-endpoint model: routes based on first_frame presence."""
    spec = get_fal_video_spec("fal:seedance-1.5-pro")
    assert _select_endpoint(spec, has_first_frame=False) == spec.endpoint_t2v
    assert _select_endpoint(spec, has_first_frame=True) == spec.endpoint_i2v


# ---------------------------------------------------------------------------
# Per-family request builders
# ---------------------------------------------------------------------------


def test_build_kling_request_t2v_includes_aspect_ratio():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    args = _build_kling_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        first_frame_url=None, end_frame_url=None,
    )
    assert args == {"prompt": "p", "duration": "5", "aspect_ratio": "16:9"}


def test_build_kling_request_i2v_uses_start_image_url_and_omits_aspect_ratio():
    """Kling I2V uses `start_image_url` (not `image_url`) and rejects aspect_ratio."""
    spec = get_fal_video_spec("fal:kling-v3-pro-i2v")
    args = _build_kling_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        first_frame_url="https://fal/storage/first.png", end_frame_url=None,
    )
    assert "aspect_ratio" not in args
    assert args["start_image_url"] == "https://fal/storage/first.png"
    assert "image_url" not in args


def test_build_kling_request_i2v_supports_end_image_url():
    spec = get_fal_video_spec("fal:kling-v3-pro-i2v")
    args = _build_kling_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        first_frame_url="https://fal/storage/a.png",
        end_frame_url="https://fal/storage/b.png",
    )
    assert args["end_image_url"] == "https://fal/storage/b.png"


def test_build_hailuo_standard_request_includes_duration():
    spec = get_fal_video_spec("fal:hailuo-02-standard-t2v")
    args = _build_hailuo_request(
        spec, prompt="p", duration="6", first_frame_url=None, end_frame_url=None,
    )
    assert args == {"prompt": "p", "duration": "6"}


def test_build_hailuo_pro_i2v_request_omits_duration_and_uses_image_url():
    """Hailuo Pro I2V has no duration field; uses standard `image_url`."""
    spec = get_fal_video_spec("fal:hailuo-02-pro-i2v")
    args = _build_hailuo_request(
        spec, prompt="p", duration=None,
        first_frame_url="https://fal/storage/x.png", end_frame_url=None,
    )
    assert "duration" not in args
    assert args["image_url"] == "https://fal/storage/x.png"


def test_build_luma_ray2_request_uses_duration_with_s_suffix_already_serialized():
    """Caller already serialized `5` → `"5s"`; builder passes it through."""
    spec = get_fal_video_spec("fal:luma-ray-2-t2v")
    args = _build_luma_ray2_request(
        spec, prompt="p", duration="5s", aspect_ratio="16:9", resolution="720p",
    )
    assert args == {
        "prompt": "p", "aspect_ratio": "16:9", "resolution": "720p", "duration": "5s",
    }


def test_build_wan_request_omits_audio_url_when_none():
    spec = get_fal_video_spec("fal:wan-2.5-t2v")
    args = _build_wan_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        resolution="720p", audio_url=None,
    )
    assert "audio_url" not in args


def test_build_wan_request_includes_audio_url_when_provided():
    spec = get_fal_video_spec("fal:wan-2.5-t2v")
    args = _build_wan_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        resolution="720p", audio_url="https://example.com/audio.mp3",
    )
    assert args["audio_url"] == "https://example.com/audio.mp3"


def test_build_seedance_t2v_request_omits_image_url():
    spec = get_fal_video_spec("fal:seedance-1.5-pro")
    args = _build_seedance_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9",
        resolution="720p", first_frame_url=None, end_frame_url=None,
    )
    assert "image_url" not in args
    assert args == {
        "prompt": "p", "aspect_ratio": "16:9", "resolution": "720p", "duration": "5",
    }


def test_build_seedance_i2v_request_includes_image_url_and_optional_end():
    spec = get_fal_video_spec("fal:seedance-1.5-pro")
    args = _build_seedance_request(
        spec, prompt="p", duration="5", aspect_ratio="16:9", resolution="720p",
        first_frame_url="https://fal/a.png", end_frame_url="https://fal/b.png",
    )
    assert args["image_url"] == "https://fal/a.png"
    assert args["end_image_url"] == "https://fal/b.png"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def test_parse_video_response_extracts_url():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    result = {"video": {"url": "https://fal.media/output/clip.mp4"}}
    assert _parse_video_response(spec, result) == "https://fal.media/output/clip.mp4"


def test_parse_video_response_raises_when_no_video_field():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    with pytest.raises(RuntimeError) as exc:
        _parse_video_response(spec, {"foo": "bar"})
    assert "no video object" in str(exc.value)


def test_parse_video_response_raises_when_url_missing():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    with pytest.raises(RuntimeError) as exc:
        _parse_video_response(spec, {"video": {}})
    assert "without a URL" in str(exc.value)


# ---------------------------------------------------------------------------
# invoke_fal_video (mocked end-to-end)
# ---------------------------------------------------------------------------


def _patch_fal_video_env(monkeypatch, *, value: str | None = "test-key"):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    if value is None:
        monkeypatch.delenv("FAL_KEY", raising=False)
    else:
        monkeypatch.setenv("FAL_KEY", value)


def _patch_video_deps(monkeypatch, *, subscribe_result: dict, tmp_dir: str):
    """Patch fal_client.SyncClient, httpx.AsyncClient, and the video_utils helpers.

    `invoke_fal_video` does function-local imports of `fal_client`, `httpx`, and
    `video_generation_agent.tools.utils.video_utils`. Patching the canonical
    module surface is the only reliable interception point — patching the
    consumer module's attribute would miss the lazy import.
    """
    # fal_client.SyncClient
    client = MagicMock()
    client.subscribe = MagicMock(return_value=subscribe_result)
    monkeypatch.setattr("fal_client.SyncClient", MagicMock(return_value=client))

    # httpx.AsyncClient — async context-manager that yields a mock with .get()
    response_mock = MagicMock()
    response_mock.content = b"\x00\x00\x00\x18ftypmp42"  # tiny MP4-ish bytes
    response_mock.raise_for_status = MagicMock()
    async_client_instance = MagicMock()
    async_client_instance.__aenter__ = AsyncMock(return_value=async_client_instance)
    async_client_instance.__aexit__ = AsyncMock(return_value=None)
    async_client_instance.get = AsyncMock(return_value=response_mock)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=async_client_instance))

    # video_generation_agent.tools.utils.video_utils — the openswarm template
    # exposes these symbols at the real module path. Stub the leaf module
    # (only) so unit tests don't depend on ffmpeg or moviepy. Parent packages
    # resolve via the conftest's sys.path injection.
    real_path = "video_generation_agent.tools.utils.video_utils"
    fake_video_utils = types.ModuleType(real_path)
    fake_video_utils.extract_last_frame = MagicMock(return_value=None)
    fake_video_utils.generate_spritesheet = MagicMock(return_value=None)
    fake_video_utils.get_videos_dir = MagicMock(return_value=tmp_dir)
    monkeypatch.setitem(sys.modules, real_path, fake_video_utils)

    return client, fake_video_utils


def test_invoke_fal_video_seedance_t2v_returns_local_path(monkeypatch, tmp_path):
    """Mocked Seedance T2V call writes to mnt path and returns the local string."""
    _patch_fal_video_env(monkeypatch)
    client, _ = _patch_video_deps(
        monkeypatch,
        subscribe_result={"video": {"url": "https://fal.media/out/clip.mp4"}},
        tmp_dir=str(tmp_path),
    )
    spec = get_fal_video_spec("fal:seedance-1.5-pro")
    output = asyncio.run(invoke_fal_video(
        spec, prompt="a sunset", seconds=5, size="1280x720",
        name="sunset_clip", product_name="test_product",
    ))
    assert str(tmp_path) in output
    assert output.endswith("sunset_clip.mp4")
    # Confirm we called the T2V endpoint, not I2V
    endpoint = client.subscribe.call_args.args[0]
    assert endpoint == spec.endpoint_t2v


def test_invoke_fal_video_seedance_i2v_routes_when_first_frame_url_provided(monkeypatch, tmp_path):
    _patch_fal_video_env(monkeypatch)
    client, _ = _patch_video_deps(
        monkeypatch,
        subscribe_result={"video": {"url": "https://fal.media/out/clip.mp4"}},
        tmp_dir=str(tmp_path),
    )
    # Patch resolve_image_for_fal_sync via the lazy-imported module so we don't
    # touch the disk-search path.
    monkeypatch.setattr(
        "shared_tools.fal_adapter._image.resolve_image_for_fal_sync",
        lambda fal, product, ref: f"https://fal/storage/{ref}",
    )
    spec = get_fal_video_spec("fal:seedance-1.5-pro")
    asyncio.run(invoke_fal_video(
        spec, prompt="a sunset", seconds=5, size="1280x720",
        name="sunset_clip", product_name="test_product",
        first_frame_ref="hero_image",
    ))
    endpoint = client.subscribe.call_args.args[0]
    assert endpoint == spec.endpoint_i2v
    args = client.subscribe.call_args.kwargs["arguments"]
    assert args["image_url"] == "https://fal/storage/hero_image"


def test_invoke_fal_video_missing_key_raises_with_availability_text(monkeypatch, tmp_path):
    _patch_fal_video_env(monkeypatch, value=None)
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    with pytest.raises(ValueError) as exc:
        asyncio.run(invoke_fal_video(
            spec, prompt="p", seconds=5, size="1280x720",
            name="x", product_name="p",
        ))
    msg = str(exc.value)
    assert "FAL_KEY" in msg
    assert "fal:" in msg


def test_invoke_fal_video_rejects_audio_url_on_non_wan_endpoint(monkeypatch, tmp_path):
    _patch_fal_video_env(monkeypatch)
    _patch_video_deps(
        monkeypatch,
        subscribe_result={"video": {"url": "https://fal.media/out/clip.mp4"}},
        tmp_dir=str(tmp_path),
    )
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    with pytest.raises(ValueError) as exc:
        asyncio.run(invoke_fal_video(
            spec, prompt="p", seconds=5, size="1280x720",
            name="x", product_name="p",
            audio_url="https://example.com/a.mp3",
        ))
    assert "does not support audio_url" in str(exc.value)


def test_invoke_fal_video_rejects_end_frame_on_endpoint_without_support(monkeypatch, tmp_path):
    _patch_fal_video_env(monkeypatch)
    _patch_video_deps(
        monkeypatch,
        subscribe_result={"video": {"url": "https://fal.media/out/clip.mp4"}},
        tmp_dir=str(tmp_path),
    )
    spec = get_fal_video_spec("fal:hailuo-02-standard-t2v")  # supports_end_frame=False
    with pytest.raises(ValueError) as exc:
        asyncio.run(invoke_fal_video(
            spec, prompt="p", seconds=6, size="1280x720",
            name="x", product_name="p",
            end_frame_ref="some_image",
        ))
    assert "end-frame" in str(exc.value)


# ---------------------------------------------------------------------------
# Drift test: tool Literal vs catalog keys
# ---------------------------------------------------------------------------


def test_generate_video_literal_includes_all_fal_catalog_models():
    """Every FAL_VIDEO_CATALOG key must appear in GenerateVideo.model Literal.

    Guards against catalog-vs-tool drift. The legacy `seedance-1.5-pro` literal
    and the direct-provider literals (sora-*, veo-*) are tracked separately and
    allowed to be present.
    """
    from image_generation_agent.tools.utils.image_io import (  # noqa: F401  (parent package warm)
        get_images_dir,
    )
    from video_generation_agent.tools.GenerateVideo import GenerateVideo

    literal_values = set(get_args(GenerateVideo.model_fields["model"].annotation))
    direct_provider_or_legacy = {
        "sora-2",
        "sora-2-pro",
        "veo-3.1-generate-preview",
        "veo-3.1-fast-generate-preview",
        SEEDANCE_LEGACY_ALIAS,
    }
    fal_literal_values = literal_values - direct_provider_or_legacy
    assert fal_literal_values == set(FAL_VIDEO_CATALOG.keys()), (
        f"GenerateVideo Literal drift: tool exposes {fal_literal_values!r} "
        f"but catalog has {set(FAL_VIDEO_CATALOG.keys())!r}"
    )


# ---------------------------------------------------------------------------
# Cost-tier hint propagation across the umbrella
# ---------------------------------------------------------------------------


def test_cost_tier_hint_works_for_video_specs():
    """cost_tier_hint() must accept FalVideoSpec (umbrella signature widened in PR 3)."""
    for spec in FAL_VIDEO_CATALOG.values():
        hint = cost_tier_hint(spec)
        assert hint.startswith("Estimated cost tier:")
        assert spec.cost_tier in hint
