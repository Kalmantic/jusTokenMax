"""Lockfile + minified-asset compression.

Dependency lockfiles (package-lock.json, yarn.lock, pnpm-lock.yaml,
poetry.lock, Cargo.lock, Gemfile.lock) are enormous and almost entirely noise
to an agent: integrity hashes, resolved tarball URLs, transitive bookkeeping.
What an agent actually needs is the resolved set — which package is pinned to
which version. This collapses a lockfile to a flat "name@version" table.

Minified assets (.min.js / .min.css, or any file that is one giant line) are
opaque single tokens of generated code; we stub them out entirely and point at
`justokenmax retrieve` for the source.

Lossy by design, reversible via the cache (the original is kept by content
hash). Our own code; stdlib only (json + re).
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

# A single physical line longer than this is treated as a minified asset.
MINIFIED_LINE_BYTES = 5 * 1024

_LOCK_NAMES = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "poetry.lock": "poetry",
    "cargo.lock": "cargo",
    "gemfile.lock": "gemfile",
}


def lock_flavor(path: str) -> Optional[str]:
    """Return the lockfile flavor for a path's basename, or None."""
    return _LOCK_NAMES.get(os.path.basename(path).lower())


def is_minified_name(path: str) -> bool:
    name = os.path.basename(path).lower()
    return name.endswith(".min.js") or name.endswith(".min.css")


def _table(pairs: List[Tuple[str, str]], flavor: str) -> Tuple[str, dict]:
    """Render resolved name->version pairs as a compact table digest."""
    # Deterministic: stable de-dup by name, sorted.
    seen: dict = {}
    for name, ver in pairs:
        if name and name not in seen:
            seen[name] = ver
    rows = sorted(seen.items())
    out = [f"# Lockfile digest ({flavor}) — {len(rows)} packages",
           "# integrity hashes / resolved URLs dropped; "
           "`justokenmax retrieve` for full",
           ""]
    out += [f"{name}@{ver}" if ver else name for name, ver in rows]
    digest = "\n".join(out) + "\n"
    stats = {"kind": "lockfile", "ok": True, "flavor": flavor,
             "packages": len(rows)}
    return digest, stats


def _npm_lock(text: str, flavor: str) -> Tuple[str, dict]:
    data = json.loads(text)
    pairs: List[Tuple[str, str]] = []
    # lockfile v2/v3: "packages": {"node_modules/foo": {"version": ...}}
    pkgs = data.get("packages")
    if isinstance(pkgs, dict):
        for path, info in pkgs.items():
            if not isinstance(info, dict):
                continue
            name = info.get("name") or path.split("node_modules/")[-1]
            if not name or path == "":
                continue
            pairs.append((name, str(info.get("version", ""))))
    # lockfile v1: "dependencies": {"foo": {"version": ...}}
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        for name, info in deps.items():
            ver = info.get("version", "") if isinstance(info, dict) else ""
            pairs.append((name, str(ver)))
    return _table(pairs, flavor)


_YARN_ENTRY = re.compile(r'^"?([^"@\s][^@\n]*)@', re.MULTILINE)
_YARN_VERSION = re.compile(r'^\s+version:?\s+"?([^"\s]+)"?', re.MULTILINE)


def _yarn_lock(text: str, flavor: str) -> Tuple[str, dict]:
    pairs: List[Tuple[str, str]] = []
    # Split into blocks separated by blank lines; each block is one package.
    # A block may carry leading comment lines (the file banner) — drop those
    # before reading the entry header.
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        if not lines:
            continue
        m = _YARN_ENTRY.match(lines[0])
        ver_m = _YARN_VERSION.search(block)
        if m and ver_m:
            pairs.append((m.group(1).strip().strip('"'), ver_m.group(1)))
    return _table(pairs, flavor)


_TOML_NAME = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)
_TOML_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


def _toml_lock(text: str, flavor: str) -> Tuple[str, dict]:
    """poetry.lock / Cargo.lock — TOML [[package]] arrays of tables."""
    pairs: List[Tuple[str, str]] = []
    for block in re.split(r"\n\s*\[\[\s*package\s*\]\]", text):
        nm = _TOML_NAME.search(block)
        ver = _TOML_VERSION.search(block)
        if nm:
            pairs.append((nm.group(1), ver.group(1) if ver else ""))
    return _table(pairs, flavor)


_GEM_SPEC = re.compile(r"^\s{4,6}([a-zA-Z0-9_.\-]+) \(([^)]+)\)", re.MULTILINE)


def _gemfile_lock(text: str, flavor: str) -> Tuple[str, dict]:
    pairs = [(m.group(1), m.group(2)) for m in _GEM_SPEC.finditer(text)]
    return _table(pairs, flavor)


def compress_lockfile(text: str, flavor: str) -> Tuple[str, dict]:
    """Return (name@version table digest, stats) for a lockfile.

    Fail-open: any parse failure returns the original text with ok=False so the
    caller passes the raw file through untouched.
    """
    try:
        if flavor == "npm":
            return _npm_lock(text, flavor)
        if flavor == "yarn":
            return _yarn_lock(text, flavor)
        if flavor == "pnpm":
            return _pnpm_lock(text, flavor)
        if flavor in ("poetry", "cargo"):
            return _toml_lock(text, flavor)
        if flavor == "gemfile":
            return _gemfile_lock(text, flavor)
    except Exception:  # noqa: BLE001 — fail-open, never raise into the hook
        return text, {"kind": "lockfile", "ok": False, "note": "parse failed"}
    return text, {"kind": "lockfile", "ok": False, "note": "unknown flavor"}


_PNPM_DEP = re.compile(r"^\s{2,}([^\s:][^:]*):\s*$", re.MULTILINE)
_PNPM_PKG = re.compile(r"^\s+/?(@?[^@\s/][^@\s]*?)@([0-9][^\s:(]*)", re.MULTILINE)


def _pnpm_lock(text: str, flavor: str) -> Tuple[str, dict]:
    """pnpm-lock.yaml — packages keyed by /name@version (or name@version)."""
    pairs = [(m.group(1), m.group(2)) for m in _PNPM_PKG.finditer(text)]
    return _table(pairs, flavor)


def minified_stub(n_bytes: int, label: str = "minified asset") -> Tuple[str, dict]:
    """A deterministic one-line stub for an opaque generated asset."""
    digest = f"<{label}, {n_bytes} bytes — `justokenmax retrieve` for source>\n"
    stats = {"kind": "minified", "ok": True, "bytes": n_bytes}
    return digest, stats


def looks_minified(text: str, path: str = "") -> bool:
    """True for a .min.js/.min.css name, or any text with a single line
    longer than MINIFIED_LINE_BYTES (the hallmark of a packed/minified file)."""
    if path and is_minified_name(path):
        return True
    if not text:
        return False
    return max((len(ln) for ln in text.splitlines()), default=0) > MINIFIED_LINE_BYTES
