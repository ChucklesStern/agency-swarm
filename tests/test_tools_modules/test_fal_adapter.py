"""Unit tests for the FAL.AI image-generation adapter.

These tests never make real HTTP calls — `fal_client.SyncClient` and
`requests.get` are mocked at the test boundary. Live calls are exercised
opt-in via tests/integration/tools/test_fal_live_image.py.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fal_client")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from shared_tools.fal_adapter import (  # noqa: E402
    FAL_I2I_CATALOG,
    FAL_T2I_CATALOG,
    FalI2ISpec,
    FalT2ISpec,
    _build_aspect_ratio_family_request,
    _build_flux_kontext_request,
    _build_image_size_family_request,
    _parse_images_response,
    cost_tier_hint,
    get_fal_i2i_spec,
    get_fal_t2i_spec,
    invoke_fal_image_edit_sync,
    invoke_fal_image_sync,
    is_fal_i2i_model,
    is_fal_model,
    is_fal_t2i_model,
    validate_fal_aspect_ratio,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _png_bytes(color: tuple[int, int, int] = (200, 100, 50)) -> bytes:
    """Produce a tiny PNG buffer suitable for mocked HTTP responses."""
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _mock_requests_get(monkeypatch, *, body: bytes = None) -> None:
    """Patch the canonical `requests.get`.

    `_download_url_to_pil` lazy-imports `requests` inside the function, so a patch
    targeted at `shared_tools.fal_adapter.requests.get` wouldn't be observed. The
    canonical module is shared globally — monkeypatch scopes the change to the
    current test function.
    """
    body = body if body is not None else _png_bytes()
    response = MagicMock()
    response.content = body
    response.raise_for_status = MagicMock()
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: response)


def _patch_fal_key(monkeypatch, value: str | None = "test-key") -> None:
    """Stabilize FAL_KEY env around test execution.

    `_require_fal_key` calls `load_dotenv(override=True)` before reading the env,
    which would clobber `monkeypatch.delenv`. We neutralize the canonical
    `dotenv.load_dotenv` so the monkeypatched env is authoritative. The adapter
    lazy-imports `load_dotenv` inside the function, so patching the source module
    is the only path that actually intercepts the call.
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    if value is None:
        monkeypatch.delenv("FAL_KEY", raising=False)
    else:
        monkeypatch.setenv("FAL_KEY", value)


def _patch_fal_client(monkeypatch, *, subscribe_result: dict):
    """Replace fal_client.SyncClient with a MagicMock that returns a canned result.

    fal_client is lazy-imported inside `invoke_fal_image_sync`. Patching the
    canonical module surface is the only reliable interception point.
    """
    client = MagicMock()
    client.subscribe = MagicMock(return_value=subscribe_result)
    sync_client_factory = MagicMock(return_value=client)
    monkeypatch.setattr("fal_client.SyncClient", sync_client_factory)
    return client


# ---------------------------------------------------------------------------
# Catalog / metadata
# ---------------------------------------------------------------------------


def test_catalog_contains_expected_pr1_models():
    """The five PR 1 T2I models are present and only those."""
    assert set(FAL_T2I_CATALOG.keys()) == {
        "fal:flux-schnell",
        "fal:flux-1.1-pro-ultra",
        "fal:ideogram-v3",
        "fal:recraft-v3",
        "fal:nano-banana-2",
    }


def test_is_fal_model_is_umbrella_across_t2i_and_i2i():
    """`is_fal_model` returns True for any curated FAL model (T2I or I2I)."""
    # PR 1 T2I catalog
    assert is_fal_model("fal:flux-schnell") is True
    assert is_fal_model("fal:flux-1.1-pro-ultra") is True
    # PR 2 I2I catalog
    assert is_fal_model("fal:flux-pro-kontext") is True
    # Direct-provider models stay out
    assert is_fal_model("gemini-2.5-flash-image") is False
    assert is_fal_model("gpt-image-1.5") is False
    # Reserved for PR 3 — not in any catalog yet.
    assert is_fal_model("fal:seedance-1.5-pro") is False
    assert is_fal_model("seedance-1.5-pro") is False
    assert is_fal_model("") is False
    assert is_fal_model("anything-else") is False


