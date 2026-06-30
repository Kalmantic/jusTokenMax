"""JUnit XML compression.

CI test reports are often large XML files where the useful signal is the
summary plus failing/skipped cases. This keeps those details and drops the bulk
passing testcase payload.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Tuple

MAX_CASES = 40
MAX_TEXT = 500


def _tag(el) -> str:
    return str(el.tag).rsplit("}", 1)[-1]


def _int_attr(el, name: str) -> int:
    try:
        return int(float(el.attrib.get(name, "0") or 0))
    except ValueError:
        return 0


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + f"...(+{len(text) - MAX_TEXT} chars)"


def compress_junit_xml(text: str) -> Tuple[str, dict]:
    """Return (markdown_digest, stats), or ok=False when XML is not JUnit."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return text, {"kind": "junit", "ok": False, "note": "not valid XML"}

    root_tag = _tag(root)
    if root_tag not in {"testsuite", "testsuites"}:
        return text, {"kind": "junit", "ok": False, "note": "not JUnit XML"}

    suites = [el for el in root.iter() if _tag(el) == "testsuite"]
    cases = [el for el in root.iter() if _tag(el) == "testcase"]
    if not suites and not cases:
        return text, {"kind": "junit", "ok": False, "note": "empty JUnit XML"}

    totals = {
        "tests": sum(_int_attr(s, "tests") for s in suites) or len(cases),
        "failures": sum(_int_attr(s, "failures") for s in suites),
        "errors": sum(_int_attr(s, "errors") for s in suites),
        "skipped": sum(_int_attr(s, "skipped") for s in suites),
    }
    interesting = []
    for case in cases:
        markers = [child for child in list(case)
                   if _tag(child) in {"failure", "error", "skipped"}]
        if not markers:
            continue
        for marker in markers:
            interesting.append((case, marker))

    lines = [
        "# JUnit XML summary",
        "",
        f"- suites: {len(suites)}",
        f"- testcases: {len(cases)}",
        f"- tests: {totals['tests']}",
        f"- failures: {totals['failures']}",
        f"- errors: {totals['errors']}",
        f"- skipped: {totals['skipped']}",
    ]
    if interesting:
        hidden = max(0, len(interesting) - MAX_CASES)
        lines += ["", "## Failing / skipped cases"]
        for case, marker in interesting[:MAX_CASES]:
            label = _tag(marker)
            classname = case.attrib.get("classname", "")
            name = case.attrib.get("name", "")
            full_name = ".".join(x for x in (classname, name) if x)
            message = marker.attrib.get("message") or marker.attrib.get("type") or ""
            lines.append(f"- {label}: {full_name or '(unnamed testcase)'}")
            if message:
                lines.append(f"  message: {_clip(message)}")
            body = _clip(marker.text or "")
            if body:
                lines.append(f"  detail: {body}")
        if hidden:
            lines.append(f"- ... {hidden} more failing/skipped cases elided")

    digest = "\n".join(lines) + "\n"
    return digest, {
        "kind": "junit",
        "ok": True,
        "suites": len(suites),
        "testcases": len(cases),
        "interesting": len(interesting),
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
