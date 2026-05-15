"""Shared HTML scaffold and validation helpers for slides."""

import os
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

# Extensions we consider valid for slide images (PPTX-friendly)
VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


def ensure_full_html(html_content: str) -> tuple[str, bool]:
    """Ensure the slide has a full HTML scaffold."""
    html_lower = html_content.lower()
    is_full_doc = "<html" in html_lower or "<!doctype" in html_lower
    if is_full_doc:
        return html_content, False

    base_css = """
    * { box-sizing: border-box; }
    html, body {
      width: 1280px;
      height: 720px;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background-color: #0f0f0f;
    }
    body {
      position: relative;
    }
    .slide-wrapper {
      width: 1280px;
      height: 720px;
      margin: 0;
      padding: 0;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      background-color: #151517;
      color: #ffffff;
    }
    .bg-grid {
      background-image: url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='0.03' fill-rule='evenodd'%3E%3Cpath d='M0 40L40 0H20L0 20M40 40V20L20 40'/%3E%3C/g%3E%3C/svg%3E");
    }
    .glass-panel {
      background: rgba(255, 255, 255, 0.03);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 24px;
    }
    .title-font {
      font-family: 'Space Grotesk', sans-serif;
    }
    .slide {
      width: 100%;
      height: 100%;
      padding: 0;
      position: relative;
      z-index: 10;
      display: flex;
      flex-direction: column;
    }
    .content-safe-area {
      width: 100%;
      max-width: 1100px;
      margin: 0 auto;
      padding: 54px 0;
      flex: 1;
      display: flex;
      flex-direction: column;
    }
    .canvas {
      width: 100%;
      height: 100%;
    }
"""
    full_html = f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet" />
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700&family=Space+Grotesk:wght@500;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="./_theme.css" />
    <style>
{base_css}
    </style>
  </head>
  <body>
    <div class="slide-wrapper bg-grid">
      <div class="slide">
        <div class="content-safe-area">
{html_content}
        </div>
      </div>
    </div>
  </body>
