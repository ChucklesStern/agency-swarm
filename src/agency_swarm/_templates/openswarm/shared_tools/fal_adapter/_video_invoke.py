"""FAL.AI adapter — video invocation (Tier B).

Async per-family request builders, response parser, and the public
`invoke_fal_video` entry point. Imports `fal_client`, `httpx`, and the
`video_generation_agent` spritesheet / last-frame helpers — all loaded lazily
so that importing the package's Tier A catalog (`_video_catalog`) does not pay
the heavy-dep import cost.
"""

from __future__ import annotations

from ._video_catalog import (
    FalVideoSpec,
    derive_resolution_and_aspect,
    validate_fal_video_aspect_ratio,
    validate_fal_video_duration,
    validate_fal_video_resolution,
)


def _require_fal_key_for_video() -> str:
    """Read FAL_KEY from env or raise with the standard video-availability message."""
    import os

    from dotenv import load_dotenv

    from shared_tools.model_availability import video_model_availability_message

    load_dotenv(override=True)
    api_key = os.getenv("FAL_KEY")
    if not api_key:
        raise ValueError(
            video_model_availability_message(
                None,
                failed_requirement="FAL_KEY is not set. FAL video generation requires the fal.ai add-on key.",
            )
        )
    return api_key


def _serialize_duration(spec: FalVideoSpec, seconds: int) -> str:
    """Serialize a seconds integer to the endpoint-expected duration string.

    Luma Ray 2 expects values like `"5s"` / `"9s"` (verified Phase 0). All other
    endpoints accept bare integer strings (`"5"`, `"10"`).
    """
    if spec.family == "luma_ray2":
        return f"{seconds}s"
    return str(seconds)


def _select_endpoint(spec: FalVideoSpec, *, has_first_frame: bool) -> str:
    """Pick the right backing endpoint based on whether a first-frame ref was provided.

    Raises ValueError if the user-id's modality doesn't match the call:
    - T2V-only id with first_frame_ref set → reject.
    - I2V-only id without first_frame_ref → reject.
    Seedance has both endpoints set and auto-routes.
    """
    if has_first_frame:
        if spec.endpoint_i2v is None:
            raise ValueError(
                f"FAL video model '{spec.user_id}' is T2V-only; do not pass first_frame_ref. "
                "Use an I2V-capable model (e.g. 'fal:kling-v3-pro-i2v', 'fal:hailuo-02-pro-i2v', "
                "'fal:seedance-1.5-pro') instead."
            )
        return spec.endpoint_i2v
    if spec.endpoint_t2v is None:
        raise ValueError(
            f"FAL video model '{spec.user_id}' is I2V-only; first_frame_ref is required. "
            "Provide a starting image, or pick a T2V-capable model."
        )
    return spec.endpoint_t2v


def _build_kling_request(
    spec: FalVideoSpec,
    *,
    prompt: str,
    duration: str,
    aspect_ratio: str,
    first_frame_url: str | None,
    end_frame_url: str | None,
) -> dict:
    """Kling V3 Pro: T2V uses `aspect_ratio`; I2V uses `start_image_url` (+ optional `end_image_url`).

    The I2V endpoint does NOT accept `aspect_ratio` — output AR is derived from
    `start_image_url` dimensions per the Phase 0 schema.
    """
    args: dict = {"prompt": prompt, "duration": duration}
    if first_frame_url is None:
        args["aspect_ratio"] = aspect_ratio
    else:
        args["start_image_url"] = first_frame_url
        if end_frame_url is not None:
            args["end_image_url"] = end_frame_url
    return args


def _build_hailuo_request(
    spec: FalVideoSpec,
    *,
    prompt: str,
    duration: str | None,
    first_frame_url: str | None,
    end_frame_url: str | None,
) -> dict:
    """Hailuo-02: Standard T2V accepts `duration`; Pro I2V has no duration field.

    Neither variant exposes `aspect_ratio` or `resolution`. Pro I2V uses
    `image_url` (standard FAL field name).
    """
    args: dict = {"prompt": prompt}
    if duration is not None and spec.supported_durations:
        args["duration"] = duration
    if first_frame_url is not None:
        args["image_url"] = first_frame_url
        if end_frame_url is not None:
            args["end_image_url"] = end_frame_url
    return args