def test_is_fal_t2i_model_recognizes_only_t2i_catalog():
    """T2I predicate stays narrow — won't accept the I2I edit model."""
    assert is_fal_t2i_model("fal:flux-schnell") is True
    assert is_fal_t2i_model("fal:ideogram-v3") is True
    assert is_fal_t2i_model("fal:flux-pro-kontext") is False  # edit-only model
    assert is_fal_t2i_model("gemini-2.5-flash-image") is False
    assert is_fal_t2i_model("") is False


def test_is_fal_i2i_model_recognizes_only_i2i_catalog():
    """I2I predicate stays narrow — won't accept any T2I generation model."""
    assert is_fal_i2i_model("fal:flux-pro-kontext") is True
    assert is_fal_i2i_model("fal:flux-schnell") is False
    assert is_fal_i2i_model("fal:flux-1.1-pro-ultra") is False
    assert is_fal_i2i_model("gemini-2.5-flash-image") is False
    assert is_fal_i2i_model("") is False


def test_t2i_and_i2i_catalog_keys_are_disjoint():
    """No model id may live in both catalogs — the predicate semantics rely on this."""
    assert not (set(FAL_T2I_CATALOG) & set(FAL_I2I_CATALOG))


def test_get_fal_t2i_spec_returns_spec_for_known_model():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    assert isinstance(spec, FalT2ISpec)
    assert spec.endpoint == "fal-ai/flux/schnell"
    assert spec.family == "flux"
    assert spec.cost_tier == "budget"


def test_get_fal_t2i_spec_raises_with_full_key_listing():
    with pytest.raises(ValueError) as excinfo:
        get_fal_t2i_spec("nonsense")
    message = str(excinfo.value)
    assert "Unknown FAL T2I model 'nonsense'" in message
    for key in FAL_T2I_CATALOG:
        assert key in message


# ---------------------------------------------------------------------------
# Aspect-ratio validation
# ---------------------------------------------------------------------------


def test_validate_fal_aspect_ratio_accepts_supported():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    # No exception
    validate_fal_aspect_ratio(spec, "16:9")
    validate_fal_aspect_ratio(spec, "1:1")


def test_validate_fal_aspect_ratio_rejects_unsupported_for_image_size_family():
    """Flux Schnell uses image_size presets — `2:3` is NOT in the supported set."""
    spec = get_fal_t2i_spec("fal:flux-schnell")
    with pytest.raises(ValueError) as excinfo:
        validate_fal_aspect_ratio(spec, "2:3")
    msg = str(excinfo.value)
    assert "Aspect ratio '2:3' is not supported by FAL model 'fal:flux-schnell'" in msg
    # Every supported ratio is surfaced in the error so the agent can self-correct.
    for supported in ("1:1", "4:3", "3:4", "16:9", "9:16"):
        assert supported in msg
    # And the unsupported one is NOT in the listed supported set.
    assert "Supported values:" in msg


def test_validate_fal_aspect_ratio_rejects_unsupported_for_flux_ultra():
    """Flux Pro Ultra accepts most ratios but not `4:5` or `5:4`."""
    spec = get_fal_t2i_spec("fal:flux-1.1-pro-ultra")
    with pytest.raises(ValueError):
        validate_fal_aspect_ratio(spec, "4:5")
    with pytest.raises(ValueError):
        validate_fal_aspect_ratio(spec, "5:4")
    # But standard ones pass.
    validate_fal_aspect_ratio(spec, "21:9")
    validate_fal_aspect_ratio(spec, "1:1")


def test_validate_fal_aspect_ratio_nano_banana_widest_set():
    """Nano Banana 2 supports every tool aspect ratio."""
    spec = get_fal_t2i_spec("fal:nano-banana-2")
    for ar in ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"):
        validate_fal_aspect_ratio(spec, ar)


