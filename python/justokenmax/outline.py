"""File outline — a file's shape (signatures + line numbers), not its body.

When the agent needs to understand a file's structure but not every line, the
outline is ~10-20x cheaper than reading it: every function/class/method with its
signature, line number, and first docstring line — no bodies. Read the full
range only for the symbol you actually care about.

Reuses the same parsers as the code index (Python via stdlib `ast`; JS/TS/Go/
Rust/Java/Ruby/C++ via regex).
"""

from __future__ import annotations

import os
from typing import Tuple

from . import codeindex


def file_outline(path: str) -> Tuple[str, dict]:
    """Return (outline_text, stats) for a source file."""
    ext = os.path.splitext(path)[1].lower()
    lang = codeindex.LANGS.get(ext)
    if not lang:
        return "", {"kind": "outline", "ok": False, "note": "unsupported language"}

    rel = os.path.basename(path)
    syms = codeindex.parse_file(path, rel, lang)
    if not syms:
        return "", {"kind": "outline", "ok": False, "note": "no symbols found"}

    syms.sort(key=lambda s: s["line"])
    lines = [f"# outline: {rel} ({lang}) — {len(syms)} symbols"]
    for s in syms:
        indent = "  " if s["kind"] == "method" else ""
        doc = f"  — {s['doc']}" if s.get("doc") else ""
        lines.append(f"{s['line']:>5}  {indent}{s['sig']}{doc}")
    text = "\n".join(lines) + "\n"

    stats = {"kind": "outline", "ok": True, "symbols": len(syms), "lang": lang}
    return text, stats
