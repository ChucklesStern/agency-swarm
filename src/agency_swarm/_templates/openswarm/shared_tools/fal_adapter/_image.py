"""FAL.AI adapter — image modality (T2I + I2I).

Split into two tiers so `model_availability.py` can describe the catalog without
importing heavy media dependencies.

Tier A: catalog metadata only. No `fal_client`, `PIL`, `requests`, or other heavy imports.
Tier B: actual invocation of FAL endpoints. Imports `fal_client`, `requests`, `PIL`.

The umbrella `is_fal_model` predicate and the 3-catalog disjoint assertion live in
the package's `__init__.py` so a single import surface remains correct across
image and video modalities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Tier A — catalog metadata (no heavy imports)
# ---------------------------------------------------------------------------

FalT2IFamily = Literal["flux", "flux_ultra", "ideogram", "recraft", "nano_banana"]
FalCostTier = Literal["budget", "standard", "premium"]


@dataclass(frozen=True)
class FalT2ISpec:
    """Metadata for a curated FAL text-to-image endpoint.

    Per-family request builders and the uniform response parser live in Tier B and
    look up the family on the spec.
    """

    user_id: str
    endpoint: str
    family: FalT2IFamily
    supported_aspect_ratios: frozenset[str]
    description: str
    cost_tier: FalCostTier


# All five rows below are verified in docs/fal_catalog_verification.md (PR 0).
# Aspect-ratio sets are constrained to the tool's Pydantic Literal — the adapter
# rejects ratios outside the spec's supported set with a clear error.
FAL_T2I_CATALOG: dict[str, FalT2ISpec] = {
    "fal:flux-schnell": FalT2ISpec(
        user_id="fal:flux-schnell",
        endpoint="fal-ai/flux/schnell",
        family="flux",
        supported_aspect_ratios=frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"}),
        description="Fast/cheap drafts. Best for iteration and variant fan-out.",
        cost_tier="budget",
    ),
    "fal:flux-1.1-pro-ultra": FalT2ISpec(
        user_id="fal:flux-1.1-pro-ultra",
        endpoint="fal-ai/flux-pro/v1.1-ultra",
        family="flux_ultra",
        supported_aspect_ratios=frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}),
        description="Photoreal premium / high-res hero shots. Premium tier — one variant per call.",
        cost_tier="premium",
    ),
    "fal:ideogram-v3": FalT2ISpec(
        user_id="fal:ideogram-v3",
        endpoint="fal-ai/ideogram/v3",
        family="ideogram",
        supported_aspect_ratios=frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"}),
        description="Typography and in-image text. Best for posters and logos.",
        cost_tier="standard",
    ),
    "fal:recraft-v3": FalT2ISpec(
        user_id="fal:recraft-v3",
        endpoint="fal-ai/recraft/v3/text-to-image",
        family="recraft",
        supported_aspect_ratios=frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"}),
        description="Stylized / design work, vector illustration.",
        cost_tier="standard",
    ),
    "fal:nano-banana-2": FalT2ISpec(
        user_id="fal:nano-banana-2",
        endpoint="fal-ai/nano-banana-2",
        family="nano_banana",
        supported_aspect_ratios=frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}),
        description="Fast Google-backed alternative. Balanced speed and quality.",
        cost_tier="standard",
    ),
}


FalI2IFamily = Literal["flux_kontext"]


@dataclass(frozen=True)
class FalI2ISpec:
    """Metadata for a curated FAL image-to-image (edit) endpoint.

    Same structural shape as FalT2ISpec, kept as a separate type so tool-side
    dispatch (`is_fal_i2i_model`, `get_fal_i2i_spec`) can never accidentally
    accept a T2I model into an edit code path, or vice versa.
    """

    user_id: str
    endpoint: str
    family: FalI2IFamily
    supported_aspect_ratios: frozenset[str]
    description: str
    cost_tier: FalCostTier


# All I2I rows are verified in docs/fal_catalog_verification.md.
FAL_I2I_CATALOG: dict[str, FalI2ISpec] = {
    "fal:flux-pro-kontext": FalI2ISpec(
        user_id="fal:flux-pro-kontext",
        endpoint="fal-ai/flux-pro/kontext",
        family="flux_kontext",
        supported_aspect_ratios=frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}),
        description="Instruction-driven image edit. Premium tier — one variant per call.",
        cost_tier="premium",
    ),
}


def is_fal_t2i_model(model_id: str) -> bool:
    """Return True only for keys present in `FAL_T2I_CATALOG`."""
    return model_id in FAL_T2I_CATALOG


def is_fal_i2i_model(model_id: str) -> bool:
    """Return True only for keys present in `FAL_I2I_CATALOG`."""
    return model_id in FAL_I2I_CATALOG


def get_fal_t2i_spec(model_id: str) -> FalT2ISpec:
    """Look up a T2I spec by user-facing id.

    Raises ValueError with the full set of known T2I keys on miss.
    """
    spec = FAL_T2I_CATALOG.get(model_id)
    if spec is None:
        raise ValueError(f"Unknown FAL T2I model '{model_id}'. Known models: {sorted(FAL_T2I_CATALOG.keys())}")
    return spec


def get_fal_i2i_spec(model_id: str) -> FalI2ISpec:
    """Look up an I2I (image-edit) spec by user-facing id.

    Raises ValueError with the full set of known I2I keys on miss.
    """
    spec = FAL_I2I_CATALOG.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown FAL I2I (image-edit) model '{model_id}'. Known models: {sorted(FAL_I2I_CATALOG.keys())}"
        )
    return spec


def validate_fal_aspect_ratio(spec: FalT2ISpec | FalI2ISpec, aspect_ratio: str) -> None:
    """Reject aspect ratios outside the spec's supported set."""
    if aspect_ratio not in spec.supported_aspect_ratios:
        raise ValueError(
            f"Aspect ratio '{aspect_ratio}' is not supported by FAL model "
            f"'{spec.user_id}'. Supported values: {sorted(spec.supported_aspect_ratios)}"
        )


