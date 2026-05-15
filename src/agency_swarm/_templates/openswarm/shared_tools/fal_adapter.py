"""FAL.AI adapter for image generation models.

Split into two tiers so `model_availability.py` can describe the catalog without
importing heavy media dependencies.

Tier A: catalog metadata only. No `fal_client`, `PIL`, `requests`, or other heavy imports.
Tier B: actual invocation of FAL endpoints. Imports `fal_client`, `requests`, `PIL`.

PR 1 ships T2I image models only. Video (PR 3), image-edit (PR 2), and the Seedance
backward-compat alias all extend this file in later PRs.
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


def is_fal_model(model_id: str) -> bool:
    """Return True only for keys present in PR 1's curated T2I catalog.

    PR 2 (image edit) and PR 3 (video + Seedance alias) widen this. In PR 1 the
    function must reject every direct-provider model id, every unknown string,
    and `"fal:flux-pro-kontext"` (which is reserved for PR 2 but not yet in the catalog).
    """
    return model_id in FAL_T2I_CATALOG


def get_fal_t2i_spec(model_id: str) -> FalT2ISpec:
    """Look up a T2I spec by user-facing id.

    Raises ValueError with the full set of known T2I keys on miss.
    """
    spec = FAL_T2I_CATALOG.get(model_id)
    if spec is None:
        raise ValueError(f"Unknown FAL T2I model '{model_id}'. Known models: {sorted(FAL_T2I_CATALOG.keys())}")
    return spec


def validate_fal_aspect_ratio(spec: FalT2ISpec, aspect_ratio: str) -> None:
    """Reject aspect ratios outside the spec's supported set."""
    if aspect_ratio not in spec.supported_aspect_ratios:
        raise ValueError(
            f"Aspect ratio '{aspect_ratio}' is not supported by FAL model "
            f"'{spec.user_id}'. Supported values: {sorted(spec.supported_aspect_ratios)}"
        )


def cost_tier_hint(spec: FalT2ISpec) -> str:
    """One-line cost surface for tool output.

    Intentionally tier-only, never a numeric price. Numeric pricing only ships
    when Phase 0 records a dated pricing source with a refresh commitment.
    """
    return f"Estimated cost tier: {spec.cost_tier}. Check FAL dashboard for exact pricing."


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


def _require_fal_key() -> str:
    """Read FAL_KEY from env or raise with the standard availability message."""
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


def _parse_images_response(spec: FalT2ISpec, result: dict) -> list[str]:
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

    api_key = _require_fal_key()
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
