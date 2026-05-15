"""Tests for the FAL.AI integration inside GenerateImages.

The lower-level adapter logic is exercised in test_fal_adapter.py. These tests
focus on the tool-side wiring: Pydantic validators, dispatch, and the
end-to-end output shape (including the cost-tier hint).
"""

from __future__ import annotations

from typing import get_args
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pydantic import ValidationError

pytest.importorskip("fal_client")

from image_generation_agent.tools.EditImages import EditImages  # noqa: E402
from image_generation_agent.tools.GenerateImages import GenerateImages  # noqa: E402
from shared_tools.fal_adapter import FAL_I2I_CATALOG, FAL_T2I_CATALOG  # noqa: E402

from agency_swarm import ToolOutputText  # noqa: E402


def _make_pil(color: tuple[int, int, int] = (10, 20, 30)) -> Image.Image:
    return Image.new("RGB", (8, 8), color)


# ---------------------------------------------------------------------------
# Drift / Literal coverage
# ---------------------------------------------------------------------------


def test_model_literal_fal_values_match_catalog():
    """Tool Literal and adapter catalog must stay in lockstep."""
    model_annotation = GenerateImages.model_fields["model"].annotation
    literal_values = set(get_args(model_annotation))
    fal_values = {v for v in literal_values if v.startswith("fal:")}
    assert fal_values == set(FAL_T2I_CATALOG.keys())


# ---------------------------------------------------------------------------
# Premium-tier guard (validator)
# ---------------------------------------------------------------------------


def test_premium_model_rejects_multiple_variants():
    """`fal:flux-1.1-pro-ultra` is premium and must reject num_variants > 1."""
    with pytest.raises(ValidationError) as excinfo:
        GenerateImages(
            product_name="t",
            prompt="hero shot",
            file_name="hero",
            model="fal:flux-1.1-pro-ultra",
            num_variants=2,
            aspect_ratio="1:1",
        )
    message = str(excinfo.value)
    assert "premium-tier" in message
    assert "num_variants=1" in message


def test_premium_model_accepts_single_variant():
    """num_variants=1 is fine — the guard only blocks > 1."""
    tool = GenerateImages(
        product_name="t",
        prompt="hero shot",
        file_name="hero",
        model="fal:flux-1.1-pro-ultra",
        num_variants=1,
        aspect_ratio="1:1",
    )
    assert tool.num_variants == 1


def test_budget_and_standard_models_allow_multiple_variants():
    """Only the premium tier triggers the variant guard."""
    GenerateImages(
        product_name="t",
        prompt="draft",
        file_name="d",
        model="fal:flux-schnell",
        num_variants=4,
        aspect_ratio="1:1",
    )
    GenerateImages(
        product_name="t",
        prompt="poster",
        file_name="p",
        model="fal:ideogram-v3",
        num_variants=3,
        aspect_ratio="1:1",
    )


# ---------------------------------------------------------------------------
# Structural T2I-only enforcement (Pydantic Literal)
# ---------------------------------------------------------------------------


def test_flux_kontext_rejected_by_pydantic_literal():
    """`fal:flux-pro-kontext` is reserved for PR 2's EditImages — not in PR 1's Literal."""
    with pytest.raises(ValidationError) as excinfo:
        GenerateImages(
            product_name="t",
            prompt="edit",
            file_name="x",
            model="fal:flux-pro-kontext",
            aspect_ratio="1:1",
        )
    # Pydantic enum-mismatch error class — confirms it's structural, not our custom check.
    assert "literal" in str(excinfo.value).lower() or "Input should be" in str(excinfo.value)


def test_seedance_rejected_by_pydantic_literal():
    """Seedance is PR 3 video; rejected in PR 1's image Literal."""
    with pytest.raises(ValidationError):
        GenerateImages(
            product_name="t",
            prompt="x",
            file_name="x",
            model="fal:seedance-1.5-pro",
            aspect_ratio="1:1",
        )


