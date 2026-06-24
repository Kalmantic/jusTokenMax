"""CSV / TSV sampling.

A big table doesn't need every row in context to be understood — the agent needs
the shape: how many rows, what the columns are and their types, and a handful of
representative rows. This emits exactly that as a compact Markdown digest.

Our own code; stdlib `csv` only.
"""

from __future__ import annotations

import csv
import io
from typing import List, Tuple


def _sniff_delim(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ""
        return "\t" if "\t" in first else ","


def _looks_int(v: str) -> bool:
    try:
        int(v)
    except ValueError:
        return False
    return True


def _looks_float(v: str) -> bool:
    try:
        float(v)
    except ValueError:
        return False
    return True


def _infer_type(values: List[str]) -> str:
    seen = set()
    for v in values:
        v = v.strip()
        if v == "":
            continue
        if v.lower() in ("true", "false"):
            seen.add("bool")
            continue
        if _looks_int(v):
            seen.add("int")
            continue
        if _looks_float(v):
            seen.add("float")
            continue
        seen.add("str")
    if not seen:
        return "empty"
    if seen == {"int"}:
        return "int"
    if seen <= {"int", "float"}:
        return "float"
    if seen == {"bool"}:
        return "bool"
    return "str"


def _md_table(header: List[str], rows: List[List[str]]) -> str:
    width = len(header)
    norm = [(r + [""] * width)[:width] for r in rows]
    cells = [[c.replace("|", "\\|").replace("\n", " ") for c in r] for r in norm]
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in cells]
    return "\n".join(out)


def compress_csv(text: str, sample: int = 5) -> Tuple[str, dict]:
    """Return (markdown_digest, stats)."""
    delim = _sniff_delim(text[:8192])
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return text, {"kind": "csv", "ok": False, "note": "empty"}

    header = rows[0]
    body = rows[1:]
    n = len(body)
    ncol = len(header)
    types = [_infer_type([r[c] for r in body if c < len(r)])
             for c in range(ncol)]

    head = body[:sample]
    tail = body[-sample:] if n > 2 * sample else []
    table_rows = head + ([["…"] * ncol] if tail else []) + tail

    out = [f"# CSV digest — {n} rows × {ncol} columns (delimiter {delim!r})", ""]
    out.append("## Schema")
    out += [f"- {col}: {t}" for col, t in zip(header, types)]
    out.append("")
    span = f"first {len(head)}" + (f" + last {len(tail)}" if tail else "")
    out.append(f"## Sample rows ({span} of {n})")
    out.append(_md_table(header, table_rows))
    md = "\n".join(out) + "\n"

    stats = {"kind": "csv", "ok": True, "rows": n, "cols": ncol,
             "delimiter": delim}
    return md, stats
