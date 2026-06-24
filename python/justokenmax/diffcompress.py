"""Git-diff compression.

Large diffs are dominated by noise the reviewer doesn't read line-by-line: a
single `npm install` can balloon `package-lock.json` by tens of thousands of
lines; generated/minified/vendored files add more. This keeps the meaningful
code hunks and collapses each noise file's diff to a one-line summary, so a
review-sized diff stays review-sized.

Hunk- and file-aware (file boundaries and `@@` hunks are natural semantic
firewalls). Our own code; stdlib `re`/`os` only.
"""

from __future__ import annotations

import os
import re
from typing import List, Tuple

# Files whose diffs are almost never read line-by-line.
NOISE_BASENAMES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "Gemfile.lock", "poetry.lock", "Cargo.lock", "go.sum",
    "Pipfile.lock", "flake.lock",
}
NOISE_SUFFIXES = (".min.js", ".min.css", ".map", ".lock", ".snap")
NOISE_DIR_MARKERS = ("dist/", "build/", "node_modules/", "vendor/", ".next/",
                     "out/", "__generated__/", ".pb.go")
NOISE_GENERATED = (".pb.go", "_pb2.py", ".generated.", "_generated.", ".g.dart")

# Cap on changed lines kept for a single non-noise file.
MAX_FILE_CHANGED = 600

_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_PLUS = re.compile(r"^\+\+\+ b/(.+)$")


def _is_noise(path: str) -> bool:
    base = os.path.basename(path)
    if base in NOISE_BASENAMES:
        return True
    if path.endswith(NOISE_SUFFIXES):
        return True
    if any(m in path for m in NOISE_DIR_MARKERS):
        return True
    if any(g in path for g in NOISE_GENERATED):
        return True
    return False


def _section_path(section: List[str]) -> str:
    for ln in section:
        m = _PLUS.match(ln)
        if m and m.group(1) != "/dev/null":
            return m.group(1)
    m = _DIFF_GIT.match(section[0])
    if m:
        return m.group(2)
    return "?"


def _count_changes(section: List[str]) -> Tuple[int, int]:
    adds = sum(1 for ln in section if ln.startswith("+") and not ln.startswith("+++"))
    dels = sum(1 for ln in section if ln.startswith("-") and not ln.startswith("---"))
    return adds, dels


def compress_diff(text: str) -> Tuple[str, dict]:
    """Return (compressed_diff, stats)."""
    lines = text.split("\n")
    # Split into per-file sections at each `diff --git` header.
    sections: List[List[str]] = []
    preamble: List[str] = []
    cur: List[str] = None
    for ln in lines:
        if ln.startswith("diff --git "):
            if cur is not None:
                sections.append(cur)
            cur = [ln]
        elif cur is None:
            preamble.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        sections.append(cur)

    out: List[str] = [ln for ln in preamble if ln.strip()]
    files_total = len(sections)
    files_elided = 0

    for section in sections:
        path = _section_path(section)
        adds, dels = _count_changes(section)
        if _is_noise(path):
            files_elided += 1
            out.append(f"diff --git a/{path} b/{path}")
            out.append(f"# [jusTokenMax] {path}: +{adds}/-{dels} lines "
                       f"(lockfile/generated — diff elided)")
            continue
        if adds + dels > MAX_FILE_CHANGED:
            # Keep the header + a capped window of the body.
            header = []
            body = []
            in_body = False
            for ln in section:
                if ln.startswith("@@"):
                    in_body = True
                if in_body:
                    body.append(ln)
                else:
                    header.append(ln)
            keep = MAX_FILE_CHANGED // 2
            out.extend(header)
            out.extend(body[:keep])
            out.append(f"# [jusTokenMax] {path}: large diff truncated "
                       f"({adds + dels} changed lines; showing first {keep})")
            continue
        out.extend(section)

    digest = "\n".join(out).rstrip("\n") + "\n"
    stats = {
        "kind": "diff",
        "files_total": files_total,
        "files_elided": files_elided,
        "lines_before": len(lines),
        "lines_after": len(digest.split("\n")),
    }
    return digest, stats
