"""Apply text replacements to a PowerPoint presentation."""

import sys
from pathlib import Path

from agency_swarm.tools import BaseTool
from pydantic import Field

# Add pptx/scripts to path for replace module
PPTX_SCRIPTS_DIR = Path(__file__).parent.parent / "pptx" / "scripts"
sys.path.insert(0, str(PPTX_SCRIPTS_DIR))


class ApplyPptxTextReplacements(BaseTool):
    """
    Apply text replacements to shapes in a PowerPoint presentation.

    Takes a PPTX file and a JSON file containing replacement paragraphs,
    then applies the replacements while preserving formatting. All text
    shapes identified in the inventory will have their text cleared unless
    "paragraphs" is specified for that shape in the replacements JSON.

    The replacements JSON should follow the structure from ExtractPptxTextInventory:
    {
        "slide-0": {
            "shape-0": {
                "paragraphs": [
                    {"text": "New title", "bold": true, "alignment": "CENTER"},
                    {"text": "Bullet point", "bullet": true, "level": 0}
                ]
            }
        }
    }

    The tool validates that:
    - All referenced shapes exist in the presentation
    - Text overflow does not worsen after replacements
    - No bullet formatting warnings are triggered
    """

    input_pptx: str = Field(
        ...,
        description="Path to the input PowerPoint file (.pptx)",
    )
    replacements_json: str = Field(
        ...,
        description="Path to the JSON file containing replacement paragraphs",
    )
    output_pptx: str = Field(
        ...,
        description="Path where the updated presentation will be saved",
    )

    def run(self) -> str:
        """Apply replacements and save the updated presentation."""
        import sys
        from pathlib import Path as PathLib
        
        # Add pptx/scripts to path for replace import
        scripts_dir = PathLib(__file__).parent.parent / "pptx" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        
        from replace import apply_replacements  # type: ignore

        input_path = Path(self.input_pptx)
        json_path = Path(self.replacements_json)
        output_path = Path(self.output_pptx)

        # Validate inputs
        if not input_path.exists():
            return f"Error: Input file not found: {self.input_pptx}"
        if input_path.suffix.lower() != ".pptx":
            return f"Error: Input must be a PowerPoint file (.pptx), got: {input_path.suffix}"
        if not json_path.exists():
            return f"Error: Replacements JSON not found: {self.replacements_json}"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Apply replacements
        try:
            apply_replacements(str(input_path), str(json_path), str(output_path))
            return f"Presentation saved to: {output_path}\nReplacements applied successfully"
        except ValueError as e:
            return f"Error: {e}"


if __name__ == "__main__":
    print("ApplyPptxTextReplacements tool definition is valid.")
    print("Requires input PPTX and replacements JSON to test.")
