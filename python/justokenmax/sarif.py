"""SARIF report compression.

Static-analysis and code-scanning reports are verbose JSON. The useful agent
signal is the finding inventory: tool, rules, severity counts, messages, and
locations. The original report remains retrievable when a full result is needed.
"""

from __future__ import annotations

import json
from typing import Tuple

MAX_RESULTS = 60
MAX_MESSAGE = 300


def _message(obj) -> str:
    if not isinstance(obj, dict):
        return ""
    msg = obj.get("message")
    if isinstance(msg, dict):
        text = msg.get("text") or msg.get("markdown") or ""
    else:
        text = str(msg or "")
    text = " ".join(text.split())
    if len(text) <= MAX_MESSAGE:
        return text
    return text[:MAX_MESSAGE] + f"...(+{len(text) - MAX_MESSAGE} chars)"


def _location(result) -> str:
    locs = result.get("locations") if isinstance(result, dict) else None
    if not isinstance(locs, list) or not locs:
        return ""
    phys = locs[0].get("physicalLocation", {}) if isinstance(locs[0], dict) else {}
    artifact = phys.get("artifactLocation", {}) if isinstance(phys, dict) else {}
    region = phys.get("region", {}) if isinstance(phys, dict) else {}
    uri = artifact.get("uri") if isinstance(artifact, dict) else None
    line = region.get("startLine") if isinstance(region, dict) else None
    if uri and line:
        return f"{uri}:{line}"
    return str(uri or "")


def compress_sarif(text: str) -> Tuple[str, dict]:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return text, {"kind": "sarif", "ok": False, "note": "not JSON"}
    if not isinstance(data, dict) or "runs" not in data:
        return text, {"kind": "sarif", "ok": False, "note": "not SARIF"}

    runs = data.get("runs")
    if not isinstance(runs, list):
        return text, {"kind": "sarif", "ok": False, "note": "not SARIF"}

    level_counts: dict = {}
    rule_counts: dict = {}
    shown = []
    total_results = 0
    rule_total = 0
    tool_names = []

    for run in runs:
        if not isinstance(run, dict):
            continue
        tool = run.get("tool", {}).get("driver", {})
        if isinstance(tool, dict):
            name = tool.get("name")
            if name:
                tool_names.append(str(name))
            rules = tool.get("rules")
            if isinstance(rules, list):
                rule_total += len(rules)
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            total_results += 1
            level = str(result.get("level") or "none")
            rule_id = str(result.get("ruleId") or result.get("rule", {}).get("id")
                          or "unknown")
            level_counts[level] = level_counts.get(level, 0) + 1
            rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
            if len(shown) < MAX_RESULTS:
                shown.append({
                    "level": level,
                    "rule": rule_id,
                    "location": _location(result),
                    "message": _message(result),
                })

    lines = [
        "# SARIF summary",
        "",
        f"- version: {data.get('version', '')}",
        f"- runs: {len(runs)}",
        f"- tools: {', '.join(tool_names) if tool_names else '(unknown)'}",
        f"- rules: {rule_total}",
        f"- results: {total_results}",
    ]
    if level_counts:
        lines += ["", "## Results by Level"]
        for level, count in sorted(level_counts.items()):
            lines.append(f"- {level}: {count}")
    if rule_counts:
        lines += ["", "## Top Rules"]
        for rule, count in sorted(rule_counts.items(), key=lambda item: (-item[1], item[0]))[:20]:
            lines.append(f"- {rule}: {count}")
    if shown:
        lines += ["", "## Findings"]
        for item in shown:
            loc = f" at {item['location']}" if item["location"] else ""
            lines.append(f"- {item['level']} {item['rule']}{loc}: {item['message']}")
        hidden = max(0, total_results - len(shown))
        if hidden:
            lines.append(f"- ... {hidden} more findings elided")

    digest = "\n".join(lines) + "\n"
    return digest, {
        "kind": "sarif",
        "ok": True,
        "runs": len(runs),
        "rules": rule_total,
        "results": total_results,
        "bytes_before": len(text),
        "bytes_after": len(digest),
    }