</html>"""
    return full_html, True


def _collect_local_image_refs(html_content: str) -> list[str]:
    """Collect img src and url() in style that look like local paths (./ or no scheme)."""
    refs = []
    # <img src="..."> and <img src='...'>
    for m in re.finditer(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html_content, re.IGNORECASE):
        refs.append(m.group(1).strip())
    # url(...) in style or style attribute
    for m in re.finditer(r'url\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)', html_content, re.IGNORECASE):
        refs.append(m.group(1).strip())
    # Keep only local-looking refs (no http/https/data:)
    local = []
    for r in refs:
        r_lower = r.lower()
        if r_lower.startswith(("http://", "https://", "data:")):
            continue
        local.append(r)
    return local


def _validate_image_refs(project_dir: Path, html_content: str) -> list[str]:
    """Check that every local image reference in HTML exists under project_dir and is a valid image."""
    errors = []
    project_dir = project_dir.resolve()
    seen = set()
    for ref in _collect_local_image_refs(html_content):
        if not ref or ref in seen:
            continue
        seen.add(ref)
        # Resolve relative to project_dir (ref may be ./assets/x or assets/x)
        normalized = ref.lstrip("/").replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        full_path = (project_dir / normalized).resolve()
        try:
            full_path.relative_to(project_dir)
        except (ValueError, TypeError):
            errors.append(f"Image path escapes project: {ref}")
            continue
        if not full_path.exists():
            errors.append(f"Image file not found: {ref} (resolved to {full_path})")
            continue
        if full_path.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
            errors.append(
                f"Image '{ref}' has unsupported extension '{full_path.suffix}'. "
                f"Use one of: {', '.join(sorted(VALID_IMAGE_EXTENSIONS))}"
            )
            continue
        # Optional: verify file is readable as image (avoid corrupt or HTML-masquerading files)
        try:
            with open(full_path, "rb") as f:
                header = f.read(32)
            if header.startswith(b"<") or header.startswith(b"<!") or b"<html" in header[:50].lower():
                errors.append(f"Image '{ref}' is not a valid image file (looks like HTML). Re-download with DownloadImage.")
        except Exception:
            pass
    return errors


def validate_html(html_content: str, project_dir: Path, used_scaffold: bool) -> dict:
    """Validate HTML layout using Playwright."""
    errors = []

    # Validate local image references (photos) exist and are valid
    errors.extend(_validate_image_refs(project_dir, html_content))

    if re.search(r"[\U0001F300-\U0001FAFF]", html_content):
        errors.append(
            "Emoji/Unicode symbols detected. Use image icons (PNG) instead of emoji."
        )

    if re.search(r"<span[^>]*class=[\"'][^\"']*\\bdot\\b[^\"']*[\"'][^>]*>\\s*</span>", html_content, flags=re.IGNORECASE):
        errors.append(
            "Detected empty .dot spans used as colored bullets. Replace with inline SVG circles or image assets to ensure PPTX rendering."
        )

    # Detect inline badges/pills inside flowing text (<p> or <li> containing sibling text nodes AND styled spans)
    # Pattern: <p ...> or <li ...> that contains both plain text AND a <span> or <code> with inline style containing background
    _inline_badge_in_text = re.compile(
        # Requires at least one text character before the badge ([^<]+) to avoid flagging badge-only paragraphs.
        r'<(?:p|li)[^>]*>[^<]+<(?:span|code|a)[^>]+style=["\'][^"\']*background[^"\']*["\'][^>]*>[^<]+</(?:span|code|a)>',
        re.IGNORECASE | re.DOTALL,
    )
    if _inline_badge_in_text.search(html_content):
        errors.append(
            "Styled badge/pill detected inline inside <p> or <li> text. "
            "Inline elements with background-color split the surrounding sentence into separate PPTX text boxes. "
            "Move the badge to its own line or container, or use plain monospace text (no background) for inline code references."
        )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        delete=False,
        encoding="utf-8",
        dir=project_dir,
    ) as f:
        f.write(html_content)
        temp_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"file://{temp_path}", wait_until="load")

            if not used_scaffold and "_theme.css" not in html_content:
                errors.append("Missing theme link: include <link rel=\"stylesheet\" href=\"./_theme.css\" />")

            body_dims = page.evaluate("""() => {
                const body = document.body;
                const slide = document.querySelector('.content-safe-area') || document.querySelector('.slide') || document.querySelector('.slide-wrapper') || body;
                const style = window.getComputedStyle(body);
                return {
                    width: parseFloat(style.width),
                    height: parseFloat(style.height),
                    scrollWidth: Math.max(body.scrollWidth, slide.scrollWidth),
                    scrollHeight: Math.max(body.scrollHeight, slide.scrollHeight)
                };
            }""")

            expected_width = 1280
            expected_height = 720

            if abs(body_dims["width"] - expected_width) > 2:
                errors.append(f"Body width must be 1280px, got {body_dims['width']:.0f}px")
            if abs(body_dims["height"] - expected_height) > 2:
                errors.append(f"Body height must be 720px, got {body_dims['height']:.0f}px")

            width_overflow = max(0, body_dims["scrollWidth"] - body_dims["width"] - 1)
            height_overflow = max(0, body_dims["scrollHeight"] - body_dims["height"] - 1)

            if width_overflow > 0:
                errors.append(f"Content overflows horizontally by {width_overflow:.0f}px")
                errors.append("  💡 Hint: Reduce content width or increase right margin")

            if height_overflow > 0:
                errors.append(f"Content overflows vertically by {height_overflow:.0f}px")
                errors.append("  💡 Hint: Reduce content height, use smaller font, or move elements up from the bottom edge.")

            # Check for descender clipping (elements too close to the bottom edge)
            descender_issues = page.evaluate("""() => {
                const body = document.body;
                const bodyRect = body.getBoundingClientRect();
                const textElements = Array.from(body.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, span'));
                const issues = [];
                for (const el of textElements) {
                    const r = el.getBoundingClientRect();
                    const distToBottom = bodyRect.bottom - r.bottom;
                    // If text is within 3px of the bottom, it's likely clipping descenders
                    if (distToBottom >= -1 && distToBottom < 3 && el.textContent.trim()) {
                        issues.push({
                            text: el.textContent.trim().substring(0, 30),
                            dist: distToBottom
                        });
                    }
                }
                return issues;
            }""")

            if descender_issues:
                for issue in descender_issues[:2]:
                    errors.append(f"Text \"{issue['text']}...\" is too close to the bottom edge ({issue['dist']:.1f}px). Descenders (like 'g', 'y', 'p') may be clipped.")
                errors.append("  💡 Hint: Move the element up by at least 5-10px for safety.")

            if width_overflow > 0 or height_overflow > 0:
                offenders = page.evaluate("""() => {
                    const body = document.body;
                    const bodyRect = body.getBoundingClientRect();
                    const nodes = Array.from(body.querySelectorAll("*"));
                    const over = [];
                    for (const el of nodes) {
                        const r = el.getBoundingClientRect();
                        const overflowRight = Math.max(0, r.right - bodyRect.right);
                        const overflowBottom = Math.max(0, r.bottom - bodyRect.bottom);
                        const overflowLeft = Math.max(0, bodyRect.left - r.left);
                        const overflowTop = Math.max(0, bodyRect.top - r.top);
                        if (overflowRight > 0 || overflowBottom > 0 || overflowLeft > 0 || overflowTop > 0) {
                            const area = Math.max(0, r.width) * Math.max(0, r.height);
                            over.push({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || "",
                                className: el.className || "",
                                overflowRight,
                                overflowBottom,
                                overflowLeft,
                                overflowTop,
                                area,
                            });
                        }
                    }
                    over.sort((a, b) => b.area - a.area);
                    return over.slice(0, 3);
                }""")
                if offenders:
                    errors.append("Top overflow offenders:")
                    for off in offenders:
                        ident = off["tag"]
                        if off["id"]:
                            ident += f"#{off['id']}"
                        if off["className"]:
                            ident += f".{str(off['className']).strip().replace(' ', '.')}"
                        errors.append(
                            f"  - {ident} (R:{off['overflowRight']:.0f}px, B:{off['overflowBottom']:.0f}px, "
                            f"L:{off['overflowLeft']:.0f}px, T:{off['overflowTop']:.0f}px)"
                        )

            unwrapped = page.evaluate("""() => {
                const divs = document.querySelectorAll('div');
                const issues = [];
                divs.forEach(div => {
                    for (const node of div.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                            const text = node.textContent.trim().substring(0, 50);
                            issues.push(text + (node.textContent.trim().length > 50 ? '...' : ''));
                        }
                    }
                });
                return issues;
            }""")

            if unwrapped:
                errors.append("Found unwrapped text in DIV elements:")
                for text in unwrapped[:3]:
                    errors.append(f"  - \"{text}\"")
                errors.append("  💡 Hint: Wrap all text in <p>, <h1>-<h6>, <ul>, or <ol> tags")

            browser.close()
    except Exception as e:
        errors.append(f"Validation error: {e}")
    finally:
        os.unlink(temp_path)

    if errors:
        return {"valid": False, "error": "\n".join(errors)}
    return {"valid": True, "error": ""}


MAIN_TEXT_MAX_CHARS = 100


def list_slide_filenames(project_dir: Path) -> list[str]:
    if not project_dir.exists():
        return []
    return sorted(p.name for p in project_dir.iterdir() if p.suffix.lower() == ".html")


def _strip_html_to_text(html: str, max_chars: int = MAIN_TEXT_MAX_CHARS) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:max_chars] + "…") if len(text) > max_chars else text
