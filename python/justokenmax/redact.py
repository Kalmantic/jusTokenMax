"""Redaction — strip token-heavy noise and mask secrets from text.

Dual purpose: it cuts tokens (base64 blobs and data-URIs can be kilobytes of
gibberish the model never needs) and it improves safety (API keys, tokens, and
passwords get masked before they reach the context). Applied automatically
inside the text digests (log/JSON/notebook/CSV) and available standalone.

Our own code; stdlib `re` only.
"""

from __future__ import annotations

import re
from typing import Tuple

_DATA_URI = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]{20,}")
_B64_BLOB = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{200,}={0,2}(?![A-Za-z0-9+/])")

# Recognizable secret token shapes.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),                 # OpenAI-style
    re.compile(r"AKIA[0-9A-Z]{16}"),                    # AWS access key id
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),          # GitHub token
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),             # Google API key
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),        # Slack token
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT
]

# key = value / key: "value" style secrets.
_KV_SECRET = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"client[_-]?secret)\b(\s*[=:]\s*)(['\"]?)([^\s'\"]{4,})\3"
)


def _mask(s: str) -> str:
    if len(s) <= 8:
        return "****"
    return s[:4] + "…" + s[-4:]  # keep a recognizable prefix/suffix


def mask_secrets(text: str) -> Tuple[str, int]:
    """Mask recognizable secret tokens and `key = value` secrets in `text`.

    Safety-only (no blob elision), so it is cheap and side-effect-free enough to
    run UNCONDITIONALLY before any digest is stored — a live API key or password
    must never reach a cache artifact, even when the optional `redact` token-
    cutting pass is disabled. Returns (masked_text, n_secrets_masked).
    """
    n = 0

    def _secret(m):
        nonlocal n
        n += 1
        return _mask(m.group(0))

    for pat in _SECRET_PATTERNS:
        text = pat.sub(_secret, text)

    def _kv(m):
        nonlocal n
        n += 1
        return m.group(1) + m.group(2) + m.group(3) + _mask(m.group(4)) + m.group(3)

    text = _KV_SECRET.sub(_kv, text)
    return text, n


def redact(text: str) -> Tuple[str, dict]:
    """Return (redacted_text, stats): elide base64 blobs/data-URIs AND mask
    secrets. The blob elision is the token-cutting half; secret masking reuses
    `mask_secrets` so the same safety pass runs whether or not blobs are elided."""
    counts = {"blobs": 0, "secrets": 0}

    def _datauri(m):
        counts["blobs"] += 1
        return f"[data-uri elided {len(m.group(0))} chars]"

    def _blob(m):
        counts["blobs"] += 1
        return f"[base64 blob elided {len(m.group(0))} chars]"

    text = _DATA_URI.sub(_datauri, text)
    text = _B64_BLOB.sub(_blob, text)

    text, counts["secrets"] = mask_secrets(text)

    stats = {
        "kind": "redact",
        "blobs_elided": counts["blobs"],
        "secrets_masked": counts["secrets"],
    }
    return text, stats
