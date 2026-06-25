"""Structured-output (JSON) compression.

Tool outputs, API responses, and RAG payloads are often huge JSON: pretty-
printed whitespace, arrays with thousands of near-identical elements, giant
embedded strings. This shrinks them while keeping the shape and a representative
sample, so the agent still understands the structure at a fraction of the cost.

Two modes:
  * sample (default) keeps head+tail elements of long arrays — good for small
    or heterogeneous data where individual values matter;
  * schema collapses a large homogeneous array of objects to a single inferred
    schema node ("[N x {id:int, name:str, ...}]") — a near-flat digest for the
    bulk RAG / table-dump case where only the shape matters.

Lossy by design (it elides bulk), reversible via the cache (the original is kept
by content hash). Our own code; only the stdlib `json` is used.
"""

from __future__ import annotations

import json
from typing import Tuple

SAMPLE = 3          # keep this many head + tail elements of a long array
MAX_STR = 400       # truncate strings longer than this
MAX_DEPTH = 12      # collapse structure deeper than this

# A homogeneous array must be at least this long before schema mode collapses it
# to a single schema node (shorter arrays read fine sampled).
SCHEMA_MIN_ITEMS = 8


def _shrink(node, depth: int, sample: int, max_str: int, max_depth: int):
    if depth > max_depth:
        return "...(nested structure elided)..."
    if isinstance(node, dict):
        return {k: _shrink(v, depth + 1, sample, max_str, max_depth)
                for k, v in node.items()}
    if isinstance(node, list):
        n = len(node)
        if n > 2 * sample + 1:
            head = [_shrink(x, depth + 1, sample, max_str, max_depth)
                    for x in node[:sample]]
            tail = [_shrink(x, depth + 1, sample, max_str, max_depth)
                    for x in node[-sample:]]
            return head + [f"...({n - 2 * sample} more of {n} items elided)..."] + tail
        return [_shrink(x, depth + 1, sample, max_str, max_depth) for x in node]
    if isinstance(node, str) and len(node) > max_str:
        return node[:max_str] + f"...(+{len(node) - max_str} chars)"
    return node


