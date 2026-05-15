"""Download an image into a project's assets folder."""

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agency_swarm.tools import BaseTool
from pydantic import Field

from .slide_file_utils import get_project_dir


class DownloadImage(BaseTool):
    """
    Download an image from a URL into the project's assets folder.
    """

    project_name: str = Field(..., description="Name of the presentation project")
    url: str = Field(..., description="Image URL to download")
    image_name: str = Field(..., description="Desired filename (with or without extension)")

    def run(self) -> str:
        project_dir = get_project_dir(self.project_name)
        assets_dir = project_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https"):
            return "Error: URL must start with http or https."

        file_name = self._ensure_extension(self.image_name, self.url)
        output_path = assets_dir / file_name

        try:
            request = Request(self.url, headers={"User-Agent": "slides_agent/1.0"})
            with urlopen(request, timeout=30) as response:
                content = response.read()
            # Reject HTML or non-image content (e.g. error pages)
            if content.lstrip()[:100].lower().startswith((b"<!doctype", b"<html", b"< ")):
                return "Error: URL did not return an image (got HTML). Use a direct image URL or try another source."
            output_path.write_bytes(content)
            # Verify we can read it as an image (SVGs are validated separately)
            if output_path.suffix.lower() == ".svg":
                snippet = content.lstrip()[:200].lower()
                if b"<svg" not in snippet and b"<?xml" not in snippet:
                    output_path.unlink(missing_ok=True)
                    return "Error: Downloaded file is not a valid SVG. Use a direct image URL or try another source."
            else:
                try:
                    from PIL import Image
                    with Image.open(output_path) as img:
                        img.verify()
                except Exception:
                    output_path.unlink(missing_ok=True)
                    return "Error: Downloaded file is not a valid image. Use a direct image URL (e.g. .jpg, .png) or try another source."
        except Exception as exc:
            return f"Error downloading image: {exc}"

        return f"Downloaded image to: {output_path}"

    def _ensure_extension(self, image_name: str, url: str) -> str:
        if Path(image_name).suffix:
            return image_name

        url_path = urlparse(url).path
        url_ext = Path(url_path).suffix
        if url_ext:
            return image_name + url_ext

        return image_name + ".png"


if __name__ == "__main__":
    tool = DownloadImage(
        project_name="openclaw_presentation_v3",
        url="https://raw.githubusercontent.com/openclaw/openclaw/main/docs/assets/sponsors/convex.svg",
        image_name="sponsor_convex.svg"
    )
    print(tool.run())
