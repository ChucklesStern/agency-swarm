"""Create and edit presentation theme CSS files."""

from agency_swarm.tools import BaseTool
from pydantic import Field

from .slide_file_utils import get_project_dir


class ManageTheme(BaseTool):
    """
    Create or edit the theme CSS file for a presentation project.
    
    The theme file is saved as `_theme.css` in the project folder and defines:
    - Color palette (CSS variables)
    - Typography (fonts, sizes, line heights)
    - Base styles for common elements
    - Reusable classes (cards, labels, etc.)
    
    Usage:
    - First time: Creates new theme file
    - Subsequent calls: Overwrites existing theme
    """

    project_name: str = Field(
        ...,
        description="Name of the presentation project"
    )
    css_content: str = Field(
        ...,
        description="Complete CSS content for the theme file"
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "If False, return an error when the theme already exists. "
            "If True, overwrite the existing theme file."
        ),
    )

    def run(self):
        """Create or update theme file."""
        project_dir = get_project_dir(self.project_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        
        theme_path = project_dir / "_theme.css"
        if theme_path.exists() and not self.overwrite:
            return (
                f"❌ Theme already exists: {theme_path}. "
                "Set overwrite=True to replace it or add a postfix to the filename."
            )
        operation = "updated" if theme_path.exists() else "created"
        
        css_content, injected = self._ensure_canvas_rules(self.css_content)

        try:
            theme_path.write_text(css_content, encoding='utf-8')
            file_size = theme_path.stat().st_size

            note = " (added base canvas rules)" if injected else ""
            return f"✅ Successfully {operation} theme: {theme_path}{note}\nSize: {file_size} bytes"
        
        except Exception as e:
            return f"Error writing theme: {e}"

    def _ensure_canvas_rules(self, css_content: str) -> tuple[str, bool]:
        """Ensure the theme defines the required slide canvas size."""
        import re

        selector_pattern = r"(html\s*,\s*body|body|html)\s*\{[^}]*\}"
        width_pattern = r"width\s*:\s*1280px"
        height_pattern = r"height\s*:\s*720px"

        has_width = False
        has_height = False

        for match in re.finditer(selector_pattern, css_content, flags=re.IGNORECASE | re.DOTALL):
            block = match.group(0)
            if re.search(width_pattern, block, flags=re.IGNORECASE):
                has_width = True
            if re.search(height_pattern, block, flags=re.IGNORECASE):
                has_height = True

        if has_width and has_height:
            return css_content, False

        canvas_rules = (
            "html, body {\n"
            "  width: 1280px;\n"
            "  height: 720px;\n"
            "  margin: 0;\n"
            "  padding: 0;\n"
            "  overflow: hidden;\n"
            "}\n\n"
        )
        return canvas_rules + css_content, True


if __name__ == "__main__":
    from pathlib import Path
    import sys

    tools_root = Path(__file__).resolve().parents[1]
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))

    from tools.deck_utils import load_theme_css

    tool = ManageTheme(
        project_name="slides_agent_test_deck",
        css_content=load_theme_css(),
    )
    print(tool.run())
