"""Extract structured text inventory from a PowerPoint presentation."""

import sys
from pathlib import Path

from agency_swarm.tools import BaseTool
from pydantic import Field

# Add pptx/scripts to path for inventory module
PPTX_SCRIPTS_DIR = Path(__file__).parent.parent / "pptx" / "scripts"
sys.path.insert(0, str(PPTX_SCRIPTS_DIR))


class ExtractPptxTextInventory(BaseTool):
    """
    Extract structured text inventory from a PowerPoint presentation.

    Returns a JSON file containing all text shapes organized by slide, with:
    - Position and dimensions (in inches)
    - Placeholder types (TITLE, BODY, SUBTITLE, etc.)
    - Paragraph formatting (bullets, alignment, fonts, colors, spacing)
    - Overflow and overlap issue detection

    Use this tool to understand the structure of a presentation before
    making text replacements, or to detect formatting issues.
    """

    input_pptx: str = Field(
        ...,
        description="Path to the input PowerPoint file (.pptx)",
    )
    output_json: str = Field(
        ...,
        description="Path where the inventory JSON will be saved",
    )
    issues_only: bool = Field(
        default=False,
        description="If True, only include shapes with overflow or overlap issues",
    )

    def run(self) -> str:
        """Extract text inventory and save to JSON."""
        import sys
        from pathlib import Path as PathLib
        
        # Add pptx/scripts to path for inventory import
        scripts_dir = PathLib(__file__).parent.parent / "pptx" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        
        from inventory import extract_text_inventory, save_inventory  # type: ignore

        input_path = Path(self.input_pptx)
        output_path = Path(self.output_json)

        # Validate input
        if not input_path.exists():
            return f"Error: Input file not found: {self.input_pptx}"
        if input_path.suffix.lower() != ".pptx":
            return f"Error: Input must be a PowerPoint file (.pptx), got: {input_path.suffix}"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract inventory
        inventory = extract_text_inventory(input_path, issues_only=self.issues_only)

        # Save to JSON
        save_inventory(inventory, output_path)

        # Generate summary
        total_slides = len(inventory)
        total_shapes = sum(len(shapes) for shapes in inventory.values())

        if self.issues_only:
            if total_shapes > 0:
                return (
                    f"Inventory saved to: {output_path}\n"
                    f"Found {total_shapes} text elements with issues across {total_slides} slides"
                )
            else:
                return f"Inventory saved to: {output_path}\nNo issues discovered"
        else:
            return (
                f"Inventory saved to: {output_path}\n"
                f"Found {total_shapes} text elements across {total_slides} slides"
            )


if __name__ == "__main__":
    # Test with a sample file if available
    import tempfile

    test_pptx = Path(__file__).parent.parent / "files" / "test.pptx"
    if test_pptx.exists():
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tool = ExtractPptxTextInventory(
                input_pptx=str(test_pptx),
                output_json=f.name,
            )
            print(tool.run())
    else:
        print(f"Test file not found: {test_pptx}")
        print("Tool definition is valid.")