# ---------------------------------------------------------------------------
# Aspect-ratio validation routes through the adapter for fal: models
# ---------------------------------------------------------------------------


def test_unsupported_ar_for_fal_model_raises():
    """Flux Schnell's image_size family doesn't accept 2:3."""
    with pytest.raises(ValidationError) as excinfo:
        GenerateImages(
            product_name="t",
            prompt="x",
            file_name="x",
            model="fal:flux-schnell",
            aspect_ratio="2:3",
        )
    assert "Aspect ratio '2:3' is not supported by FAL model 'fal:flux-schnell'" in str(excinfo.value)


def test_unsupported_ar_for_direct_model_still_uses_direct_validator():
    """The pre-existing gpt-image-1.5 AR validator still fires for direct models."""
    with pytest.raises(ValidationError):
        GenerateImages(
            product_name="t",
            prompt="x",
            file_name="x",
            model="gpt-image-1.5",
            aspect_ratio="21:9",  # gpt-image-1.5 only supports 1:1, 2:3, 3:2
        )


# ---------------------------------------------------------------------------
# run() dispatch + cost-tier hint
# ---------------------------------------------------------------------------


def test_run_dispatches_to_fal_branch_and_appends_cost_tier_hint(monkeypatch, tmp_path):
    """Successful FAL run produces ToolOutputText/Image plus a cost-tier hint tail."""
    monkeypatch.setattr(
        "image_generation_agent.tools.GenerateImages.invoke_fal_image_sync",
        lambda spec, *, prompt, aspect_ratio, num_variants: [_make_pil()],
    )
    # Redirect mnt/ output to a temp dir to avoid polluting the repo.
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.MNT_DIR",
        tmp_path,
    )

    tool = GenerateImages(
        product_name="testprod",
        prompt="hello",
        file_name="hello_file",
        model="fal:flux-schnell",
        num_variants=1,
        aspect_ratio="1:1",
    )
    outputs = tool.run()

    # The build_multimodal_outputs envelope produces at least one text + image output;
    # the FAL branch appends one extra text item carrying the cost-tier hint.
    assert isinstance(outputs, list) and outputs, "expected non-empty output list"
    text_items = [o for o in outputs if isinstance(o, ToolOutputText)]
    hint_texts = [o.text for o in text_items if "Estimated cost tier" in o.text]
    assert hint_texts, "FAL branch must append a cost-tier hint to tool output"
    assert hint_texts[-1] == ("Estimated cost tier: budget. Check FAL dashboard for exact pricing.")

    # Saved file exists where save_image put it.
    expected_dir = tmp_path / "testprod" / "generated_images"
    assert expected_dir.exists()
    saved_files = list(expected_dir.glob("*.png"))
    assert len(saved_files) == 1


def test_run_dispatches_to_fal_branch_passes_correct_arguments(monkeypatch, tmp_path):
    """The FAL branch must hand the adapter the exact prompt / AR / num_variants."""
    captured = {}

    def fake_invoke(spec, *, prompt, aspect_ratio, num_variants):
        captured["endpoint"] = spec.endpoint
        captured["prompt"] = prompt
        captured["aspect_ratio"] = aspect_ratio
        captured["num_variants"] = num_variants
        return [_make_pil()]

    monkeypatch.setattr(
        "image_generation_agent.tools.GenerateImages.invoke_fal_image_sync",
        fake_invoke,
    )
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.MNT_DIR",
        tmp_path,
    )

    tool = GenerateImages(
        product_name="p",
        prompt="A cat",
        file_name="c",
        model="fal:ideogram-v3",
        num_variants=1,
        aspect_ratio="9:16",
    )
    tool.run()

    assert captured["endpoint"] == "fal-ai/ideogram/v3"
    assert captured["prompt"] == "A cat"
    assert captured["aspect_ratio"] == "9:16"
    assert captured["num_variants"] == 1