def _build_luma_ray2_request(
    spec: FalVideoSpec,
    *,
    prompt: str,
    duration: str,
    aspect_ratio: str,
    resolution: str,
) -> dict:
    """Luma Ray 2 T2V: duration uses `"5s"`/`"9s"` (already serialized by caller)."""
    return {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration,
    }


def _build_wan_request(
    spec: FalVideoSpec,
    *,
    prompt: str,
    duration: str,
    aspect_ratio: str,
    resolution: str,
    audio_url: str | None,
) -> dict:
    """Wan 2.5 T2V: only video endpoint with optional `audio_url`."""
    args: dict = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration,
    }
    if audio_url is not None:
        args["audio_url"] = audio_url
    return args


def _build_seedance_request(
    spec: FalVideoSpec,
    *,
    prompt: str,
    duration: str,
    aspect_ratio: str,
    resolution: str,
    first_frame_url: str | None,
    end_frame_url: str | None,
) -> dict:
    """Seedance Pro: AR is on both T2V and I2V (unusual — most I2V drop AR).

    I2V variant uses `image_url` (standard) and supports `end_image_url`.
    """
    args: dict = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration,
    }
    if first_frame_url is not None:
        args["image_url"] = first_frame_url
        if end_frame_url is not None:
            args["end_image_url"] = end_frame_url
    return args


def _parse_video_response(spec: FalVideoSpec, result: dict) -> str:
    """Extract the output video URL from a FAL video response.

    All seven backing endpoints return `result["video"]["url"]` (singular File
    object, not an array). Verified Phase 0.

    Strict, spec-aware variant used by `invoke_fal_video`. Raises with the
    spec's `user_id` in the error message so generation failures are easy to
    trace. Callers that need a non-raising contract should use the public
    `parse_fal_video_response` helper instead.
    """
    video = result.get("video") if isinstance(result, dict) else None
    if not isinstance(video, dict):
        raise RuntimeError(
            f"FAL video endpoint for '{spec.user_id}' returned no video object. Response: {result!r}"
        )
    url = video.get("url")
    if not isinstance(url, str) or not url:
        raise RuntimeError(
            f"FAL video endpoint for '{spec.user_id}' returned a video entry without a URL. "
            f"Response: {result!r}"
        )
    return url


def parse_fal_video_response(result: dict) -> str | None:
    """Return the output video URL from a FAL response, or None when missing.

    Parses only. Does NOT download, save, or transform. Does NOT raise on
    malformed responses — callers handle the missing-URL case (typically with
    a tool-specific error message). For the strict, spec-aware variant used
    inside `invoke_fal_video`, see `_parse_video_response`.

    Contract (matches the pre-PR-4 `EditVideoContent._extract_video_url`
    verbatim — including the "raw return" semantics: an empty string in
    `result["video"]["url"]` is returned as `""`, NOT coerced to None):
        - `result["video"]` is a dict → return `result["video"].get("url")`.
        - Any other shape → return None.
    """
    video = result.get("video") if isinstance(result, dict) else None
    if not isinstance(video, dict):
        return None
    return video.get("url")


def download_fal_video(url: str, output_path):
    """Download a FAL video URL to `output_path` using sync streaming I/O.

    Parses nothing and creates no derivatives. Streams the response in chunks
    via `httpx.Client.stream(...)`, writes them incrementally to disk, calls
    `response.raise_for_status()` so HTTP errors surface, and creates the
    output's parent directory if it does not already exist. Returns the
    resolved local `Path`.

    Does NOT extract spritesheets, thumbnails, last frames, or any other
    generation-artifact derivatives — callers handle those tool-side.

    Sync only. The async download helper used by `invoke_fal_video` is kept
    separate (see `_download_video`); unifying sync/async download behavior
    is intentionally out of scope for this refactor.
    """
    from pathlib import Path

    import httpx

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(target, "wb") as out_file:
                for chunk in response.iter_bytes():
                    if chunk:
                        out_file.write(chunk)
    return target


async def _download_video(url: str, output_path: str, timeout: float = 120.0) -> None:
    """Stream a FAL result URL to a local file (async, used by `invoke_fal_video`).

    Kept separate from the sync `download_fal_video` per the PR 4 plan: the
    video generation flow runs inside an async event loop with `asyncio.to_thread`
    elsewhere, and unifying the two download paths is a later refactor.
    """
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as http:
        response = await http.get(url)
        response.raise_for_status()
    with open(output_path, "wb") as fh:
        fh.write(response.content)


