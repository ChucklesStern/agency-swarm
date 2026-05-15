"""Create thumbnail grids from PowerPoint presentation slides."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from agency_swarm.tools import BaseTool
from pydantic import Field

# Add pptx/scripts to path for thumbnail module
PPTX_SCRIPTS_DIR = Path(__file__).parent.parent / "pptx" / "scripts"
sys.path.insert(0, str(PPTX_SCRIPTS_DIR))


class CreatePptxThumbnailGrid(BaseTool):
    """
    Create visual thumbnail grids from PowerPoint presentation slides.

    Converts all slides to images and arranges them in a large, unlabeled grid layout.
    Useful for:
    - Template analysis: quickly understand slide layouts and design patterns
    - Content review: visual overview of entire presentation
    - Quality check: verify all slides are properly formatted
    - Navigation reference: find specific slides by visual appearance

    Grid limits by column count:
    - 3 cols: max 12 slides per grid (3×4)
    - 4 cols: max 20 slides per grid (4×5)
    - 5 cols: max 30 slides per grid (5×6) [default]
    - 6 cols: max 42 slides per grid (6×7)

    For large presentations, multiple numbered grid files are created automatically.

    Requires: LibreOffice (soffice) and Poppler (pdftoppm) to be installed.
    """

    input_pptx: str = Field(
        ...,
        description="Path to the input PowerPoint file (.pptx)",
    )
    output_prefix: str = Field(
        default="thumbnails",
        description="Output prefix for image files (creates prefix.jpg or prefix-N.jpg for multiple grids)",
    )
    cols: int = Field(
        default=5,
        description="Number of columns in the grid (1-6, default 5). Auto-reduces for small decks.",
    )
    outline_placeholders: bool = Field(
        default=False,
        description="If True, outline text placeholders with red borders for visibility",
    )

    def run(self) -> str:
        """Create thumbnail grids and return list of generated files."""
        input_path = Path(self.input_pptx)

        # Validate input
        if not input_path.exists():
            return f"Error: Input file not found: {self.input_pptx}"
        if input_path.suffix.lower() != ".pptx":
            return f"Error: Input must be a PowerPoint file (.pptx), got: {input_path.suffix}"

        # Check for required external tools
        if not self._check_soffice():
            return "Error: LibreOffice (soffice) not found. Please install LibreOffice."
        if not self._check_pdftoppm():
            return "Error: pdftoppm not found. Please install Poppler (poppler-utils)."

        # Import and run thumbnail creation
        from thumbnail import (  # type: ignore[import-not-found]
            convert_to_images,
            create_grids,
            get_placeholder_regions,
        )

        prefix_path = Path(self.output_prefix)
        if prefix_path.parent == Path("."):
            prefix_path = input_path.parent / prefix_path.name
        output_path = prefix_path.with_suffix(".jpg")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Get placeholder regions if outlining is enabled
                placeholder_regions = None
                slide_dimensions = None
                if self.outline_placeholders:
                    placeholder_regions, slide_dimensions = get_placeholder_regions(
                        input_path
                    )

                # Convert slides to images
                slide_images = convert_to_images(input_path, Path(temp_dir), 100)
                if not slide_images:
                    return "Error: No slides found in presentation"

                # Validate columns after slide count is known
                cols = max(1, min(6, self.cols))
                cols = min(cols, len(slide_images))
                if cols != self.cols:
                    pass

                # Create grids
                grid_files = create_grids(
                    slide_images,
                    cols,
                    420,  # thumbnail width
                    output_path,
                    placeholder_regions,
                    slide_dimensions,
                )

                return (
                    f"Created {len(grid_files)} thumbnail grid(s):\n"
                    + "\n".join(f"  - {f}" for f in grid_files)
                )

        except Exception as e:
            return f"Error creating thumbnails: {e}"

    def _check_soffice(self) -> bool:
        """Check if LibreOffice is available."""
        try:
            kwargs = {
                "capture_output": True,
                "timeout": 15,
                "text": True,
                "input": "\n",
            }
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

            soffice_bin = "soffice.com" if os.name == "nt" else "soffice"
            subprocess.run([soffice_bin, "--version"], **kwargs)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_pdftoppm(self) -> bool:
        """Check if pdftoppm is available."""
        try:
            kwargs = {
                "capture_output": True,
                "timeout": 5,
                "stdin": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

            subprocess.run(["pdftoppm", "-v"], **kwargs)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


if __name__ == "__main__":
    # Test with a sample file if available
    test_pptx = Path(__file__).parent.parent / "files" / "test.pptx"
    if test_pptx.exists():
        tool = CreatePptxThumbnailGrid(
            input_pptx=str(test_pptx),
            output_prefix="/tmp/test_thumbnails",
        )
        print(tool.run())
    else:
        print(f"Test file not found: {test_pptx}")
        print("Tool definition is valid.")
