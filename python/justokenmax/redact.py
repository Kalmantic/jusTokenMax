"""Redaction — strip token-heavy noise and mask secrets from text.

Dual purpose: it cuts tokens (base64 blobs and data-URIs can be kilobytes of
gibberish the model never needs) and it improves safety (API keys, tokens, and
passwords get masked before they reach the context). Applied automatically
inside the text digests (log/JSON/notebook/CSV) and available standalone.

Our own code; stdlib `re` only.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

# Placeholder token wrapping a stable per-document secret id (s1, s2, ...). The
# brackets are uncommon glyphs unlikely to collide with file content, so the
# audited-reversible map can locate and restore each masked span exactly.
_PLACEHOLDER = "⟦jtm:{}⟧"

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


def redact_with_map(text: str) -> Tuple[str, Dict[str, str]]:
    """Audited-reversible variant of `redact`: mask secrets AND return a map.

    Same masking output as `redact` (blobs elided, secrets masked), but every
    masked secret span also gets a stable placeholder `⟦jtm:sN⟧` appended to its
    masked form, and `mapping[⟦jtm:sN⟧] = original_secret`. The placeholder ids
    are content-ordered (s1, s2, ...) so the result is deterministic — no clock,
    no random. The originals live ONLY in the returned map, never in `text`, so
    the digest written to cache stays secret-safe; the map is stored separately
    (owner-only sidecar) and is what makes an audited unmask possible.
    """
    counts = {"n": 0}
    mapping: Dict[str, str] = {}

    def _datauri(m):
        return f"[data-uri elided {len(m.group(0))} chars]"

    def _blob(m):
        return f"[base64 blob elided {len(m.group(0))} chars]"

    text = _DATA_URI.sub(_datauri, text)
    text = _B64_BLOB.sub(_blob, text)

    def _tag() -> str:
        counts["n"] += 1
        return _PLACEHOLDER.format(f"s{counts['n']}")

    def _secret(m):
        original = m.group(0)
        ph = _tag()
        mapping[ph] = original
        return _mask(original) + ph

    for pat in _SECRET_PATTERNS:
        text = pat.sub(_secret, text)

    def _kv(m):
        original = m.group(4)
        # The secret-shape pass above may already have masked+tagged this value
        # (e.g. `token=sk-...`); don't double-tag a placeholder.
        if "⟦jtm:" in original:
            return m.group(0)
        ph = _tag()
        mapping[ph] = original
        return m.group(1) + m.group(2) + m.group(3) + _mask(original) + ph + m.group(3)

    text = _KV_SECRET.sub(_kv, text)
    return text, mapping


# A placeholder and the masked form that always sits immediately before it.
# _mask() emits either `****` or `<4 chars>…<4 chars>`, so the leading group is
# optional and tolerant of either form.
_MASKED_SPAN_RE = re.compile(r"(?:\*{4}|[^\s'\"]{4}…[^\s'\"]{4})?(⟦jtm:s\d+⟧)")


def unmask_text(text: str, mapping: Dict[str, str]) -> Tuple[str, int]:
    """Restore originals masked by `redact_with_map`: replace each masked span
    (`<masked>⟦jtm:sN⟧`) with its original from `mapping`. Returns
    (restored_text, n_unmasked); unknown placeholders are left intact."""
    n = 0

    def _restore(m):
        nonlocal n
        ph = m.group(1)
        if ph not in mapping:
            return m.group(0)
        n += 1
        return mapping[ph]

    return _MASKED_SPAN_RE.sub(_restore, text), n
