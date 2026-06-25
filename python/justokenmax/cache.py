"""Content-addressed cache + a running savings ledger.

Converting the same PDF twice should be free. The cache key is the source
file's content hash plus the options that affect output, so an edited file
re-converts but an unchanged one is instant.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from typing import Optional

ROOT = pathlib.Path(
    os.environ.get("JUSTOKENMAX_HOME", pathlib.Path.home() / ".justokenmax")
)
CACHE_DIR = ROOT / "cache"
LEDGER = ROOT / "stats.json"


def _harden(path: pathlib.Path) -> None:
    """Restrict a cache directory to the owner (0700) — defence in depth for the
    user's own (already-redacted) file content kept locally."""
    try:
        os.chmod(path, 0o700)
    except OSError:
        return  # best-effort: platforms without chmod (e.g. Windows)


def _hash_file(path: str, opts: dict) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(opts, sort_keys=True).encode())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_paths(src: str, opts: dict, out_ext: str) -> tuple[str, pathlib.Path]:
    """Return (key, output_path) for a source file + options."""
    key = _hash_file(src, opts)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    _harden(CACHE_DIR)
    return key, CACHE_DIR / f"{key}{out_ext}"


def meta_path(key: str) -> pathlib.Path:
    return CACHE_DIR / f"{key}.json"


def load_meta(key: str) -> Optional[dict]:
    p = meta_path(key)
    if p.exists():
        return json.loads(p.read_text())
    return None


def save_meta(key: str, meta: dict) -> None:
    meta_path(key).write_text(json.dumps(meta, indent=2))


def record_savings(tokens_saved: int, kind: str) -> dict:
    """Add to the lifetime ledger and return the updated totals."""
    ROOT.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    data = {"total_tokens_saved": 0, "runs": 0, "by_kind": {}}
    if LEDGER.exists():
        try:
            data = json.loads(LEDGER.read_text())
        except json.JSONDecodeError:
            data = {"total_tokens_saved": 0, "runs": 0, "by_kind": {}}
    data["total_tokens_saved"] = data.get("total_tokens_saved", 0) + tokens_saved
    data["runs"] = data.get("runs", 0) + 1
    data.setdefault("by_kind", {})
    data["by_kind"][kind] = data["by_kind"].get(kind, 0) + tokens_saved
    LEDGER.write_text(json.dumps(data, indent=2))
    return data


def read_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text())
        except json.JSONDecodeError:
            return {"total_tokens_saved": 0, "runs": 0, "by_kind": {}}
    return {"total_tokens_saved": 0, "runs": 0, "by_kind": {}}


ORIGINS = CACHE_DIR / "origins.json"


def _load_origins() -> dict:
    if ORIGINS.exists():
        try:
            return json.loads(ORIGINS.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def record_origin(artifact: str, source: str) -> None:
    """Map an optimized artifact back to the original it came from."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    _harden(CACHE_DIR)
    data = _load_origins()
    data[os.path.abspath(artifact)] = os.path.abspath(source)
    ORIGINS.write_text(json.dumps(data, indent=2))


def lookup_origin(artifact: str) -> Optional[str]:
    """Return the original path for an optimized artifact, or None."""
    return _load_origins().get(os.path.abspath(artifact))


def _index_cache_path(root: str) -> pathlib.Path:
    """A per-root cache of parsed symbols so the index can rebuild incrementally."""
    key = hashlib.sha256(os.path.abspath(root).encode()).hexdigest()[:16]
    return CACHE_DIR / f"index-{key}.json"


def load_index_cache(root: str) -> dict:
    """Return {rel_path: {"mtime": float, "symbols": [...]}} for `root`, or {}."""
    p = _index_cache_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_index_cache(root: str, entries: dict) -> None:
    """Persist the per-file parsed-symbol cache for `root`."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    _harden(CACHE_DIR)
    _index_cache_path(root).write_text(json.dumps(entries))
