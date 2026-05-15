"""Restore HTML slides from a PPTX export snapshot."""
from agency_swarm.tools import BaseTool
from pydantic import Field

from .slide_file_utils import get_project_dir, restore_snapshot_html


class RestoreSnapshot(BaseTool):
    """
    Restore the working HTML slides from a previous PPTX export snapshot.

    Every time BuildPptxFromHtmlSlides runs it saves a self-contained snapshot
    of the slide HTML alongside the PPTX:

        my_deck.pptx
        my_deck.pptx.slides/
            1.html
            2.html
            …

    Use this tool to roll back the working slides in a project to the state
    captured in any previous export.  The tool:

    1. Reads each numbered HTML file from the snapshot directory.
    2. Extracts the inlined ``_theme.css`` back to disk so the theme is
       available for future edits.
    3. Writes the restored ``slide_01.html``, ``slide_02.html``, … files into
       the project directory, ready to work with.

    To see which exports are available, list *.pptx files in the project folder.
    """

    project_name: str = Field(
        ...,
        description="Presentation project folder name (e.g. 'my_pitch')",
    )
    pptx_filename: str = Field(
        ...,
        description=(
            "Filename of the PPTX export to restore from, e.g. 'my_deck.pptx' "
            "or 'my_deck_v2.pptx'. The file must exist in the project folder."
        ),
    )

    def run(self) -> str:
        project_dir = get_project_dir(self.project_name)
        pptx_name = self.pptx_filename if self.pptx_filename.endswith(".pptx") else f"{self.pptx_filename}.pptx"
        slides_dir = project_dir / f"{pptx_name}.slides"

        if not slides_dir.exists():
            available = sorted(p.name for p in project_dir.glob("*.pptx.slides") if p.is_dir())
            hint = (
                "\nAvailable snapshots:\n" + "\n".join(f"  {d}" for d in available)
                if available else "\nNo snapshots found in this project."
            )
            return f"Error: No snapshot found for '{pptx_name}'.{hint}"

        snapshot_files = sorted(
            [p for p in slides_dir.glob("*.html") if p.stem.isdigit()],
            key=lambda p: int(p.stem),
        )
        if not snapshot_files:
            return "Error: Snapshot directory is empty"

        pad_width = max(2, len(str(len(snapshot_files))))
        css_written = False
        restored_slides: list[str] = []

        for i, snapshot in enumerate(snapshot_files, start=1):
            html = snapshot.read_text(encoding="utf-8")
            restored_html, css_files = restore_snapshot_html(html)

            if not css_written and css_files:
                for filename, css in css_files.items():
                    (project_dir / filename).write_text(css, encoding="utf-8")
                css_written = True

            slide_name = f"slide_{i:0{pad_width}d}.html"
            (project_dir / slide_name).write_text(restored_html, encoding="utf-8")
            restored_slides.append(slide_name)

        summary = "\n".join(f"  {s}" for s in restored_slides)
        return (
            f"Restored {len(restored_slides)} slide(s) to {project_dir}:\n{summary}"
        )

if __name__ == "__main__":
    tool = RestoreSnapshot(project_name="dinosaur_presentation_v2", pptx_filename="dinosaur_presentation_v2.pptx")
    print(tool.run())