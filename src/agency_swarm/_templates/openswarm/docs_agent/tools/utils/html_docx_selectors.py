from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag
import tinycss2


def _parse_style(style: str) -> Dict[str, str]:
    items = {}
    for rule in style.split(";"):
        if ":" not in rule:
            continue
        key, value = rule.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            items[key] = value
    return items


def _extract_css_rules(
    soup: BeautifulSoup,
) -> List[Tuple[str, Dict[str, str], Tuple[int, int, int], int]]:
    rules: List[Tuple[str, Dict[str, str], Tuple[int, int, int], int]] = []
    order = 0

    for style_tag in soup.find_all("style"):
        css_text = style_tag.string or style_tag.get_text()
        if not css_text:
            continue

        stylesheet = tinycss2.parse_stylesheet(
            css_text, skip_comments=True, skip_whitespace=True
        )
        for rule in stylesheet:
            if rule.type != "qualified-rule":
                continue

            selectors_text = tinycss2.serialize(rule.prelude).strip()
            if not selectors_text:
                continue

            declarations = tinycss2.parse_declaration_list(
                rule.content, skip_comments=True, skip_whitespace=True
            )
            style_map: Dict[str, str] = {}
            for declaration in declarations:
                if declaration.type != "declaration":
                    continue
                name = declaration.name.lower().strip() if declaration.name else ""
                value = tinycss2.serialize(declaration.value).strip()
                if name and value:
                    style_map[name] = value

            for selector in [s.strip() for s in selectors_text.split(",") if s.strip()]:
                pseudo = None
                if "::before" in selector:
                    pseudo = "before"
                    base_selector = selector.replace("::before", "").strip()
                elif "::after" in selector:
                    pseudo = "after"
                    base_selector = selector.replace("::after", "").strip()
                else:
                    base_selector = selector

                if not _is_supported_selector(base_selector):
                    continue

                rule_styles = style_map
                if pseudo:
                    rule_styles = {f"pseudo-{pseudo}-{k}": v for k, v in style_map.items()}

                specificity = _selector_specificity(base_selector)
                rules.append((base_selector, rule_styles, specificity, order))
                order += 1

    return rules


def _compute_style_map(
    element, css_rules: List[Tuple[str, Dict[str, str], Tuple[int, int, int], int]]
) -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    matches: List[Tuple[Tuple[int, int, int], int, Dict[str, str]]] = []

    for selector, styles, specificity, order in css_rules:
        if _matches_selector(element, selector):
            matches.append((specificity, order, styles))

    matches.sort(key=lambda item: (item[0], item[1]))
    for _, __, styles in matches:
        resolved.update(styles)

    inline_styles = _parse_style(element.get("style", ""))
    resolved.update(inline_styles)

    return resolved


def _is_supported_selector(selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    if any(token in selector for token in ["#", "[", "]", "*", "+", "~"]):
        return False
    return True


def _selector_specificity(selector: str) -> Tuple[int, int, int]:
    selectors = _parse_selector_chain(selector)
    class_count = sum(len(classes) for _, classes in selectors)
    tag_count = sum(1 for tag, _ in selectors if tag)
    return (0, class_count, tag_count)


def _parse_selector(selector: str) -> Tuple[Optional[str], List[str]]:
    selector = selector.strip()
    if selector.startswith("."):
        tag = None
        classes = [cls for cls in selector[1:].split(".") if cls]
    else:
        parts = [part for part in selector.split(".") if part]
        tag = parts[0] if parts else None
        classes = parts[1:] if len(parts) > 1 else []
    return tag, classes


def _matches_selector(element, selector: str) -> bool:
    chain = _parse_selector_chain(selector)
    if not chain:
        return False
    return _matches_selector_chain(element, chain)


def _parse_selector_chain(selector: str) -> List[Tuple[Optional[str], List[str]]]:
    tokens = selector.replace(">", " > ").split()
    if not tokens:
        return []
    selectors: List[Tuple[Optional[str], List[str]]] = []
    for token in tokens:
        if token == ">":
            selectors.append((">", []))
        else:
            selectors.append(_parse_selector(token))
    return selectors


def _matches_selector_chain(element: Tag, chain: List[Tuple[Optional[str], List[str]]]) -> bool:
    idx = len(chain) - 1
    current = element

    while idx >= 0:
        token = chain[idx]
        if token[0] == ">":
            idx -= 1
            if idx < 0:
                return False
            parent_selector = chain[idx]
            current = current.parent if isinstance(current.parent, Tag) else None
            if current is None or not _matches_simple_selector(current, parent_selector):
                return False
            idx -= 1
            continue

        if not _matches_simple_selector(current, token):
            return False

        idx -= 1
        if idx >= 0 and chain[idx][0] != ">":
            ancestor_selector = chain[idx]
            matched = False
            ancestor = current.parent
            while isinstance(ancestor, Tag):
                if _matches_simple_selector(ancestor, ancestor_selector):
                    matched = True
                    current = ancestor
                    break
                ancestor = ancestor.parent
            if not matched:
                return False
            idx -= 1

    return True


def _matches_simple_selector(
    element: Tag, selector: Tuple[Optional[str], List[str]]
) -> bool:
    tag, classes = selector
    if tag and element.name != tag:
        return False
    if classes:
        element_classes = set(element.get("class", []))
        if not all(cls in element_classes for cls in classes):
            return False
    return True
