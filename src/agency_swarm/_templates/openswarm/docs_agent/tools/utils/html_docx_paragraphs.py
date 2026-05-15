from typing import Dict

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from .html_docx_constants import (
    _LIST_BASE_HANGING_TWIPS,
    _LIST_BASE_LEFT_TWIPS,
    _NAMED_COLORS,
    _PADDING_SCALE,
)
from .html_docx_css import (
    _border_sz,
    _normalize_font_family,
    _parse_background_color,
    _parse_border_left,
    _parse_box_values,
    _parse_color,
    _parse_float,
    _parse_font_size_pt,
    _parse_length_to_pt,
    _parse_padding,
    _parse_px_to_pt,
)


def _apply_paragraph_style(paragraph, style_map: Dict[str, str]) -> None:
    alignment = style_map.get("text-align", "").lower()
    if alignment == "left":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    elif alignment == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alignment == "right":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif alignment == "justify":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    _apply_paragraph_spacing(paragraph, style_map)
    _apply_paragraph_borders(paragraph, style_map)
    _apply_paragraph_container_styles(paragraph, style_map)
    _apply_paragraph_line_height(paragraph, style_map)


def _apply_run_style(run, style_map: Dict[str, str]) -> None:
    font_family = style_map.get("font-family")
    if font_family:
        _set_run_font(run, _normalize_font_family(font_family))

    font_size = style_map.get("font-size")
    if font_size:
        size_pt = _parse_font_size_pt(font_size)
        if size_pt is not None:
            run.font.size = Pt(size_pt)

    color = style_map.get("color")
    if color:
        rgb = _parse_color(color)
        if rgb is not None:
            run.font.color.rgb = rgb

    font_weight = style_map.get("font-weight", "").strip().lower()
    if font_weight in {"bold", "bolder"}:
        run.font.bold = True
    else:
        weight = _parse_float(font_weight) if font_weight else None
        if weight is not None and weight >= 600:
            run.font.bold = True

    font_style = style_map.get("font-style", "").strip().lower()
    if font_style == "italic":
        run.font.italic = True

    text_decoration = style_map.get("text-decoration", "").strip().lower()
    if "underline" in text_decoration:
        run.font.underline = True

    letter_spacing = style_map.get("letter-spacing", "").strip().lower()
    if letter_spacing:
        spacing_pt = _parse_px_to_pt(letter_spacing)
        if spacing_pt is not None:
            r_pr = run._r.get_or_add_rPr()
            spacing = r_pr.find(qn("w:spacing"))
            if spacing is None:
                spacing = OxmlElement("w:spacing")
                r_pr.append(spacing)
            spacing.set(qn("w:val"), str(int(spacing_pt * 20)))


def _set_run_font(run, font_name: str) -> None:
    run.font.name = font_name
    r_pr = run._r.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    r_fonts.set(qn("w:ascii"), font_name)
    r_fonts.set(qn("w:hAnsi"), font_name)
    r_fonts.set(qn("w:cs"), font_name)
    r_fonts.set(qn("w:eastAsia"), font_name)


def _apply_paragraph_container_styles(paragraph, style_map: Dict[str, str]) -> None:
    bg_color = _parse_background_color(style_map)
    if bg_color:
        p_pr = paragraph._p.get_or_add_pPr()
        shd = p_pr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd")
            p_pr.append(shd)
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), bg_color)

    border_left = _parse_border_left(style_map)
    if border_left:
        width_pt, color = border_left
        p_pr = paragraph._p.get_or_add_pPr()
        p_bdr = p_pr.find(qn("w:pBdr"))
        if p_bdr is None:
            p_bdr = OxmlElement("w:pBdr")
            p_pr.append(p_bdr)
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), _border_sz(width_pt))
        left.set(qn("w:color"), color)
        p_bdr.append(left)

    padding = _parse_padding(style_map.get("padding", ""))
    if padding:
        top, right, bottom, left = padding
        if left:
            paragraph.paragraph_format.left_indent = Pt(left * _PADDING_SCALE)
        if right:
            paragraph.paragraph_format.right_indent = Pt(right * _PADDING_SCALE)


def _apply_paragraph_line_height(paragraph, style_map: Dict[str, str]) -> None:
    line_height = style_map.get("line-height", "").strip().lower()
    if not line_height:
        # Spacer-div pattern: <div style="height: Xpt"> with no other content.
        # Convert the height to an exact line-height so the paragraph takes up
        # the intended vertical space. Zero values are the divider pattern
        # (<div style="height: 0pt; border-top: ...">), which should keep default
        # spacing so the border renders correctly.
        height_str = style_map.get("height", "").strip().lower()
        if height_str:
            height_pt = _parse_length_to_pt(height_str)
            if height_pt:
                paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                paragraph.paragraph_format.line_spacing = Pt(height_pt)
                return
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph.paragraph_format.line_spacing = 1
        return
    if line_height.endswith("px") or line_height.endswith("pt"):
        height_pt = _parse_px_to_pt(line_height)
        if height_pt is not None:
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            paragraph.paragraph_format.line_spacing = Pt(height_pt)
            return
    value = _parse_float(line_height)
    if value:
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph.paragraph_format.line_spacing = value


def _apply_paragraph_spacing(paragraph, style_map: Dict[str, str]) -> None:
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)

    margin = _parse_box_values(style_map.get("margin", ""))
    margin_top = _parse_px_to_pt(style_map.get("margin-top", ""))
    margin_bottom = _parse_px_to_pt(style_map.get("margin-bottom", ""))

    if margin:
        top, _, bottom, _ = margin
        if top is not None:
            paragraph.paragraph_format.space_before = Pt(top)
        if bottom is not None:
            paragraph.paragraph_format.space_after = Pt(bottom)

    if margin_top is not None:
        paragraph.paragraph_format.space_before = Pt(margin_top)
    if margin_bottom is not None:
        paragraph.paragraph_format.space_after = Pt(margin_bottom)


