from typing import Dict, Optional, Tuple

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from .html_docx_constants import _PAGE_SIZES_PT
from .html_docx_css import _parse_background_color, _parse_float, _parse_length_to_pt

_DEFAULT_DOCX_MARGIN_PT = 72.0


def _apply_page_settings(doc: Document, html_content: str) -> None:
    page_css = _extract_page_css(html_content)
    margins_pt = _extract_page_margin_box_pt(page_css)
    page_size = _extract_page_size_pt(page_css)
    for section in doc.sections:
        if page_size:
            width_pt, height_pt, is_landscape = page_size
            if is_landscape:
                section.orientation = WD_ORIENT.LANDSCAPE
            section.page_width = Pt(width_pt)
            section.page_height = Pt(height_pt)
        elif "landscape" in page_css and section.orientation != WD_ORIENT.LANDSCAPE:
            section.orientation = WD_ORIENT.LANDSCAPE
            section.page_width, section.page_height = (
                section.page_height,
                section.page_width,
            )
        if margins_pt is not None:
            top, right, bottom, left = margins_pt
            if top is not None:
                section.top_margin = Pt(top)
            if right is not None:
                section.right_margin = Pt(right)
            if bottom is not None:
                section.bottom_margin = Pt(bottom)
            if left is not None:
                section.left_margin = Pt(left)


def _apply_page_background(doc: Document, body_style: Dict[str, str]) -> None:
    bg_color = _parse_background_color(body_style)
    if not bg_color:
        return
    doc_element = doc._part._element
    background = doc_element.find(qn("w:background"))
    if background is None:
        background = OxmlElement("w:background")
        doc_element.insert(0, background)
    background.set(qn("w:color"), bg_color)


def _ensure_display_background_shape(doc: Document) -> None:
    settings = doc._part.settings._element
    existing = settings.find(qn("w:displayBackgroundShape"))
    if existing is None:
        elem = OxmlElement("w:displayBackgroundShape")
        settings.append(elem)


def _extract_page_css(html_content: str) -> str:
    lower = html_content.lower()
    start = lower.find("@page")
    if start == -1:
        return ""
    block_start = lower.find("{", start)
    if block_start == -1:
        return ""
    block_end = lower.find("}", block_start)
    if block_end == -1:
        return ""
    return lower[block_start + 1:block_end]


def _extract_page_margin_box_pt(
    page_css: str,
) -> Optional[Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]]:
    top = right = bottom = left = None
    shorthand: Optional[Tuple[float, float, float, float]] = None

    for rule in page_css.split(";"):
        if ":" not in rule:
            continue
        key, value = [part.strip() for part in rule.split(":", 1)]
        if key == "margin":
            shorthand = _parse_margin_shorthand_pt(value)
        elif key == "margin-top":
            top = _parse_length_to_pt(value)
        elif key == "margin-right":
            right = _parse_length_to_pt(value)
        elif key == "margin-bottom":
            bottom = _parse_length_to_pt(value)
        elif key == "margin-left":
            left = _parse_length_to_pt(value)

    if shorthand is not None:
        s_top, s_right, s_bottom, s_left = shorthand
        top = top if top is not None else s_top
        right = right if right is not None else s_right
        bottom = bottom if bottom is not None else s_bottom
        left = left if left is not None else s_left

    if all(value is None for value in (top, right, bottom, left)):
        return None
    return top, right, bottom, left


def _parse_margin_shorthand_pt(value: str) -> Optional[Tuple[float, float, float, float]]:
    parts = [part for part in value.replace(",", " ").split() if part]
    if not parts:
        return None

    parsed = [_parse_length_to_pt(part) for part in parts]
    if any(part is None for part in parsed):
        return None

    values = [float(part) for part in parsed if part is not None]
    if len(values) == 1:
        return values[0], values[0], values[0], values[0]
    if len(values) == 2:
        return values[0], values[1], values[0], values[1]
    if len(values) == 3:
        return values[0], values[1], values[2], values[1]
    return values[0], values[1], values[2], values[3]


def _extract_page_geometry_pt(
    html_content: str,
) -> Tuple[float, float, float, float, float, float]:
    page_css = _extract_page_css(html_content)
    page_size = _extract_page_size_pt(page_css)
    if page_size is None:
        width_pt, height_pt = _PAGE_SIZES_PT["a4"]
    else:
        width_pt, height_pt, _is_landscape = page_size

    margins_pt = _extract_page_margin_box_pt(page_css)
    if margins_pt is None:
        return (
            width_pt,
            height_pt,
            _DEFAULT_DOCX_MARGIN_PT,
            _DEFAULT_DOCX_MARGIN_PT,
            _DEFAULT_DOCX_MARGIN_PT,
            _DEFAULT_DOCX_MARGIN_PT,
        )

    top, right, bottom, left = margins_pt
    return (
        width_pt,
        height_pt,
        top if top is not None else _DEFAULT_DOCX_MARGIN_PT,
        right if right is not None else _DEFAULT_DOCX_MARGIN_PT,
        bottom if bottom is not None else _DEFAULT_DOCX_MARGIN_PT,
        left if left is not None else _DEFAULT_DOCX_MARGIN_PT,
    )


def _extract_page_size_pt(page_css: str) -> Optional[Tuple[float, float, bool]]:
    if "size" not in page_css:
        return None
    for rule in page_css.split(";"):
        if "size" not in rule:
            continue
        key, value = [part.strip() for part in rule.split(":", 1)]
        if key != "size":
            continue
        tokens = [token.strip().lower() for token in value.split() if token.strip()]
        if not tokens:
            return None
        size_token = next((token for token in tokens if token in _PAGE_SIZES_PT), None)
        if not size_token:
            return None
        width_pt, height_pt = _PAGE_SIZES_PT[size_token]
        is_landscape = "landscape" in tokens
        is_portrait = "portrait" in tokens
        if is_landscape and width_pt < height_pt:
            width_pt, height_pt = height_pt, width_pt
        if is_portrait and width_pt > height_pt:
            width_pt, height_pt = height_pt, width_pt
        return width_pt, height_pt, is_landscape
    return None
