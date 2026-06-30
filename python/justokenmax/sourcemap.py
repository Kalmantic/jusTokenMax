"""JavaScript source map compression.

Source maps are usually generated JSON with huge `mappings` strings and often
full `sourcesContent` copies. For agent context, the useful signal is the bundle
target and which source files are represented; the bulk can be retrieved from
the original when needed.
"""

from __future__ import annotations

import json
from typing import Tuple

MAX_SOURCES = 20


def compress_sourcemap(text: str) -> Tuple[str, dict]:
    """Return (digest, stats) for a v3 source map, or ok=False if unsupported."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return text, {"kind": "sourcemap", "ok": False, "note": "not JSON"}

    if not isinstance(data, dict) or "mappings" not in data:
        return text, {"kind": "sourcemap", "ok": False, "note": "not a source map"}

    sources = data.get("sources") if isinstance(data.get("sources"), list) else []
    names = data.get("names") if isinstance(data.get("names"), list) else []
    sources_content = (
        data.get("sourcesContent")
        if isinstance(data.get("sourcesContent"), list)
        else []
    )
    mappings = data.get("mappings", "")

    shown = [str(s) for s in sources[:MAX_SOURCES]]
    hidden = max(0, len(sources) - len(shown))
    digest = {
        "sourceMap": {
            "version": data.get("version"),
            "file": data.get("file"),
            "sourceRoot": data.get("sourceRoot"),
            "sources": {
                "count": len(sources),
                "shown": shown,
                "elided": hidden,
            },
            "names": len(names),
            "mappings_chars": len(mappings) if isinstance(mappings, str) else 0,
            "sourcesContent": {
                "entries": len(sources_content),
                "elided": bool(sources_content),
            },
        }
    }
    out = json.dumps(digest, indent=2, ensure_ascii=False) + "\n"
    return out, {
        "kind": "sourcemap",
        "ok": True,
        "sources": len(sources),
        "sources_shown": len(shown),
        "sources_elided": hidden,
        "sources_content": len(sources_content),
        "mappings_chars": len(mappings) if isinstance(mappings, str) else 0,
        "bytes_before": len(text),
        "bytes_after": len(out),
    }
