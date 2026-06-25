"""PDF -> Markdown.

Our own small extractor. Prefers pdfplumber when installed (better tables),
falls back to pypdf for plain text. Either way the output is page-delimited
Markdown so the agent can quote and search it instead of paying per-page image
cost.
"""

from __future__ import annotations

from typing import Tuple

# Safety caps. A hostile or pathological PDF could declare an enormous page
# count or decompress into gigabytes of text; since the Read hook runs this
# automatically on untrusted files, we bound both the work and the disk write.
MAX_PAGES = 2000
MAX_OUTPUT_CHARS = 5_000_000  # ~1.25M tokens of text; well past any real doc

_TRUNCATED = "\n\n> _[justokenmax: output truncated — document exceeds safety caps]_\n"

# Raster images (logos, charts, diagrams) are dropped — we extract text only.
# Leaving a per-page marker so a reader/agent knows visual content existed and
# can read the source page if it matters, instead of silently losing it.
_IMG_NOTE = ("\n> _[justokenmax: {n} image(s) on this page not extracted — "
             "read the source page if visual data matters]_")


def _clean(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    # collapse 3+ blank lines to a single blank line
    out, blanks = [], 0
    for ln in lines:
        if ln.strip():
            blanks = 0
            out.append(ln)
        else:
            blanks += 1
            if blanks <= 1:
                out.append("")
    return "\n".join(out).strip()


def _table_to_md(table) -> str:
    """Render a pdfplumber table (list of rows) as a GitHub Markdown table."""
    rows = [[("" if c is None else str(c).replace("\n", " ").strip()) for c in row]
            for row in table if any(c is not None and str(c).strip() for c in row)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    md = ["| " + " | ".join(header) + " |",
          "| " + " | ".join(["---"] * width) + " |"]
    md += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(md)


def _assemble(parts: list, n_pages: int, truncated: bool) -> Tuple[str, int]:
    out = "\n".join(parts).strip() + "\n"
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + _TRUNCATED
        truncated = True
    if truncated and not out.endswith(_TRUNCATED):
        out = out.rstrip("\n") + _TRUNCATED
    return out, n_pages


def _with_pdfplumber(path: str) -> Tuple[str, int]:
    import pdfplumber

    parts = []
    chars = 0
    truncated = False
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            if i > MAX_PAGES or chars > MAX_OUTPUT_CHARS:
                truncated = True
                break
            parts.append(f"## Page {i}\n")
            text = page.extract_text() or ""
            if text.strip():
                cleaned = _clean(text)
                chars += len(cleaned)
                parts.append(cleaned)
            for table in page.extract_tables() or []:
                md = _table_to_md(table)
                if md:
                    chars += len(md)
                    parts.append("\n" + md)
            if page.images:
                parts.append(_IMG_NOTE.format(n=len(page.images)))
            parts.append("")
    return _assemble(parts, n_pages, truncated)


def _with_pypdf(path: str) -> Tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    n_pages = len(reader.pages)
    parts = []
    chars = 0
    truncated = False
    for i, page in enumerate(reader.pages, 1):
        if i > MAX_PAGES or chars > MAX_OUTPUT_CHARS:
            truncated = True
            break
        parts.append(f"## Page {i}\n")
        cleaned = _clean(page.extract_text() or "")
        chars += len(cleaned)
        parts.append(cleaned)
        # pypdf decodes image XObjects on access and can raise on exotic
        # filters; stay fail-open and just skip the marker if so.
        try:
            n_img = len(page.images)
        except Exception:
            n_img = 0
        if n_img:
            parts.append(_IMG_NOTE.format(n=n_img))
        parts.append("")
    return _assemble(parts, n_pages, truncated)


def pdf_to_markdown(path: str) -> Tuple[str, int]:
    """Return (markdown, page_count). Uses pdfplumber if available."""
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        return _with_pypdf(path)
    return _with_pdfplumber(path)
