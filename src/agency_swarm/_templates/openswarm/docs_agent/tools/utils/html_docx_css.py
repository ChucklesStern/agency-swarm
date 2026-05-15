from typing import Dict, Optional, Tuple

from docx.shared import RGBColor

from .html_docx_constants import _BORDER_SCALE, _NAMED_COLORS


def _normalize_font_family(font_family: str) -> str:
    font_family = font_family.strip().strip('"').strip("'")
    if "," in font_family:
        return font_family.split(",", 1)[0].strip().strip('"').strip("'")
    return font_family


def _parse_font_size_pt(font_size: str) -> Optional[float]:
    size = font_size.strip().lower()
    if size.endswith("pt"):
        return _parse_float(size[:-2])
    if size.endswith("px"):
        px = _parse_float(size[:-2])
        if px is not None:
            return px * 0.75
    return None


def _parse_color(value: str) -> Optional[RGBColor]:
    color = value.strip().lower()
    if color in _NAMED_COLORS:
        r, g, b = _NAMED_COLORS[color]
        return RGBColor(r, g, b)
    if color.startswith("#"):
        hex_value = color[1:]
        if len(hex_value) == 3:
            hex_value = "".join([c * 2 for c in hex_value])
        if len(hex_value) == 6:
            try:
                r = int(hex_value[0:2], 16)
                g = int(hex_value[2:4], 16)
                b = int(hex_value[4:6], 16)
                return RGBColor(r, g, b)
            except ValueError:
                return None
    if color.startswith("rgb(") and color.endswith(")"):
        values = color[4:-1].split(",")
        if len(values) == 3:
            try:
                r, g, b = [int(v.strip()) for v in values]
                return RGBColor(r, g, b)
            except ValueError:
                return None
    return None


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_background_color(style_map: Dict[str, str]) -> Optional[str]:
    bg = style_map.get("background", "") or style_map.get("background-color", "")
    bg = bg.strip().lower()
    if not bg:
        return None
    if bg in _NAMED_COLORS:
        r, g, b = _NAMED_COLORS[bg]
        return f"{r:02X}{g:02X}{b:02X}"
    if "linear-gradient" in bg and "#" in bg:
        start = bg.find("#")
        return bg[start + 1:start + 7].upper()
    if bg.startswith("#"):
        hex_value = bg[1:]
        if len(hex_value) == 3:
            hex_value = "".join([c * 2 for c in hex_value])
        if len(hex_value) == 6:
            return hex_value.upper()
    return None


def _parse_border_left(style_map: Dict[str, str]) -> Optional[Tuple[float, str]]:
    border = style_map.get("border-left", "")
    if border:
        parts = border.split()
        width_pt = _parse_px_to_pt(parts[0]) if parts else None
        color = None
        for part in parts:
            if part.startswith("#"):
                color = part[1:].upper()
                break
        if width_pt and color:
            return width_pt, color

    width = style_map.get("border-left-width", "")
    color = style_map.get("border-left-color", "")
    if width and color:
        width_pt = _parse_px_to_pt(width)
        color = color[1:].upper() if color.startswith("#") else None
        if width_pt and color:
            return width_pt, color

    pseudo_width = style_map.get("pseudo-before-width", "")
    pseudo_bg = style_map.get("pseudo-before-background", "") or style_map.get(
        "pseudo-before-background-color", ""
    )
    if pseudo_width and pseudo_bg:
        width_pt = _parse_px_to_pt(pseudo_width)
        color = _parse_color_hex(pseudo_bg)
        if width_pt and color:
            return width_pt, color
    return None


def _parse_border(border_value: str) -> Optional[Tuple[float, str]]:
    border = border_value.strip()
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


def _parse_padding(padding_value: str) -> Optional[Tuple[float, float, float, float]]:
    if not padding_value:
        return None
    parts = [p for p in padding_value.replace(",", " ").split() if p]
    if not parts:
        return None
    values = [_parse_px_to_pt(p) for p in parts]
    values = [v for v in values if v is not None]
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0], values[0]
    if len(values) == 2:
        return values[0], values[1], values[0], values[1]
    if len(values) == 3:
        return values[0], values[1], values[2], values[1]
    return values[0], values[1], values[2], values[3]


def _resolve_padding(
    style_map: Dict[str, str],
) -> Optional[Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]]:
    padding = _parse_padding(style_map.get("padding", ""))
    top, right, bottom, left = padding if padding else (None, None, None, None)
    padding_top = _parse_length_to_pt(style_map.get("padding-top", ""))
    padding_right = _parse_length_to_pt(style_map.get("padding-right", ""))
    padding_bottom = _parse_length_to_pt(style_map.get("padding-bottom", ""))
    padding_left = _parse_length_to_pt(style_map.get("padding-left", ""))
    if padding_top is not None:
        top = padding_top
    if padding_right is not None:
        right = padding_right
    if padding_bottom is not None:
        bottom = padding_bottom
    if padding_left is not None:
        left = padding_left
    if all(value is None for value in (top, right, bottom, left)):
        return None
    return top, right, bottom, left


def _normalize_padding(
    padding: Tuple[Optional[float], Optional[float], Optional[float], Optional[float]],
) -> Tuple[float, float, float, float]:
    top, right, bottom, left = padding
    return (
        top or 0.0,
        right or 0.0,
        bottom or 0.0,
        left or 0.0,
    )


def _parse_px_to_pt(value: str) -> Optional[float]:
    val = value.strip().lower()
    if val.endswith("px"):
        px = _parse_float(val[:-2])
        if px is not None:
            return px * 0.75
    if val.endswith("pt"):
        return _parse_float(val[:-2])
    return None


def _parse_length_to_pt(value: str) -> Optional[float]:
    val = value.strip().lower()
    if not val:
        return None
    if val.endswith("pt") or val.endswith("px"):
        return _parse_px_to_pt(val)
    if val.endswith("%"):
        return None
    if val.isdigit():
        return _parse_px_to_pt(f"{val}px")
    return None


def _parse_percentage(value: str) -> Optional[float]:
    val = value.strip().replace("%", "")
    try:
        return float(val) / 100.0
    except ValueError:
        return None


def _parse_color_hex(value: str) -> Optional[str]:
    color = value.strip().lower()
    if color in _NAMED_COLORS:
        r, g, b = _NAMED_COLORS[color]
        return f"{r:02X}{g:02X}{b:02X}"
    if color.startswith("#"):
        hex_value = color[1:]
        if len(hex_value) == 3:
            hex_value = "".join([c * 2 for c in hex_value])
        if len(hex_value) == 6:
            return hex_value.upper()
    if color.startswith("rgb(") and color.endswith(")"):
        values = color[4:-1].split(",")
        if len(values) == 3:
            try:
                r, g, b = [int(v.strip()) for v in values]
                return f"{r:02X}{g:02X}{b:02X}"
            except ValueError:
                return None
    return None


def _parse_box_values(
    value: str,
) -> Optional[Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]]:
    if not value:
        return None
    parts = [p for p in value.replace(",", " ").split() if p]
    if not parts:
        return None
    values = [_parse_px_to_pt(p) for p in parts]
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0], values[0]
    if len(values) == 2:
        return values[0], values[1], values[0], values[1]
    if len(values) == 3:
        return values[0], values[1], values[2], values[1]
    return values[0], values[1], values[2], values[3]


def _border_sz(width_pt: float) -> str:
    return str(int(width_pt * 8 * _BORDER_SCALE))