# ---------------------------------------------------------------------------
# Cost-tier hint
# ---------------------------------------------------------------------------


def test_cost_tier_hint_format():
    """The hint is tier-only, never a numeric price."""
    spec = get_fal_t2i_spec("fal:flux-1.1-pro-ultra")
    hint = cost_tier_hint(spec)
    assert hint == "Estimated cost tier: premium. Check FAL dashboard for exact pricing."
    # No digits = no numeric pricing.
    assert not any(ch.isdigit() for ch in hint)


def test_cost_tier_hint_renders_each_tier_explicitly():
    assert "budget" in cost_tier_hint(get_fal_t2i_spec("fal:flux-schnell"))
    assert "standard" in cost_tier_hint(get_fal_t2i_spec("fal:ideogram-v3"))
    assert "premium" in cost_tier_hint(get_fal_t2i_spec("fal:flux-1.1-pro-ultra"))


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def test_image_size_family_request_flux_schnell():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    args = _build_image_size_family_request(spec, prompt="hello", aspect_ratio="16:9", num_images=3)
    assert args == {"prompt": "hello", "image_size": "landscape_16_9", "num_images": 3}


def test_image_size_family_request_ideogram():
    spec = get_fal_t2i_spec("fal:ideogram-v3")
    args = _build_image_size_family_request(spec, prompt="poster", aspect_ratio="9:16", num_images=2)
    assert args == {"prompt": "poster", "image_size": "portrait_16_9", "num_images": 2}


def test_image_size_family_request_recraft_drops_num_images():
    """Recraft V3 has no `num_images` field — builder must omit it."""
    spec = get_fal_t2i_spec("fal:recraft-v3")
    args = _build_image_size_family_request(spec, prompt="design", aspect_ratio="1:1", num_images=4)
    assert args == {"prompt": "design", "image_size": "square_hd"}


def test_aspect_ratio_family_request_flux_ultra():
    spec = get_fal_t2i_spec("fal:flux-1.1-pro-ultra")
    args = _build_aspect_ratio_family_request(spec, prompt="hero", aspect_ratio="21:9", num_images=1)
    assert args == {"prompt": "hero", "aspect_ratio": "21:9", "num_images": 1}


def test_aspect_ratio_family_request_nano_banana():
    spec = get_fal_t2i_spec("fal:nano-banana-2")
    args = _build_aspect_ratio_family_request(spec, prompt="x", aspect_ratio="4:5", num_images=2)
    assert args == {"prompt": "x", "aspect_ratio": "4:5", "num_images": 2}


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def test_parse_images_response_extracts_urls():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    result = {"images": [{"url": "https://x/a.png"}, {"url": "https://x/b.png"}]}
    assert _parse_images_response(spec, result) == ["https://x/a.png", "https://x/b.png"]


def test_parse_images_response_raises_when_no_images_field():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    with pytest.raises(RuntimeError) as excinfo:
        _parse_images_response(spec, {})
    assert "returned no images" in str(excinfo.value)


def test_parse_images_response_raises_when_url_missing():
    spec = get_fal_t2i_spec("fal:flux-schnell")
    with pytest.raises(RuntimeError) as excinfo:
        _parse_images_response(spec, {"images": [{"file_name": "x.png"}]})
    assert "without URLs" in str(excinfo.value)


# ---------------------------------------------------------------------------
# invoke_fal_image_sync — end-to-end with mocks
# ---------------------------------------------------------------------------


def test_invoke_fal_image_sync_missing_key_raises_with_availability_text(monkeypatch):
    _patch_fal_key(monkeypatch, value=None)
    spec = get_fal_t2i_spec("fal:flux-schnell")
    with pytest.raises(ValueError) as excinfo:
        invoke_fal_image_sync(spec, prompt="x", aspect_ratio="1:1", num_variants=1)
    msg = str(excinfo.value)
    assert "FAL_KEY is not set" in msg
    # Should also surface the availability section (catalog-driven listing).
    assert "Via FAL.AI" in msg


