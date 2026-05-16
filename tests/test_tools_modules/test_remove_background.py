"""Equivalence tests for RemoveBackground after the PR-4 resolver swap.

Strategy: keep a verbatim copy of the pre-refactor `_resolve_to_upload_url`
method inside this test file as `_legacy_resolve_to_upload_url`, and assert
that the shared `resolve_image_for_fal_sync` adapter helper produces the same
return value / raises the same error for each of the resolver's three input
shapes (URL, absolute path, generated-image name).

A separate "FAL request equivalence" test then runs `RemoveBackground.run()`
end-to-end against a mocked `fal_client.SyncClient` and asserts that the
endpoint constant and `fal.subscribe` argument dict match the legacy code's
exact call shape. RGBA download routing is also asserted.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

pytest.importorskip("fal_client")
pytest.importorskip("PIL")

from image_generation_agent.tools.RemoveBackground import (  # noqa: E402
    FAL_ENDPOINT,
    RemoveBackground,
)
from image_generation_agent.tools.utils.image_io import find_image_path_from_name  # noqa: E402
from PIL import Image  # noqa: E402
from shared_tools.fal_adapter import resolve_image_for_fal_sync  # noqa: E402

# ---------------------------------------------------------------------------
# Verbatim copy of the pre-refactor method body (PR-4 baseline)
# ---------------------------------------------------------------------------


def _legacy_resolve_to_upload_url(images_dir: Path, fal, ref: str) -> str:
    """Verbatim copy of `RemoveBackground._resolve_to_upload_url` from the
    pre-PR-4 head (commit 48397218). Any change here would invalidate the
    refactor's behavior-preserving claim — do not edit this function except
    to track the legacy source.
    """
    ref = ref.strip()

    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https"):
        return ref

    candidate = Path(ref).expanduser().resolve()
    if candidate.exists():
        return fal.upload_file(str(candidate))

    by_name = find_image_path_from_name(images_dir, ref)
    if by_name is not None:
        return fal.upload_file(str(by_name))

    raise FileNotFoundError(
        f"Could not resolve image reference '{ref}' as URL, path, or name in {images_dir}."
    )


# ---------------------------------------------------------------------------
# Resolver equivalence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    ["http://example.com/img.png", "https://example.com/img.png"],
)
def test_resolver_url_passthrough_matches_legacy(monkeypatch, tmp_path, ref):
    """URL references pass through unchanged in both paths; fal.upload_file is never called."""
    fal = MagicMock()
    fal.upload_file.side_effect = AssertionError("upload_file must not be called for URL refs")

    # Adapter helper does its own get_images_dir lookup; mock it deterministically.
    monkeypatch.setattr(
        "shared_tools.fal_adapter._resources.get_images_dir",
        lambda product: str(tmp_path),
        raising=False,
    )

    new_result = resolve_image_for_fal_sync(fal, "product", ref)
    legacy_result = _legacy_resolve_to_upload_url(tmp_path, fal, ref)
    assert new_result == legacy_result == ref


def test_resolver_absolute_path_matches_legacy(monkeypatch, tmp_path):
    """An existing absolute path is uploaded; both paths upload the same `str(resolved)`."""
    f = tmp_path / "subject.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(
        "shared_tools.fal_adapter._resources.get_images_dir",
        lambda product: str(tmp_path),
        raising=False,
    )

    fal_new = MagicMock()
    fal_new.upload_file.return_value = "https://fal/storage/subject.png"
    fal_legacy = MagicMock()
    fal_legacy.upload_file.return_value = "https://fal/storage/subject.png"

    new_result = resolve_image_for_fal_sync(fal_new, "product", str(f))
    legacy_result = _legacy_resolve_to_upload_url(tmp_path, fal_legacy, str(f))

    expected_arg = str(f.resolve())
    assert fal_new.upload_file.call_args.args == (expected_arg,)
    assert fal_legacy.upload_file.call_args.args == (expected_arg,)
    assert new_result == legacy_result == "https://fal/storage/subject.png"


def test_resolver_generated_name_lookup_matches_legacy(monkeypatch, tmp_path):
    """A bare name resolves via find_image_path_from_name in both paths."""
    located = tmp_path / "hero.png"
    located.write_bytes(b"\x89PNG")

    def fake_find(images_dir, name):
        assert Path(str(images_dir)) == tmp_path
        assert name == "hero"
        return str(located)

    # Both paths route through `image_generation_agent.tools.utils.image_io`
    # — patch both helpers on that module so the adapter's function-local
    # import picks up the doubles.
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.find_image_path_from_name",
        fake_find,
    )
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.get_images_dir",
        lambda product: str(tmp_path),
    )

    fal_new = MagicMock()
    fal_new.upload_file.return_value = "https://fal/storage/hero.png"
    fal_legacy = MagicMock()
    fal_legacy.upload_file.return_value = "https://fal/storage/hero.png"

    new_result = resolve_image_for_fal_sync(fal_new, "product", "hero")
    legacy_result = _legacy_resolve_to_upload_url(tmp_path, fal_legacy, "hero")

    assert fal_new.upload_file.call_args.args == (str(located),)
    assert fal_legacy.upload_file.call_args.args == (str(located),)
    assert new_result == legacy_result == "https://fal/storage/hero.png"


def test_resolver_unresolvable_ref_raises_same_error_as_legacy(monkeypatch, tmp_path):
    """Unresolvable ref → FileNotFoundError with the same message format in both paths."""
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.find_image_path_from_name",
        lambda images_dir, name: None,
    )
    monkeypatch.setattr(
        "image_generation_agent.tools.utils.image_io.get_images_dir",
        lambda product: str(tmp_path),
    )

    fal = MagicMock()

    with pytest.raises(FileNotFoundError) as new_exc:
        resolve_image_for_fal_sync(fal, "product", "nope")
    with pytest.raises(FileNotFoundError) as legacy_exc:
        _legacy_resolve_to_upload_url(tmp_path, fal, "nope")
    assert str(new_exc.value) == str(legacy_exc.value)


# ---------------------------------------------------------------------------
# FAL request equivalence (full tool run)
# ---------------------------------------------------------------------------


def _rgba_png_bytes(size: tuple[int, int] = (4, 4)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (10, 20, 30, 128)).save(buf, format="PNG")
    return buf.getvalue()


def test_run_calls_fal_subscribe_with_expected_endpoint_and_args(monkeypatch, tmp_path):
    """RemoveBackground.run() must call fal.subscribe with the exact Pixelcut endpoint
    and the exact arguments dict `{"image_url", "output_format": "rgba", "sync_mode": False}`.
    """
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    images_dir = tmp_path / "generated_images"
    images_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "image_generation_agent.tools.RemoveBackground.get_images_dir",
        lambda product: str(images_dir),
    )
    monkeypatch.setattr(
        "shared_tools.fal_adapter._resources.get_images_dir",
        lambda product: str(images_dir),
        raising=False,
    )

    # Saved-image side: don't touch the disk inside save_image.
    monkeypatch.setattr(
        "image_generation_agent.tools.RemoveBackground.save_image",
        lambda image, name, dir_: (name, f"{dir_}/{name}.png"),
    )

    # Mocked fal client: subscribe returns a canned image URL; upload_file
    # passes through deterministically.
    client = MagicMock()
    client.subscribe = MagicMock(return_value={"image": {"url": "https://fal.media/result.png"}})
    client.upload_file = MagicMock(side_effect=AssertionError("upload_file should not run for URL refs"))
    monkeypatch.setattr("fal_client.SyncClient", MagicMock(return_value=client))

    # Stub the download path so we don't make real HTTP.
    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout=None: _FakeResponse(_rgba_png_bytes()),
    )

    tool = RemoveBackground(
        product_name="test_product",
        input_image_ref="https://example.com/in.png",
        output_file_name="hero_no_bg",
    )
    tool.run()

    call = client.subscribe.call_args
    assert call.args[0] == FAL_ENDPOINT
    assert call.kwargs["arguments"] == {
        "image_url": "https://example.com/in.png",
        "output_format": "rgba",
        "sync_mode": False,
    }


def test_run_downloads_and_converts_to_rgba(monkeypatch, tmp_path):
    """The RGBA download path stays in the tool — assert the final image is RGBA."""
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    monkeypatch.setattr(
        "image_generation_agent.tools.RemoveBackground.get_images_dir",
        lambda product: str(tmp_path),
    )
    monkeypatch.setattr(
        "shared_tools.fal_adapter._resources.get_images_dir",
        lambda product: str(tmp_path),
        raising=False,
    )

    captured = {}

    def fake_save_image(image, name, dir_):
        captured["mode"] = image.mode
        return (name, f"{dir_}/{name}.png")

    monkeypatch.setattr(
        "image_generation_agent.tools.RemoveBackground.save_image", fake_save_image
    )

    client = MagicMock()
    client.subscribe = MagicMock(return_value={"image": {"url": "https://fal.media/result.png"}})
    monkeypatch.setattr("fal_client.SyncClient", MagicMock(return_value=client))

    # Send an RGB body — the tool's _download_rgba must convert to RGBA.
    rgb_buf = io.BytesIO()
    Image.new("RGB", (4, 4), (5, 6, 7)).save(rgb_buf, format="PNG")
    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout=None: _FakeResponse(rgb_buf.getvalue()),
    )

    tool = RemoveBackground(
        product_name="test_product",
        input_image_ref="https://example.com/in.png",
        output_file_name="hero_no_bg",
    )
    tool.run()
    assert captured["mode"] == "RGBA"


def test_run_raises_when_fal_returns_no_image_url(monkeypatch, tmp_path):
    """Existing error path stays — RuntimeError with the same message after the resolver swap."""
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "image_generation_agent.tools.RemoveBackground.get_images_dir",
        lambda product: str(tmp_path),
    )
    monkeypatch.setattr(
        "shared_tools.fal_adapter._resources.get_images_dir",
        lambda product: str(tmp_path),
        raising=False,
    )

    client = MagicMock()
    client.subscribe = MagicMock(return_value={"image": {}})  # no url
    monkeypatch.setattr("fal_client.SyncClient", MagicMock(return_value=client))

    tool = RemoveBackground(
        product_name="test_product",
        input_image_ref="https://example.com/in.png",
        output_file_name="hero_no_bg",
    )
    with pytest.raises(RuntimeError) as exc:
        tool.run()
    assert "no image URL" in str(exc.value)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Mimics `requests.Response` enough for `_download_rgba`."""

    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:  # pragma: no cover — trivial
        return None
