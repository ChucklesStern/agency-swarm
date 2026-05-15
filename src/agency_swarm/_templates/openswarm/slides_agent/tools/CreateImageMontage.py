"""Create labeled montage images from a collection of images."""

import re
import tempfile
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING, List, Literal, Optional

from agency_swarm.tools import BaseTool
from pydantic import Field

if TYPE_CHECKING:
    from PIL import Image

# Supported image extensions (same as EnsureRasterImage)
RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
CONVERTIBLE_EXTS = {
    ".emf", ".wmf", ".emz", ".wmz",
    ".svg", ".svgz",
    ".wdp", ".jxr",
    ".heic", ".heif",
    ".pdf", ".eps", ".ps",
}
SUPPORTED_EXTS = RASTER_EXTS | CONVERTIBLE_EXTS


class CreateImageMontage(BaseTool):
    """
    Create a labeled montage image from a collection of images.

    Arranges images in a grid layout with optional labels (numbers or filenames).
    Useful for:
    - Reviewing slide images extracted from presentations
    - Comparing multiple versions of assets
    - Creating visual indexes of image collections

    Non-raster formats (SVG, EMF, etc.) are automatically converted to PNG
    before inclusion in the montage.
    """

    input_files: Optional[List[str]] = Field(
        default=None,
        description="List of image file paths (mutually exclusive with input_dir)",
    )
    input_dir: Optional[str] = Field(
        default=None,
        description="Directory containing images (mutually exclusive with input_files)",
    )
    output_file: str = Field(
        ...,
        description="Path for the output montage image",
    )
    num_col: int = Field(
        default=5,
        description="Number of columns in the grid (default 5)",
    )
    cell_width: int = Field(
        default=400,
        description="Width of each cell in pixels (default 400)",
    )
    cell_height: int = Field(
        default=225,
        description="Height of each cell in pixels (default 225)",
    )
    gap: int = Field(
        default=16,
        description="Gap between cells in pixels (default 16)",
    )
    label_mode: Literal["number", "filename", "none"] = Field(
        default="number",
        description="Label mode: 'number' (1-based index), 'filename', or 'none'",
    )

    def run(self) -> str:
        """Create the montage and return the output path."""
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageOps
        except ImportError:
            return "Error: PIL/Pillow not installed"

        # Validate inputs
        if self.input_files and self.input_dir:
            return "Error: Specify either input_files or input_dir, not both"
        if not self.input_files and not self.input_dir:
            return "Error: Must specify either input_files or input_dir"

        # Gather input files
        if self.input_files:
            input_paths = [Path(f) for f in self.input_files]
            for p in input_paths:
                if not p.exists():
                    return f"Error: File not found: {p}"
        else:
            input_dir = Path(self.input_dir)
            if not input_dir.is_dir():
                return f"Error: Directory not found: {self.input_dir}"
            # Natural sort for proper ordering (slide-1, slide-2, ..., slide-10)
            input_paths = sorted(
                [p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTS],
                key=lambda p: self._natural_key(p.name)
            )
            if not input_paths:
                return f"Error: No supported images found in {self.input_dir}"

        # Validate parameters
        if self.num_col <= 0:
            return "Error: num_col must be positive"
        if self.cell_width <= 0 or self.cell_height <= 0:
            return "Error: cell_width and cell_height must be positive"

        # Load images (converting non-raster formats as needed)
        labels = [p.name for p in input_paths]
        images = []
        placeholder = None

        with tempfile.TemporaryDirectory(prefix="montage_convert_") as tmp_dir:
            for p in input_paths:
                try:
                    img_path = self._ensure_raster(p, tmp_dir)
                    images.append(Image.open(img_path))
                except Exception:
                    pass
                    images.append(None)

        # Check we have at least one valid image
        valid_count = sum(1 for img in images if img is not None)
        if valid_count == 0:
            return "Error: No valid images to render"

        # Create placeholder for failed images
        if valid_count < len(images):
            placeholder = self._make_placeholder(
                int(min(self.cell_width, self.cell_height) * 0.6)
            )

        # Calculate grid dimensions
        cols = self.num_col
        rows = ceil(len(images) / cols)

        # Set up font
        try:
            font_size = max(12, min(36, int(self.cell_height * 0.12)))
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
            font_size = 12

        # Calculate label height
        draw_labels = self.label_mode != "none"
        label_height = 0
        if draw_labels:
            temp_img = Image.new("RGB", (10, 10))
            temp_draw = ImageDraw.Draw(temp_img)
            sample = "1" if self.label_mode == "number" else "Ag"
            bbox = temp_draw.textbbox((0, 0), sample, font=font)
            label_height = ceil(bbox[3] - bbox[1]) + 6

        row_h = self.cell_height + label_height
        canvas_w = cols * self.cell_width + (cols + 1) * self.gap
        canvas_h = rows * row_h + (rows + 1) * self.gap

        # Create canvas
        canvas = Image.new("RGB", (canvas_w, canvas_h), (242, 242, 242))
        draw = ImageDraw.Draw(canvas)

        # Place images
        for idx, img in enumerate(images):
            col = idx % cols
            row = idx // cols
            x0 = self.gap + col * (self.cell_width + self.gap)
            y0 = self.gap + row * (row_h + self.gap)

            # Prepare label
            if self.label_mode == "number":
                label = str(idx + 1)
            elif self.label_mode == "filename":
                label = labels[idx]
            else:
                label = ""

            # Get image to display
            if img is not None:
                resized = ImageOps.contain(
                    img.convert("RGBA"),
                    (self.cell_width, self.cell_height),
                    method=Image.Resampling.LANCZOS,
                )
            else:
                resized = placeholder

            # Calculate position
            paste_x = x0 + (self.cell_width - resized.width) // 2
            paste_y = y0 + (self.cell_height - resized.height) // 2

            # Paste image
            canvas.paste(
                resized,
                (paste_x, paste_y),
                mask=resized.split()[3] if resized.mode == "RGBA" else None,
            )

            # Draw border
            draw.rectangle(
                [paste_x - 1, paste_y - 1, paste_x + resized.width, paste_y + resized.height],
                outline=(160, 160, 160),
                width=1,
            )

            # Draw label
            if draw_labels and label:
                bbox = draw.textbbox((0, 0), label, font=font)
                text_w = bbox[2] - bbox[0]
                tx = x0 + (self.cell_width - text_w) // 2
                ty = y0 + self.cell_height + 3
                draw.text((tx, ty), label, font=font, fill=(0, 0, 0))

        # Save output
        output_path = Path(self.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(output_path))

        return f"Montage saved to: {output_path}\n{len(images)} images in {rows}x{cols} grid"

    def _natural_key(self, s: str) -> list:
        """Key function for natural sorting (e.g., slide2 before slide10)."""
        return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", s)]

    def _make_placeholder(self, size: int) -> "Image.Image":
        """Create a placeholder image for failed loads."""
        from PIL import Image, ImageDraw

        ph = Image.new("RGBA", (size, size), (220, 220, 220, 255))
        draw = ImageDraw.Draw(ph)
        draw.line([(0, 0), (size - 1, size - 1)], fill=(180, 0, 0, 255), width=3)
        draw.line([(size - 1, 0), (0, size - 1)], fill=(180, 0, 0, 255), width=3)
        return ph

    def _ensure_raster(self, path: Path, tmp_dir: str) -> str:
        """Ensure the image is in a raster format, converting if needed."""
        ext = path.suffix.lower()
        if ext in RASTER_EXTS:
            return str(path)

        # Use EnsureRasterImage tool logic for conversion
        from .EnsureRasterImage import EnsureRasterImage

        tool = EnsureRasterImage(input_path=str(path), output_dir=tmp_dir)
        result = tool.run()

        if result.startswith("Error"):
            raise RuntimeError(result)

        # Extract the output path from the result
        if result.startswith("Converted to:"):
            return result.replace("Converted to:", "").strip()
        return str(path)


if __name__ == "__main__":
    print("CreateImageMontage tool definition is valid.")
    print(f"Supported formats: {', '.join(sorted(SUPPORTED_EXTS))}")
