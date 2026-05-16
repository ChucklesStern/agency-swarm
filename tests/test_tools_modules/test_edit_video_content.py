"""Equivalence tests for EditVideoContent after the PR-4 helper swap.

Strategy: keep verbatim copies of the pre-refactor `_resolve_media_url`,
`_extract_video_url`, and `_download_file` method bodies inside this test
file as `_legacy_*` helpers, and assert that the shared adapter helpers
(`resolve_video_for_fal_sync`, `parse_fal_video_response`, `download_fal_video`)
produce the same outputs / behavior for the same inputs.

Tool-level "FAL request equivalence" tests then run `EditVideoContent.run()`
end-to-end against a mocked `fal_client.SyncClient` and assert the exact
`(endpoint, arguments)` call shape — both with and without reference images.
A "local artifact behavior" test asserts the output video path, the thumbnail
/ spritesheet / last-frame extraction call sequence, and the final
`ToolOutputText` shape.
"""

from __future__ import annotations

import asyncio
import os
import os.path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fal_client")
pytest.importorskip("httpx")

from shared_tools.fal_adapter import (  # noqa: E402
    download_fal_video,
    parse_fal_video_response,
    resolve_video_for_fal_sync,
)
from video_generation_agent.tools.EditVideoContent import (  # noqa: E402
    EditMode,
    EditVideoContent,
)

# ---------------------------------------------------------------------------
# Verbatim copies of the pre-refactor methods (PR-4 baseline)
# ---------------------------------------------------------------------------


def _legacy_resolve_media_url(
    product_name: str,
    value: str | None,
    fal,
    get_videos_dir,
) -> str:
    """Verbatim copy of `EditVideoContent._resolve_media_url` pre-PR-4.

    Refactored to take `product_name` and `get_videos_dir` as explicit
    parameters (rather than `self.product_name` and a module-level helper)
    so the test can call it directly without instantiating the tool.
    """
    if value is None:
        raise ValueError("Media source is required")

    if value.startswith("http://") or value.startswith("https://"):
        return value

    path = os.path.expanduser(value)
    if os.path.exists(path):
        return fal.upload_file(path)

    videos_dir = get_videos_dir(product_name)

    for ext in [".mp4", ".mov", ".avi", ".webm"]:
        video_path = os.path.join(videos_dir, f"{value}{ext}")
        if os.path.exists(video_path):
            return fal.upload_file(video_path)

        video_path = os.path.join(videos_dir, value)
        if os.path.exists(video_path):
            return fal.upload_file(video_path)

    raise FileNotFoundError(
        f"Video file not found: '{value}'\n"
        f"  Searched in: {videos_dir}\n"
        f"  Also tried as absolute/relative path: {path}"
    )


def _legacy_extract_video_url(result: dict) -> str | None:
    """Verbatim copy of `EditVideoContent._extract_video_url` pre-PR-4."""
    video_info = result.get("video")
    if isinstance(video_info, dict):
        return video_info.get("url")
    return None


def _legacy_download_file(url: str, output_path: str) -> None:
    """Verbatim copy of `EditVideoContent._download_file` pre-PR-4."""
    import httpx

    with httpx.Client(timeout=120.0) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as out_file:
                for chunk in response.iter_bytes():
                    if chunk:
                        out_file.write(chunk)


# ---------------------------------------------------------------------------
# Resolver equivalence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["http://example.com/v.mp4", "https://example.com/v.mp4"])
def test_video_resolver_url_passthrough_matches_legacy(monkeypatch, tmp_path, ref):
    """URL refs pass through unchanged; fal.upload_file is never called."""
    fal = MagicMock()
    fal.upload_file.side_effect = AssertionError("upload_file must not be called for URL refs")

    monkeypatch.setattr(
        "video_generation_agent.tools.utils.video_utils.get_videos_dir",
        lambda product: str(tmp_path),
    )

    new_result = resolve_video_for_fal_sync(fal, "product", ref)
    legacy_result = _legacy_resolve_media_url(
        "product", ref, fal, lambda product: str(tmp_path)
    )
    assert new_result == legacy_result == ref