def test_run_does_not_call_fal_for_gemini_model(monkeypatch):
    """Pre-existing Gemini dispatch must still bypass the FAL branch."""
    sentinel = MagicMock()
    monkeypatch.setattr(
        "image_generation_agent.tools.GenerateImages.invoke_fal_image_sync",
        sentinel,
    )

    # We don't run the Gemini path here (it needs GOOGLE_API_KEY); we just confirm
    # the dispatch shape by instantiating with the default direct model and asserting
    # `is_fal_model(self.model)` is False on its model.
    from shared_tools.fal_adapter import is_fal_model

    tool = GenerateImages(
        product_name="p",
        prompt="x",
        file_name="x",
        model="gemini-2.5-flash-image",
        aspect_ratio="1:1",
    )
    assert not is_fal_model(tool.model)
    sentinel.assert_not_called()


# ---------------------------------------------------------------------------
# PR 2: EditImages — Flux Kontext (fal:flux-pro-kontext) integration
# ---------------------------------------------------------------------------


def test_editimages_literal_includes_only_fal_i2i_catalog_keys():
    """Drift guard: every `fal:` value in EditImages.model Literal must be an I2I key."""
    model_annotation = EditImages.model_fields["model"].annotation
    literal_values = set(get_args(model_annotation))
    fal_values = {v for v in literal_values if v.startswith("fal:")}
    assert fal_values == set(FAL_I2I_CATALOG.keys())


def test_editimages_does_not_accept_t2i_models_in_literal():
    """Cross-modality guard: T2I-only fal: ids must NOT appear in EditImages.model."""
    model_annotation = EditImages.model_fields["model"].annotation
    literal_values = set(get_args(model_annotation))
    t2i_keys_in_edit_literal = literal_values & set(FAL_T2I_CATALOG.keys())
    assert not t2i_keys_in_edit_literal


def test_editimages_premium_model_rejects_multiple_variants():
    """Flux Kontext is premium — `num_variants > 1` must be rejected."""
    with pytest.raises(ValidationError) as excinfo:
        EditImages(
            product_name="t",
            input_image_ref="https://x/in.png",
            edit_prompt="add stars",
            output_file_name="out",
            model="fal:flux-pro-kontext",
            num_variants=2,
            aspect_ratio="1:1",
        )
    message = str(excinfo.value)
    assert "premium-tier" in message
    assert "num_variants=1" in message


def test_editimages_premium_model_accepts_single_variant():
    tool = EditImages(
        product_name="t",
        input_image_ref="https://x/in.png",
        edit_prompt="add stars",
        output_file_name="out",
        model="fal:flux-pro-kontext",
        num_variants=1,
        aspect_ratio="1:1",
    )
    assert tool.num_variants == 1


def test_editimages_rejects_unsupported_ar_for_flux_kontext():
    """Flux Kontext doesn't accept 4:5 or 5:4 (tool Literal has them, spec doesn't)."""
    with pytest.raises(ValidationError) as excinfo:
        EditImages(
            product_name="t",
            input_image_ref="https://x/in.png",
            edit_prompt="x",
            output_file_name="x",
            model="fal:flux-pro-kontext",
            aspect_ratio="4:5",
        )
    assert "not supported by FAL model 'fal:flux-pro-kontext'" in str(excinfo.value)


def test_editimages_unsupported_ar_for_direct_model_still_uses_direct_validator():
    """Pre-existing direct-provider AR validator must keep firing for non-FAL models."""
    with pytest.raises(ValidationError):
        EditImages(
            product_name="t",
            input_image_ref="https://x/in.png",
            edit_prompt="x",
            output_file_name="x",
            model="gpt-image-1.5",
            aspect_ratio="21:9",  # gpt-image-1.5 only supports 1:1, 2:3, 3:2
        )


