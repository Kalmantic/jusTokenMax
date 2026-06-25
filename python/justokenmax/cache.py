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


def _harden_file(path: pathlib.Path) -> None:
    """Restrict a file to owner read/write (0600) — for sidecars that hold
    recoverable secret material (the redaction map). Best-effort like `_harden`."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


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


# --- Audited reversible redaction (opt-in) --------------------------------
#
# The redaction map (placeholder -> original secret) is stored SEPARATELY from
# the digest artifact, in an owner-only (0600) sidecar keyed by the same cache
# key, so secrets are never written into the digest. An audited `unmask` reads
# the map back and appends a row to a JSONL audit log — every recovery leaves a
# trail. This whole path is opt-in; the default mask-before-cache flow is
# untouched and never writes a map.

def redaction_map_path(key: str) -> pathlib.Path:
    return CACHE_DIR / f"{key}.redmap.json"


AUDIT_LOG = ROOT / "redaction-audit.jsonl"


def save_redaction_map(key: str, mapping: dict) -> pathlib.Path:
    """Write the placeholder->secret map to an owner-only sidecar (0600).

    Stored apart from the digest so the secret material never lands in a shared
    artifact. Returns the sidecar path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    _harden(CACHE_DIR)
    p = redaction_map_path(key)
    p.write_text(json.dumps(mapping, indent=2))
    _harden_file(p)
    return p


def load_redaction_map(key: str) -> Optional[dict]:
    """Return the stored placeholder->secret map for `key`, or None."""
    p = redaction_map_path(key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _record_unmask(key: str, n_unmasked: int, actor: Optional[str]) -> None:
    """Append one audit row. Content is deterministic (no clock/random) so it is
    test-stable; the row records what was unmasked, by whom."""
    ROOT.mkdir(parents=True, exist_ok=True)
    _harden(ROOT)
    row = {"key": key, "n_unmasked": n_unmasked, "actor": actor}
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    _harden_file(AUDIT_LOG)


def read_audit_log() -> list:
    """Return the audit rows (oldest first), or [] if none."""
    if not AUDIT_LOG.exists():
        return []
    rows = []
    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def unmask(key: str, masked_text: str, audit_actor: Optional[str] = None) -> str:
    """Audited recovery: restore originals in `masked_text` using the stored map
    for `key`, append an audit row, and return the recovered text. With no
    stored map, returns `masked_text` unchanged (and audits n_unmasked=0)."""
    from .redact import unmask_text
    mapping = load_redaction_map(key)
    if not mapping:
        _record_unmask(key, 0, audit_actor)
        return masked_text
    restored, n = unmask_text(masked_text, mapping)
    _record_unmask(key, n, audit_actor)
    return restored
