"""Render a slide to an image attachment."""

from __future__ import annotations

from agency_swarm.tools import BaseTool
from pydantic import Field

from .CheckSlide import CheckSlide
from .slide_file_utils import get_project_dir, list_slide_files


class SlideScreenshot(BaseTool):
    """
    Render a single HTML slide from a project to an image attachment.
    Cannot be ran in parallel with other tools.
    """

    project_name: str = Field(
        ...,
        description="Project folder name",
    )
    slide_name: str = Field(
        ...,
        description="Slide filename (e.g., 'slide_01_title' or 'slide_01_title.html')",
    )
    slide_index: int | None = Field(
        default=None,
        description="Optional 1-based slide index to render using project slide order",
    )
    output_image_path: str | None = Field(
        default=None,
        description="Optional output image path (.jpg)",
    )
    layout: str = Field(
        default="LAYOUT_16x9_1280",
        description="Layout for HTML slides",
    )

    class ToolConfig:
        one_call_at_a_time: bool = True

    def run(self):
        project_dir = get_project_dir(self.project_name)
        slide_path = None
        if self.slide_index is not None:
            slides = list_slide_files(project_dir)
            if self.slide_index < 1 or self.slide_index > len(slides):
                return f"Error: slide_index out of range (1-{len(slides)})"
            slide_path = slides[self.slide_index - 1].path
        else:
            slide_name = self.slide_name if self.slide_name.endswith(".html") else f"{self.slide_name}.html"
            slide_path = project_dir / slide_name
        if not slide_path.exists():
            return f"Error: Slide not found at {slide_path}"

        tool = CheckSlide(
            slide_path=str(slide_path),
            output_image_path=self.output_image_path,
            layout=self.layout,
        )
        return tool.run()


if __name__ == "__main__":
    tool = SlideScreenshot(project_name="claude_cowork_deck", slide_name="slide_01_title", output_image_path="test.jpg")
    print(tool.run())
