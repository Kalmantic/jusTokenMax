#!/usr/bin/env python3
"""justokenmax benchmark harness.

Measures how much justokenmax reduces the token cost of attachments. It runs on
whatever you drop into ``benchmarks/fixtures/`` (PDFs and images); if that
folder is empty it generates representative samples so the benchmark runs out
of the box.

Token counting is deliberately honest:
  * The Markdown (post-conversion) side is counted with a REAL tokenizer
    (tiktoken/cl100k) when available, falling back to a chars/4 estimate.
  * The PDF "before" side uses Anthropic's documented image-token model: a page
    is ingested as a page-image costing ~(w*h)/750 tokens after the API clamps
    it to <=1568px / <=1.15MP. For a US-letter page that lands ~1.5k tokens.

Run:  python benchmarks/benchmark.py            # uses/creates fixtures
      python benchmarks/benchmark.py --fetch    # also try to download real PDFs
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))
FIXTURES = os.path.join(HERE, "fixtures")

from justokenmax import codeindex                     # noqa: E402
from justokenmax.image import compress_image          # noqa: E402
from justokenmax.logs import compress_log             # noqa: E402
from justokenmax.pdf import pdf_to_markdown            # noqa: E402
from justokenmax.tokens import (                       # noqa: E402
    MAX_EDGE,
    PDF_PAGE_IMAGE_TOKENS,
    bytes_to_tokens,
)

# Public PDFs worth benchmarking if --fetch and network are available.
SAMPLE_URLS = [
    "https://www.irs.gov/pub/irs-pdf/fw9.pdf",   # IRS W-9 tax form, ~6 pages
    "https://arxiv.org/pdf/1706.03762",          # "Attention Is All You Need"
]


# --------------------------------------------------------------------------- #
# token counting
# --------------------------------------------------------------------------- #
def count_text_tokens(text: str):
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken/cl100k"
    except Exception:
        return max(1, len(text) // 4), "estimate(chars/4)"


# --------------------------------------------------------------------------- #
# fixture generation (guaranteed fallback)
# --------------------------------------------------------------------------- #
_PROSE = (
    "The optimizer reduces the cost of attachments by converting them into the "
    "cheapest faithful representation before they enter the model's context. A "
    "page of a portable document is normally rendered as an image and billed by "
    "its pixel area, which is wasteful when the page is mostly text. Extracting "
    "the underlying characters into structured markdown preserves the meaning "
    "while collapsing the token footprint, and the result is searchable, "
    "quotable, and easy to diff against later revisions of the same document. "
)


def _wrap_pages(n_pages: int, lines_per_page: int = 42, width: int = 88):
    body = (_PROSE * 60)
    wrapped = textwrap.wrap(body, width=width)
    # repeat until we have enough lines for the requested page count
    need = n_pages * lines_per_page
    while len(wrapped) < need:
        wrapped += wrapped
    pages = [wrapped[i * lines_per_page:(i + 1) * lines_per_page]
             for i in range(n_pages)]
    return pages


def _build_multipage_pdf(path: str, n_pages: int):
    """Write a valid multi-page, text-heavy PDF with a correct xref table."""
    pages = _wrap_pages(n_pages)

    objects = []  # 1=catalog, 2=pages, then per page: [page, content]; font last
    # placeholders; we know the numbering up front
    n = n_pages
    page_obj_ids = [3 + 2 * i for i in range(n)]
    content_obj_ids = [4 + 2 * i for i in range(n)]
    font_id = 3 + 2 * n

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")  # obj 1
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("latin-1")
    )  # obj 2

    page_blobs, content_blobs = [], []
    for i in range(n):
        stream_lines = ["BT", "/F1 11 Tf", "54 760 Td", "13 TL"]
        for j, line in enumerate(pages[i]):
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({esc}) Tj" if j == 0 else f"T* ({esc}) Tj")
        stream_lines.append("ET")
        content = "\n".join(stream_lines).encode("latin-1")
        content_blobs.append(
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
            + content + b"\nendstream"
        )
        page_blobs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_obj_ids[i]} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode("latin-1")
        )

    # interleave page/content objects in id order (3,4,5,6,...)
    for i in range(n):
        objects.append(page_blobs[i])
        objects.append(content_blobs[i])
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n".encode(
        "latin-1"
    )
    out += b"%%EOF"
    with open(path, "wb") as f:
        f.write(out)


def _build_sample_image(path: str):
    """A smooth gradient + light noise PNG — representative of a screenshot."""
    from PIL import Image

    w, h = 3000, 2000
    img = Image.new("RGB", (w, h))
    px = img.load()
    noise = os.urandom(w)  # one row of noise reused, cheap + light
    for y in range(h):
        base = int(255 * y / h)
        for x in range(w):
            n = noise[x % w] >> 5  # 0..7 light dithering
            px[x, y] = ((base + x) % 256, (base) % 256, (255 - base + n) % 256)
    img.save(path, "PNG")


def ensure_fixtures(do_fetch: bool):
    os.makedirs(FIXTURES, exist_ok=True)
    if do_fetch:
        for url in SAMPLE_URLS:
            base = os.path.basename(url)
            if not base.lower().endswith(".pdf"):
                base += ".pdf"
            name = os.path.join(FIXTURES, base)
            if os.path.exists(name):
                continue
            try:
                subprocess.run(
                    ["curl", "-fsSL", "--max-time", "20", "-o", name, url],
                    check=True,
                )
                print(f"  fetched {url}")
            except Exception:
                if os.path.exists(name):
                    os.remove(name)
                print(f"  (skip) could not fetch {url}")

    pdfs = glob.glob(os.path.join(FIXTURES, "*.pdf"))
    if not pdfs:
        print("  generating sample PDFs (no fixtures found)")
        _build_multipage_pdf(os.path.join(FIXTURES, "sample-10page.pdf"), 10)
        _build_multipage_pdf(os.path.join(FIXTURES, "sample-30page.pdf"), 30)

    imgs = _images()
    if not imgs:
        print("  generating sample image")
        _build_sample_image(os.path.join(FIXTURES, "sample-screenshot.png"))


def _images():
    out = []
    for ext in ("png", "jpg", "jpeg", "webp"):
        out += glob.glob(os.path.join(FIXTURES, f"*.{ext}"))
    return sorted(out)


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def human(n):
    return f"{n:,}"


def bench_pdfs():
    rows = []
    for path in sorted(glob.glob(os.path.join(FIXTURES, "*.pdf"))):
        md, pages = pdf_to_markdown(path)
        after, tk = count_text_tokens(md)
        # A PDF is billed as text + a per-page image; Markdown keeps the text
        # and drops the image channel. before = text + images; after = text.
        before = after + pages * PDF_PAGE_IMAGE_TOKENS
        if before == 0:
            continue
        pct = 100 * (before - after) // before
        rows.append((os.path.basename(path), pages, before, after, pct, tk))
    return rows


def bench_images():
    rows = []
    tmp = os.path.join(FIXTURES, ".out")
    os.makedirs(tmp, exist_ok=True)
    for path in _images():
        out = os.path.join(tmp, os.path.basename(path))
        try:
            _, st = compress_image(path, out, max_edge=MAX_EDGE, quality=80)
        except Exception as e:  # skip unreadable
            print(f"  (skip image) {path}: {e}")
            continue
        bb, ba = st["bytes_before"], st["bytes_after"]
        tb, ta = bytes_to_tokens(bb), bytes_to_tokens(ba)
        bpct = 100 * (bb - ba) // bb if bb else 0
        rows.append((os.path.basename(path), st["orig_size"], st["new_size"],
                     bb, ba, bpct, tb, ta))
    return rows


def _representative_log() -> str:
    lines = ["[12:00:00] INFO build started"]
    for i in range(4000):
        lines.append(f"[12:00:0{i % 9}] DEBUG compiling module_{i} "
                     f"with flags --opt --verbose --target=es2020")
    lines += ["[12:00:30] WARN  resolving dependency tree"] * 300
    lines += ["Traceback (most recent call last):"]
    lines += [f'  File "src/mod_{i}.py", line {i*7}, in handler_{i}'
              for i in range(40)]
    lines += ["TypeError: cannot read property 'x' of undefined",
              "[12:00:59] ERROR build failed", "Done in 59.2s"]
    return "\n".join(lines)


def bench_logs():
    rows = []
    paths = sorted(glob.glob(os.path.join(FIXTURES, "*.log")))
    if not paths:
        p = os.path.join(FIXTURES, "sample-build.log")
        with open(p, "w") as f:
            f.write(_representative_log())
        paths = [p]
    for path in paths:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        digest, st = compress_log(raw)
        tb, _ = count_text_tokens(raw)
        ta, _ = count_text_tokens(digest)
        pct = 100 * (tb - ta) // tb if tb else 0
        rows.append((os.path.basename(path), st["lines_before"],
                     st["lines_after"], tb, ta, pct))
    return rows


def _representative_json() -> str:
    import json as _json
    data = {
        "status": "ok",
        "page": 1,
        "results": [
            {"id": i, "title": f"record number {i}",
             "tags": ["alpha", "beta", "gamma"],
             "description": "lorem ipsum dolor sit amet " * 6,
             "active": i % 3 == 0}
            for i in range(2000)
        ],
    }
    return _json.dumps(data, indent=2)


def bench_json():
    from justokenmax.jsoncompress import compress_json
    rows = []
    paths = sorted(glob.glob(os.path.join(FIXTURES, "*.json")))
    if not paths:
        p = os.path.join(FIXTURES, "sample-response.json")
        with open(p, "w") as f:
            f.write(_representative_json())
        paths = [p]
    for path in paths:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        digest, st = compress_json(raw)
        if not st.get("ok"):
            continue
        tb, _ = count_text_tokens(raw)
        ta, _ = count_text_tokens(digest)
        pct = 100 * (tb - ta) // tb if tb else 0
        rows.append((os.path.basename(path), tb, ta, pct))
    return rows


def bench_index():
    """Cost of finding a symbol via the index vs reading its whole file.

    Indexes justokenmax's own source, then for each module's first symbol compares
    the tokens to read the entire containing file against the tokens of a single
    `justokenmax query` hit line.
    """
    root = os.path.join(ROOT, "python")
    idx = codeindex.build_index(root)
    # one representative symbol per file
    seen, picks = set(), []
    for s in idx["symbols"]:
        if s["file"] not in seen:
            seen.add(s["file"])
            picks.append(s)
    file_tok_sum = hit_tok_sum = 0
    for s in picks:
        full = Path(os.path.join(root, s["file"])).read_text(
            encoding="utf-8", errors="replace")
        file_tok_sum += count_text_tokens(full)[0]
        hit_tok_sum += count_text_tokens(codeindex.format_hits([s]))[0]
    pct = 100 * (file_tok_sum - hit_tok_sum) // file_tok_sum if file_tok_sum else 0
    return {"symbols": len(idx["symbols"]), "files": idx["files"],
            "lookups": len(picks), "file_tokens": file_tok_sum,
            "hit_tokens": hit_tok_sum, "pct": pct}


def _count2(text):
    return count_text_tokens(text)[0]


def bench_notebook():
    import json as _json
    from justokenmax.notebook import notebook_to_markdown
    cells = [{"cell_type": "markdown", "source": ["# Report\n"]}]
    for i in range(20):
        cells.append({"cell_type": "code", "source": [f"plot(df{i})\n"],
                      "outputs": [
                          {"output_type": "display_data",
                           "data": {"image/png": "P" * 40000}},
                          {"output_type": "stream", "text": [f"rows: {i}\n"]}]})
    raw = _json.dumps({"cells": cells, "metadata": {}, "nbformat": 4})
    md, _ = notebook_to_markdown(raw)
    tb, ta = _count2(raw), _count2(md)
    return tb, ta, (100 * (tb - ta) // tb if tb else 0)


def bench_csv():
    from justokenmax.csvtable import compress_csv
    rows = ["id,name,score,active"]
    rows += [f"{i},name{i},{i * 1.5},{'true' if i % 2 == 0 else 'false'}"
             for i in range(5000)]
    raw = "\n".join(rows) + "\n"
    md, _ = compress_csv(raw)
    tb, ta = _count2(raw), _count2(md)
    return tb, ta, (100 * (tb - ta) // tb if tb else 0)


def _build_sample_deck(path, n_slides=12):
    """A representative deck: titled slides with bullets, one data table, a few
    images, and speaker notes — enough to exercise the extractor honestly."""
    from pptx import Presentation
    from pptx.util import Inches
    from PIL import Image

    prs = Presentation()
    for i in range(n_slides):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = f"Section {i}: findings and next steps"
        body = slide.placeholders[1].text_frame
        body.text = "Headline takeaway for this section"
        for b in ("supporting detail with measurable impact",
                  "second point that motivates the recommendation",
                  "owner and timeline for the follow-up action"):
            p = body.add_paragraph(); p.text = b; p.level = 1
        slide.notes_slide.notes_text_frame.text = (
            "Speaker note: emphasise the ROI figure and pause for questions.")
        if i % 4 == 0:  # a couple of image-bearing slides
            img = os.path.join(FIXTURES, f"_deckimg{i}.png")
            Image.new("RGB", (32, 32), (i * 10 % 255, 80, 160)).save(img)
            slide.shapes.add_picture(img, Inches(6), Inches(1))
    tbl_slide = prs.slides.add_slide(prs.slide_layouts[5])
    tbl_slide.shapes.title.text = "Metrics"
    tbl = tbl_slide.shapes.add_table(4, 3, Inches(1), Inches(2),
                                     Inches(8), Inches(3)).table
    for c, h in enumerate(("metric", "baseline", "target")):
        tbl.cell(0, c).text = h
    for r in range(1, 4):
        tbl.cell(r, 0).text = f"KPI {r}"
        tbl.cell(r, 1).text = str(r * 10)
        tbl.cell(r, 2).text = str(r * 15)
    prs.save(path)


def bench_pptx():
    """PPTX is conversion, not compression: the text was already text, so tokens
    are preserved (before == after). The win is that an otherwise-opaque binary
    deck becomes readable structured Markdown with its dropped visuals flagged.
    Reported honestly — no fake reduction %."""
    try:
        import pptx  # noqa: F401
    except ImportError:
        return None
    from justokenmax.pptx import pptx_to_markdown
    path = os.path.join(FIXTURES, "sample-deck.pptx")
    if not os.path.exists(path):
        _build_sample_deck(path)
    md, stats = pptx_to_markdown(path)
    return {"slides": stats["slides"], "images": stats["images"],
            "charts": stats["charts"], "tables": stats["tables"],
            "tokens": _count2(md)}


def bench_delta():
    import difflib
    base = [f"line {i}" for i in range(600)]
    edited = list(base)
    edited[300] = "line 300 EDITED"
    edited.insert(50, "a newly inserted line")
    full = "\n".join(edited) + "\n"
    diff = "".join(difflib.unified_diff([x + "\n" for x in base],
                                        [x + "\n" for x in edited]))
    tb, ta = _count2(full), _count2(diff)
    return tb, ta, (100 * (tb - ta) // tb if tb else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true",
                    help="try to download real public PDFs into fixtures/")
    args = ap.parse_args()

    print("jusTokenMax benchmark")
    print("====================")
    ensure_fixtures(args.fetch)

    pdf_rows = bench_pdfs()
    img_rows = bench_images()
    log_rows = bench_logs()
    json_rows = bench_json()
    nb_tb, nb_ta, nb_pct = bench_notebook()
    csv_tb, csv_ta, csv_pct = bench_csv()
    d_tb, d_ta, d_pct = bench_delta()
    pptx_row = bench_pptx()
    idx = bench_index()

    lines = []
    lines.append("# jusTokenMax benchmark results\n")
    lines.append("_Token counts: Markdown side via "
                 f"`{pdf_rows[0][5] if pdf_rows else 'n/a'}`; PDF 'before' via "
                 f"Anthropic page-image model (~{PDF_PAGE_IMAGE_TOKENS} tok/page)._\n")

    lines.append("\n## PDF -> Markdown\n")
    lines.append("| file | pages | tokens before | tokens after | reduction |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    tb_sum = ta_sum = 0
    for name, pages, before, after, pct, _ in pdf_rows:
        tb_sum += before
        ta_sum += after
        lines.append(f"| {name} | {pages} | {human(before)} | {human(after)} | "
                     f"**-{pct}%** |")
    if pdf_rows:
        opct = 100 * (tb_sum - ta_sum) // tb_sum
        lines.append(f"| **total** | | **{human(tb_sum)}** | **{human(ta_sum)}** "
                     f"| **-{opct}%** |")

    lines.append("\n## Image compression\n")
    lines.append("| file | orig px | new px | bytes before | bytes after | "
                 "bytes saved | base64 tokens before→after |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
    for name, osz, nsz, bb, ba, bpct, tb, ta in img_rows:
        lines.append(
            f"| {name} | {osz[0]}x{osz[1]} | {nsz[0]}x{nsz[1]} | "
            f"{human(bb)} | {human(ba)} | **-{bpct}%** | "
            f"{human(tb)} → {human(ta)} |"
        )
    lines.append("\n_Image note: native-vision models downscale to <=1568px "
                 "anyway, so the byte savings translate to token savings only in "
                 "pipelines that inline images as base64._\n")

    lines.append("\n## Log compression\n")
    lines.append("| file | lines before | lines after | tokens before | "
                 "tokens after | reduction |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, lb, la, tb, ta, pct in log_rows:
        lines.append(f"| {name} | {human(lb)} | {human(la)} | {human(tb)} | "
                     f"{human(ta)} | **-{pct}%** |")

    lines.append("\n## JSON / structured-output compression\n")
    lines.append("| file | tokens before | tokens after | reduction |")
    lines.append("| --- | ---: | ---: | ---: |")
    for name, tb, ta, pct in json_rows:
        lines.append(f"| {name} | {human(tb)} | {human(ta)} | **-{pct}%** |")

    lines.append("\n## Notebook / CSV / delta\n")
    lines.append("| input | tokens before | tokens after | reduction |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(f"| notebook (20 cells, image outputs) | {human(nb_tb)} | "
                 f"{human(nb_ta)} | **-{nb_pct}%** |")
    lines.append(f"| CSV (5,000 rows) | {human(csv_tb)} | {human(csv_ta)} | "
                 f"**-{csv_pct}%** |")
    lines.append(f"| delta re-read (1 edit in 600 lines) | {human(d_tb)} | "
                 f"{human(d_ta)} | **-{d_pct}%** |")

    if pptx_row:
        lines.append("\n## PowerPoint (.pptx) — conversion, not compression\n")
        lines.append("A deck's text is already text, so tokens are preserved "
                     "(before == after). The win is that an opaque binary deck "
                     "becomes readable structured Markdown — titles, bullets, "
                     "tables, speaker notes — with every dropped image/chart "
                     "flagged per slide so visual-only slides never vanish "
                     "silently.\n")
        lines.append("| input | slides | tables | images flagged | "
                     "extracted tokens |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        lines.append(f"| sample deck | {pptx_row['slides']} | "
                     f"{pptx_row['tables']} | {pptx_row['images']} | "
                     f"{human(pptx_row['tokens'])} |")

    lines.append("\n## Code index (read symbols, not files)\n")
    lines.append(f"Indexed **{human(idx['symbols'])} symbols** across "
                 f"**{idx['files']} files**. Cost to locate a symbol, summed over "
                 f"{idx['lookups']} lookups:\n")
    lines.append("| approach | tokens |")
    lines.append("| --- | ---: |")
    lines.append(f"| read each whole file | {human(idx['file_tokens'])} |")
    lines.append(f"| one `justokenmax query` hit each | {human(idx['hit_tokens'])} |")
    lines.append(f"| **reduction** | **-{idx['pct']}%** |")

    report = "\n".join(lines)
    print("\n" + report)
    with open(os.path.join(HERE, "RESULTS.md"), "w") as f:
        f.write(report + "\n")
    print(f"\nwrote {os.path.join(HERE, 'RESULTS.md')}")


if __name__ == "__main__":
    main()