def test_editimages_run_dispatches_to_fal_branch_and_appends_cost_tier_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "image_generation_agent.tools.EditImages.invoke_fal_image_edit_sync",
        lambda spec, *, prompt, input_image_ref, product_name, aspect_ratio, num_variants: [_make_pil()],
    )
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.MNT_DIR",
        tmp_path,
    )

    tool = EditImages(
        product_name="testprod",
        input_image_ref="https://x/in.png",
        edit_prompt="replace background with starry sky",
        output_file_name="edited",
        model="fal:flux-pro-kontext",
        num_variants=1,
        aspect_ratio="1:1",
    )
    outputs = tool.run()

    assert isinstance(outputs, list) and outputs
    text_items = [o for o in outputs if isinstance(o, ToolOutputText)]
    hint_texts = [o.text for o in text_items if "Estimated cost tier" in o.text]
    assert hint_texts
    assert hint_texts[-1] == ("Estimated cost tier: premium. Check FAL dashboard for exact pricing.")

    saved_files = list((tmp_path / "testprod" / "generated_images").glob("*.png"))
    assert len(saved_files) == 1


def test_editimages_run_passes_correct_arguments_to_adapter(monkeypatch, tmp_path):
    """The FAL edit branch must forward prompt / input_image_ref / product_name / AR / variants."""
    captured = {}

    def fake_invoke(spec, *, prompt, input_image_ref, product_name, aspect_ratio, num_variants):
        captured["endpoint"] = spec.endpoint
        captured["prompt"] = prompt
        captured["input_image_ref"] = input_image_ref
        captured["product_name"] = product_name
        captured["aspect_ratio"] = aspect_ratio
        captured["num_variants"] = num_variants
        return [_make_pil()]

    monkeypatch.setattr(
        "image_generation_agent.tools.EditImages.invoke_fal_image_edit_sync",
        fake_invoke,
    )
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.MNT_DIR",
        tmp_path,
    )

    tool = EditImages(
        product_name="p",
        input_image_ref="hero_image",
        edit_prompt="make it night",
        output_file_name="night",
        model="fal:flux-pro-kontext",
        num_variants=1,
        aspect_ratio="16:9",
    )
    tool.run()

    assert captured["endpoint"] == "fal-ai/flux-pro/kontext"
    assert captured["prompt"] == "make it night"
    assert captured["input_image_ref"] == "hero_image"
    assert captured["product_name"] == "p"
    assert captured["aspect_ratio"] == "16:9"
    assert captured["num_variants"] == 1


def test_editimages_does_not_call_fal_for_gemini_model(monkeypatch):
    """Gemini/OpenAI dispatch must bypass the FAL edit branch."""
    sentinel = MagicMock()
    monkeypatch.setattr(
        "image_generation_agent.tools.EditImages.invoke_fal_image_edit_sync",
        sentinel,
    )

    from shared_tools.fal_adapter import is_fal_i2i_model

    tool = EditImages(
        product_name="p",
        input_image_ref="https://x/in.png",
        edit_prompt="x",
        output_file_name="x",
        model="gemini-2.5-flash-image",
        aspect_ratio="1:1",
    )
    assert not is_fal_i2i_model(tool.model)
    sentinel.assert_not_called()


# ---------------------------------------------------------------------------
# PR 2: GenerateImages must STILL reject fal:flux-pro-kontext after PR 2
# ---------------------------------------------------------------------------


def test_generateimages_still_rejects_flux_kontext_after_pr2():
    """Cross-modality guard: Flux Kontext is edit-only and must remain invalid here.

    PR 2 widens `is_fal_model` to umbrella across catalogs, but
    `GenerateImages.model` Literal does NOT include `fal:flux-pro-kontext`,
    so Pydantic structurally rejects it before any dispatch runs.
    """
    with pytest.raises(ValidationError) as excinfo:
        GenerateImages(
            product_name="t",
            prompt="x",
            file_name="x",
            model="fal:flux-pro-kontext",
            aspect_ratio="1:1",
        )
    # Structural Pydantic rejection — confirm by message content.
    text = str(excinfo.value).lower()
    assert "literal" in text or "input should be" in text