def _type_name(value) -> str:
    """A terse type tag for a scalar/container, used in schema digests."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _infer_schema(node):
    """Infer a compact schema description for a value.

    Objects -> {key: <type>, ...}; uniform lists of objects/scalars -> a tagged
    "[N x <schema>]" string. Deterministic: keys are walked in first-seen order
    across the sample so output never depends on dict iteration luck.
    """
    if isinstance(node, dict):
        return {k: _infer_schema(v) for k, v in node.items()}
    if isinstance(node, list):
        n = len(node)
        if n == 0:
            return "[0 x any]"
        elem = _merge_schemas(node)
        if isinstance(elem, dict):
            fields = ", ".join(f"{k}:{_schema_str(v)}" for k, v in elem.items())
            return f"[{n} x {{{fields}}}]"
        return f"[{n} x {_schema_str(elem)}]"
    return _type_name(node)


def _merge_schemas(items):
    """Merge the inferred schemas of list elements into one representative.

    For a list of objects, the union of fields (first-seen order) maps each key
    to its type; a key seen with differing types collapses to a "|"-joined tag.
    For scalars, returns the (possibly "|"-joined) scalar type tag.
    """
    schemas = [_infer_schema(x) for x in items]
    if all(isinstance(s, dict) for s in schemas):
        merged: dict = {}
        for s in schemas:
            for k, v in s.items():
                if k not in merged:
                    merged[k] = v
                elif merged[k] != v and v not in str(merged[k]).split("|"):
                    merged[k] = f"{merged[k]}|{v}"
        return merged
    # mixed / scalar elements: union of distinct type tags, order-stable
    seen: list = []
    for s in schemas:
        tag = _schema_str(s)
        if tag not in seen:
            seen.append(tag)
    return "|".join(seen)


def _schema_str(node) -> str:
    """Render an inferred-schema fragment to its terse string form."""
    if isinstance(node, dict):
        fields = ", ".join(f"{k}:{_schema_str(v)}" for k, v in node.items())
        return f"{{{fields}}}"
    return str(node)


def is_uniform_object_array(node) -> bool:
    """True if `node` is a list of >=SCHEMA_MIN_ITEMS dicts (schema-mode bait)."""
    return (isinstance(node, list)
            and len(node) >= SCHEMA_MIN_ITEMS
            and all(isinstance(x, dict) for x in node))


def looks_like_json(text: str) -> bool:
    s = text.lstrip()
    if not s or s[0] not in "{[":
        return False
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return False


def schema_json(text: str) -> Tuple[str, dict]:
    """Collapse JSON to an inferred-schema digest instead of a sample.

    Each large homogeneous array of objects becomes one "[N x {field:type,...}]"
    node; the surrounding structure (and scalars) is kept verbatim. Returns
    (digest, stats). If `text` isn't JSON, returns it unchanged.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text, {"kind": "json", "ok": False, "note": "not valid JSON"}

    schema = _schema_node(data)
    digest = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
    stats = {
        "kind": "json",
        "mode": "schema",
        "ok": True,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
    return digest, stats


def _schema_node(node):
    """Walk a parsed value, replacing uniform object arrays with schema nodes
    and keeping everything else as-is (recursing into nested structure)."""
    if is_uniform_object_array(node):
        return _infer_schema(node)
    if isinstance(node, dict):
        return {k: _schema_node(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_schema_node(x) for x in node]
    return node


def _shape(node) -> str:
    """A compact, deterministic description of a record's shape.

    Objects are summarized by their sorted key set, lists/scalars by type. This
    is the grouping key for NDJSON: records with the same shape are bucketed and
    counted instead of dumped one by one.
    """
    if isinstance(node, dict):
        return "{" + ",".join(sorted(node)) + "}"
    if isinstance(node, list):
        return "[]"
    if node is None:
        return "null"
    if isinstance(node, bool):
        return "bool"
    if isinstance(node, (int, float)):
        return "num"
    return type(node).__name__


def compress_ndjson(text: str, sample: int = SAMPLE, max_str: int = MAX_STR,
                    max_depth: int = MAX_DEPTH) -> Tuple[str, dict]:
    """Compress newline-delimited JSON (one JSON value per line).

    A whole-file ``json.loads`` fails on NDJSON, so parse line by line, bucket
    records by their SHAPE (sorted key set), and emit one
    ``[N × {shape}]`` summary per shape with a couple of representative,
    individually-shrunk examples. Malformed lines are tolerated (collected under
    a "<malformed>" bucket) so a single bad line never sinks the whole file.

    Returns (digest, stats). ``stats['ok']`` is False when no line parsed.
    """
    shapes = []                 # preserve first-seen order
    counts: dict = {}
    examples: dict = {}
    parsed = 0
    malformed = 0
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except (ValueError, TypeError):
            malformed += 1
            key = "<malformed>"
            ex = s[:max_str]
        else:
            parsed += 1
            key = _shape(rec)
            ex = rec
        if key not in counts:
            counts[key] = 0
            examples[key] = []
            shapes.append(key)
        counts[key] += 1
        if len(examples[key]) < sample:
            examples[key].append(ex)

    if parsed == 0 and malformed == 0:
        return text, {"kind": "ndjson", "ok": False, "note": "empty"}
    if parsed == 0:
        return text, {"kind": "ndjson", "ok": False, "note": "no valid JSON"}

    out_lines = []
    for key in shapes:
        n = counts[key]
        out_lines.append(f"[{n} × {key}]")
        for ex in examples[key]:
            if key == "<malformed>":
                out_lines.append(f"  {ex}")
            else:
                shrunk = _shrink(ex, 0, sample, max_str, max_depth)
                out_lines.append(
                    "  " + json.dumps(shrunk, separators=(",", ":"),
                                      ensure_ascii=False))
    digest = "\n".join(out_lines) + "\n"
    stats = {
        "kind": "ndjson",
        "ok": True,
        "records": parsed + malformed,
        "shapes": len(shapes),
        "malformed": malformed,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
    return digest, stats


def compress_json(text: str, sample: int = SAMPLE, max_str: int = MAX_STR,
                  max_depth: int = MAX_DEPTH,
                  schema: bool = False) -> Tuple[str, dict]:
    """Return (compact_json, stats). If `text` isn't JSON, returns it unchanged.

    When `schema` is set, emits an inferred-schema digest (see `schema_json`)
    instead of a head+tail sample — far smaller for bulk uniform arrays.
    """
    if schema:
        return schema_json(text)

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text, {"kind": "json", "ok": False, "note": "not valid JSON"}

    shrunk = _shrink(data, 0, sample, max_str, max_depth)
    # Minify: pretty-printed JSON wastes tokens on whitespace.
    digest = json.dumps(shrunk, separators=(",", ":"), ensure_ascii=False)
    stats = {
        "kind": "json",
        "mode": "sample",
        "ok": True,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
    return digest, stats
