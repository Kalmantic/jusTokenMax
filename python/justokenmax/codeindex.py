"""Code index — read symbols, not whole files.

The biggest avoidable input cost in a coding session is reading entire files to
find one function. This builds a symbol map of the repo so the agent can ask
"where is `parse_config`?" and get `file:line` + a *full signature* in a few
tokens, then read only that range.

Parsing depth by language:
  * Python  — stdlib `ast`: type-annotated params, return types, decorators,
              async, methods, and module-level constants.
  * JS/TS   — brace-aware scanner: functions, arrow exports, class methods,
              and TS interfaces / types / enums / namespaces.
  * Java    — brace-aware scanner: classes/interfaces/enums/records, methods
              (with modifiers + return types), constructors, and fields.
  * others  — fast regex heuristics (Go, Rust, Ruby, C/C++).
No heavy parser dependency.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import List, Optional

INDEX_DIRNAME = ".justokenmax"
INDEX_FILE = "index.json"

SKIP_DIRS = {
    ".git", ".justokenmax", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", "target", ".pytest_cache", ".mypy_cache",
    "vendor", ".idea", ".vscode",
}

LANGS = {
    ".py": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
}


def _iter_source_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in LANGS:
                yield os.path.join(dirpath, fn), LANGS[ext]


# --------------------------------------------------------------------------- #
# Python (ast)
# --------------------------------------------------------------------------- #
def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _py_sig(node) -> str:
    a = node.args
    params: List[str] = []
    for arg in a.posonlyargs + a.args:
        s = arg.arg
        if arg.annotation:
            s += ": " + _unparse(arg.annotation)
        params.append(s)
    if a.posonlyargs:
        params.insert(len(a.posonlyargs), "/")
    if a.vararg:
        s = "*" + a.vararg.arg
        if a.vararg.annotation:
            s += ": " + _unparse(a.vararg.annotation)
        params.append(s)
    elif a.kwonlyargs:
        params.append("*")
    for arg in a.kwonlyargs:
        s = arg.arg
        if arg.annotation:
            s += ": " + _unparse(arg.annotation)
        params.append(s)
    if a.kwarg:
        s = "**" + a.kwarg.arg
        if a.kwarg.annotation:
            s += ": " + _unparse(a.kwarg.annotation)
        params.append(s)
    sig = f"{node.name}({', '.join(params)})"
    if node.returns is not None:
        sig += " -> " + _unparse(node.returns)
    return sig


def _py_decorators(node) -> str:
    out = []
    for d in node.decorator_list:
        txt = _unparse(d).split("(")[0]
        if txt:
            out.append("@" + txt)
    return (" ".join(out) + " ") if out else ""


def _index_python(path: str, rel: str) -> List[dict]:
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return []
    out: List[dict] = []

    def doc1(node):
        d = ast.get_docstring(node)
        return d.strip().splitlines()[0] if d else ""

    def emit(name, kind, node, sig, doc=""):
        out.append({"name": name, "kind": kind, "file": rel,
                    "line": node.lineno,
                    "end": getattr(node, "end_lineno", node.lineno),
                    "sig": sig, "doc": doc})

    def visit(node, cls=None):
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                deco = _py_decorators(child)
                call = _py_sig(child)
                if cls:
                    sig = f"{deco}{cls}.{call}"
                else:
                    kw = "async def " if isinstance(child, ast.AsyncFunctionDef) else "def "
                    sig = f"{deco}{kw}{call}"
                emit(child.name, "method" if cls else "func", child, sig, doc1(child))
            elif isinstance(child, ast.ClassDef):
                bases = ", ".join(_unparse(b) for b in child.bases)
                sig = f"class {child.name}" + (f"({bases})" if bases else "")
                emit(child.name, "class", child, sig, doc1(child))
                visit(child, cls=child.name)
            elif cls is None and isinstance(child, ast.AnnAssign) and \
                    isinstance(child.target, ast.Name):
                emit(child.target.id, "const", child,
                     f"{child.target.id}: {_unparse(child.annotation)}")
            elif cls is None and isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name) and t.id.isupper():
                        emit(t.id, "const", child, f"{t.id} = {_unparse(child.value)[:60]}")

    visit(tree)
    return out


# --------------------------------------------------------------------------- #
# JavaScript / TypeScript (brace-aware scanner)
# --------------------------------------------------------------------------- #
_JS_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "do",
                "else", "function", "await", "typeof", "new", "in", "of",
                "case", "default", "super", "this"}

_JS_CONTAINER = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(?P<name>[\w$]+)")
_JS_FUNC = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+"
    r"(?P<name>[\w$]+)\s*(?P<params>\([^)]*\))")
_JS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+(?P<name>[\w$]+)\s*"
    r"(?::[^=]+)?=\s*(?:async\s*)?(?P<params>\([^)]*\)|[\w$]+)\s*=>")
_TS_IFACE = re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?interface\s+(?P<name>[\w$]+)")
_TS_TYPE = re.compile(r"^\s*(?:export\s+)?type\s+(?P<name>[\w$]+)\s*[=<]")
_TS_ENUM = re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+(?P<name>[\w$]+)")
_TS_NS = re.compile(r"^\s*(?:export\s+)?(?:namespace|module)\s+(?P<name>[\w$.]+)")
_JS_METHOD = re.compile(
    r"^\s*(?:(?:public|private|protected|static|readonly|abstract|async|get|set|\*)\s+)*"
    r"(?P<name>#?[A-Za-z_$][\w$]*)\s*(?P<params>\([^;{]*\))\s*(?::\s*[^={]+)?\{")


def _index_js(path: str, rel: str, lang: str) -> List[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[dict] = []
    depth = 0
    stack: List[tuple] = []          # (class_name, open_depth)
    pending_doc = ""
    in_block = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # --- JSDoc capture ---
        if in_block:
            if "*/" in stripped:
                in_block = False
            elif not pending_doc:
                pending_doc = stripped.lstrip("* ").strip()
            line_is_comment = True
        elif stripped.startswith("/**"):
            in_block = "*/" not in stripped
            pending_doc = ""
            line_is_comment = True
        else:
            line_is_comment = stripped.startswith("//") or stripped.startswith("*")

        cls = stack[-1][0] if stack else None
        matched = False

        if not line_is_comment:
            m = _JS_CONTAINER.match(line)
            if m:
                out.append({"name": m.group("name"), "kind": "class", "file": rel,
                            "line": i, "end": i, "sig": stripped.split("{")[0].strip()[:160],
                            "doc": pending_doc})
                stack.append((m.group("name"), depth))
                pending_doc = ""
                matched = True
            if not matched:
                for kind, pat in (("interface", _TS_IFACE), ("type", _TS_TYPE),
                                  ("enum", _TS_ENUM), ("namespace", _TS_NS)):
                    if lang == "js" and kind in ("interface", "type"):
                        continue
                    m = pat.match(line)
                    if m:
                        out.append({"name": m.group("name"), "kind": kind,
                                    "file": rel, "line": i, "end": i,
                                    "sig": stripped.split("{")[0].strip()[:160],
                                    "doc": pending_doc})
                        pending_doc = ""
                        matched = True
                        break
            if not matched:
                m = _JS_FUNC.match(line) or _JS_ARROW.match(line)
                if m:
                    params = m.group("params")
                    if not params.startswith("("):
                        params = f"({params})"
                    out.append({"name": m.group("name"), "kind": "func", "file": rel,
                                "line": i, "end": i,
                                "sig": f"{m.group('name')}{params}", "doc": pending_doc})
                    pending_doc = ""
                    matched = True
            if not matched and cls:
                m = _JS_METHOD.match(line)
                if m and m.group("name") not in _JS_KEYWORDS:
                    out.append({"name": m.group("name"), "kind": "method", "file": rel,
                                "line": i, "end": i,
                                "sig": f"{cls}.{m.group('name')}{m.group('params')}",
                                "doc": pending_doc})
                    pending_doc = ""
                    matched = True
            if not matched and stripped and not stripped.startswith(("import", "export {")):
                pass  # keep pending_doc for the next symbol

        # --- brace depth + pop containers ---
        depth += line.count("{") - line.count("}")
        while stack and depth <= stack[-1][1]:
            stack.pop()

    return out


# --------------------------------------------------------------------------- #
# Java (brace-aware scanner)
# --------------------------------------------------------------------------- #
_JAVA_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new",
                  "do", "else", "synchronized", "try"}
_JAVA_CONTAINER = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|sealed|\s)*)"
    r"(?P<kind>class|interface|enum|record)\s+(?P<name>\w+)")
_JAVA_METHOD = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|"
    r"native|default|\s)+)(?P<ret>[\w<>\[\],.?\s]+?)\s+(?P<name>\w+)\s*"
    r"(?P<params>\([^;{]*\))\s*(?:throws[\w,.\s]+)?\{")
_JAVA_FIELD = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|volatile|transient)\s+)+"
    r"(?P<type>[\w<>\[\].]+)\s+(?P<name>\w+)\s*[=;]")


def _index_java(path: str, rel: str) -> List[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[dict] = []
    depth = 0
    stack: List[tuple] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            depth += line.count("{") - line.count("}")
            while stack and depth <= stack[-1][1]:
                stack.pop()
            continue
        cls = stack[-1][0] if stack else None
        matched = False

        m = _JAVA_CONTAINER.match(line)
        if m:
            out.append({"name": m.group("name"), "kind": m.group("kind"),
                        "file": rel, "line": i, "end": i,
                        "sig": stripped.split("{")[0].strip()[:160], "doc": ""})
            stack.append((m.group("name"), depth))
            matched = True
        if not matched and cls:
            m = _JAVA_METHOD.match(line)
            if m and m.group("name") not in _JAVA_KEYWORDS and \
                    m.group("ret").strip() not in _JAVA_KEYWORDS:
                ret = m.group("ret").strip()
                out.append({"name": m.group("name"), "kind": "method", "file": rel,
                            "line": i, "end": i,
                            "sig": f"{cls}.{m.group('name')}{m.group('params')}: {ret}",
                            "doc": ""})
                matched = True
            if not matched:
                # constructor: name == class, no return type
                mc = re.match(r"^\s*(?:(?:public|private|protected)\s+)?"
                              r"(?P<name>\w+)\s*(?P<params>\([^;{]*\))\s*"
                              r"(?:throws[\w,.\s]+)?\{", line)
                if mc and mc.group("name") == cls:
                    out.append({"name": mc.group("name"), "kind": "method",
                                "file": rel, "line": i, "end": i,
                                "sig": f"{cls}.{mc.group('name')}{mc.group('params')}",
                                "doc": ""})
                    matched = True
            if not matched:
                mf = _JAVA_FIELD.match(line)
                if mf and mf.group("name") not in _JAVA_KEYWORDS:
                    out.append({"name": mf.group("name"), "kind": "field", "file": rel,
                                "line": i, "end": i,
                                "sig": f"{cls}.{mf.group('name')}: {mf.group('type')}",
                                "doc": ""})
                    matched = True

        depth += line.count("{") - line.count("}")
        while stack and depth <= stack[-1][1]:
            stack.pop()

    return out


# --------------------------------------------------------------------------- #
# Remaining languages (regex heuristics)
# --------------------------------------------------------------------------- #
_GENERIC = {
    "go": [
        ("func", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>\w+)\s*\(")),
        ("type", re.compile(r"^\s*type\s+(?P<name>\w+)\s+(?:struct|interface)")),
    ],
    "rust": [
        ("fn", re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)")),
        ("struct", re.compile(r"^\s*(?:pub\s+)?struct\s+(?P<name>\w+)")),
        ("trait", re.compile(r"^\s*(?:pub\s+)?trait\s+(?P<name>\w+)")),
        ("impl", re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?P<name>\w+)")),
    ],
    "ruby": [
        ("def", re.compile(r"^\s*def\s+(?P<name>[\w.?!]+)")),
        ("class", re.compile(r"^\s*class\s+(?P<name>\w+)")),
        ("module", re.compile(r"^\s*module\s+(?P<name>\w+)")),
    ],
    "cpp": [("class", re.compile(r"^\s*(?:class|struct)\s+(?P<name>\w+)"))],
    "c": [],
}


def _index_generic(path: str, rel: str, lang: str) -> List[dict]:
    patterns = _GENERIC.get(lang, [])
    if not patterns:
        return []
    out = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for i, line in enumerate(lines, 1):
        for kind, pat in patterns:
            m = pat.match(line)
            if m:
                out.append({"name": m.group("name"), "kind": kind, "file": rel,
                            "line": i, "end": i, "sig": line.strip()[:120], "doc": ""})
                break
    return out


def parse_file(path: str, rel: str, lang: str) -> List[dict]:
    """Dispatch a single file to the right language parser."""
    if lang == "python":
        return _index_python(path, rel)
    if lang in ("js", "ts"):
        return _index_js(path, rel, lang)
    if lang == "java":
        return _index_java(path, rel)
    return _index_generic(path, rel, lang)


# --------------------------------------------------------------------------- #
# Index build / query
# --------------------------------------------------------------------------- #
def build_index(root: str) -> dict:
    """Walk `root`, extract symbols, write `.justokenmax/index.json`, return it."""
    root = os.path.abspath(root)
    symbols: List[dict] = []
    n_files = 0
    for path, lang in _iter_source_files(root):
        rel = os.path.relpath(path, root)
        syms = parse_file(path, rel, lang)
        if syms:
            n_files += 1
            symbols.extend(syms)

    index = {"root": root, "files": n_files, "symbols": symbols}
    out_dir = os.path.join(root, INDEX_DIRNAME)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, INDEX_FILE), "w", encoding="utf-8") as f:
        json.dump(index, f)
    return index


def load_index(root: str) -> Optional[dict]:
    p = os.path.join(os.path.abspath(root), INDEX_DIRNAME, INDEX_FILE)
    if os.path.exists(p):
        return json.loads(Path(p).read_text(encoding="utf-8"))
    return None


def query(root: str, term: str, kind: Optional[str] = None,
          limit: int = 50) -> List[dict]:
    """Return symbols whose name contains `term` (case-insensitive)."""
    index = load_index(root)
    if not index:
        return []
    term_l = term.lower()
    hits = [s for s in index["symbols"]
            if term_l in s["name"].lower() and (not kind or s["kind"] == kind)]
    hits.sort(key=lambda s: (s["name"].lower() != term_l, s["file"], s["line"]))
    return hits[:limit]


def format_hits(hits: List[dict]) -> str:
    if not hits:
        return "no matches (build the index first with `justokenmax index`)"
    lines = []
    for s in hits:
        loc = f"{s['file']}:{s['line']}"
        doc = f"  — {s['doc']}" if s.get("doc") else ""
        lines.append(f"{loc}  [{s['kind']}]  {s['sig']}{doc}")
    return "\n".join(lines)
