"""Tool for editing video content via fal.ai models."""

import asyncio
import logging
import os
import re
from typing import Annotated, Literal, Optional, Union

import cv2
import fal_client
from dotenv import load_dotenv
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field, field_validator
from shared_tools.fal_adapter import (
    download_fal_video,
    parse_fal_video_response,
    resolve_video_for_fal_sync,
)
from shared_tools.model_availability import video_model_availability_message

from agency_swarm import BaseTool, ToolOutputText

from .utils.video_utils import (
    create_image_output,
    extract_last_frame,
    generate_spritesheet,
    get_gemini_client,
    get_openai_client,
    get_videos_dir,
    save_veo_video_with_metadata,
    save_video_with_metadata,
)

_VEO_MODEL = "veo-3.1-generate-preview"

logger = logging.getLogger(__name__)


def _ensure_not_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


class EditMode(BaseModel):
    action: Literal["edit"]
    video_source: str = Field(
        ...,
        description="Source video path or HTTP/HTTPS URL.",
    )
    prompt: str = Field(
        ...,
        description="Editing prompt.",
    )
    reference_images: Optional[list[str]] = Field(
        default=None,
        description="Optional reference image paths or URLs.",
    )

    @field_validator("video_source")
    @classmethod
    def _video_source_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value, "video_source")

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if re.match(r"^\[.*\]", value) or re.match(r"^\[.*?\]\s+.+", value):
            raise ValueError(
                "PROMPT CANNOT CONTAIN VARIABLES. Rewrite the full prompt from scratch — "
                "this tool is stateless and does not retain prior context."
            )
        return _ensure_not_blank(value, "prompt")


class RemixMode(BaseModel):
    action: Literal["remix"]
    video_id: str = Field(
        ...,
        description="Sora video ID to remix.",
    )
    prompt: str = Field(
        ...,
        description="Remix prompt.",
    )

    @field_validator("video_id")
    @classmethod
    def _video_id_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value, "video_id")

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if re.match(r"^\[.*\]", value) or re.match(r"^\[.*?\]\s+.+", value):
            raise ValueError(
                "PROMPT CANNOT CONTAIN VARIABLES. Rewrite the full prompt from scratch — "
                "this tool is stateless and does not retain prior context."
            )
        return _ensure_not_blank(value, "prompt")


class ExtendMode(BaseModel):
    action: Literal["extend"]
    veo_video_ref: str = Field(
        ...,
        description=(
            "Veo video reference from a previous Veo generation "
            "(e.g., 'files/abc123' or a Veo download URL)."
        ),
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Optional extension prompt.",
    )

    @field_validator("veo_video_ref")
    @classmethod
    def _veo_video_ref_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value, "veo_video_ref")

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if re.match(r"^\[.*\]", value) or re.match(r"^\[.*?\]\s+.+", value):
            raise ValueError(
                "PROMPT CANNOT CONTAIN VARIABLES. Rewrite the full prompt from scratch — "
                "this tool is stateless and does not retain prior context."
            )
        return _ensure_not_blank(value, "prompt")


EditModeUnion = Annotated[
    Union[EditMode, RemixMode, ExtendMode],
    Field(discriminator="action"),
]


