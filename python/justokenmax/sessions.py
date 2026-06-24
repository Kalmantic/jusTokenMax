"""Per-session stats — analyze how effective jusTokenMax is over time.

The lifetime ledger (`justokenmax stats`) is a running total. This records one
row per *session*: how many tokens were saved between the previous snapshot and
now, by kind. A Claude Code `Stop` hook calls `record()` at the end of every
session, so you get a time series you can analyze (avg saved per session, trend,
which levers carry the load).

Stored as newline-delimited JSON at `~/.justokenmax/sessions.jsonl`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import cache


def _sessions_path() -> Path:
    return cache.ROOT / "sessions.jsonl"


def _snapshot_path() -> Path:
    return cache.ROOT / ".session_snapshot.json"


def _load_snapshot() -> dict:
    p = _snapshot_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def record(session_id: Optional[str] = None) -> Optional[dict]:
    """Append a session row = (lifetime ledger now) − (last snapshot). Returns the
    row, or None if nothing was saved this session (so we don't log empties)."""
    led = cache.read_ledger()
    snap = _load_snapshot()
    delta_total = led.get("total_tokens_saved", 0) - snap.get("total_tokens_saved", 0)
    delta_runs = led.get("runs", 0) - snap.get("runs", 0)
    prev_kind = snap.get("by_kind", {})
    by_kind = {k: led["by_kind"][k] - prev_kind.get(k, 0)
               for k in led.get("by_kind", {})
               if led["by_kind"][k] - prev_kind.get(k, 0) > 0}

    # advance the snapshot regardless, so a session never double-counts
    cache.ROOT.mkdir(parents=True, exist_ok=True)
    cache._harden(cache.ROOT)
    _snapshot_path().write_text(json.dumps({
        "total_tokens_saved": led.get("total_tokens_saved", 0),
        "runs": led.get("runs", 0),
        "by_kind": led.get("by_kind", {}),
    }), encoding="utf-8")

    if delta_total <= 0 and delta_runs <= 0:
        return None

    row = {
        "ended": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tokens_saved": delta_total,
        "runs": delta_runs,
        "by_kind": by_kind,
    }
    if session_id:
        row["session_id"] = session_id
    with open(_sessions_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def read(limit: Optional[int] = None) -> List[dict]:
    p = _sessions_path()
    if not p.exists():
        return []
    rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return rows[-limit:] if limit else rows


def summary() -> dict:
    rows = read()
    n = len(rows)
    total = sum(r.get("tokens_saved", 0) for r in rows)
    by_kind: dict = {}
    for r in rows:
        for k, v in r.get("by_kind", {}).items():
            by_kind[k] = by_kind.get(k, 0) + v
    return {
        "sessions": n,
        "tokens_saved": total,
        "avg_per_session": (total // n) if n else 0,
        "by_kind": by_kind,
        "recent": rows[-5:],
    }
