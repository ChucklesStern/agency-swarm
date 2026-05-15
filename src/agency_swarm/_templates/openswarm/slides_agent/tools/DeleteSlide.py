"""Delete HTML slide files from a presentation project."""

from .slide_file_utils import get_project_dir, list_slide_files

from agency_swarm.tools import BaseTool
from pydantic import Field


class DeleteSlide(BaseTool):
    """
    Delete an HTML slide file from a presentation project.
    
    Use this tool to remove slides that are no longer needed.
    """

    project_name: str = Field(
        ...,
        description="Name of the presentation project"
    )
    slide_name: str | None = Field(
        default=None,
        description="Name of the slide file to delete (e.g., 'slide_01' - .html extension added automatically)"
    )
    slide_indexes: list[int] | None = Field(
        default=None,
        description="1-based slide indexes to delete (uses project slide order)",
    )
    file_prefix: str = Field(
        default="slide",
        description="Slide filename prefix when deleting by index",
    )

    def run(self):
        """Delete the specified slide file."""
        project_dir = get_project_dir(self.project_name)
        
        if not project_dir.exists():
            return f"❌ Project '{self.project_name}' does not exist at {project_dir}"
        
        if self.slide_indexes:
            slides = list_slide_files(project_dir, self.file_prefix)
            missing = [idx for idx in self.slide_indexes if idx < 1 or idx > len(slides)]
            if missing:
                return f"❌ Slide indexes out of range: {missing}"
            deleted = []
            for idx in sorted(self.slide_indexes, reverse=True):
                slide_path = slides[idx - 1].path
                if slide_path.exists():
                    slide_path.unlink()
                    deleted.append(slide_path)
            if not deleted:
                return "❌ No slides deleted."
            return "✅ Deleted slides:\n" + "\n".join(f"- {path}" for path in deleted)

        if not self.slide_name:
            return "Error: Provide slide_name or slide_indexes to delete slides."

        slide_name = self.slide_name if self.slide_name.endswith('.html') else f"{self.slide_name}.html"
        slide_path = project_dir / slide_name

        if not slide_path.exists():
            return f"❌ Slide '{slide_name}' does not exist in project '{self.project_name}'"

        try:
            slide_path.unlink()
            return f"✅ Successfully deleted slide: {slide_path}"

        except Exception as e:
            return f"Error deleting slide: {e}"


if __name__ == "__main__":
    # Test (will fail if file doesn't exist, which is expected)
    tool = DeleteSlide(
        project_name="test_project",
        slide_name="slide_01"
    )
    print(tool.run())
