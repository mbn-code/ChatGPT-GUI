"""Lightweight Markdown rendering into a Tkinter Text widget.

Not a full CommonMark implementation — just the subset that shows up in chat
replies: headings, bold/italic, inline code, bullet/numbered lists,
blockquotes, and fenced code blocks (with a language label and a Copy button).
Anything it doesn't recognise is rendered as plain text, so it never throws on
unexpected input.
"""

from __future__ import annotations

import re
import tkinter as tk
from typing import Callable, Dict

_FENCE = re.compile(r"^\s*```(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")

# inline spans, in priority order
_INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*[^*]+\*\*|__[^_]+__)"
    r"|(?P<italic>\*[^*\n]+\*|_[^_\n]+_)"
)


def configure_tags(text, fonts: Dict, palette: Dict) -> None:
    """Set up the tags used by render(). Safe to call repeatedly."""
    text.configure(bg=palette["bubble_asst"], fg=palette["bubble_asst_fg"])
    text.tag_configure("normal", font=fonts["body"], foreground=palette["bubble_asst_fg"])
    text.tag_configure("bold", font=fonts["bold"])
    text.tag_configure("italic", font=fonts["italic"])
    text.tag_configure("bolditalic", font=fonts["bolditalic"])
    text.tag_configure("h1", font=fonts["h1"], spacing1=8, spacing3=4)
    text.tag_configure("h2", font=fonts["h2"], spacing1=8, spacing3=4)
    text.tag_configure("h3", font=fonts["h3"], spacing1=6, spacing3=3)
    text.tag_configure("bullet", lmargin1=18, lmargin2=34, spacing3=2)
    text.tag_configure("quote", lmargin1=16, lmargin2=16, foreground=palette["muted"],
                       font=fonts["italic"])
    text.tag_configure("code_inline", font=fonts["mono"], foreground=palette["code_inline_fg"])
    text.tag_configure("code_block", font=fonts["mono"], foreground=palette["code_fg"],
                       background=palette["code_bg"], lmargin1=12, lmargin2=12,
                       rmargin=12, spacing1=2, spacing3=2, borderwidth=0)


def _insert_inline(text, segment: str, base_tag: str) -> None:
    """Insert one line of text, applying inline bold/italic/code styles."""
    pos = 0
    for m in _INLINE.finditer(segment):
        if m.start() > pos:
            text.insert("end", segment[pos:m.start()], base_tag)
        if m.group("code"):
            text.insert("end", m.group("code")[1:-1], (base_tag, "code_inline"))
        elif m.group("bold"):
            text.insert("end", m.group("bold")[2:-2], (base_tag, "bold"))
        elif m.group("italic"):
            text.insert("end", m.group("italic")[1:-1], (base_tag, "italic"))
        pos = m.end()
    if pos < len(segment):
        text.insert("end", segment[pos:], base_tag)


def _insert_code_block(text, code: str, lang: str, fonts, palette,
                       copy_cb: Callable[[str], None]) -> None:
    """Insert a fenced code block with a header (language + Copy button)."""
    header = tk.Frame(text, bg=palette["code_header"], height=24)
    tk.Label(header, text=(lang or "code"), bg=palette["code_header"],
             fg=palette["muted"], font=fonts["caption"]).pack(side="left", padx=10)
    copy = tk.Label(header, text="Copy", bg=palette["code_header"], fg=palette["muted"],
                    font=fonts["caption"], cursor="hand2", padx=10)
    copy.pack(side="right")

    def do_copy(_e=None):
        copy_cb(code)
        copy.configure(text="Copied")
        copy.after(1200, lambda: copy.configure(text="Copy"))

    copy.bind("<Button-1>", do_copy)
    copy.bind("<Enter>", lambda e: copy.configure(fg=palette["bubble_asst_fg"]))
    copy.bind("<Leave>", lambda e: copy.configure(fg=palette["muted"]))

    text.insert("end", "\n")
    text.window_create("end", window=header, stretch=True)
    text.insert("end", "\n")
    text.insert("end", code.rstrip("\n") + "\n", "code_block")


def render(text, markdown: str, *, fonts: Dict, palette: Dict,
           copy_cb: Callable[[str], None]) -> None:
    """Replace the contents of `text` with the rendered `markdown`."""
    was_disabled = str(text.cget("state")) == "disabled"
    text.configure(state="normal")
    # drop any embedded widgets from a previous render
    for child in list(text.winfo_children()):
        child.destroy()
    text.delete("1.0", "end")

    lines = markdown.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            lang = fence.group(1).strip()
            body = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            _insert_code_block(text, "\n".join(body), lang, fonts, palette, copy_cb)
            continue

        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        if heading:
            level = len(heading.group(1))
            _insert_inline(text, heading.group(2), f"h{level}")
            text.insert("end", "\n")
        elif bullet:
            text.insert("end", "•  ", "bullet")
            _insert_inline(text, bullet.group(2), "bullet")
            text.insert("end", "\n")
        elif numbered:
            text.insert("end", f"{numbered.group(2)}.  ", "bullet")
            _insert_inline(text, numbered.group(3), "bullet")
            text.insert("end", "\n")
        elif line.startswith(">"):
            _insert_inline(text, line.lstrip(">").strip(), "quote")
            text.insert("end", "\n")
        else:
            _insert_inline(text, line, "normal")
            text.insert("end", "\n")
        i += 1

    # trim the trailing newline we always add
    if text.get("end-2c", "end-1c") == "\n":
        text.delete("end-2c", "end-1c")
    if was_disabled:
        text.configure(state="disabled")