def test_video_resolver_absolute_path_matches_legacy(monkeypatch, tmp_path):
    """An existing absolute path is uploaded directly; both paths upload the same value."""
    f = tmp_path / "subject.mp4"
    f.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    monkeypatch.setattr(
        "video_generation_agent.tools.utils.video_utils.get_videos_dir",
        lambda product: str(tmp_path / "nowhere"),
    )

    fal_new = MagicMock()
    fal_new.upload_file.return_value = "https://fal/storage/subject.mp4"
    fal_legacy = MagicMock()
    fal_legacy.upload_file.return_value = "https://fal/storage/subject.mp4"

    new_result = resolve_video_for_fal_sync(fal_new, "product", str(f))
    legacy_result = _legacy_resolve_media_url(
        "product", str(f), fal_legacy, lambda product: str(tmp_path / "nowhere")
    )

    expected_arg = os.path.expanduser(str(f))
    assert fal_new.upload_file.call_args.args == (expected_arg,)
    assert fal_legacy.upload_file.call_args.args == (expected_arg,)
    assert new_result == legacy_result == "https://fal/storage/subject.mp4"


@pytest.mark.parametrize("ext", [".mp4", ".mov", ".avi", ".webm"])
def test_video_resolver_generated_name_lookup_matches_legacy(monkeypatch, tmp_path, ext):
    """A bare generated-name resolves against `generated_videos/{name}{ext}` for each
    supported extension; both paths upload the same located path.
    """
    videos_dir = tmp_path / "generated_videos"
    videos_dir.mkdir()
    located = videos_dir / f"clip{ext}"
    located.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    monkeypatch.setattr(
        "video_generation_agent.tools.utils.video_utils.get_videos_dir",
        lambda product: str(videos_dir),
    )

    fal_new = MagicMock()
    fal_new.upload_file.return_value = f"https://fal/storage/clip{ext}"
    fal_legacy = MagicMock()
    fal_legacy.upload_file.return_value = f"https://fal/storage/clip{ext}"

    new_result = resolve_video_for_fal_sync(fal_new, "product", "clip")
    legacy_result = _legacy_resolve_media_url(
        "product", "clip", fal_legacy, lambda product: str(videos_dir)
    )

    assert fal_new.upload_file.call_args.args == (str(located),)
    assert fal_legacy.upload_file.call_args.args == (str(located),)
    assert new_result == legacy_result


def test_video_resolver_unresolvable_ref_raises_same_error_as_legacy(monkeypatch, tmp_path):
    """Unresolvable ref → identical FileNotFoundError message in both paths."""
    videos_dir = tmp_path / "generated_videos"
    videos_dir.mkdir()
    monkeypatch.setattr(
        "video_generation_agent.tools.utils.video_utils.get_videos_dir",
        lambda product: str(videos_dir),
    )

    fal = MagicMock()

    with pytest.raises(FileNotFoundError) as new_exc:
        resolve_video_for_fal_sync(fal, "product", "nope")
    with pytest.raises(FileNotFoundError) as legacy_exc:
        _legacy_resolve_media_url("product", "nope", fal, lambda product: str(videos_dir))
    assert str(new_exc.value) == str(legacy_exc.value)


# ---------------------------------------------------------------------------
# Parser equivalence
# ---------------------------------------------------------------------------


def test_parser_matches_legacy_on_well_formed_response():
    result = {"video": {"url": "https://fal/result.mp4"}}
    assert parse_fal_video_response(result) == _legacy_extract_video_url(result)
    assert parse_fal_video_response(result) == "https://fal/result.mp4"


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"video": None},
        # Empty-string `url` is legitimately returned as `""` by the legacy
        # parser (not coerced to None). Both parsers must agree on that
        # raw-return contract, and the caller's `if not output_url` branch
        # converts both `""` and None into the same RuntimeError downstream.
        {"video": {"url": ""}},
        {"video": "not-a-dict"},
        {"video": {}},
        {"other": "shape"},
    ],
)
def test_parser_malformed_response_matches_legacy(result):
    """Whatever the legacy parser returns for a malformed shape, the new parser
    must return the identical value (None or empty string).
    """
    assert parse_fal_video_response(result) == _legacy_extract_video_url(result)


