"""FAL.AI adapter — public API.

Split into modality sub-modules to keep individual files under the 500-line
ceiling. Callers continue to import from `shared_tools.fal_adapter` directly;
the public surface matches the pre-split single-file module exactly, plus the
new video symbols.

Tier A (catalog metadata) stays import-light so `model_availability.py` can
describe the catalog without pulling in `fal_client`, `PIL`, `httpx`, or video
utilities. Tier B helpers do lazy / function-local imports of those deps.
"""

from __future__ import annotations

from ._image import (
    FAL_I2I_CATALOG,
    FAL_T2I_CATALOG,
    FalCostTier,
    FalI2IFamily,
    FalI2ISpec,
    FalT2IFamily,
    FalT2ISpec,
    _build_aspect_ratio_family_request,
    _build_flux_kontext_request,
    _build_image_size_family_request,
    _parse_images_response,
    get_fal_i2i_spec,
    get_fal_t2i_spec,
    invoke_fal_image_edit_sync,
    invoke_fal_image_sync,
    is_fal_i2i_model,
    is_fal_t2i_model,
    resolve_image_for_fal_sync,
    validate_fal_aspect_ratio,
)
from ._video_catalog import (
    FAL_VIDEO_CATALOG,
    SEEDANCE_LEGACY_ALIAS,
    FalVideoFamily,
    FalVideoSpec,
    derive_resolution_and_aspect,
    get_fal_video_spec,
    is_fal_video_model,
    normalize_fal_model_id,
    validate_fal_video_aspect_ratio,
    validate_fal_video_duration,
    validate_fal_video_resolution,
)
from ._video_invoke import invoke_fal_video

__all__ = [
    "FAL_I2I_CATALOG",
    "FAL_T2I_CATALOG",
    "FAL_VIDEO_CATALOG",
    "SEEDANCE_LEGACY_ALIAS",
    "FalCostTier",
    "FalI2IFamily",
    "FalI2ISpec",
    "FalT2IFamily",
    "FalT2ISpec",
    "FalVideoFamily",
    "FalVideoSpec",
    # Private builders/parsers exposed at the package surface so unit tests in
    # `tests/test_tools_modules/` can import them. Module consumers should
    # treat them as private — the underscore prefix is intentional.
    "_build_aspect_ratio_family_request",
    "_build_flux_kontext_request",
    "_build_image_size_family_request",
    "_parse_images_response",
    "cost_tier_hint",
    "derive_resolution_and_aspect",
    "get_fal_i2i_spec",
    "get_fal_t2i_spec",
    "get_fal_video_spec",
    "invoke_fal_image_edit_sync",
    "invoke_fal_image_sync",
    "invoke_fal_video",
    "is_fal_i2i_model",
    "is_fal_model",
    "is_fal_t2i_model",
    "is_fal_video_model",
    "normalize_fal_model_id",
    "resolve_image_for_fal_sync",
    "validate_fal_aspect_ratio",
    "validate_fal_video_aspect_ratio",
    "validate_fal_video_duration",
    "validate_fal_video_resolution",
]


# Sanity: a model id must never appear in more than one catalog. If a future
# PR introduces a multi-modality endpoint we will need to redesign the
# predicates, so make the assumption explicit at import time.
assert not (FAL_T2I_CATALOG.keys() & FAL_I2I_CATALOG.keys()), (
    "FAL_T2I_CATALOG and FAL_I2I_CATALOG must have disjoint keys"
)
assert not (FAL_T2I_CATALOG.keys() & FAL_VIDEO_CATALOG.keys()), (
    "FAL_T2I_CATALOG and FAL_VIDEO_CATALOG must have disjoint keys"
)
assert not (FAL_I2I_CATALOG.keys() & FAL_VIDEO_CATALOG.keys()), (
    "FAL_I2I_CATALOG and FAL_VIDEO_CATALOG must have disjoint keys"
)


def is_fal_model(model_id: str) -> bool:
    """Return True for any model id present in any curated FAL catalog.

    Umbrella predicate — useful for "is this a fal: route at all?" checks.
    Tool-side dispatch should use the modality-specific predicates
    (`is_fal_t2i_model`, `is_fal_i2i_model`, `is_fal_video_model`) so a T2I
    tool can never accidentally accept a video model and vice versa.
    """
    return (
        model_id in FAL_T2I_CATALOG
        or model_id in FAL_I2I_CATALOG
        or model_id in FAL_VIDEO_CATALOG
    )


def cost_tier_hint(spec: FalT2ISpec | FalI2ISpec | FalVideoSpec) -> str:
    """One-line cost surface for tool output.

    Intentionally tier-only, never a numeric price. Numeric pricing only ships
    when Phase 0 records a dated pricing source with a refresh commitment.
    """
    return f"Estimated cost tier: {spec.cost_tier}. Check FAL dashboard for exact pricing."
