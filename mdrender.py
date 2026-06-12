"""Markdown rendering helpers for the Qt UI.

Splits a reply into prose and fenced-code segments, turns prose into the HTML
subset Qt's rich text understands (with inline styling so it looks right in a
QLabel), and syntax-highlights code with Pygments using inline styles.
"""

from __future__ import annotations

import re
from typing import Dict, List

import markdown as _markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

_FENCE = re.compile(r"^[ \t]*```([^\n`]*)\n(.*?)(?:^[ \t]*```[ \t]*$|\Z)",
                    re.DOTALL | re.MULTILINE)
_PYGMENTS_STYLE = "stata-dark"


def parse_segments(text: str) -> List[Dict]:
    """Split text into ordered prose / code segments."""
    segments: List[Dict] = []
    pos = 0
    for m in _FENCE.finditer(text):
        if m.start() > pos:
            prose = text[pos:m.start()].strip("\n")
            if prose.strip():
                segments.append({"type": "prose", "text": prose})
        segments.append({"type": "code", "lang": m.group(1).strip(),
                         "code": m.group(2).rstrip("\n")})
        pos = m.end()
    if pos < len(text):
        prose = text[pos:].strip("\n")
        if prose.strip():
            segments.append({"type": "prose", "text": prose})
    if not segments and text.strip():
        segments.append({"type": "prose", "text": text})
    return segments


def prose_to_html(md_text: str, palette: Dict) -> str:
    """Render prose Markdown to inline-styled HTML for a QLabel."""
    html = _markdown.markdown(md_text, extensions=["extra", "sane_lists", "nl2br"])
    code_style = (f"background-color:{palette['code_inline_bg']};"
                  f"color:{palette['code_inline_fg']};"
                  "font-family:'SF Mono','Menlo','Consolas',monospace;")
    html = html.replace("<code>", f"<code style=\"{code_style}\">")
    html = html.replace("<a ", f"<a style=\"color:{palette['link']};\" ")
    return html


def highlight_to_html(code: str, lang: str) -> str:
    """Syntax-highlight code to inline-styled HTML (newlines preserved)."""
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
    except (ClassNotFound, ValueError):
        try:
            lexer = guess_lexer(code)
        except (ClassNotFound, ValueError):
            from pygments.lexers import TextLexer
            lexer = TextLexer()
    body = highlight(code, lexer, HtmlFormatter(noclasses=True, nowrap=True,
                                                style=_PYGMENTS_STYLE))
    return body
