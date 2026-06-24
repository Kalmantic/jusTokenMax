"""Dispatch an attachment to the right optimizer, with caching + ledger."""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

from . import cache
from .tokens import pdf_image_tokens, text_tokens

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
LOG_EXTS = {".log"}
JSON_EXTS = {".json", ".ndjson"}
NB_EXTS = {".ipynb"}
CSV_EXTS = {".csv", ".tsv"}
DIFF_EXTS = {".diff", ".patch"}
# Ambiguous extensions whose kind we decide by sniffing the content.
GENERIC_EXTS = {".txt", ".out", ".text", ""}

# Below this, a downscale/recompress isn't worth a new file.
IMAGE_MIN_BYTES = 200 * 1024
# Below this a log is already cheap; compressing adds churn for no gain.
LOG_MIN_BYTES = 8 * 1024
# Below this a JSON blob isn't worth compressing.
JSON_MIN_BYTES = 4 * 1024
# Below this a CSV is small enough to read whole.
CSV_MIN_BYTES = 4 * 1024

# Below this a diff is small enough to read whole.
DIFF_MIN_BYTES = 4 * 1024

# Text kinds whose digests get a redaction pass (strip blobs, mask secrets).
_REDACTED_KINDS = {"log", "json", "notebook", "csv", "diff"}


@dataclasses.dataclass
class OptimizeResult:
    ok: bool
    kind: str                 # "pdf" | "image" | "skip"
    source: str
    output: Optional[str]     # path to optimized artifact (None if skipped)
    tokens_before: int
    tokens_after: int
    cached: bool
    note: str = ""

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["tokens_saved"] = self.tokens_saved
        return d


def _redact(text: str) -> str:
    """Strip base64 blobs / data-URIs and mask secrets in a text digest."""
    from .redact import redact
    return redact(text)[0]


def _sniff(path: str) -> str:
    """Decide kind by content for ambiguous extensions (.txt/.out/no ext)."""
    try:
        head = open(path, encoding="utf-8", errors="replace").read(65536)
    except OSError:
        return "skip"
    from .jsoncompress import looks_like_json
    if looks_like_json(head):
        return "json"
    # log-ish: many lines, or ANSI/timestamps present
    if "\x1b[" in head or head.count("\n") >= 50:
        return "log"
    return "skip"


def _kind_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in LOG_EXTS:
        return "log"
    if ext in JSON_EXTS:
        return "json"
    if ext in NB_EXTS:
        return "notebook"
    if ext in CSV_EXTS:
        return "csv"
    if ext in DIFF_EXTS:
        return "diff"
    if ext in GENERIC_EXTS:
        return _sniff(path)
    return "skip"


