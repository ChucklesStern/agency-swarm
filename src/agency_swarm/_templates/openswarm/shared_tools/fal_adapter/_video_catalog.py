"""FAL.AI adapter — video catalog (Tier A).

Catalog metadata only — no `fal_client`, `httpx`, or video-utility imports.
`model_availability.py` can describe the video catalog through this module
without paying any heavy-dep import cost.

All seven user-facing video models are verified in
`docs/fal_catalog_verification.md` (PR 3 section). Catalog rows mirror that doc
exactly — any drift must be fixed by re-running Phase 0 first.

Tier B invocation lives in `_video_invoke.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ._image import FalCostTier

# ---------------------------------------------------------------------------
# Tier A — catalog metadata (no heavy imports)
# ---------------------------------------------------------------------------

FalVideoFamily = Literal["kling_pro", "hailuo", "luma_ray2", "wan", "seedance"]


@dataclass(frozen=True)
class FalVideoSpec:
    """Metadata for a curated FAL video endpoint.

    Single source of truth for the per-endpoint constraints captured in
    `docs/fal_catalog_verification.md`. Tool-side validators (`GenerateVideo`)
    and the adapter request builders both read from these fields.

    Modality is implicit in the (endpoint_t2v, endpoint_i2v) pair:
    - Both set            → user-id auto-routes (Seedance only).
    - endpoint_t2v only   → T2V-only id.
    - endpoint_i2v only   → I2V-only id (must have first_frame_field set).

    Empty constraint sets (`supported_*` of `frozenset()`) mean the endpoint
    does not accept that field at all — the adapter drops the argument
    rather than rejecting the user's value.
    """

    user_id: str
    family: FalVideoFamily
    cost_tier: FalCostTier
    description: str
    endpoint_t2v: str | None
    endpoint_i2v: str | None
    # Per-endpoint constraints. Empty set = field not exposed by the endpoint.
    supported_aspect_ratios: frozenset[str]
    supported_durations: frozenset[int]
    supported_resolutions: frozenset[str]
    # Image-input field-name quirks.
    first_frame_field: str | None  # "image_url" / "start_image_url" / None for T2V-only
    supports_end_frame: bool
    supports_audio_url: bool


# Cost tiers and constraint sets mirror docs/fal_catalog_verification.md PR 3.
# Endpoint slugs are verified live (OpenAPI + model page).
FAL_VIDEO_CATALOG: dict[str, FalVideoSpec] = {
    "fal:kling-v3-pro-t2v": FalVideoSpec(
        user_id="fal:kling-v3-pro-t2v",
        family="kling_pro",
        cost_tier="premium",
        description="Cinematic T2V with native audio. Premium tier — one video per call.",
        endpoint_t2v="fal-ai/kling-video/v3/pro/text-to-video",
        endpoint_i2v=None,
        supported_aspect_ratios=frozenset({"16:9", "9:16", "1:1"}),
        supported_durations=frozenset({3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}),
        supported_resolutions=frozenset(),
        first_frame_field=None,
        supports_end_frame=False,
        supports_audio_url=False,
    ),
    "fal:kling-v3-pro-i2v": FalVideoSpec(
        user_id="fal:kling-v3-pro-i2v",
        family="kling_pro",
        cost_tier="premium",
        description="Cinematic I2V with start/end-frame control. Premium tier.",
        endpoint_t2v=None,
        endpoint_i2v="fal-ai/kling-video/v3/pro/image-to-video",
        supported_aspect_ratios=frozenset(),  # AR is derived from start_image_url
        supported_durations=frozenset({3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}),
        supported_resolutions=frozenset(),
        first_frame_field="start_image_url",  # Kling uses start_image_url, not image_url
        supports_end_frame=True,
        supports_audio_url=False,
    ),
    "fal:hailuo-02-standard-t2v": FalVideoSpec(
        user_id="fal:hailuo-02-standard-t2v",
        family="hailuo",
        cost_tier="budget",
        description="Cost-efficient T2V draft. Output fixed at 768p.",
        endpoint_t2v="fal-ai/minimax/hailuo-02/standard/text-to-video",
        endpoint_i2v=None,
        supported_aspect_ratios=frozenset(),  # endpoint has no aspect_ratio field
        supported_durations=frozenset({6, 10}),
        supported_resolutions=frozenset(),  # fixed 768p
        first_frame_field=None,
        supports_end_frame=False,
        supports_audio_url=False,
    ),
    "fal:hailuo-02-pro-i2v": FalVideoSpec(
        user_id="fal:hailuo-02-pro-i2v",
        family="hailuo",
        cost_tier="premium",
        description="Physics-rich 1080p I2V. Premium tier — duration is model-determined.",
        endpoint_t2v=None,
        endpoint_i2v="fal-ai/minimax/hailuo-02/pro/image-to-video",
        supported_aspect_ratios=frozenset(),
        supported_durations=frozenset(),  # model-determined; no duration field
        supported_resolutions=frozenset(),  # fixed 1080p
        first_frame_field="image_url",
        supports_end_frame=True,
        supports_audio_url=False,
    ),
    "fal:luma-ray-2-t2v": FalVideoSpec(
        user_id="fal:luma-ray-2-t2v",
        family="luma_ray2",
        cost_tier="standard",
        description="Motion-physics T2V. Veo alternative.",
        endpoint_t2v="fal-ai/luma-dream-machine/ray-2",
        endpoint_i2v=None,
        supported_aspect_ratios=frozenset({"16:9", "9:16", "4:3", "3:4", "21:9", "9:21"}),
        supported_durations=frozenset({5, 9}),  # serialized with "s" suffix by builder
        supported_resolutions=frozenset({"540p", "720p", "1080p"}),
        first_frame_field=None,  # T2V-only at this user-id (Luma's bare slug also supports I2V, deferred)
        supports_end_frame=False,
        supports_audio_url=False,
    ),
    "fal:wan-2.5-t2v": FalVideoSpec(
        user_id="fal:wan-2.5-t2v",
        family="wan",
        cost_tier="standard",
        description="Open-class T2V; only catalog video endpoint with audio input support.",
        endpoint_t2v="fal-ai/wan-25-preview/text-to-video",
        endpoint_i2v=None,
        supported_aspect_ratios=frozenset({"16:9", "9:16", "1:1"}),
        supported_durations=frozenset({5, 10}),
        supported_resolutions=frozenset({"480p", "720p", "1080p"}),
        first_frame_field=None,
        supports_end_frame=False,
        supports_audio_url=True,  # WAV/MP3, 3-30s, max 15MB; optional
    ),
    "fal:seedance-1.5-pro": FalVideoSpec(
        user_id="fal:seedance-1.5-pro",
        family="seedance",
        cost_tier="standard",
        description="ByteDance Seedance Pro. Auto-routes T2V/I2V based on first_frame_ref.",
        endpoint_t2v="fal-ai/bytedance/seedance/v1.5/pro/text-to-video",
        endpoint_i2v="fal-ai/bytedance/seedance/v1.5/pro/image-to-video",
        supported_aspect_ratios=frozenset({"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "auto"}),
        supported_durations=frozenset({4, 5, 6, 7, 8, 9, 10, 11, 12}),
        supported_resolutions=frozenset({"480p", "720p", "1080p"}),
        first_frame_field="image_url",
        supports_end_frame=True,
        supports_audio_url=False,
    ),
}


# Legacy literal kept working for one release per the plan. New code uses the
# canonical `fal:seedance-1.5-pro` id from FAL_VIDEO_CATALOG.
SEEDANCE_LEGACY_ALIAS = "seedance-1.5-pro"


def normalize_fal_model_id(model_id: str) -> str:
    """Translate legacy literals to their canonical `fal:` ids.

    Currently handles only `seedance-1.5-pro` → `fal:seedance-1.5-pro`. Other
    inputs pass through unchanged. Call this in a Pydantic `model_validator` on
    every video tool so dispatch code can assume canonical ids.
    """
    if model_id == SEEDANCE_LEGACY_ALIAS:
        return "fal:seedance-1.5-pro"
    return model_id


def is_fal_video_model(model_id: str) -> bool:
    """Return True only for keys present in `FAL_VIDEO_CATALOG`.

    Does NOT match the legacy `seedance-1.5-pro` literal — call
    `normalize_fal_model_id` first.
    """
    return model_id in FAL_VIDEO_CATALOG


def get_fal_video_spec(model_id: str) -> FalVideoSpec:
    """Look up a video spec by user-facing id. Raises ValueError on miss."""
    spec = FAL_VIDEO_CATALOG.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown FAL video model '{model_id}'. Known models: {sorted(FAL_VIDEO_CATALOG.keys())}"
        )
    return spec


def validate_fal_video_duration(spec: FalVideoSpec, seconds: int) -> None:
    """Reject seconds values outside the spec's supported set.

    No-op when `spec.supported_durations` is empty (endpoint does not accept
    a duration field — the adapter drops the argument silently).
    """
    if not spec.supported_durations:
        return
    if seconds not in spec.supported_durations:
        raise ValueError(
            f"Duration {seconds}s is not supported by FAL video model "
            f"'{spec.user_id}'. Supported values: {sorted(spec.supported_durations)}"
        )


def validate_fal_video_aspect_ratio(spec: FalVideoSpec, aspect_ratio: str) -> None:
    """Reject aspect ratios outside the spec's supported set.

    No-op when `spec.supported_aspect_ratios` is empty (endpoint does not
    accept an AR field).
    """
    if not spec.supported_aspect_ratios:
        return
    if aspect_ratio not in spec.supported_aspect_ratios:
        raise ValueError(
            f"Aspect ratio '{aspect_ratio}' is not supported by FAL video model "
            f"'{spec.user_id}'. Supported values: {sorted(spec.supported_aspect_ratios)}"
        )


def validate_fal_video_resolution(spec: FalVideoSpec, resolution: str) -> None:
    """Reject resolution values outside the spec's supported set.

    No-op when `spec.supported_resolutions` is empty (endpoint output is fixed).
    """
    if not spec.supported_resolutions:
        return
    if resolution not in spec.supported_resolutions:
        raise ValueError(
            f"Resolution '{resolution}' is not supported by FAL video model "
            f"'{spec.user_id}'. Supported values: {sorted(spec.supported_resolutions)}"
        )


def derive_resolution_and_aspect(size: str) -> tuple[str, str]:
    """Derive (resolution, aspect_ratio) from a `WIDTHxHEIGHT` size string.

    Matches the existing logic in `GenerateVideo._generate_with_seedance` so the
    adapter is a drop-in replacement. Resolution is bucketed to the nearest
    standard tier (480p / 720p / 1080p) by max dimension; aspect ratio is
    classified as portrait (9:16), landscape (16:9), or square (1:1) by the
    width vs height comparison.
    """
    width_str, _sep, height_str = size.partition("x")
    width = int(width_str)
    height = int(height_str)
    max_dim = max(width, height)
    if max_dim >= 1080:
        resolution = "1080p"
    elif max_dim >= 720:
        resolution = "720p"
    else:
        resolution = "480p"
    if width < height:
        aspect_ratio = "9:16"
    elif width > height:
        aspect_ratio = "16:9"
    else:
        aspect_ratio = "1:1"
    return resolution, aspect_ratio

