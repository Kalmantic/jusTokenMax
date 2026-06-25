"""Log / tool-output compression.

Verbose logs (build output, test runs, CI, stack traces) are a major token sink
and are mostly noise: ANSI colour codes, progress spam, and the same line
repeated hundreds of times. This collapses that into a faithful digest that
keeps everything that matters — errors, warnings, and the head/tail for
orientation — while dropping the redundancy.

Reversible by design: the optimizer caches the original (see optimize.py), so
the full log is one read away if it's ever needed.
"""

from __future__ import annotations

import re
from typing import Tuple

# Strip ANSI colour / cursor escapes.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Lines we never drop, regardless of budget. Tokens are matched loosely (no
# strict word boundary) so CamelCase exceptions like "ValueError" / "TypeError"
# are caught as well as plain words.
_IMPORTANT = re.compile(
    r"(error|fail|failed|failure|fatal|panic|exception|traceback|"
    r"warn|warning|denied|refused|timeout|timed out|cannot|unable|missing|"
    r"undefined|unhandled|segfault|assert)",
    re.IGNORECASE,
)

# Collapsed-repeat marker, e.g. "downloading dep  (x50)" — always worth keeping.
_REPEAT = re.compile(r"\(x\d+\)")

# Stack-trace frame lines (Python "  File ...", JS "    at ...", Java "\tat ...").
_FRAME = re.compile(r"^\s*(at\s+\S|File\s+\"|#\d+\s|\tat\s)")

# Volatile prefixes that make otherwise-identical lines look unique: leading
# timestamps and counters. Stripped only for the dedup comparison, not output.
_VOLATILE = re.compile(
    r"^\s*(\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.,\d]*Z?\]?|"
    r"\[\d{2}:\d{2}:\d{2}[.,\d]*\]|\d+ms|\(\d+/\d+\))\s*"
)

# Volatile tokens that distinguish otherwise-identical lint/type/error lines:
# file paths, line:col positions, hex/pointers, UUIDs, and bare numbers. Stripped
# to build a normalized *signature* so the same complaint groups regardless of
# which file/line it fired on. Order matters (UUID/hex before plain numbers).
_SIG_SUBS = (
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<hex>"),
    # path-like tokens (with a slash and an extension or directory separator)
    (re.compile(r"(?:[\w.\-]+/)+[\w.\-]+"), "<path>"),
    # remaining ":line:col" or ":line" positions
    (re.compile(r":\d+(?::\d+)?\b"), ":<n>"),
    (re.compile(r"\b\d+\b"), "<n>"),
)

HEAD_LINES = 12
TAIL_LINES = 20

# Below this many same-signature notable lines we keep them verbatim; at or above
# we collapse to "<signature> (×N)" plus a couple of concrete examples.
_GROUP_MIN = 3
_GROUP_EXAMPLES = 2


def _dedup_key(line: str) -> str:
    return _VOLATILE.sub("", line).strip()


def _signature(line: str) -> str:
    """Normalize a line into a path/number-free signature for grouping."""
    sig = _ANSI.sub("", line)
    for pat, repl in _SIG_SUBS:
        sig = pat.sub(repl, sig)
    return re.sub(r"\s+", " ", sig).strip()


def _group_notable(lines: list) -> list:
    """Bucket notable lines by normalized signature.

    Runs of >= _GROUP_MIN lines sharing a signature collapse to a single
    "<signature>  (×N)" row plus a couple of verbatim examples; everything else
    is emitted unchanged and in order. Stable: a signature is materialized at the
    position of its first occurrence.
    """
    counts: dict = {}
    examples: dict = {}
    order = []
    for ln in lines:
        sig = _signature(ln)
        if sig not in counts:
            counts[sig] = 0
            examples[sig] = []
            order.append(sig)
        counts[sig] += 1
        if len(examples[sig]) < _GROUP_EXAMPLES:
            examples[sig].append(ln)

    out = []
    emitted = set()
    for ln in lines:
        sig = _signature(ln)
        n = counts[sig]
        if n < _GROUP_MIN:
            out.append(ln)
            continue
        if sig in emitted:
            continue
        emitted.add(sig)
        for ex in examples[sig]:
            out.append(ex)
        out.append(f"    {sig}  (×{n})")
    return out


def compress_log(text: str, head: int = HEAD_LINES, tail: int = TAIL_LINES
                 ) -> Tuple[str, dict]:
    """Return (digest, stats) for a chunk of log text."""
    raw_lines = _ANSI.sub("", text).split("\n")
    n_in = len(raw_lines)

    # 1) Collapse consecutive duplicates (ignoring volatile prefixes).
    collapsed = []
    prev_key = object()
    count = 0
    for ln in raw_lines:
        key = _dedup_key(ln)
        if key == prev_key and key != "":
            count += 1
            continue
        if count > 1:
            collapsed[-1] = f"{collapsed[-1]}  (x{count})"
        collapsed.append(ln)
        prev_key = key
        count = 1
    if count > 1:
        collapsed[-1] = f"{collapsed[-1]}  (x{count})"

    # 2) Budget: keep head + tail + every notable line in between. Notable =
    #    errors/warnings, repeat markers, or stack frames (so traces survive).
    def notable(ln: str) -> bool:
        return bool(_IMPORTANT.search(ln) or _REPEAT.search(ln) or _FRAME.match(ln))

    if len(collapsed) <= head + tail:
        kept = collapsed
    else:
        head_block = collapsed[:head]
        tail_block = collapsed[-tail:]
        middle = collapsed[head:-tail]
        notable_mid = [ln for ln in middle if notable(ln)]
        elided = len(middle) - len(notable_mid)
        # Bucket repetitive notable lines (lint/typecheck/error spam) by a
        # normalized signature so 5000 near-identical complaints become a few
        # "<signature> (×N)" rows instead of 5000 verbatim lines.
        kept_mid = _group_notable(notable_mid)
        kept = list(head_block)
        if elided:
            kept.append(f"    --- {elided} routine lines hidden ---")
        kept.extend(kept_mid)
        kept.extend(tail_block)

    # 3) Fold long runs of stack frames in the kept output to first+last+count.
    folded = []
    i = 0
    while i < len(kept):
        if _FRAME.match(kept[i]):
            j = i
            while j < len(kept) and _FRAME.match(kept[j]):
                j += 1
            run = kept[i:j]
            if len(run) > 4:
                folded.append(run[0])
                folded.append(f"    ... ({len(run) - 2} stack frames elided) ...")
                folded.append(run[-1])
            else:
                folded.extend(run)
            i = j
        else:
            folded.append(kept[i])
            i += 1

    digest = "\n".join(folded).strip() + "\n"
    stats = {
        "kind": "log",
        "lines_before": n_in,
        "lines_after": len(folded),
    }
    return digest, stats
