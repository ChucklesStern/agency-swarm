"""FAL.AI adapter — shared resource resolvers.

Sync helpers that translate a tool-side image or video reference (URL, local
path, or generated-asset name) into a FAL-storage URL via `fal.upload_file()`.
Both helpers exist so image and video tools can share the same resolution
contract instead of each tool re-implementing it.

Tier B by import semantics: `fal.upload_file` needs an active `fal_client`
handle and the template-side asset directories. The template-internal imports
(image_io, video_utils) are kept function-local so importing this module from
`model_availability.py` would not pay any heavy-dep cost.
"""

from __future__ import annotations


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

    Raises FileNotFoundError when the reference cannot be resolved by any of
    the three paths above. The image_io helpers are imported lazily so this
    function does not pull `PIL` / `image_io` into Tier A.
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


def resolve_video_for_fal_sync(fal, product_name: str, ref: str) -> str:
    """Resolve a tool-side video reference into a FAL-usable URL.

    Mirrors the resolution contract of `resolve_image_for_fal_sync` but for
    video assets. Accepts:

    1. HTTP(S) URL → passed through unchanged.
    2. Absolute / relative local path (expands `~`) → uploaded via
       `fal.upload_file()`.
    3. Generated-video name → searches `mnt/{product_name}/generated_videos/`
       for the value as-is and with the `.mp4` / `.mov` / `.avi` / `.webm`
       extensions appended, in that order. First match wins, then uploaded.

    The search order mirrors the pre-refactor `EditVideoContent._resolve_media_url`
    verbatim, including the per-iteration raw-`value` check.

    Raises FileNotFoundError with an error message that lists both the
    `generated_videos/` directory and the expanded local path that were tried.
    """
    import os

    from video_generation_agent.tools.utils.video_utils import get_videos_dir

    if ref is None:
        raise ValueError("Media source is required")

    if ref.startswith("http://") or ref.startswith("https://"):
        return ref

    # Try as absolute / relative path first.
    path = os.path.expanduser(ref)
    if os.path.exists(path):
        return fal.upload_file(path)

    # Search the product's generated_videos directory.
    videos_dir = get_videos_dir(product_name)

    for ext in [".mp4", ".mov", ".avi", ".webm"]:
        # Try with extension appended.
        video_path = os.path.join(videos_dir, f"{ref}{ext}")
        if os.path.exists(video_path):
            return fal.upload_file(video_path)

        # Try without adding extension (in case ref already has one).
        video_path = os.path.join(videos_dir, ref)
        if os.path.exists(video_path):
            return fal.upload_file(video_path)

    raise FileNotFoundError(
        f"Video file not found: '{ref}'\n"
        f"  Searched in: {videos_dir}\n"
        f"  Also tried as absolute/relative path: {path}"
    )
