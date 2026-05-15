"""Tool for combining multiple videos into a single video using ffmpeg."""

import os
import subprocess
import tempfile

from pydantic import Field, field_validator

from agency_swarm import BaseTool, ToolOutputText

from .utils.video_utils import get_videos_dir, resolve_ffmpeg_executable


class CombineVideos(BaseTool):
    """Combine multiple videos into a single video using instant cut transitions (ffmpeg).
    
    Videos are saved to: mnt/{product_name}/generated_videos/
    """

    product_name: str = Field(
        ...,
        description="Name of the product these videos are for (e.g., 'Acme_Widget_Pro', 'Green_Tea_Extract'). Used to locate and save videos in product-specific folders.",
    )
    video_names: list[str] = Field(
        ...,
        description="List of video file names (without extension) to combine in order.",
    )
    name: str = Field(
        ...,
        description="The name for the combined video file (without extension)",
    )

    @field_validator("video_names")
    @classmethod
    def _validate_video_names(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("video_names must not be empty")
        if len(value) < 2:
            raise ValueError("At least 2 videos are required for combining")
        for name in value:
            if not name.strip():
                raise ValueError("Video names must not be empty")
        return value

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value

    def run(self) -> list:
        """Combine videos using ffmpeg concat demuxer."""
        videos_dir = get_videos_dir(self.product_name)

        video_paths = []
        for video_name in self.video_names:
            video_path = os.path.join(videos_dir, f"{video_name}.mp4")
            if not os.path.exists(video_path):
                raise FileNotFoundError(
                    f"Video file not found: {video_path}. "
                    f"Make sure the video exists in the {videos_dir} directory."
                )
            video_paths.append(video_path)

        output_path = os.path.join(videos_dir, f"{self.name}.mp4")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            for path in video_paths:
                abs_path = os.path.abspath(path).replace('\\', '/')
                escaped_path = abs_path.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
            concat_file = f.name

        try:
            ffmpeg_executable = resolve_ffmpeg_executable()
            cmd = [
                ffmpeg_executable,
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # copy streams without re-encoding
                '-y',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg concatenation failed: {result.stderr}")
        finally:
            try:
                os.unlink(concat_file)
            except Exception:
                pass

        lines = [f"Combined {len(self.video_names)} videos:"]
        for i, name in enumerate(self.video_names, 1):
            lines.append(f"  {i}. {name}.mp4")
        lines.append(f"\nOutput: {self.name}.mp4")
        lines.append(f"Path: {output_path}")

        return [ToolOutputText(type="text", text="\n".join(lines))]


if __name__ == "__main__":
    # Example usage
    tool = CombineVideos(
        product_name="Test_Product",
        video_names=["herbaluxe_01_hook_v2","herbaluxe_02_formula","herbaluxe_03_result_consistency_fix","herbaluxe_04_cta"],
        name="x_combine_test",
    )
    result = tool.run()
    print(result)