# ---------------------------------------------------------------------------
# Tier B — invocation (imports fal_client, requests, PIL)
# ---------------------------------------------------------------------------
# All Tier B symbols are kept at module scope but use lazy / function-local imports
# where the dependency would otherwise leak into Tier A's import cost. This keeps
# `model_availability.py` lightweight even when it imports the whole module.

_TOOL_AR_TO_IMAGE_SIZE_PRESET: dict[str, str] = {
    "1:1": "square_hd",
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
}


def _require_fal_key_for_image() -> str:
    """Read FAL_KEY from env or raise with the standard image-availability message."""
    import os

    from dotenv import load_dotenv

    from shared_tools.model_availability import image_model_availability_message

    load_dotenv(override=True)
    api_key = os.getenv("FAL_KEY")
    if not api_key:
        raise ValueError(
            image_model_availability_message(
                None,
                failed_requirement=("FAL_KEY is not set. FAL image generation requires the fal.ai add-on key."),
            )
        )
    return api_key


def _build_image_size_family_request(spec: FalT2ISpec, *, prompt: str, aspect_ratio: str, num_images: int) -> dict:
    """Build a request for endpoints that accept `image_size` presets.

    Applies to Flux Schnell, Ideogram V3, and Recraft V3. Recraft V3 does not
    accept `num_images` — the caller is responsible for fan-out via
    `run_parallel_variants_sync`; this builder always emits a single-image request
    when called for Recraft.
    """
    image_size = _TOOL_AR_TO_IMAGE_SIZE_PRESET[aspect_ratio]
    args: dict = {"prompt": prompt, "image_size": image_size}
    if spec.family != "recraft":
        args["num_images"] = num_images
    return args


def _build_aspect_ratio_family_request(spec: FalT2ISpec, *, prompt: str, aspect_ratio: str, num_images: int) -> dict:
    """Build a request for endpoints that accept `aspect_ratio` ratio strings.

    Applies to Flux Pro Ultra and Nano Banana 2. Both accept `num_images` 1-4.
    """
    return {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "num_images": num_images,
    }


def _parse_images_response(spec: FalT2ISpec | FalI2ISpec, result: dict) -> list[str]:
    """Extract image URLs from a FAL response.

    All five PR 1 endpoints return `result["images"][i]["url"]`. This is verified
    in docs/fal_catalog_verification.md; if any future endpoint diverges,
    add a family-specific parser rather than complicating this one.
    """
    images = result.get("images") if isinstance(result, dict) else None
    if not images:
        raise RuntimeError(f"FAL endpoint '{spec.endpoint}' returned no images. Response: {result!r}")

    urls: list[str] = []
    for entry in images:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if isinstance(url, str) and url:
            urls.append(url)

    if not urls:
        raise RuntimeError(f"FAL endpoint '{spec.endpoint}' returned image entries without URLs. Response: {result!r}")
    return urls


def _download_url_to_pil(url: str, timeout: float = 60.0):
    """Download a FAL result URL into a PIL Image (RGB)."""
    import io

    import requests
    from PIL import Image

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))
    return image.convert("RGB")


def invoke_fal_image_sync(
    spec: FalT2ISpec,
    *,
    prompt: str,
    aspect_ratio: str,
    num_variants: int = 1,
) -> list:
    """Run a FAL T2I endpoint and return downloaded PIL images.

    The caller (typically `GenerateImages._run_fal`) is responsible for saving
    the images via the existing `save_image` utility and assembling tool output.
    The adapter intentionally returns PIL objects (not URLs) so callers cannot
    accidentally rely on FAL's time-limited URLs.
    """
    import fal_client

    api_key = _require_fal_key_for_image()
    validate_fal_aspect_ratio(spec, aspect_ratio)

    fal = fal_client.SyncClient(key=api_key)

    if spec.family == "recraft":
        return _invoke_recraft_fanout(
            fal=fal,
            spec=spec,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            num_variants=num_variants,
        )

    if spec.family in {"flux", "ideogram"}:
        args = _build_image_size_family_request(spec, prompt=prompt, aspect_ratio=aspect_ratio, num_images=num_variants)
    elif spec.family in {"flux_ultra", "nano_banana"}:
        args = _build_aspect_ratio_family_request(
            spec, prompt=prompt, aspect_ratio=aspect_ratio, num_images=num_variants
        )
    else:
        raise ValueError(f"Unsupported FAL T2I family: {spec.family!r}")

    result = fal.subscribe(spec.endpoint, arguments=args)
    urls = _parse_images_response(spec, result)
    return [_download_url_to_pil(url) for url in urls]


