"""Catalog-side unit tests for the FAL.AI video adapter (Tier A).

Companion to `test_fal_adapter_video_invoke.py` (Tier B). Covers catalog
metadata, predicates / lookups, validators (duration / AR / resolution),
size→(resolution, aspect_ratio) derivation, and duration serialization.

No `fal_client`, `httpx`, or video-utility imports are needed at module top —
mirrors the import-discipline split of the source `_video_catalog.py` module.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fal_client")

from shared_tools.fal_adapter import (  # noqa: E402
    FAL_I2I_CATALOG,
    FAL_T2I_CATALOG,
    FAL_VIDEO_CATALOG,
    SEEDANCE_LEGACY_ALIAS,
    FalVideoSpec,
    derive_resolution_and_aspect,
    get_fal_video_spec,
    is_fal_i2i_model,
    is_fal_model,
    is_fal_t2i_model,
    is_fal_video_model,
    normalize_fal_model_id,
    validate_fal_video_aspect_ratio,
    validate_fal_video_duration,
    validate_fal_video_resolution,
)
from shared_tools.fal_adapter._video_invoke import _serialize_duration  # noqa: E402

# ---------------------------------------------------------------------------
# Catalog shape and disjointness
# ---------------------------------------------------------------------------


def test_video_catalog_contains_expected_pr3_models():
    """All seven verified user-facing video models are in the catalog."""
    expected = {
        "fal:kling-v3-pro-t2v",
        "fal:kling-v3-pro-i2v",
        "fal:hailuo-02-standard-t2v",
        "fal:hailuo-02-pro-i2v",
        "fal:luma-ray-2-t2v",
        "fal:wan-2.5-t2v",
        "fal:seedance-1.5-pro",
    }
    assert set(FAL_VIDEO_CATALOG.keys()) == expected


def test_video_catalog_disjoint_from_t2i_and_i2i():
    """Modality catalogs must not share user-facing ids."""
    assert FAL_T2I_CATALOG.keys().isdisjoint(FAL_VIDEO_CATALOG.keys())
    assert FAL_I2I_CATALOG.keys().isdisjoint(FAL_VIDEO_CATALOG.keys())


def test_seedance_legacy_alias_is_constant():
    """Legacy literal must remain the bare seedance-1.5-pro string for back-compat."""
    assert SEEDANCE_LEGACY_ALIAS == "seedance-1.5-pro"


# ---------------------------------------------------------------------------
# Predicates and lookups
# ---------------------------------------------------------------------------


def test_is_fal_video_model_recognizes_only_video_catalog():
    """is_fal_video_model is the video-only modality predicate."""
    for key in FAL_VIDEO_CATALOG:
        assert is_fal_video_model(key)
    assert not is_fal_video_model("fal:flux-schnell")
    assert not is_fal_video_model("fal:flux-pro-kontext")
    assert not is_fal_video_model("sora-2")
    assert not is_fal_video_model("veo-3.1-generate-preview")


def test_is_fal_video_model_rejects_legacy_seedance_literal():
    """Legacy seedance-1.5-pro must NOT match the predicate — callers normalize first."""
    assert not is_fal_video_model(SEEDANCE_LEGACY_ALIAS)


def test_is_fal_model_umbrella_includes_video():
    """The umbrella predicate spans T2I + I2I + Video catalogs."""
    assert is_fal_model("fal:kling-v3-pro-t2v")
    assert is_fal_model("fal:seedance-1.5-pro")
    # Image-side still works through the umbrella
    assert is_fal_model("fal:flux-schnell")
    assert is_fal_model("fal:flux-pro-kontext")
    # Modality-specific predicates remain disjoint
    assert not is_fal_t2i_model("fal:kling-v3-pro-t2v")
    assert not is_fal_i2i_model("fal:kling-v3-pro-t2v")


def test_get_fal_video_spec_returns_spec_for_known_model():
    spec = get_fal_video_spec("fal:wan-2.5-t2v")
    assert isinstance(spec, FalVideoSpec)
    assert spec.user_id == "fal:wan-2.5-t2v"
    assert spec.supports_audio_url is True


def test_get_fal_video_spec_raises_with_full_key_listing():
    with pytest.raises(ValueError) as exc:
        get_fal_video_spec("fal:bogus-video-model")
    assert "fal:bogus-video-model" in str(exc.value)
    for known in FAL_VIDEO_CATALOG:
        assert known in str(exc.value)


# ---------------------------------------------------------------------------
# Legacy normalization
# ---------------------------------------------------------------------------


def test_normalize_fal_model_id_translates_seedance_legacy():
    assert normalize_fal_model_id("seedance-1.5-pro") == "fal:seedance-1.5-pro"


def test_normalize_fal_model_id_is_passthrough_for_canonical_ids():
    for canonical in ("fal:seedance-1.5-pro", "fal:flux-schnell", "sora-2", "veo-3.1-generate-preview"):
        assert normalize_fal_model_id(canonical) == canonical


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_validate_fal_video_duration_accepts_supported_values():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")
    for seconds in spec.supported_durations:
        validate_fal_video_duration(spec, seconds)


def test_validate_fal_video_duration_rejects_out_of_set_with_listing():
    spec = get_fal_video_spec("fal:hailuo-02-standard-t2v")  # only {6, 10}
    with pytest.raises(ValueError) as exc:
        validate_fal_video_duration(spec, 8)
    msg = str(exc.value)
    assert "Duration 8s" in msg
    assert "fal:hailuo-02-standard-t2v" in msg
    assert "[6, 10]" in msg


def test_validate_fal_video_duration_is_noop_when_set_empty():
    """Hailuo Pro I2V has no duration field — validator must not reject any value."""
    spec = get_fal_video_spec("fal:hailuo-02-pro-i2v")
    assert spec.supported_durations == frozenset()
    validate_fal_video_duration(spec, 42)  # arbitrary — must not raise


def test_validate_fal_video_aspect_ratio_rejects_unsupported():
    spec = get_fal_video_spec("fal:kling-v3-pro-t2v")  # {"16:9","9:16","1:1"}
    with pytest.raises(ValueError) as exc:
        validate_fal_video_aspect_ratio(spec, "21:9")
    assert "21:9" in str(exc.value)
    assert "fal:kling-v3-pro-t2v" in str(exc.value)


def test_validate_fal_video_aspect_ratio_is_noop_when_set_empty():
    """Kling I2V derives AR from input image — validator must not reject any value."""
    spec = get_fal_video_spec("fal:kling-v3-pro-i2v")
    assert spec.supported_aspect_ratios == frozenset()
    validate_fal_video_aspect_ratio(spec, "21:9")


def test_validate_fal_video_resolution_rejects_unsupported():
    spec = get_fal_video_spec("fal:wan-2.5-t2v")  # {"480p","720p","1080p"}
    with pytest.raises(ValueError) as exc:
        validate_fal_video_resolution(spec, "540p")
    assert "540p" in str(exc.value)


def test_validate_fal_video_resolution_is_noop_when_set_empty():
    """Hailuo (both variants) and Kling Pro have fixed output — validator must not reject."""
    spec = get_fal_video_spec("fal:hailuo-02-standard-t2v")
    assert spec.supported_resolutions == frozenset()
    validate_fal_video_resolution(spec, "4K")


# ---------------------------------------------------------------------------
# Size derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "size, expected_resolution, expected_ar",
    [
        # max_dim >= 1080 → "1080p" tier (existing Seedance behavior preserved verbatim).
        # 1280x720 / 720x1280 are commonly called "720p" by humans, but the existing
        # bucketing classifies them as the 1080p tier because max(width, height) ≥ 1080.
        # PR 3 is a refactor — bug-fixing that classification is intentionally deferred.
        ("1280x720", "1080p", "16:9"),
        ("720x1280", "1080p", "9:16"),
        ("1792x1024", "1080p", "16:9"),
        ("1024x1792", "1080p", "9:16"),
        ("640x480", "480p", "16:9"),
        ("960x540", "720p", "16:9"),
        ("720x720", "720p", "1:1"),
    ],
)
def test_derive_resolution_and_aspect(size, expected_resolution, expected_ar):
    """Mirrors the pre-refactor Seedance size→(resolution, AR) mapping verbatim."""
    assert derive_resolution_and_aspect(size) == (expected_resolution, expected_ar)


# ---------------------------------------------------------------------------
# Duration serialization
# ---------------------------------------------------------------------------


def test_serialize_duration_emits_bare_integer_string_for_most_families():
    for user_id in ("fal:kling-v3-pro-t2v", "fal:hailuo-02-standard-t2v", "fal:wan-2.5-t2v", "fal:seedance-1.5-pro"):
        spec = get_fal_video_spec(user_id)
        assert _serialize_duration(spec, 5) == "5"


def test_serialize_duration_for_luma_appends_s_suffix():
    """Luma Ray 2 is the only catalog endpoint with `"5s"`/`"9s"` duration format."""
    spec = get_fal_video_spec("fal:luma-ray-2-t2v")
    assert _serialize_duration(spec, 5) == "5s"
    assert _serialize_duration(spec, 9) == "9s"
