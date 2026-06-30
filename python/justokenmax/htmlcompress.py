"""HTML snapshot compression.

Saved pages and browser/tool dumps often include large scripts, styles, and DOM
boilerplate. This extracts the human-visible page signal into a small markdown
digest while keeping the original retrievable from the cache.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Tuple

MAX_HEADINGS = 60
MAX_LINKS = 30
MAX_TEXT_CHARS = 6000


class _DigestParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.heading_level = 0
        self.title_parts = []
        self.headings = []
        self.links = []
        self.text_parts = []
        self.text_chars = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = int(tag[1])
        if tag == "a" and len(self.links) < MAX_LINKS:
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth:
            if tag in {"script", "style", "noscript", "svg", "canvas"}:
                self.skip_depth -= 1
            return
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = 0

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.heading_level and len(self.headings) < MAX_HEADINGS:
            self.headings.append((self.heading_level, text))
        self.text_chars += len(text)
        if sum(len(x) for x in self.text_parts) < MAX_TEXT_CHARS:
            self.text_parts.append(text)


def compress_html(text: str) -> Tuple[str, dict]:
    parser = _DigestParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return text, {"kind": "html", "ok": False, "note": "HTML parse failed"}

    title = " ".join(parser.title_parts).strip()
    visible = " ".join(parser.text_parts).strip()
    if not title and not parser.headings and not visible:
        return text, {"kind": "html", "ok": False, "note": "no visible text"}

    lines = ["# HTML summary", ""]
    if title:
        lines += [f"- title: {title}"]
    lines += [
        f"- headings: {len(parser.headings)} captured",
        f"- links: {len(parser.links)} captured",
        f"- visible_text_chars: {parser.text_chars}",
    ]
    if parser.headings:
        lines += ["", "## Headings"]
        for level, heading in parser.headings:
            lines.append(f"{'#' * min(level + 1, 6)} {heading}")
    if parser.links:
        lines += ["", "## Links"]
        for href in parser.links:
            lines.append(f"- {href}")
    if visible:
        suffix = ""
        shown_chars = len(visible)
        if parser.text_chars > shown_chars:
            suffix = f"\n\n...(+{parser.text_chars - shown_chars} visible chars)"
        lines += ["", "## Visible Text Sample", visible + suffix]

    digest = "\n".join(lines) + "\n"
    return digest, {
        "kind": "html",
        "ok": True,
        "headings": len(parser.headings),
        "links": len(parser.links),
        "visible_text_chars": parser.text_chars,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
