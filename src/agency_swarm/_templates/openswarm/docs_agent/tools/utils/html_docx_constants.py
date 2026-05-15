_BLOCK_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "div",
    "section",
    "header",
    "ul",
    "ol",
    "table",
}
_INLINE_TAGS = {"span", "a", "strong", "em", "b", "i", "u", "small", "sup", "sub"}
_INHERITABLE_STYLES = {
    "font-family",
    "font-size",
    "color",
    "font-weight",
    "font-style",
    "text-decoration",
    "text-transform",
    "text-align",
    "line-height",
}

_NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "lightgray": (211, 211, 211),
    "lightgrey": (211, 211, 211),
    "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "navy": (0, 0, 128),
    "purple": (128, 0, 128),
    "teal": (0, 128, 128),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
}

_PADDING_SCALE = 0.7
_BORDER_SCALE = 1.5

_PAGE_SIZES_PT = {
    "a4": (595.3, 841.9),
    "letter": (612.0, 792.0),
}

_LIST_BASE_LEFT_TWIPS = 360
_LIST_BASE_HANGING_TWIPS = 360  # matches ilvl-0 hanging in the default Word template abstractNum

_UA_RESET_STYLE = """<style>
        /* UA reset to neutralize browser defaults */
        * {
            margin: 0;
            padding: 0;
            border: 0;
            font: inherit;
            vertical-align: baseline;
        }
        h1, h2, h3, h4, h5, h6 {
            font-weight: normal;
        }
        p, ul, ol, li {
            margin: 0;
            padding: 0;
        }
        ul { list-style: disc; padding-left: 20px; }
        ol { list-style: decimal; padding-left: 20px; }
    </style>"""