"""Rough token estimators, used only to report savings.

These are deliberately simple. The point is a defensible before/after number,
not accounting-grade precision. Constants follow Anthropic's published guidance
for image tokens (~ width*height / 750) and the common ~4 chars/token rule for
text.

Text counting prefers tiktoken (o200k_base) when the optional `accurate` extra
is installed; otherwise it falls back to the ~4 chars/token heuristic. The image
estimators are intentionally left alone — they follow Anthropic's image formula.
"""

from __future__ import annotations

# Optional accurate tokenizer. Guarded so the base install (pypdf + Pillow only)
# never imports it, and a missing/broken tiktoken silently degrades to len//4.
try:  # pragma: no cover - import availability is environment-dependent
    import tiktoken
except Exception:  # noqa: BLE001 - any import failure means "not available"
    tiktoken = None

_ENCODER = None  # cached encoder; None means "fall back to len//4"
_ENCODER_TRIED = False  # so a one-time failed lookup isn't retried each call


def _encoder():
    """Return a cached tiktoken encoder, or None if unavailable.

    Tries o200k_base (current Claude/GPT family) and falls back to cl100k_base.
    Any failure caches None so we don't pay the lookup cost repeatedly.
    """
    global _ENCODER, _ENCODER_TRIED
    if _ENCODER_TRIED:
        return _ENCODER
    _ENCODER_TRIED = True
    if tiktoken is None:
        return None
    for name in ("o200k_base", "cl100k_base"):
        try:
            _ENCODER = tiktoken.get_encoding(name)
            return _ENCODER
        except Exception:  # noqa: BLE001 - try the next encoding / give up
            continue
    return None

# Long-edge ceiling Claude resizes images to before tokenizing. Anything larger
# is downscaled by the API anyway, so shipping bigger pixels just wastes bytes.
MAX_EDGE = 1568

# When a PDF is ingested, each page is sent BOTH as extracted text AND as a page
# image (so the model can see layout/figures). Converting to Markdown keeps the
# text and drops the image channel. This is the per-page image cost we remove —
# a US-letter page clamps to ~1.15MP, i.e. ~1,530 tokens; we use a conservative
# 1,500 so we never overclaim the saving.
PDF_PAGE_IMAGE_TOKENS = 1500


def text_tokens(text: str) -> int:
    """Estimate tokens for a chunk of text.

    Uses tiktoken (o200k_base) when the optional `accurate` extra is installed,
    which counts punctuation/symbol-dense text more faithfully. Falls back to the
    ~4 chars/token heuristic when tiktoken is absent or errors. Always >= 1.
    """
    enc = _encoder()
    if enc is not None:
        try:
            return max(1, len(enc.encode(text)))
        except Exception:  # noqa: BLE001 - never raise from a counting helper
            pass
    return max(1, len(text) // 4)


def image_tokens(width: int, height: int) -> int:
    """Vision-cost reference: tokens an image costs a native-vision model.

    Mirrors the API: clamp the long edge to MAX_EDGE (preserving aspect), then
    tokens ~= (w * h) / 750. Note: because the API downscales automatically,
    OUR downscaling does not reduce this number — it only reduces bytes. For the
    savings ledger we use `bytes_to_tokens` instead (see below).
    """
    if width <= 0 or height <= 0:
        return 0
    long_edge = max(width, height)
    if long_edge > MAX_EDGE:
        scale = MAX_EDGE / long_edge
        width = round(width * scale)
        height = round(height * scale)
    return int((width * height) / 750)


def bytes_to_tokens(n_bytes: int) -> int:
    """Estimate tokens for an image carried as base64 text.

    Many agent pipelines inline images as base64 in the prompt; base64 expands
    bytes ~4/3 and tokenizes ~4 chars/token, so tokens ~= bytes / 3. This is the
    figure that actually shrinks when we recompress an image, so it's what the
    image savings ledger reports.
    """
    return max(0, n_bytes // 3)


def pdf_image_tokens(n_pages: int) -> int:
    """The page-image token cost that converting to Markdown removes.

    A PDF is billed as text + a per-page image; Markdown keeps the text and
    eliminates this image channel, so this is the saving.
    """
    return n_pages * PDF_PAGE_IMAGE_TOKENS
