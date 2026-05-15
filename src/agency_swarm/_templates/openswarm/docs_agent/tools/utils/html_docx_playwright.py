import tempfile
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import subprocess
from .html_docx_page import _extract_page_geometry_pt

_PT_TO_PX = 96.0 / 72.0

# Elements that must never be split across a page boundary.
_UNSPLITTABLE_SELECTORS = "table, img, figure, blockquote, pre, svg"

# CSS applied to the inserted page-break div.
_PB_STYLE = "page-break-before:always;break-before:page;margin:0;padding:0;height:0;"

# Block-level tags whose children can directly receive a page-break sibling.
_BLOCK_PARENTS = frozenset(["BODY", "DIV", "TD", "TH", "SECTION", "ARTICLE", "MAIN"])


def auto_page_breaks(html_content: str) -> str:
    """Insert page-break divs before unsplittable elements that cross a page boundary.

    Renders the HTML in a single Playwright session at A4 width, identifies every
    table / img / figure / blockquote / pre / svg whose bounding box crosses a page
    boundary, and inserts a zero-height page-break-before div directly before it in
    the live DOM.  The modified HTML is returned via page.content().

    No thresholds — if the element crosses any boundary, it moves to the next page.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as fh:
        fh.write(html_content)
        tmp_path = Path(fh.name)

    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium_with_install(playwright)
            viewport_width_px, page_height_px = _extract_page_geometry_px(html_content)
            page = browser.new_page(
                viewport={"width": viewport_width_px, "height": page_height_px * 20}
            )
            page.emulate_media(media="print")
            page.route(
                "**/*",
                lambda route, request: route.abort()
                if request.resource_type in {"media", "font"}
                else route.continue_(),
            )
            page.goto(tmp_path.as_uri(), wait_until="load")

            block_parents_js = str(list(_BLOCK_PARENTS))
            page.evaluate(
                f"""([selectors, pageH, pbStyle]) => {{
                    const BLOCK_PARENTS = new Set({block_parents_js});
                    const processed = new WeakSet();

                    for (const el of document.querySelectorAll(selectors)) {{
                        const rect = el.getBoundingClientRect();
                        if (rect.height <= 0) continue;

                        // Mark tables that fit within one page — the DOCX converter will
                        // apply w:cantSplit to their rows so Word keeps them together.
                        if (el.tagName === 'TABLE' && rect.height < pageH) {{
                            el.setAttribute('data-docx-cant-split', '1');
                        }}

                        // Inject page-break before unsplittable elements that cross a boundary.
                        if (rect.height >= pageH) continue;
                        const topPage = Math.floor(rect.top / pageH);
                        const botPage = Math.floor((rect.bottom - 1) / pageH);
                        if (topPage === botPage) continue;

                        let node = el;
                        while (node.parentElement && !BLOCK_PARENTS.has(node.parentElement.tagName))
                            node = node.parentElement;

                        if (!node.parentElement) continue;
                        if (processed.has(node)) continue;
                        processed.add(node);

                        const pb = document.createElement('div');
                        pb.setAttribute('style', pbStyle);
                        node.parentElement.insertBefore(pb, node);
                    }}
                }}""",
                [_UNSPLITTABLE_SELECTORS, page_height_px, _PB_STYLE],
            )

            modified_html = page.content()
            browser.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    return modified_html


def _extract_page_geometry_px(html_content: str) -> tuple[int, int]:
    width_pt, height_pt, top_pt, _right_pt, bottom_pt, _left_pt = _extract_page_geometry_pt(
        html_content
    )
    viewport_width_px = max(1, round(width_pt * _PT_TO_PX))
    content_height_pt = max(1.0, height_pt - top_pt - bottom_pt)
    page_height_px = max(1, round(content_height_pt * _PT_TO_PX))
    return viewport_width_px, page_height_px


def _annotate_tables(soup: BeautifulSoup) -> str:
    tables = soup.find_all("table")
    for idx, table in enumerate(tables):
        table["data-docx-table-idx"] = str(idx)
    return str(soup)


def _compute_table_auto_widths(html_content: str) -> dict[int, list[float]]:
    widths_by_index: dict[int, list[float]] = {}
    with sync_playwright() as playwright:
        browser = _launch_chromium_with_install(playwright)
        page = browser.new_page(viewport={"width": 1200, "height": 1600})
        page.route(
            "**/*",
            lambda route, request: route.abort()
            if request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )
        page.set_content(html_content, wait_until="domcontentloaded")
        tables = page.query_selector_all("table[data-docx-table-idx]")
        for table in tables:
            idx_value = table.get_attribute("data-docx-table-idx")
            if idx_value is None:
                continue
            rows = table.query_selector_all("tr")
            if not rows:
                continue
            row = rows[0]
            cells = row.query_selector_all(":scope > td, :scope > th")
            if not cells:
                continue
            widths_px = []
            for cell in cells:
                box = cell.bounding_box()
                if box:
                    widths_px.append(box["width"])
            if widths_px:
                widths_by_index[int(idx_value)] = [width * 0.75 for width in widths_px]
        browser.close()
    return widths_by_index


def _extract_auto_widths(
    table_node, table_auto_widths: dict[int, list[float]], column_count: int
) -> Optional[list[float]]:
    idx_value = table_node.get("data-docx-table-idx")
    if idx_value is None:
        return None
    try:
        idx = int(idx_value)
    except ValueError:
        return None
    widths = table_auto_widths.get(idx)
    if not widths or len(widths) < column_count:
        return None
    return widths[:column_count]


def _launch_chromium_with_install(playwright_instance):
    try:
        return playwright_instance.chromium.launch()
    except Exception as exc:
        if _is_missing_playwright_browser_error(exc):
            _install_playwright_chromium()
            return playwright_instance.chromium.launch()
        raise


def _is_missing_playwright_browser_error(exc: Exception) -> bool:
    message = str(exc)
    return "Executable doesn't exist" in message or "playwright install" in message


def _install_playwright_chromium() -> None:
    subprocess.run(["playwright", "install", "chromium"], check=True)
