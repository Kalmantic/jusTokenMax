"""Markdown document compression.

Long READMEs/specs often have enough structure for a compact first pass:
headings tell the agent where to look, while small head/tail samples preserve
context. The original remains retrievable when a section needs full detail.
"""

from __future__ import annotations

import re
from typing import Tuple

MAX_HEADINGS = 120
MAX_SAMPLE_CHARS = 200
MAX_FENCES = 40

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^(```|~~~)\s*([A-Za-z0-9_+.-]*)")


def _clip(text: str, limit: int = MAX_SAMPLE_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n...(+{len(text) - limit} chars)"


def compress_markdown(text: str) -> Tuple[str, dict]:
    lines = text.splitlines()
    headings = []
    fences = []
    table_lines = 0
    in_fence = False
    fence_lang = ""
    fence_start = 0
    fence_lines = 0

    for idx, line in enumerate(lines, 1):
        if in_fence:
            if line.startswith("```") or line.startswith("~~~"):
                fences.append((fence_lang or "plain", fence_start, fence_lines))
                in_fence = False
            else:
                fence_lines += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            in_fence = True
            fence_lang = fence.group(2)
            fence_start = idx
            fence_lines = 0
            continue

        match = HEADING_RE.match(line)
        if match and len(headings) < MAX_HEADINGS:
            headings.append((len(match.group(1)), idx, match.group(2).strip()))
        if "|" in line and line.count("|") >= 2:
            table_lines += 1

    if in_fence:
        fences.append((fence_lang or "plain", fence_start, fence_lines))

    if not headings and len(text) <= MAX_SAMPLE_CHARS * 2:
        return text, {"kind": "markdown", "ok": False, "note": "too little structure"}

    out = [
        "# Markdown summary",
        "",
        f"- lines: {len(lines)}",
        f"- headings: {len(headings)} captured",
        f"- code_fences: {len(fences)}",
        f"- table_like_lines: {table_lines}",
    ]
    if headings:
        out += ["", "## Outline"]
        for level, line_no, title in headings:
            indent = "  " * (level - 1)
            out.append(f"{indent}- L{line_no}: {title}")
    if fences:
        out += ["", "## Code Fences"]
        for lang, line_no, count in fences[:MAX_FENCES]:
            out.append(f"- L{line_no}: {lang}, {count} lines")
        hidden = max(0, len(fences) - MAX_FENCES)
        if hidden:
            out.append(f"- ... {hidden} more code fences elided")

    head = _clip(text[:MAX_SAMPLE_CHARS])
    tail = _clip(text[-MAX_SAMPLE_CHARS:]) if len(text) > MAX_SAMPLE_CHARS else ""
    out += ["", "## Start Sample", head]
    if tail and tail != head:
        out += ["", "## End Sample", tail]

    digest = "\n".join(out) + "\n"
    return digest, {
        "kind": "markdown",
        "ok": True,
        "lines": len(lines),
        "headings": len(headings),
        "code_fences": len(fences),
        "table_lines": table_lines,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
