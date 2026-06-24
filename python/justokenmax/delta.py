"""Delta reads — return only what changed since the last read.

In an edit loop the agent re-reads the same file many times; each full re-read
pays for content it already has. This snapshots a file by path on read and, on
the next read, returns a unified diff instead of the whole file. The first read
is full (nothing to diff against); every re-read after an edit is just the diff.

Stateful by *path* (not content hash), so the snapshot store lives alongside the
cache. Our own code; stdlib `difflib`/`hashlib` only.
"""

from __future__ import annotations

import difflib
import hashlib
import os
from pathlib import Path
from typing import Tuple

from . import cache
from .tokens import text_tokens


def _snap_dir():
    # Read cache.ROOT at call time so it honours JUSTOKENMAX_HOME (and tests).
    return cache.ROOT / "snapshots"


def _snap_path(path: str):
    h = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()
    return _snap_dir() / h


def delta(path: str) -> Tuple[str, dict]:
    """Return (artifact, stats). artifact is the full file on first read, else a
    unified diff (or a 'no changes' note)."""
    current = Path(path).read_text(encoding="utf-8", errors="replace")
    snap = _snap_path(path)

    if snap.exists():
        previous = snap.read_text(encoding="utf-8")
        had_prior = True
        if previous == current:
            artifact = "(no changes since last read)\n"
            changed = False
        else:
            diff = "".join(difflib.unified_diff(
                previous.splitlines(keepends=True),
                current.splitlines(keepends=True),
                fromfile=f"{os.path.basename(path)} (previous)",
                tofile=f"{os.path.basename(path)} (current)",
            ))
            artifact = diff or "(content changed but no textual diff)\n"
            changed = True
    else:
        artifact = current
        had_prior = False
        changed = True

    _snap_dir().mkdir(parents=True, exist_ok=True)
    snap.write_text(current, encoding="utf-8")

    stats = {
        "kind": "delta",
        "had_prior": had_prior,
        "changed": changed,
        "tokens_full": text_tokens(current),
        "tokens_delta": text_tokens(artifact),
    }
    return artifact, stats
