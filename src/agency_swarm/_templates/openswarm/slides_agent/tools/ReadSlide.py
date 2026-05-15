"""Read the raw HTML of a slide file."""

from __future__ import annotations

from agency_swarm.tools import BaseTool
from pydantic import Field

from .slide_file_utils import get_project_dir


class ReadSlide(BaseTool):
    """Return the raw HTML source of a slide so the agent can inspect its current design and content."""

    project_name: str = Field(..., description="Project folder name")
    slide_name: str = Field(
        ...,
        description="Slide filename (e.g. 'slide_01_title' or 'slide_01_title.html')",
    )

    def run(self) -> str:
        project_dir = get_project_dir(self.project_name)
        slide_name = self.slide_name if self.slide_name.endswith(".html") else f"{self.slide_name}.html"
        slide_path = project_dir / slide_name
        if not slide_path.exists():
            return f"Error: slide not found at {slide_path}"
        return slide_path.read_text(encoding="utf-8")