def optimize(
    path: str,
    quality: int = 80,
    max_edge: Optional[int] = None,
    record: bool = True,
) -> OptimizeResult:
    """Optimize a single attachment. Idempotent and cached."""
    if not os.path.isfile(path):
        return OptimizeResult(False, "skip", path, None, 0, 0, False,
                              note="not a file")

    kind = _kind_for(path)
    if kind == "skip":
        return OptimizeResult(False, "skip", path, None, 0, 0, False,
                              note="unsupported type")

    opts = {"kind": kind, "quality": quality, "max_edge": max_edge}

    if kind == "pdf":
        key, out = cache.cache_paths(path, opts, ".md")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "pdf", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .pdf import pdf_to_markdown
        md, n_pages = pdf_to_markdown(path)
        out.write_text(md, encoding="utf-8")
        # A PDF is billed as text + a per-page image. Markdown keeps the text
        # and drops the image channel, so the saving is exactly that channel.
        text_after = text_tokens(md)
        tokens_before = pdf_image_tokens(n_pages) + text_after
        tokens_after = text_after
        meta = {"tokens_before": tokens_before, "tokens_after": tokens_after,
                "pages": n_pages}
        cache.save_meta(key, meta)
        res = OptimizeResult(True, "pdf", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{n_pages} pages")

    elif kind == "log":
        if os.path.getsize(path) < LOG_MIN_BYTES:
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="log already small")
        key, out = cache.cache_paths(path, opts, ".log.txt")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "log", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .logs import compress_log
        raw = open(path, encoding="utf-8", errors="replace").read()
        digest, stats = compress_log(raw)
        digest = _redact(digest)
        out.write_text(digest, encoding="utf-8")
        tokens_before = text_tokens(raw)
        tokens_after = text_tokens(digest)
        meta = {"tokens_before": tokens_before, "tokens_after": tokens_after,
                "lines": [stats["lines_before"], stats["lines_after"]]}
        cache.save_meta(key, meta)
        res = OptimizeResult(True, "log", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{stats['lines_before']} -> "
                                  f"{stats['lines_after']} lines")

    elif kind == "json":
        if os.path.getsize(path) < JSON_MIN_BYTES:
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="json already small")
        key, out = cache.cache_paths(path, opts, ".min.json")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "json", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .jsoncompress import compress_json
        raw = open(path, encoding="utf-8", errors="replace").read()
        digest, stats = compress_json(raw)
        if not stats.get("ok"):
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="not valid JSON")
        digest = _redact(digest)
        out.write_text(digest, encoding="utf-8")
        tokens_before = text_tokens(raw)
        tokens_after = text_tokens(digest)
        meta = {"tokens_before": tokens_before, "tokens_after": tokens_after}
        cache.save_meta(key, meta)
        res = OptimizeResult(True, "json", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{stats['bytes_before']//1024}KB -> "
                                  f"{stats['bytes_after']//1024}KB")

    elif kind == "notebook":
        key, out = cache.cache_paths(path, opts, ".ipynb.md")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "notebook", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .notebook import notebook_to_markdown
        raw = open(path, encoding="utf-8", errors="replace").read()
        digest, stats = notebook_to_markdown(raw)
        if not stats.get("ok"):
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="not a notebook")
        digest = _redact(digest)
        out.write_text(digest, encoding="utf-8")
        tokens_before = text_tokens(raw)
        tokens_after = text_tokens(digest)
        cache.save_meta(key, {"tokens_before": tokens_before,
                              "tokens_after": tokens_after})
        res = OptimizeResult(True, "notebook", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{stats['cells']} cells, "
                                  f"{stats['images_elided']} images elided")

    elif kind == "csv":
        if os.path.getsize(path) < CSV_MIN_BYTES:
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="csv already small")
        key, out = cache.cache_paths(path, opts, ".csv.md")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "csv", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .csvtable import compress_csv
        raw = open(path, encoding="utf-8", errors="replace").read()
        digest, stats = compress_csv(raw)
        if not stats.get("ok"):
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="empty csv")
        digest = _redact(digest)
        out.write_text(digest, encoding="utf-8")
        tokens_before = text_tokens(raw)
        tokens_after = text_tokens(digest)
        cache.save_meta(key, {"tokens_before": tokens_before,
                              "tokens_after": tokens_after})
        res = OptimizeResult(True, "csv", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{stats['rows']} rows x {stats['cols']} cols")

    elif kind == "diff":
        if os.path.getsize(path) < DIFF_MIN_BYTES:
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="diff already small")
        key, out = cache.cache_paths(path, opts, ".diff")
        meta = cache.load_meta(key)
        if meta and out.exists():
            return OptimizeResult(True, "diff", path, str(out),
                                  meta["tokens_before"], meta["tokens_after"],
                                  cached=True, note="cache hit")
        from .diffcompress import compress_diff
        raw = open(path, encoding="utf-8", errors="replace").read()
        digest, stats = compress_diff(raw)
        digest = _redact(digest)
        out.write_text(digest, encoding="utf-8")
        tokens_before = text_tokens(raw)
        tokens_after = text_tokens(digest)
        cache.save_meta(key, {"tokens_before": tokens_before,
                              "tokens_after": tokens_after})
        res = OptimizeResult(True, "diff", path, str(out), tokens_before,
                             tokens_after, cached=False,
                             note=f"{stats['files_elided']}/{stats['files_total']} "
                                  f"files elided")

    else:  # image
        if os.path.getsize(path) < IMAGE_MIN_BYTES:
            return OptimizeResult(False, "skip", path, None, 0, 0, False,
                                  note="image already small")
        from .image import compress_image
        from .tokens import MAX_EDGE
        edge = max_edge or MAX_EDGE
        opts["max_edge"] = edge
        key, out = cache.cache_paths(path, opts, ".img")
        existing = cache.load_meta(key)
        if existing and existing.get("output") and os.path.exists(existing["output"]):
            return OptimizeResult(True, "image", path, existing["output"],
                                  existing["tokens_before"],
                                  existing["tokens_after"],
                                  cached=True, note="cache hit")
        out_path, stats = compress_image(path, str(out), max_edge=edge,
                                         quality=quality)
        stats["output"] = out_path
        cache.save_meta(key, stats)
        res = OptimizeResult(True, "image", path, out_path,
                             stats["tokens_before"], stats["tokens_after"],
                             cached=False,
                             note=f"{stats['bytes_before']//1024}KB -> "
                                  f"{stats['bytes_after']//1024}KB")

    if res.ok and res.output:
        # Reversibility: remember which original produced this artifact so
        # `justokenmax retrieve <artifact>` can hand the full version back.
        cache.record_origin(res.output, res.source)
    if record and res.ok and not res.cached:
        cache.record_savings(res.tokens_saved, res.kind)
    return res
