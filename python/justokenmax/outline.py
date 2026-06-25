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
from typing import List, Tuple

from . import codeindex, config, tokens

# Symbol kinds that live inside another symbol (indented in the outline). Every
# other kind is treated as top-level/exported and ranked first under a budget.
_NESTED_KINDS = ("method", "field")


def _span(s: dict) -> str:
    """Line pointer for a symbol: 'start-end' when an end span is known."""
    line = s["line"]
    end = s.get("end")
    if end and end > line:
        return f"{line}-{end}"
    return str(line)


def _render(syms: List[dict], rel: str, lang: str, total: int,
            n_dropped: int = 0) -> str:
    head = f"# outline: {rel} ({lang}) — {total} symbols"
    lines = [head]
    for s in syms:
        indent = "  " if s["kind"] in _NESTED_KINDS else ""
        doc = f"  — {s['doc']}" if s.get("doc") else ""
        lines.append(f"{_span(s):>9}  {indent}{s['sig']}{doc}")
    if n_dropped > 0:
        lines.append(f"... ({n_dropped} more symbols)")
    return "\n".join(lines) + "\n"


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
    total = len(syms)
    text = _render(syms, rel, lang, total)

    # Token budget: if the full outline overruns the ceiling, keep the most
    # salient symbols (top-level/exported first, then source order) and mark the
    # remainder. Deterministic — ranking depends only on kind + source line, and
    # selection grows a budget greedily in that order (one render at the end).
    budget = config.max_read_tokens()
    capped = False
    if budget > 0 and tokens.text_tokens(text) > budget:
        capped = True
        ranked = sorted(
            range(total),
            key=lambda i: (syms[i]["kind"] in _NESTED_KINDS, syms[i]["line"]),
        )
        kept: List[int] = []
        for i in ranked:
            trial = kept + [i]
            candidate = _render([syms[j] for j in sorted(trial)], rel, lang,
                                total, total - len(trial))
            if tokens.text_tokens(candidate) > budget and kept:
                break
            kept = trial
        kept_syms = [syms[j] for j in sorted(kept)]
        text = _render(kept_syms, rel, lang, total, total - len(kept_syms))

    stats = {"kind": "outline", "ok": True, "symbols": total, "lang": lang}
    if capped:
        stats["capped"] = True
        stats["shown"] = len(text.splitlines()) - 2  # minus header + "...more"
    return text, stats
