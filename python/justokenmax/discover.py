"""Survey Claude Code history for missed token-saving opportunities.

Claude Code logs every session to ~/.claude/projects/**/*.jsonl. Each Read
tool-use names a file the agent pulled in whole. This walks that history,
replays a dry-run optimize() over each still-existing file, and reports:

  * total recoverable tokens (what jusTokenMax *would* have saved), bucketed
    by kind and by path, and
  * the most frequent UNSUPPORTED extensions — the backlog of compressors to
    build next (the Repomix "token-count tree" idea).

Fail-open: a missing history dir, an unreadable line, or a per-file optimize
error never raises — the survey just skips it.
"""

from __future__ import annotations

import glob
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from .optimize import _kind_for

# Tool names (across agents) whose input names a single file path read whole.
_READ_TOOLS = {"Read", "read_file", "view", "cat"}
# Keys an input dict might use for the file path.
_PATH_KEYS = ("file_path", "path", "filename", "file", "target_file", "abspath")


def history_dir() -> str:
    """Where Claude Code keeps per-project session logs."""
    return os.environ.get("JUSTOKENMAX_HISTORY") or str(
        Path.home() / ".claude" / "projects"
    )


def _read_paths(jsonl_path: str):
    """Yield every file path a Read-style tool-use named in one session log."""
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in _READ_TOOLS:
                        continue
                    inp = block.get("input")
                    if not isinstance(inp, dict):
                        continue
                    for k in _PATH_KEYS:
                        v = inp.get(k)
                        if isinstance(v, str) and v:
                            yield v
                            break
    except OSError:
        return


def _within_window(log: str, cutoff: Optional[float]) -> bool:
    """True if `log`'s mtime is at/after `cutoff` (or no window in effect).

    Fail-open: an unstattable log is kept (better to over-survey than to drop a
    file because its mtime was momentarily unreadable).
    """
    if cutoff is None:
        return True
    try:
        return os.stat(log).st_mtime >= cutoff
    except OSError:
        return True


def discover(
    root: Optional[str] = None,
    max_files: int = 5000,
    newer_than_days: Optional[float] = None,
) -> dict:
    """Survey history under `root` and return a recoverable-tokens report.

    The report is deterministic for a fixed history + filesystem (no clock or
    random input baked into the output), so it is safe to cache or diff.

    `newer_than_days` is an optional window: only session logs whose file
    st_mtime is within the last N days are scanned (the "weekly" flywheel
    view). The cutoff is derived from the wall clock as a *filter input* only —
    it is never written into the report — so for a fixed set of mtimes the set
    of surveyed logs, and therefore the report, is reproducible.
    """
    root = root or history_dir()
    report = {
        "history_dir": root,
        "sessions": 0,
        "reads_total": 0,
        "files_seen": 0,
        "files_missing": 0,
        "recoverable_tokens": 0,
        "by_kind": {},
        "by_path": {},
        "unsupported_exts": {},
    }
    if newer_than_days is not None:
        report["window_days"] = newer_than_days
    if not os.path.isdir(root):
        report["note"] = "no history dir"
        return report

    by_kind: Counter = Counter()
    by_path: Counter = Counter()
    unsupported: Counter = Counter()
    seen_paths: set = set()
    n_reads = 0

    cutoff = None
    if newer_than_days is not None:
        cutoff = time.time() - newer_than_days * 86400.0

    logs = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    logs = [g for g in logs if _within_window(g, cutoff)]
    report["sessions"] = len(logs)
    capped = False
    for log in logs:
        if capped:
            break
        for raw_path in _read_paths(log):
            if len(seen_paths) >= max_files:
                # Cap reached: every remaining read is either a duplicate or a
                # path we'd refuse to add, so stop scanning rather than walking
                # the rest of history for nothing (was `continue`, i.e. O(all)).
                capped = True
                break
            n_reads += 1
            if raw_path in seen_paths:
                continue
            seen_paths.add(raw_path)
            saved, kind = _recoverable(raw_path, unsupported, report)
            if saved > 0:
                by_kind[kind] += saved
                by_path[os.path.abspath(raw_path)] += saved

    report["reads_total"] = n_reads
    report["files_seen"] = len(seen_paths)
    report["recoverable_tokens"] = sum(by_kind.values())
    report["by_kind"] = dict(by_kind.most_common())
    # Largest-saving paths first; keep the list bounded for a terse report.
    report["by_path"] = dict(by_path.most_common(20))
    report["unsupported_exts"] = dict(unsupported.most_common())
    return report


