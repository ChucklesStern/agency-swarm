def _remove_trailing_empty_paragraph(container) -> None:
    if not hasattr(container, "paragraphs"):
        return
    if not container.paragraphs:
        return
    last = container.paragraphs[-1]
    if last.text.strip():
        return
    # Preserve empty paragraphs that carry a visual border (used as divider lines).
    if "<w:pBdr>" in last._p.xml:
        return
    last._element.getparent().remove(last._element)


def _remove_leading_empty_paragraph(container) -> None:
    if not hasattr(container, "paragraphs"):
        return
    if not container.paragraphs:
        return
    first = container.paragraphs[0]
    if first.text.strip():
        return
    first._element.getparent().remove(first._element)