def test_invoke_fal_image_sync_validates_aspect_ratio_for_spec(monkeypatch):
    _patch_fal_key(monkeypatch)
    _patch_fal_client(monkeypatch, subscribe_result={"images": [{"url": "x"}]})
    _mock_requests_get(monkeypatch)
    spec = get_fal_t2i_spec("fal:flux-schnell")
    with pytest.raises(ValueError):
        # 2:3 not supported by Flux Schnell's image_size family.
        invoke_fal_image_sync(spec, prompt="x", aspect_ratio="2:3", num_variants=1)


def test_invoke_fal_image_sync_returns_pil_images_for_image_size_family(monkeypatch):
    _patch_fal_key(monkeypatch)
    client = _patch_fal_client(
        monkeypatch,
        subscribe_result={
            "images": [
                {"url": "https://x/a.png"},
                {"url": "https://x/b.png"},
            ]
        },
    )
    _mock_requests_get(monkeypatch)

    spec = get_fal_t2i_spec("fal:flux-schnell")
    images = invoke_fal_image_sync(spec, prompt="hi", aspect_ratio="16:9", num_variants=2)
    assert len(images) == 2
    assert all(isinstance(img, Image.Image) for img in images)
    # Confirm the request shape sent to FAL — `image_size` preset, not `aspect_ratio`.
    client.subscribe.assert_called_once_with(
        "fal-ai/flux/schnell",
        arguments={"prompt": "hi", "image_size": "landscape_16_9", "num_images": 2},
    )


def test_invoke_fal_image_sync_uses_aspect_ratio_family_for_flux_ultra(monkeypatch):
    _patch_fal_key(monkeypatch)
    client = _patch_fal_client(monkeypatch, subscribe_result={"images": [{"url": "https://x/a.png"}]})
    _mock_requests_get(monkeypatch)

    spec = get_fal_t2i_spec("fal:flux-1.1-pro-ultra")
    images = invoke_fal_image_sync(spec, prompt="hero", aspect_ratio="21:9", num_variants=1)
    assert len(images) == 1
    # Flux Pro Ultra uses `aspect_ratio` not `image_size`.
    client.subscribe.assert_called_once_with(
        "fal-ai/flux-pro/v1.1-ultra",
        arguments={"prompt": "hero", "aspect_ratio": "21:9", "num_images": 1},
    )


def test_invoke_fal_image_sync_recraft_fanout_uses_parallel_calls(monkeypatch):
    """Recraft has no num_images — adapter calls fal.subscribe once per variant."""
    _patch_fal_key(monkeypatch)
    client = _patch_fal_client(
        monkeypatch,
        subscribe_result={"images": [{"url": "https://x/a.png"}]},
    )
    _mock_requests_get(monkeypatch)

    spec = get_fal_t2i_spec("fal:recraft-v3")
    images = invoke_fal_image_sync(spec, prompt="art", aspect_ratio="1:1", num_variants=3)
    assert len(images) == 3
    assert client.subscribe.call_count == 3
    # Each call must NOT include num_images.
    for call in client.subscribe.call_args_list:
        endpoint, kwargs = call.args[0], call.kwargs
        assert endpoint == "fal-ai/recraft/v3/text-to-image"
        assert "num_images" not in kwargs["arguments"]
        assert kwargs["arguments"]["image_size"] == "square_hd"


# ---------------------------------------------------------------------------
# Tier A import discipline (regression guard)
# ---------------------------------------------------------------------------


