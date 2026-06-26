"""XLSX -> Markdown digest.

A spreadsheet doesn't need every row in context to be understood — the agent
needs the shape: the sheets, their columns and types, the row counts, and a
handful of representative rows. This mirrors what csvtable does for CSV, per
sheet, and is the one Office format that genuinely compresses (thousands of
rows -> schema + sample).

Thin extractor over openpyxl. Read in read-only + data-only mode: read-only so a
huge workbook streams instead of loading whole, data-only so formula cells yield
their last cached value ("1,200") rather than the raw formula ("=A1*B1").
"""

from __future__ import annotations

import zipfile
from collections import deque
from typing import List, Tuple

# Safety cap, same rationale as pdf.py — the Read hook runs this on untrusted
# files, so bound the work and the disk write.
MAX_OUTPUT_CHARS = 5_000_000
# Very wide sheets are capped so one monster sheet can't blow the budget.
MAX_COLS = 20
# Rows sampled from the head and the tail of each sheet.
SAMPLE = 20
# Rows scanned to infer each column's type (a sample is enough).
TYPE_SCAN = 200

_TRUNCATED = "\n\n> _[justokenmax: output truncated — workbook exceeds safety caps]_\n"

# Embedded images and charts are dropped — we extract tabular text only. Flag
# them at the workbook level so visual content isn't lost silently (mirrors
# pdf.py). Charts are a distinct, common case: a financial model's chart is its
# whole point, yet it carries no row data, so without this it vanishes silently.
def _visual_note(images: int, charts: int) -> str:
    """Build the dropped-visual marker from whatever is present. Keeps the
    'image(s) in this workbook not extracted' phrasing when images exist so the
    note reads naturally for the common image-only case."""
    parts = []
    if images:
        parts.append(f"{images} image(s)")
    if charts:
        parts.append(f"{charts} chart(s)")
    what = " and ".join(parts)
    return (f"> _[justokenmax: {what} in this workbook not extracted — "
            "read the source if visual data matters]_")


def _count_images(path: str) -> int:
    """Images live as members under xl/media/ in the .xlsx ZIP. Counting them
    there is cheap and independent of the read-only load. Fail-open: 0 on error."""
    try:
        with zipfile.ZipFile(path) as z:
            return sum(1 for n in z.namelist() if n.startswith("xl/media/"))
    except Exception:
        return 0


def _count_charts(path: str) -> int:
    """Charts live as xl/charts/chartN.xml members in the .xlsx ZIP (separate
    from xl/media/, so the image count never sees them). Fail-open: 0 on error."""
    try:
        with zipfile.ZipFile(path) as z:
            return sum(1 for n in z.namelist()
                       if n.startswith("xl/charts/chart") and n.endswith(".xml"))
    except Exception:
        return 0


def _infer_type(values: list) -> str:
    """Column type from sampled cell values (openpyxl returns native types)."""
    seen = set()
    for v in values:
        if v is None or v == "":
            continue
        if isinstance(v, bool):          # bool is a subclass of int — check first
            seen.add("bool")
        elif isinstance(v, int):
            seen.add("int")
        elif isinstance(v, float):
            seen.add("float")
        else:
            # datetime/date have an isoformat; everything else is a string
            seen.add("datetime" if hasattr(v, "isoformat") else "str")
    if not seen:
        return "empty"
    if seen == {"int"}:
        return "int"
    if seen <= {"int", "float"}:
        return "float"
    if seen == {"bool"}:
        return "bool"
    if seen == {"datetime"}:
        return "datetime"
    return "str"


def _cell(v) -> str:
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


def _md_table(header: List[str], rows: List[list]) -> str:
    width = len(header)
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    for r in rows:
        padded = (list(r) + [None] * width)[:width]
        out.append("| " + " | ".join(_cell(c) for c in padded) + " |")
    return "\n".join(out)


def _sheet_digest(name: str, header: list, head: list, tail: list,
                  n: int, ncols: int, types: List[str]) -> str:
    shown_cols = min(ncols, MAX_COLS)
    hdr = [_cell(h) for h in header[:shown_cols]]
    col_note = (f" (+{ncols - shown_cols} columns not shown)"
                if ncols > shown_cols else "")

    parts = [f"## Sheet: {name} — {n} rows × {ncols} columns{col_note}", ""]
    parts.append("### Schema")
    parts += [f"- {h}: {t}" for h, t in zip(hdr, types[:shown_cols])]
    parts.append("")

    def clip(row):
        return list(row[:shown_cols])

    if n > 2 * SAMPLE:
        sample_rows = [clip(r) for r in head] + [["…"] * shown_cols] + \
                      [clip(r) for r in tail]
        span = f"first {len(head)} + last {len(tail)} of {n}"
        hidden = n - len(head) - len(tail)
        parts.append(f"### Sample rows ({span}; {hidden} rows not shown)")
    else:
        sample_rows = [clip(r) for r in head]
        parts.append(f"### Rows ({n})")
    parts.append(_md_table(hdr, sample_rows))
    parts.append("")
    return "\n".join(parts)


def xlsx_to_markdown(path: str) -> Tuple[str, str, dict]:
    """Return (digest, full_render, stats).

    digest is the schema + head/tail sample written to the cache; full_render is
    every row of every sheet as text — the honest "before" baseline (what dumping
    the whole workbook into context would cost), used by optimize() to compute a
    real reduction. stats = {sheets, total_rows, images}.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    digest_parts: List[str] = []
    full_parts: List[str] = []
    full_chars = 0
    sheets = 0
    total_rows = 0

    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                continue  # empty sheet
            sheets += 1
            ncols = len(header)
            head: list = []
            tail: deque = deque(maxlen=SAMPLE)
            type_cols: List[list] = [[] for _ in range(min(ncols, MAX_COLS))]
            n = 0

            full_parts.append(f"# {ws.title}")
            if full_chars < MAX_OUTPUT_CHARS:
                line = "\t".join(_cell(c) for c in header)
                full_parts.append(line)
                full_chars += len(line)

            for row in rows:
                n += 1
                if len(head) < SAMPLE:
                    head.append(row)
                tail.append(row)
                if n <= TYPE_SCAN:
                    for c in range(min(ncols, MAX_COLS)):
                        type_cols[c].append(row[c] if c < len(row) else None)
                if full_chars < MAX_OUTPUT_CHARS:
                    line = "\t".join(_cell(c) for c in row)
                    full_parts.append(line)
                    full_chars += len(line)

            total_rows += n
            # tail overlaps head when the sheet is small; only show a distinct
            # tail when there are genuinely unseen middle rows.
            tail_rows = list(tail) if n > 2 * SAMPLE else []
            types = [_infer_type(col) for col in type_cols]
            digest_parts.append(_sheet_digest(ws.title, list(header), head,
                                              tail_rows, n, ncols, types))
    finally:
        wb.close()

    images = _count_images(path)
    charts = _count_charts(path)
    if images or charts:
        digest_parts.append(_visual_note(images, charts))

    digest = "\n".join(digest_parts).strip() + "\n"
    if len(digest) > MAX_OUTPUT_CHARS:
        digest = digest[:MAX_OUTPUT_CHARS] + _TRUNCATED
    full_render = "\n".join(full_parts).strip() + "\n"

    return digest, full_render, {"sheets": sheets, "total_rows": total_rows,
                                 "images": images, "charts": charts}