# ---------------------------------------------------------------------------
# Downloader equivalence
# ---------------------------------------------------------------------------


def test_downloader_writes_same_bytes_as_legacy(monkeypatch, tmp_path):
    """Both downloaders stream chunks from the same `httpx.Client.stream` shape and
    write byte-identical files. We assert file equality, not the HTTP path.
    """
    body = b"FAKE-MP4-BYTES-" * 64

    class _StreamCtx:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield self._body[: len(self._body) // 2]
            yield self._body[len(self._body) // 2 :]

    class _ClientCtx:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url):
            assert method == "GET"
            return _StreamCtx(body)

    monkeypatch.setattr("httpx.Client", _ClientCtx)

    new_path = tmp_path / "new" / "clip.mp4"
    legacy_path = tmp_path / "legacy" / "clip.mp4"
    legacy_path.parent.mkdir()

    returned = download_fal_video("https://fal/result.mp4", str(new_path))
    _legacy_download_file("https://fal/result.mp4", str(legacy_path))

    assert new_path.read_bytes() == legacy_path.read_bytes() == body
    assert str(returned) == str(new_path)


# ---------------------------------------------------------------------------
# FAL request equivalence: full EditVideoContent.run()
# ---------------------------------------------------------------------------


def _build_tool_for_edit(product_name: str, source: str, prompt: str, refs=None):
    return EditVideoContent(
        product_name=product_name,
        name="edited_clip",
        mode=EditMode(action="edit", video_source=source, prompt=prompt, reference_images=refs),
    )


def _patch_for_run(monkeypatch, tmp_path, *, subscribe_result):
    """Wire mocks: FAL_KEY env, fal_client.SyncClient, video utility helpers."""
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    videos_dir = tmp_path / "generated_videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Patch get_videos_dir at BOTH callsites:
    # - inside EditVideoContent (used to build the output path)
    # - inside the resource resolver's function-local import
    monkeypatch.setattr(
        "video_generation_agent.tools.EditVideoContent.get_videos_dir",
        lambda product: str(videos_dir),
    )
    monkeypatch.setattr(
        "video_generation_agent.tools.utils.video_utils.get_videos_dir",
        lambda product: str(videos_dir),
    )

    # No-op artifact helpers — record calls instead.
    artifact_calls: dict[str, list[tuple]] = {
        "spritesheet": [],
        "first_frame": [],
        "last_frame": [],
        "create_image_output": [],
        "download": [],
    }
    monkeypatch.setattr(
        "video_generation_agent.tools.EditVideoContent.generate_spritesheet",
        lambda video_path, output_path: artifact_calls["spritesheet"].append((video_path, output_path)) or None,
    )
    monkeypatch.setattr(
        "video_generation_agent.tools.EditVideoContent.extract_last_frame",
        lambda video_path, output_path: artifact_calls["last_frame"].append((video_path, output_path)) or None,
    )
    monkeypatch.setattr(
        "video_generation_agent.tools.EditVideoContent.create_image_output",
        lambda path, label: artifact_calls["create_image_output"].append((path, label)) or [],
    )

    # Stub download_fal_video (don't actually fetch). Record the call.
    def fake_download(url, output_path):
        artifact_calls["download"].append((url, str(output_path)))
        return output_path

    monkeypatch.setattr(
        "video_generation_agent.tools.EditVideoContent.download_fal_video", fake_download
    )

    # Stub _extract_first_frame so cv2.VideoCapture doesn't actually open the file.
    # Patch via the class so all instances pick it up.
    monkeypatch.setattr(
        EditVideoContent,
        "_extract_first_frame",
        lambda self, video_path, output_path: artifact_calls["first_frame"].append((video_path, output_path)) or None,
    )

    # Mocked fal_client.SyncClient. Each upload_file call returns a deterministic URL.
    client = MagicMock()
    client.subscribe = MagicMock(return_value=subscribe_result)
    client.upload_file = MagicMock(side_effect=lambda path: f"https://fal/storage/{os.path.basename(path)}")
    monkeypatch.setattr("fal_client.SyncClient", MagicMock(return_value=client))

    return client, artifact_calls, str(videos_dir)


def test_run_edit_action_subscribes_with_expected_endpoint_and_args_no_refs(monkeypatch, tmp_path):
    """Edit-action without reference_images: assert (endpoint, arguments)."""
    client, _, _ = _patch_for_run(
        monkeypatch, tmp_path, subscribe_result={"video": {"url": "https://fal.media/edited.mp4"}}
    )

    tool = _build_tool_for_edit("test_product", "https://example.com/in.mp4", "Make it cinematic")
    asyncio.run(tool.run())

    call = client.subscribe.call_args
    assert call.args[0] == "fal-ai/kling-video/o3/standard/video-to-video/edit"
    assert call.kwargs["arguments"] == {
        "video_url": "https://example.com/in.mp4",
        "prompt": "Make it cinematic",
    }
    assert call.kwargs.get("with_logs") is True
    assert "image_urls" not in call.kwargs["arguments"]


def test_run_edit_action_subscribes_with_expected_endpoint_and_args_with_refs(monkeypatch, tmp_path):
    """Edit-action with reference_images: assert image_urls list preserves input order
    and resolves each ref through `resolve_video_for_fal_sync`.
    """
    client, _, _ = _patch_for_run(
        monkeypatch, tmp_path, subscribe_result={"video": {"url": "https://fal.media/edited.mp4"}}
    )

    refs = [
        "https://example.com/a.png",
        "https://example.com/b.png",
        "https://example.com/c.png",
    ]
    tool = _build_tool_for_edit("test_product", "https://example.com/in.mp4", "Make it cinematic", refs=refs)
    asyncio.run(tool.run())

    call = client.subscribe.call_args
    args = call.kwargs["arguments"]
    assert args["image_urls"] == refs  # URL refs pass through unchanged, order preserved


def test_run_raises_when_response_lacks_video_url(monkeypatch, tmp_path):
    """Existing error path stays — RuntimeError surfaced with the same message."""
    _patch_for_run(monkeypatch, tmp_path, subscribe_result={"video": {}})

    tool = _build_tool_for_edit("test_product", "https://example.com/in.mp4", "Make it cinematic")
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(tool.run())
    assert "did not include a video URL" in str(exc.value)


# ---------------------------------------------------------------------------
# Local artifact behavior equivalence
# ---------------------------------------------------------------------------


def test_run_writes_artifacts_at_expected_paths_and_calls_helpers_in_order(monkeypatch, tmp_path):
    """Output video path, thumbnail/spritesheet/last-frame call sequence, and
    final ToolOutputText shape must all be preserved post-refactor.
    """
    client, artifacts, videos_dir = _patch_for_run(
        monkeypatch, tmp_path, subscribe_result={"video": {"url": "https://fal.media/edited.mp4"}}
    )

    tool = _build_tool_for_edit("test_product", "https://example.com/in.mp4", "Make it cinematic")
    outputs = asyncio.run(tool.run())

    expected_video_path = os.path.join(videos_dir, "edited_clip.mp4")
    expected_spritesheet = os.path.join(videos_dir, "edited_clip_spritesheet.jpg")
    expected_thumbnail = os.path.join(videos_dir, "edited_clip_thumbnail.jpg")
    expected_last_frame = os.path.join(videos_dir, "edited_clip_last_frame.jpg")

    assert artifacts["download"] == [("https://fal.media/edited.mp4", expected_video_path)]
    assert artifacts["spritesheet"] == [(expected_video_path, expected_spritesheet)]
    assert artifacts["first_frame"] == [(expected_video_path, expected_thumbnail)]
    assert artifacts["last_frame"] == [(expected_video_path, expected_last_frame)]

    # Final ToolOutputText: only the final summary survives the no-op artifact
    # helpers (create_image_output returns []), so we assert its presence and shape.
    summaries = [o for o in outputs if getattr(o, "text", "").startswith("Video edit complete!")]
    assert len(summaries) == 1
    text = summaries[0].text
    assert "edited_clip.mp4" in text
    assert expected_video_path in text
