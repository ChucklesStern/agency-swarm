"""Rearrange PowerPoint slides based on a sequence of indices."""

import sys
from pathlib import Path
from typing import List, Union

from agency_swarm.tools import BaseTool
from pydantic import Field

# Add pptx/scripts to path for rearrange module
PPTX_SCRIPTS_DIR = Path(__file__).parent.parent / "pptx" / "scripts"
sys.path.insert(0, str(PPTX_SCRIPTS_DIR))


class RearrangePptxSlidesFromTemplate(BaseTool):
    """
    Build a new presentation from a template by duplicating and reordering slides.

    Takes a template PPTX and a sequence of 0-based slide indices, then creates
    a new presentation with slides in the specified order. The same slide index
    can appear multiple times to duplicate that slide.

    Example: slide_sequence=[0, 5, 5, 12, 3] creates a 5-slide deck using
    slides 0, 5 (twice), 12, and 3 from the template.
    """

    template_pptx: str = Field(
        ...,
        description="Path to the template PowerPoint file (.pptx)",
    )
    output_pptx: str = Field(
        ...,
        description="Path where the rearranged presentation will be saved",
    )
    slide_sequence: Union[str, List[int]] = Field(
        ...,
        description="Comma-separated string or list of 0-based slide indices (e.g., '0,5,5,12,3' or [0,5,5,12,3])",
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "If False, return an error when the output PPTX already exists. "
            "If True, overwrite the existing file."
        ),
    )

    def run(self) -> str:
        """Rearrange slides and save the new presentation."""
        import sys
        from pathlib import Path as PathLib
        
        # Add pptx/scripts to path for rearrange import
        scripts_dir = PathLib(__file__).parent.parent / "pptx" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        
        from rearrange import rearrange_presentation  # type: ignore

        template_path = Path(self.template_pptx)
        output_path = Path(self.output_pptx)

        # Validate template exists
        if not template_path.exists():
            return f"Error: Template file not found: {self.template_pptx}"
        if template_path.suffix.lower() != ".pptx":
            return f"Error: Template must be a PowerPoint file (.pptx), got: {template_path.suffix}"

        # Parse slide sequence
        if isinstance(self.slide_sequence, str):
            try:
                sequence = [int(x.strip()) for x in self.slide_sequence.split(",")]
            except ValueError:
                return "Error: Invalid sequence format. Use comma-separated integers (e.g., '0,5,5,12,3')"
        else:
            sequence = list(self.slide_sequence)

        if not sequence:
            return "Error: Slide sequence cannot be empty"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and not self.overwrite:
            return (
                "Error: Output file already exists. "
                "Set overwrite=True to replace it or add a postfix to the filename."
            )

        # Rearrange presentation
        try:
            rearrange_presentation(template_path, output_path, sequence)
            return (
                f"Presentation saved to: {output_path}\n"
                f"Created {len(sequence)} slides from template"
            )
        except ValueError as e:
            return f"Error: {e}"


if __name__ == "__main__":
    # Test with a sample file if available
    import tempfile

    test_pptx = Path(__file__).parent.parent / "files" / "test.pptx"
    if test_pptx.exists():
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            tool = RearrangePptxSlidesFromTemplate(
                template_pptx=str(test_pptx),
                output_pptx=f.name,
                slide_sequence="0,0,0",  # Duplicate first slide 3 times
            )
            print(tool.run())
    else:
        print(f"Test file not found: {test_pptx}")
        print("Tool definition is valid.")