def _apply_paragraph_borders(paragraph, style_map: Dict[str, str]) -> None:
    top = _parse_paragraph_border(style_map.get("border-top", ""))
    bottom = _parse_paragraph_border(style_map.get("border-bottom", ""))
    if not top and not bottom:
        return

    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)

    if top:
        width_pt, color = top
        elem = OxmlElement("w:top")
        elem.set(qn("w:val"), "single")
        elem.set(qn("w:sz"), _border_sz(width_pt))
        elem.set(qn("w:color"), color)
        p_bdr.append(elem)
    if bottom:
        width_pt, color = bottom
        elem = OxmlElement("w:bottom")
        elem.set(qn("w:val"), "single")
        elem.set(qn("w:sz"), _border_sz(width_pt))
        elem.set(qn("w:color"), color)
        p_bdr.append(elem)


def _parse_paragraph_border(border: str):
    if not border:
        return None
    parts = border.split()
    width_pt = _parse_px_to_pt(parts[0]) if parts else None
    color = None
    for part in parts:
        if part.startswith("#"):
            color = part[1:].upper()
            break
        if part.lower() in _NAMED_COLORS:
            r, g, b = _NAMED_COLORS[part.lower()]
            color = f"{r:02X}{g:02X}{b:02X}"
            break
    if width_pt and color:
        return width_pt, color
    return None


def _add_paragraph_spacing(paragraph, before_pt: float = 0, after_pt: float = 0) -> None:
    pf = paragraph.paragraph_format
    if before_pt:
        current = pf.space_before.pt if pf.space_before else 0
        pf.space_before = Pt(current + before_pt)
    if after_pt:
        current = pf.space_after.pt if pf.space_after else 0
        pf.space_after = Pt(current + after_pt)


def _add_paragraph_indent(paragraph, left_pt: float = 0, right_pt: float = 0) -> None:
    pf = paragraph.paragraph_format
    if left_pt:
        current = pf.left_indent.pt if pf.left_indent else 0
        pf.left_indent = Pt(current + left_pt)
    if right_pt:
        current = pf.right_indent.pt if pf.right_indent else 0
        pf.right_indent = Pt(current + right_pt)


def _add_list_indent_padding(paragraph, left_pt: float = 0, right_pt: float = 0) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    ind = p_pr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        p_pr.append(ind)
    if left_pt:
        current = ind.get(qn("w:left"))
        if current and current.isdigit():
            current_val = int(current)
        else:
            current_val = _LIST_BASE_LEFT_TWIPS
        ind.set(qn("w:left"), str(current_val + int(left_pt * 20)))
        if ind.get(qn("w:hanging")) is None:
            ind.set(qn("w:hanging"), str(_LIST_BASE_HANGING_TWIPS))
    if right_pt:
        current = ind.get(qn("w:right"))
        current_val = int(current) if current and current.isdigit() else 0
        ind.set(qn("w:right"), str(current_val + int(right_pt * 20)))


def _apply_ul_margin_indent(paragraph, additional_left_pt: float) -> None:
    """Shift a list item right by the parent <ul> margin-left.

    When a <ul> has margin-left: X, the entire list must shift X pt to the right.
    We add X to w:ind w:left while explicitly preserving w:hanging so the bullet
    character and text-start gap are kept intact (paragraph-level w:ind overrides
    the abstractNum's w:ind entirely, so we must carry both values).
    """
    if not additional_left_pt:
        return
    p_pr = paragraph._p.get_or_add_pPr()
    ind = p_pr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        p_pr.append(ind)
    current_left = ind.get(qn("w:left"))
    base_left = int(current_left) if current_left and current_left.isdigit() else _LIST_BASE_LEFT_TWIPS
    current_hanging = ind.get(qn("w:hanging"))
    base_hanging = int(current_hanging) if current_hanging and current_hanging.isdigit() else _LIST_BASE_HANGING_TWIPS
    ind.set(qn("w:left"), str(base_left + int(additional_left_pt * 20)))
    ind.set(qn("w:hanging"), str(base_hanging))


def _apply_list_indent(paragraph, indent_pt: float) -> None:
    _set_list_indent_xml(paragraph, indent_pt)


def _set_list_indent_xml(paragraph, indent_pt: float) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    ind = p_pr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        p_pr.append(ind)
    left_twips = ind.get(qn("w:left"))
    if left_twips and left_twips.isdigit():
        base_left = int(left_twips)
    else:
        base_left = _LIST_BASE_LEFT_TWIPS
    ind.set(qn("w:left"), str(base_left + int(indent_pt * 20)))
    if ind.get(qn("w:hanging")) is None:
        ind.set(qn("w:hanging"), str(_LIST_BASE_HANGING_TWIPS))


def _resolve_list_indent_pt(parent_style: Dict[str, str]) -> float:
    margin_left = parent_style.get("margin-left", "")
    if margin_left:
        value = _parse_length_to_pt(margin_left)
        if value:
            return value
    margin = parent_style.get("margin", "")
    if margin:
        values = _parse_padding(margin)
        if values:
            return values[3]
    padding_left = parent_style.get("padding-left", "")
    if padding_left:
        value = _parse_length_to_pt(padding_left)
        if value:
            return value
    padding = parent_style.get("padding", "")
    if padding:
        values = _parse_padding(padding)
        if values:
            return values[3]
    return 0.0
