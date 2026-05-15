"""Convert vector/container image formats to raster PNG."""

import gzip
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from agency_swarm.tools import BaseTool
from pydantic import Field

# Supported file extensions
RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
CONVERTIBLE_EXTS = {
    ".emf", ".wmf", ".emz", ".wmz",  # Windows metafiles
    ".svg", ".svgz",  # SVG
    ".wdp", ".jxr",  # JPEG XR
    ".heic", ".heif",  # HEIF
    ".pdf", ".eps", ".ps",  # Page description formats
}
SUPPORTED_EXTS = RASTER_EXTS | CONVERTIBLE_EXTS


class EnsureRasterImage(BaseTool):
    """
    Convert vector or container image formats to raster PNG.

    Supports conversion of:
    - EMF/WMF/EMZ/WMZ (Windows metafiles) via Inkscape
    - SVG/SVGZ via Inkscape
    - WDP/JXR (JPEG XR) via JxrDecApp + ImageMagick
    - HEIC/HEIF via heif-convert
    - PDF/EPS/PS (first page) via Ghostscript

    Already-raster formats (PNG, JPG, etc.) are returned as-is.

    This is useful for preparing images extracted from PowerPoint files
    for preview or re-embedding, as PPTX files may contain vector formats
    that need rasterization.

    Required external tools (depending on input format):
    - Inkscape: SVG/EMF/WMF rasterization
    - ImageMagick: format bridging
    - Ghostscript: PDF/EPS/PS rasterization
    - libheif-examples: HEIC/HEIF conversion
    - jxr-tools: JPEG XR conversion
    """

    input_path: str = Field(
        ...,
        description="Path to the input image file",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Directory for output PNG (defaults to same directory as input)",
    )
    dpi: Optional[int] = Field(
        default=None,
        description="Optional rasterization DPI for vector formats (e.g., 192 for crisp icons)",
    )

    def run(self) -> str:
        """Convert image to PNG if needed and return the output path."""
        input_path = Path(self.input_path)

        # Validate input
        if not input_path.exists():
            return f"Error: Input file not found: {self.input_path}"

        ext_lower = input_path.suffix.lower()
        if ext_lower not in SUPPORTED_EXTS:
            return f"Error: Unsupported format '{ext_lower}'. Supported: {', '.join(sorted(SUPPORTED_EXTS))}"

        # Determine output directory and path
        out_dir = Path(self.output_dir) if self.output_dir else input_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (input_path.stem + ".png")

        # Already raster - return as-is
        if ext_lower in RASTER_EXTS:
            return f"Already raster format: {input_path}"

        try:
            result_path = self._convert(input_path, out_path, ext_lower, self.dpi)
            return f"Converted to: {result_path}"
        except Exception as e:
            return f"Error converting {input_path}: {e}"

    def _convert(self, input_path: Path, out_path: Path, ext: str, dpi: Optional[int]) -> str:
        """Convert the file and return the output path."""
        out_dir = out_path.parent
        dpi_arg = [f"--export-dpi={dpi}"] if dpi else []

        # EMF/WMF via Inkscape
        if ext in (".emf", ".wmf"):
            self._run_cmd(["inkscape", str(input_path), "-o", str(out_path), *dpi_arg])
            return str(out_path)

        # EMZ/WMZ - decompress then convert
        if ext in (".emz", ".wmz"):
            decompressed = out_dir / (input_path.stem + (".emf" if ext == ".emz" else ".wmf"))
            with gzip.open(input_path, "rb") as zin, open(decompressed, "wb") as zout:
                zout.write(zin.read())
            self._run_cmd(["inkscape", str(decompressed), "-o", str(out_path), *dpi_arg])
            decompressed.unlink()  # Clean up
            return str(out_path)

        # SVG/SVGZ via Inkscape
        if ext in (".svg", ".svgz"):
            self._run_cmd(["inkscape", str(input_path), "-o", str(out_path), *dpi_arg])
            return str(out_path)

        # JPEG XR via JxrDecApp + ImageMagick
        if ext in (".wdp", ".jxr"):
            tmp_tiff = out_dir / (input_path.stem + ".tiff")
            self._run_cmd(["JxrDecApp", "-i", str(input_path), "-o", str(tmp_tiff)])
            self._imagemagick_convert(str(tmp_tiff), str(out_path))
            tmp_tiff.unlink()  # Clean up
            return str(out_path)

        # HEIC/HEIF via heif-convert
        if ext in (".heic", ".heif"):
            heif_convert = shutil.which("heif-convert") or "heif-convert"
            self._run_cmd([heif_convert, str(input_path), str(out_path)])
            return str(out_path)

        # PDF/EPS/PS via Ghostscript (first page only)
        if ext in (".pdf", ".eps", ".ps"):
            gs = shutil.which("gs") or "gs"
            dpi_value = str(dpi or 200)
            self._run_cmd([
                gs, "-dSAFER", "-dBATCH", "-dNOPAUSE",
                "-sDEVICE=pngalpha",
                "-dFirstPage=1", "-dLastPage=1",
                f"-r{dpi_value}",
                "-o", str(out_path),
                str(input_path),
            ])
            return str(out_path)

        raise ValueError(f"No conversion handler for {ext}")

    def _run_cmd(self, cmd: list) -> None:
        """Run a command and raise on failure."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")

    def _imagemagick_convert(self, src: str, dst: str) -> None:
        """Convert using ImageMagick."""
        binary = shutil.which("magick") or "convert"
        self._run_cmd([binary, src, dst])


if __name__ == "__main__":
    print("EnsureRasterImage tool definition is valid.")
    print(f"Supported formats: {', '.join(sorted(SUPPORTED_EXTS))}")