async def invoke_fal_video(
    spec: FalVideoSpec,
    *,
    prompt: str,
    seconds: int,
    size: str,
    name: str,
    product_name: str,
    first_frame_ref: str | None = None,
    end_frame_ref: str | None = None,
    audio_url: str | None = None,
) -> str:
    """Run a FAL video endpoint and return the local saved-video path.

    Validates per-spec constraints (modality, AR, duration, resolution,
    end-frame, audio), builds the family-specific request, calls `fal.subscribe`
    in a thread, downloads the result to
    `mnt/{product_name}/generated_videos/{name}.mp4`, and runs the existing
    spritesheet + last-frame extraction helpers. Returns the local file path
    string (not the FAL URL — its TTL is undocumented).
    """
    import asyncio
    import os

    import fal_client
    from video_generation_agent.tools.utils.video_utils import (
        extract_last_frame,
        generate_spritesheet,
        get_videos_dir,
    )

    api_key = _require_fal_key_for_video()

    has_first_frame = first_frame_ref is not None
    endpoint = _select_endpoint(spec, has_first_frame=has_first_frame)

    if end_frame_ref is not None and not spec.supports_end_frame:
        raise ValueError(
            f"FAL video model '{spec.user_id}' does not support an end-frame reference."
        )
    if audio_url is not None and not spec.supports_audio_url:
        raise ValueError(
            f"FAL video model '{spec.user_id}' does not support audio_url input. "
            "Only 'fal:wan-2.5-t2v' currently exposes that field."
        )

    resolution, aspect_ratio = derive_resolution_and_aspect(size)
    validate_fal_video_aspect_ratio(spec, aspect_ratio)
    validate_fal_video_resolution(spec, resolution)
    validate_fal_video_duration(spec, seconds)

    duration_str = _serialize_duration(spec, seconds)

    fal = fal_client.SyncClient(key=api_key)

    first_frame_url: str | None = None
    end_frame_url: str | None = None
    if first_frame_ref is not None:
        from ._image import resolve_image_for_fal_sync

        first_frame_url = await asyncio.to_thread(
            resolve_image_for_fal_sync, fal, product_name, first_frame_ref
        )
    if end_frame_ref is not None:
        from ._image import resolve_image_for_fal_sync

        end_frame_url = await asyncio.to_thread(
            resolve_image_for_fal_sync, fal, product_name, end_frame_ref
        )

    if spec.family == "kling_pro":
        args = _build_kling_request(
            spec,
            prompt=prompt,
            duration=duration_str,
            aspect_ratio=aspect_ratio,
            first_frame_url=first_frame_url,
            end_frame_url=end_frame_url,
        )
    elif spec.family == "hailuo":
        args = _build_hailuo_request(
            spec,
            prompt=prompt,
            duration=duration_str if spec.supported_durations else None,
            first_frame_url=first_frame_url,
            end_frame_url=end_frame_url,
        )
    elif spec.family == "luma_ray2":
        args = _build_luma_ray2_request(
            spec,
            prompt=prompt,
            duration=duration_str,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
    elif spec.family == "wan":
        args = _build_wan_request(
            spec,
            prompt=prompt,
            duration=duration_str,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            audio_url=audio_url,
        )
    elif spec.family == "seedance":
        args = _build_seedance_request(
            spec,
            prompt=prompt,
            duration=duration_str,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            first_frame_url=first_frame_url,
            end_frame_url=end_frame_url,
        )
    else:  # pragma: no cover — Literal exhaustiveness
        raise ValueError(f"Unsupported FAL video family: {spec.family!r}")

    result = await asyncio.to_thread(
        fal.subscribe, endpoint, arguments=args, with_logs=True
    )
    output_url = _parse_video_response(spec, result)

    videos_dir = get_videos_dir(product_name)
    output_path = os.path.join(videos_dir, f"{name}.mp4")

    await _download_video(output_url, output_path)

    spritesheet_path = os.path.join(videos_dir, f"{name}_spritesheet.jpg")
    await asyncio.to_thread(generate_spritesheet, output_path, spritesheet_path)

    last_frame_path = os.path.join(videos_dir, f"{name}_last_frame.jpg")
    await asyncio.to_thread(extract_last_frame, output_path, last_frame_path)

    return output_path
