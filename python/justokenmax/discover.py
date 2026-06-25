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


def discover(root: Optional[str] = None, max_files: int = 5000) -> dict:
    """Survey history under `root` and return a recoverable-tokens report.

    The report is deterministic for a fixed history + filesystem (no clock or
    random input), so it is safe to cache or diff.
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
    if not os.path.isdir(root):
        report["note"] = "no history dir"
        return report

    by_kind: Counter = Counter()
    by_path: Counter = Counter()
    unsupported: Counter = Counter()
    seen_paths: set = set()
    n_reads = 0

    logs = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    report["sessions"] = len(logs)
    for log in logs:
        for raw_path in _read_paths(log):
            n_reads += 1
            if raw_path in seen_paths:
                continue
            if len(seen_paths) >= max_files:
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


def format_report(report: dict) -> str:
    """Human-readable summary of a discover() report."""
    lines = []
    total = report.get("recoverable_tokens", 0)
    lines.append(
        f"justokenmax discover: {total:,} recoverable tokens across "
        f"{report.get('files_seen', 0)} files "
        f"({report.get('reads_total', 0)} reads in "
        f"{report.get('sessions', 0)} sessions)"
    )
    if report.get("note"):
        lines.append(f"  ({report['note']})")
    by_kind = report.get("by_kind") or {}
    if by_kind:
        lines.append("  recoverable by kind:")
        for kind, n in by_kind.items():
            lines.append(f"    {kind:9} {n:,}")
    by_path = report.get("by_path") or {}
    if by_path:
        lines.append("  top files:")
        for p, n in list(by_path.items())[:10]:
            lines.append(f"    -{n:,}  {p}")
    unsup = report.get("unsupported_exts") or {}
    if unsup:
        lines.append("  unsupported (compressor backlog):")
        for ext, n in list(unsup.items())[:10]:
            lines.append(f"    {ext:9} {n} reads")
    return "\n".join(lines)