class EditVideoContent(BaseTool):
    """
    Edit video content via fal.ai video-to-video models.

    Videos are saved to: mnt/{product_name}/generated_videos/
    """

    product_name: str = Field(
        ...,
        description="Name of the product this video is for. Used to organize files into product-specific folders.",
    )
    name: str = Field(
        ...,
        description="The name for the edited video file (without extension)",
    )
    mode: Union[EditMode, RemixMode, ExtendMode] = Field(
        ...,
        description=(
            "Action-specific inputs. Use the 'action' field to select which "
            "mode shape is required."
        ),
    )

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value, "name")

    async def run(self) -> list:
        load_dotenv(override=True)
        if self.mode.action == "remix":
            return await self._run_remix(self.mode)
        if self.mode.action == "extend":
            return await self._run_extend(self.mode)

        api_key = os.getenv("FAL_KEY")
        if not api_key:
            raise ValueError(
                video_model_availability_message(
                    self,
                    failed_requirement="FAL_KEY is not set. fal.ai video editing requires the fal.ai add-on key.",
                )
            )
        fal = fal_client.SyncClient(key=api_key)

        endpoint = self._resolve_endpoint(self.mode.action)
        video_url = resolve_video_for_fal_sync(fal, self.product_name, self.mode.video_source)
        arguments = {"video_url": video_url}

        arguments["prompt"] = self.mode.prompt
        if self.mode.reference_images:
            arguments["image_urls"] = [
                resolve_video_for_fal_sync(fal, self.product_name, ref)
                for ref in self.mode.reference_images
            ]

        result = fal.subscribe(endpoint, arguments=arguments, with_logs=True)
        output_url = parse_fal_video_response(result)

        if not output_url:
            raise RuntimeError("fal.ai response did not include a video URL")

        videos_dir = get_videos_dir(self.product_name)
        output_path = os.path.join(videos_dir, f"{self.name}.mp4")
        download_fal_video(output_url, output_path)

        output = []

        spritesheet_path = os.path.join(videos_dir, f"{self.name}_spritesheet.jpg")
        spritesheet = generate_spritesheet(output_path, spritesheet_path)
        if spritesheet:
            output.extend(create_image_output(spritesheet_path, f"{self.name}_spritesheet.jpg"))

        thumbnail_path = os.path.join(videos_dir, f"{self.name}_thumbnail.jpg")
        thumbnail = self._extract_first_frame(output_path, thumbnail_path)
        if thumbnail:
            output.extend(create_image_output(thumbnail_path, f"{self.name}_thumbnail.jpg"))

        last_frame_path = os.path.join(videos_dir, f"{self.name}_last_frame.jpg")
        last_frame = extract_last_frame(output_path, last_frame_path)
        if last_frame:
            output.extend(create_image_output(last_frame_path, f"{self.name}_last_frame.jpg"))

        output.append(
            ToolOutputText(
                type="text",
                text=f"Video edit complete!\nSaved to: `{self.name}.mp4`\nPath: {output_path}",
            )
        )

        return output

    async def _run_remix(self, payload: RemixMode) -> list:
        client = get_openai_client(tool=self)
        loop = asyncio.get_event_loop()

        video = await loop.run_in_executor(
            None,
            lambda: client.videos.remix(video_id=payload.video_id, prompt=payload.prompt),
        )
        video = await loop.run_in_executor(None, lambda: client.videos.poll(video.id))
        return save_video_with_metadata(client, video.id, self.name, self.product_name)

    async def _run_extend(self, payload: ExtendMode) -> list:
        client = get_gemini_client()
        loop = asyncio.get_event_loop()

        if payload.veo_video_ref.startswith("http://") or payload.veo_video_ref.startswith(
            "https://"
        ):
            video_uri = payload.veo_video_ref
        else:
            video_file = await loop.run_in_executor(
                None,
                lambda: client.files.get(name=payload.veo_video_ref),
            )
            video_uri = getattr(video_file, "uri", None) or getattr(
                video_file, "download_uri", None
            )
            if not video_uri:
                raise ValueError(
                    "Veo file reference did not include a usable URI. "
                    "Use the veo_video_uri value from the reference JSON."
                )

        config = types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=8,
            resolution="720p",
        )

        request_kwargs = {
            "model": _VEO_MODEL,
            "video": types.Video(uri=video_uri),
            "config": config,
        }
        if payload.prompt:
            request_kwargs["prompt"] = payload.prompt

        operation = await loop.run_in_executor(
            None,
            lambda: client.models.generate_videos(**request_kwargs),
        )

        while not operation.done:
            await asyncio.sleep(10)
            operation = await loop.run_in_executor(
                None,
                lambda: client.operations.get(operation),
            )

        generated_video = operation.response.generated_videos[0]
        return save_veo_video_with_metadata(
            client,
            generated_video.video,
            self.name,
            self.product_name,
        )

    def _resolve_endpoint(self, action: str) -> str:
        if action == "edit":
            return "fal-ai/kling-video/o3/standard/video-to-video/edit"
        raise ValueError(f"Unsupported fal.ai action: {action}")

    def _extract_first_frame(self, video_path: str, output_path: str):
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        thumbnail_image = Image.fromarray(frame_rgb)
        thumbnail_image.save(output_path)

        return thumbnail_image

if __name__ == "__main__":
    tool = EditVideoContent(
        product_name="Test_Product",
        name="test_video_edit",
        mode=EditMode(
            action="edit",
            video_source="test_video",
            prompt="Replace the dog with a fox",
        ),
    )
    try:
        result = asyncio.run(tool.run())
        print(result)
    except Exception as exc:
        print(f"Video editing failed: {exc}")
