"""Render a single slide to image and load it as attachment."""

import asyncio
import inspect
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from agency_swarm.tools import BaseTool, LoadFileAttachment
from pydantic import Field

PPTX_SCRIPTS_DIR = Path(__file__).parent.parent / "pptx" / "scripts"
sys.path.insert(0, str(PPTX_SCRIPTS_DIR))

_SLIDE_VIEWPORT = {"width": 1280, "height": 720}


class CheckSlide(BaseTool):
    """
    Render a single slide (HTML or PPTX) to an image and return a file attachment.

    Allows you to see the slide so you can inspect it for spacing, alignment, and other issues.
    """

    slide_path: str = Field(
        ...,
        description="Path to a single HTML slide or a PPTX file",
    )
    output_image_path: Optional[str] = Field(
        default=None,
        description="Optional output image path (.jpg). Defaults next to slide.",
    )
    layout: str = Field(
        default="LAYOUT_16x9_1280",
        description="Layout for HTML slides: LAYOUT_16x9_1280 or LAYOUT_16x9_1920",
    )
    slide_index: int = Field(
        default=1,
        description="1-based slide index when rendering a PPTX with multiple slides",
    )

    def run(self):
        input_path = Path(self.slide_path)
        if not input_path.exists():
            return f"Error: Slide not found: {self.slide_path}"

        if input_path.suffix.lower() == ".pptx":
            if not self._check_soffice():
                return "Error: LibreOffice (soffice) not found. Please install LibreOffice."
            if not self._check_pdftoppm():
                return "Error: pdftoppm not found. Please install Poppler (poppler-utils)."

        try:
            if input_path.suffix.lower() == ".html":
                image_path = self._screenshot_html(input_path)
            elif input_path.suffix.lower() == ".pptx":
                image_path = self._render_pptx_slide(input_path, input_path)
            else:
                return "Error: slide_path must be a .html or .pptx file."

            attachment = LoadFileAttachment(path=str(image_path))
            return self._run_attachment(attachment)
        except Exception as exc:
            return f"Error checking slide: {exc}"

    def _screenshot_html(self, html_path: Path) -> Path:
        """Direct Playwright screenshot — fast, no PPTX/PDF round-trip."""
        from playwright.sync_api import sync_playwright
        from PIL import Image

        output_path = self._resolve_output_path(html_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport=_SLIDE_VIEWPORT)
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=20_000)
            page.wait_for_timeout(800)
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            page.screenshot(
                path=str(tmp),
                clip={"x": 0, "y": 0, **_SLIDE_VIEWPORT},
                type="jpeg",
                quality=80,
            )
            browser.close()

        img = Image.open(tmp)
        new_size = (int(img.width * 0.75), int(img.height * 0.75))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        img.save(output_path, "JPEG", quality=75, optimize=True)
        return output_path

    def _build_temp_pptx(self, html_path: Path) -> Path:
        if __package__ is None:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from tools.BuildPptxFromHtmlSlides import BuildPptxFromHtmlSlides
        else:
            from .BuildPptxFromHtmlSlides import BuildPptxFromHtmlSlides

        temp_dir = Path(tempfile.mkdtemp(prefix="slide_check_"))
        output_pptx = temp_dir / "slide_check.pptx"
        tool = BuildPptxFromHtmlSlides(
            html_files=[str(html_path)],
            output_pptx=str(output_pptx),
            layout=self.layout,
        )
        result = tool.run()
        if isinstance(result, str) and result.lower().startswith("error"):
            raise RuntimeError(result)
        return output_pptx

    def _render_pptx_slide(self, pptx_path: Path, source_path: Path) -> Path:
        import sys
        from pathlib import Path as PathLib
        
        # Add pptx/scripts to path for thumbnail import
        scripts_dir = PathLib(__file__).parent.parent / "pptx" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        
        from thumbnail import convert_to_images  # type: ignore
        from PIL import Image

        output_path = self._resolve_output_path(source_path)
        with tempfile.TemporaryDirectory() as temp_dir:
            slide_images = convert_to_images(pptx_path, Path(temp_dir), 120)
            if not slide_images:
                raise RuntimeError("No slides found in presentation")

            if self.slide_index < 1 or self.slide_index > len(slide_images):
                raise RuntimeError(
                    f"slide_index out of range (1-{len(slide_images)}): {self.slide_index}"
                )

            selected = Path(slide_images[self.slide_index - 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Compress image to reduce token usage
            img = Image.open(selected)
            # Resize to 75% of original (reduces token usage significantly)
            new_size = (int(img.width * 0.75), int(img.height * 0.75))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            # Save with moderate JPEG quality
            img.save(output_path, 'JPEG', quality=75, optimize=True)
            
            return output_path

    def _resolve_output_path(self, pptx_path: Path) -> Path:
        if self.output_image_path:
            return Path(self.output_image_path)

        stem = pptx_path.stem
        if pptx_path.suffix.lower() == ".pptx":
            return pptx_path.with_name(f"{stem}_check.jpg")
        return pptx_path.with_name(f"{stem}_check.jpg")

    def _check_soffice(self) -> bool:
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

    def _run_attachment(self, attachment):
        result = attachment.run()
        if not inspect.isawaitable(result):
            return result

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(result)

        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(result)
        finally:
            new_loop.close()


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    test_pptx = repo_root / "mnt/claude_cowork_deck/presentations/claude_cowork_deck_v5_rendered.pptx"
    if test_pptx.exists():
        tool = CheckSlide(slide_path="mnt/claude_cowork_deck/presentations/claude_cowork_deck_v5_rendered.pptx", slide_index=3, output_image_path="mnt/claude_cowork_deck/presentations/_v5_prev3.jpg")
        print(tool.run())
    else:
        print(f"Test file not found: {test_pptx}")
        print("Tool definition is valid.")