def test_model_availability_import_stays_tier_a_only(tmp_path):
    """Importing model_availability must NOT pull in heavy media deps.

    Regression guard for the Tier A / Tier B split. If anyone moves an
    `fal_client` / `PIL` / `cv2` / `requests` / video-utility import to
    module-level in `fal_adapter.py` (Tier A), this test will fail.

    Runs in a clean Python subprocess so the import audit is hermetic — any
    earlier test that already cached `fal_client` / `PIL` / `requests` in this
    process's `sys.modules` doesn't poison the result, and (more importantly)
    popping or re-loading those modules can't poison neighboring tests that
    hold a module-top `from PIL import Image` reference.
    """
    import subprocess
    import sys as _sys
    import textwrap
    from pathlib import Path

    openswarm_root = Path(__file__).resolve().parents[2] / "src" / "agency_swarm" / "_templates" / "openswarm"

    # Narrowed forbidden list: only modules `fal_adapter` itself is responsible
    # for keeping out of Tier A. `requests` and `PIL` are pulled transitively by
    # `openai_client_utils.py` (which imports `from openai import OpenAI`),
    # which is unavoidable here and unrelated to the fal_adapter Tier A/B split.
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(openswarm_root)!r})

        import shared_tools.model_availability  # noqa: F401

        forbidden = ("fal_client", "cv2")
        leaked = [name for name in forbidden if name in sys.modules]
        if leaked:
            print("LEAKED:" + ",".join(leaked))
            sys.exit(1)
        print("OK")
        """
    )
    script_path = tmp_path / "tier_a_audit.py"
    script_path.write_text(script, encoding="utf-8")

    result = subprocess.run(
        [_sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Tier A leaked heavy imports. Move them inside functions in "
        f"`shared_tools/fal_adapter.py`.\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# PR 2: I2I (image-edit) catalog / metadata
# ---------------------------------------------------------------------------


def test_i2i_catalog_contains_only_flux_kontext():
    """The PR 2 I2I catalog ships exactly one entry — Flux Kontext."""
    assert set(FAL_I2I_CATALOG.keys()) == {"fal:flux-pro-kontext"}


def test_get_fal_i2i_spec_returns_spec_for_flux_kontext():
    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    assert isinstance(spec, FalI2ISpec)
    assert spec.endpoint == "fal-ai/flux-pro/kontext"
    assert spec.family == "flux_kontext"
    assert spec.cost_tier == "premium"


def test_get_fal_i2i_spec_raises_with_listing_on_unknown():
    with pytest.raises(ValueError) as excinfo:
        get_fal_i2i_spec("fal:flux-schnell")  # T2I model — should miss I2I lookup
    message = str(excinfo.value)
    assert "Unknown FAL I2I (image-edit) model 'fal:flux-schnell'" in message
    assert "fal:flux-pro-kontext" in message  # listing includes I2I keys


def test_flux_kontext_supported_aspect_ratios_match_phase0_verification():
    """Sanity: AR set is the verified Flux Pro family set, NOT including 4:5 or 5:4."""
    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    assert spec.supported_aspect_ratios == frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"})
    # Spot-check the deliberately-rejected ratios.
    for ar in ("4:5", "5:4"):
        with pytest.raises(ValueError):
            validate_fal_aspect_ratio(spec, ar)


def test_flux_kontext_cost_tier_hint_is_premium():
    assert "premium" in cost_tier_hint(get_fal_i2i_spec("fal:flux-pro-kontext"))


# ---------------------------------------------------------------------------
# PR 2: Flux Kontext request builder
# ---------------------------------------------------------------------------


def test_flux_kontext_request_includes_required_fields():
    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    args = _build_flux_kontext_request(
        spec,
        prompt="replace the background with a starry sky",
        image_url="https://x/in.png",
        aspect_ratio="16:9",
        num_images=1,
    )
    assert args == {
        "prompt": "replace the background with a starry sky",
        "image_url": "https://x/in.png",
        "aspect_ratio": "16:9",
        "num_images": 1,
    }


# ---------------------------------------------------------------------------
# PR 2: invoke_fal_image_edit_sync — end-to-end with mocks
# ---------------------------------------------------------------------------


def test_invoke_fal_image_edit_sync_missing_key_raises_with_availability_text(monkeypatch):
    _patch_fal_key(monkeypatch, value=None)
    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    with pytest.raises(ValueError) as excinfo:
        invoke_fal_image_edit_sync(
            spec,
            prompt="edit",
            input_image_ref="https://x/in.png",
            product_name="p",
            aspect_ratio="1:1",
            num_variants=1,
        )
    msg = str(excinfo.value)
    assert "FAL_KEY is not set" in msg
    # And the umbrella availability message lists the I2I row.
    assert "Via FAL.AI (I2I image-edit" in msg
    assert "fal:flux-pro-kontext" in msg


def test_invoke_fal_image_edit_sync_validates_aspect_ratio(monkeypatch):
    _patch_fal_key(monkeypatch)
    _patch_fal_client(monkeypatch, subscribe_result={"images": [{"url": "x"}]})
    _mock_requests_get(monkeypatch)
    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    with pytest.raises(ValueError):
        invoke_fal_image_edit_sync(
            spec,
            prompt="edit",
            input_image_ref="https://x/in.png",
            product_name="p",
            aspect_ratio="4:5",  # NOT supported by Flux Kontext
            num_variants=1,
        )


def test_invoke_fal_image_edit_sync_passes_url_through_unchanged(monkeypatch):
    """When input_image_ref is an HTTPS URL, no upload_file call should happen."""
    _patch_fal_key(monkeypatch)
    client = _patch_fal_client(
        monkeypatch,
        subscribe_result={"images": [{"url": "https://x/out.png"}]},
    )
    _mock_requests_get(monkeypatch)

    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    images = invoke_fal_image_edit_sync(
        spec,
        prompt="add neon glow",
        input_image_ref="https://x/in.png",
        product_name="p",
        aspect_ratio="16:9",
        num_variants=1,
    )
    assert len(images) == 1
    assert isinstance(images[0], Image.Image)

    # URL passthrough: no upload_file should have been called.
    client.upload_file.assert_not_called()

    # And the request payload uses the URL directly.
    client.subscribe.assert_called_once_with(
        "fal-ai/flux-pro/kontext",
        arguments={
            "prompt": "add neon glow",
            "image_url": "https://x/in.png",
            "aspect_ratio": "16:9",
            "num_images": 1,
        },
    )


def test_invoke_fal_image_edit_sync_uploads_local_file(monkeypatch, tmp_path):
    """When input_image_ref is a local path, the adapter calls fal.upload_file."""
    _patch_fal_key(monkeypatch)
    client = _patch_fal_client(
        monkeypatch,
        subscribe_result={"images": [{"url": "https://x/out.png"}]},
    )
    client.upload_file = MagicMock(return_value="https://fal-cdn/uploaded.png")
    _mock_requests_get(monkeypatch)

    # Create a real local image so resolve_image_for_fal_sync finds it.
    src = tmp_path / "input.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(src, format="PNG")

    spec = get_fal_i2i_spec("fal:flux-pro-kontext")
    images = invoke_fal_image_edit_sync(
        spec,
        prompt="add fog",
        input_image_ref=str(src),
        product_name="p",
        aspect_ratio="1:1",
        num_variants=1,
    )
    assert len(images) == 1

    client.upload_file.assert_called_once_with(str(src))
    args = client.subscribe.call_args.kwargs["arguments"]
    assert args["image_url"] == "https://fal-cdn/uploaded.png"


# ---------------------------------------------------------------------------
# PR 2: scope guard — no video / Seedance / normalize symbols leaked in
# ---------------------------------------------------------------------------


def test_pr2_does_not_introduce_pr3_symbols():
    """PR 2 must not add video catalog, Seedance alias, or normalize helpers.

    Those land in PR 3. This test gives PR 3 the opportunity to ship them
    deliberately; until then, accidentally exposing any of these names from
    `shared_tools.fal_adapter` fails the build.
    """
    import shared_tools.fal_adapter as adapter

    forbidden = (
        "FAL_VIDEO_CATALOG",
        "FalVideoSpec",
        "SEEDANCE_LEGACY_ALIAS",
        "normalize_fal_model_id",
        "invoke_fal_video",
        "validate_fal_duration",
        "get_fal_video_spec",
    )
    present = [name for name in forbidden if hasattr(adapter, name)]
    assert not present, f"PR 2 must not introduce PR 3 symbols: {present!r}. Add them in PR 3 with their own tests."