def _recoverable(path: str, unsupported: Counter, report: dict):
    """Dry-run optimize() on `path`; return (tokens_saved, kind).

    Unsupported file types are bucketed by extension as future-work backlog.
    Anything that errors or no longer exists contributes 0.
    """
    if not os.path.isfile(path):
        report["files_missing"] += 1
        return 0, "skip"
    kind = _kind_for(path)
    if kind == "skip":
        ext = os.path.splitext(path)[1].lower() or "(none)"
        unsupported[ext] += 1
        return 0, "skip"
    try:
        from .optimize import optimize
        res = optimize(path, record=False)
    except Exception:  # fail-open: never let one bad file sink the survey
        return 0, "skip"
    if not res.ok:
        return 0, res.kind
    return res.tokens_saved, res.kind


def format_report(report: dict, previous: Optional[dict] = None) -> str:
    """Human-readable, weekly-style summary of a discover() report.

    Deterministic: every line is derived from `report` (and the optional
    `previous` report for a "since last run" delta). No clock or random input.

    Surfaces three things to make discover a recurring flywheel rather than a
    one-shot scan: the headline recoverable total, the top file kinds by
    recoverable tokens, and the TOP MISSED FORMATS (unsupported extensions
    ranked) framed as compressors worth adding — the roadmap backlog.
    """
    lines = []
    total = report.get("recoverable_tokens", 0)
    window = report.get("window_days")
    span = f"last {window:g}d" if window is not None else "all history"
    lines.append(
        f"justokenmax discover ({span}): {total:,} recoverable tokens across "
        f"{report.get('files_seen', 0)} files "
        f"({report.get('reads_total', 0)} reads in "
        f"{report.get('sessions', 0)} sessions)"
    )
    if previous is not None:
        delta = total - previous.get("recoverable_tokens", 0)
        sign = "+" if delta >= 0 else "-"
        lines.append(f"  since last run: {sign}{abs(delta):,} recoverable tokens")
    if report.get("note"):
        lines.append(f"  ({report['note']})")
    by_kind = report.get("by_kind") or {}
    if by_kind:
        lines.append("  top kinds by recoverable tokens:")
        for kind, n in list(by_kind.items())[:10]:
            lines.append(f"    {kind:9} {n:,}")
    by_path = report.get("by_path") or {}
    if by_path:
        lines.append("  top files:")
        for p, n in list(by_path.items())[:10]:
            lines.append(f"    -{n:,}  {p}")
    unsup = report.get("unsupported_exts") or {}
    if unsup:
        lines.append("  top missed formats (compressors worth adding):")
        for ext, n in list(unsup.items())[:10]:
            lines.append(f"    {ext:9} {n} reads")
    return "\n".join(lines)


def _report_cache_path() -> Path:
    """Where the last discover() report is stashed for a 'since last run' delta."""
    from . import cache as _cache
    return _cache.ROOT / "discover_last.json"


def load_last_report() -> Optional[dict]:
    """The previous cached report, or None. Fail-open on any read/parse error."""
    try:
        with open(_report_cache_path(), encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def save_report(report: dict) -> None:
    """Stash `report` as the new baseline for the next delta. Fail-open."""
    try:
        p = _report_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(report, fh, sort_keys=True)
    except OSError:
        return