def _invoke_recraft_fanout(
    *,
    fal,
    spec: FalT2ISpec,
    prompt: str,
    aspect_ratio: str,
    num_variants: int,
) -> list:
    """Recraft V3 has no `num_images` field — fan out one call per variant.

    Uses a thread pool sized to the variant count, matching the existing
    `run_parallel_variants_sync` pattern used by the Gemini path. Inlined here
    so `shared_tools` doesn't import from `image_generation_agent`.
    """
    import concurrent.futures

    args = _build_image_size_family_request(spec, prompt=prompt, aspect_ratio=aspect_ratio, num_images=1)

    def one_variant(_idx: int):
        result = fal.subscribe(spec.endpoint, arguments=dict(args))
        urls = _parse_images_response(spec, result)
        return _download_url_to_pil(urls[0])

    results_by_index: dict[int, object] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_variants) as executor:
        future_to_index = {executor.submit(one_variant, idx): idx for idx in range(1, num_variants + 1)}
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                result = future.result()
            except Exception:
                continue
            if result is not None:
                results_by_index[idx] = result
    return [results_by_index[i] for i in sorted(results_by_index)]


# ---------------------------------------------------------------------------
# Tier B — image-to-image (edit) invocation
# ---------------------------------------------------------------------------


def resolve_image_for_fal_sync(fal, product_name: str, ref: str) -> str:
    """Resolve a tool-side image reference into a FAL-usable URL.

    Accepts the same three reference shapes as the rest of the codebase
    (matches `RemoveBackground._resolve_to_upload_url` and the Seedance I2V
    path verbatim, so the contract is uniform):

    1. HTTP(S) URL → passed through unchanged.
    2. Absolute or relative local path → uploaded via `fal.upload_file()` to
       produce a FAL-storage URL.
    3. Generated-image name (no extension) → looked up under
       `mnt/{product_name}/generated_images/`, then uploaded.

    Lives in Tier B because `fal.upload_file` needs an active `fal_client`
    handle. The image_io helpers are imported lazily so this function does
    not pull `PIL` / `image_io` into Tier A.
    """
    from urllib.parse import urlparse

    from image_generation_agent.tools.utils.image_io import (
        find_image_path_from_name,
        get_images_dir,
    )

    ref = (ref or "").strip()
    if not ref:
        raise ValueError("image reference must not be empty")

    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https"):
        return ref

    from pathlib import Path

    candidate = Path(ref).expanduser().resolve()
    if candidate.exists():
        return fal.upload_file(str(candidate))

    images_dir = get_images_dir(product_name)
    by_name = find_image_path_from_name(images_dir, ref)
    if by_name is not None:
        return fal.upload_file(str(by_name))

    raise FileNotFoundError(f"Could not resolve image reference '{ref}' as URL, path, or name in {images_dir}.")


def _build_flux_kontext_request(
    spec: FalI2ISpec, *, prompt: str, image_url: str, aspect_ratio: str, num_images: int
) -> dict:
    """Build the request payload for Flux Kontext (verified Phase 0)."""
    return {
        "prompt": prompt,
        "image_url": image_url,
        "aspect_ratio": aspect_ratio,
        "num_images": num_images,
    }


def invoke_fal_image_edit_sync(
    spec: FalI2ISpec,
    *,
    prompt: str,
    input_image_ref: str,
    product_name: str,
    aspect_ratio: str,
    num_variants: int = 1,
) -> list:
    """Run a FAL I2I (image-edit) endpoint and return downloaded PIL images.

    `input_image_ref` is a tool-side reference (URL, path, or generated-image
    name); the adapter resolves it to a FAL-storage URL internally via
    `resolve_image_for_fal_sync`.

    The caller (typically `EditImages._run_fal_edit`) is responsible for
    saving the images via the existing `save_image` utility. Returning PIL
    objects (not URLs) prevents callers from accidentally relying on FAL's
    time-limited URLs.
    """
    import fal_client

    api_key = _require_fal_key_for_image()
    validate_fal_aspect_ratio(spec, aspect_ratio)

    fal = fal_client.SyncClient(key=api_key)
    image_url = resolve_image_for_fal_sync(fal, product_name, input_image_ref)

    if spec.family == "flux_kontext":
        args = _build_flux_kontext_request(
            spec,
            prompt=prompt,
            image_url=image_url,
            aspect_ratio=aspect_ratio,
            num_images=num_variants,
        )
    else:
        raise ValueError(f"Unsupported FAL I2I family: {spec.family!r}")

    result = fal.subscribe(spec.endpoint, arguments=args)
    urls = _parse_images_response(spec, result)
    return [_download_url_to_pil(url) for url in urls]
