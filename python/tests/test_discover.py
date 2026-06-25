"""Survey of Claude Code history -> recoverable tokens + compressor backlog."""

import json
import os
import time

from justokenmax import discover


def _session(dirpath, name, reads):
    """Write a fake session .jsonl whose assistant turns Read the given paths."""
    lines = []
    for path in reads:
        msg = {"role": "assistant",
               "content": [{"type": "tool_use", "name": "Read",
                            "input": {"file_path": path}}]}
        lines.append(json.dumps({"type": "assistant", "message": msg}))
    p = dirpath / name
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_discover_reports_recoverable_tokens(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects" / "proj-a"
    hist.mkdir(parents=True)
    _session(hist, "s1.jsonl", [big_json, big_json])  # duplicate read, dedup'd
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(tmp_path / "projects"))

    rep = discover.discover()
    assert rep["sessions"] == 1
    assert rep["reads_total"] == 2
    assert rep["files_seen"] == 1            # the dup collapses
    assert rep["recoverable_tokens"] > 0
    assert "json" in rep["by_kind"]
    # the big_json file appears in the by-path breakdown
    assert any(k.endswith("response.json") for k in rep["by_path"])


def test_discover_buckets_unsupported_extensions(tmp_path, monkeypatch):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    # An unsupported-but-real source file: jusTokenMax has no .toml compressor.
    cfg = tmp_path / "pyproject.toml"
    cfg.write_text("[tool.x]\nname = 'y'\n")
    other = tmp_path / "settings.toml"
    other.write_text("a = 1\n")
    _session(hist, "s.jsonl", [str(cfg), str(other)])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    rep = discover.discover()
    assert rep["unsupported_exts"].get(".toml") == 2
    assert rep["recoverable_tokens"] == 0


def test_discover_skips_missing_files(tmp_path, monkeypatch):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    _session(hist, "s.jsonl", [str(tmp_path / "gone.json")])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    rep = discover.discover()
    assert rep["files_missing"] == 1
    assert rep["recoverable_tokens"] == 0


def test_discover_stops_scanning_at_max_files(tmp_path, monkeypatch):
    # Regression: once `max_files` unique paths are seen, every remaining read
    # is a dup or would be refused, so discover() must stop rather than scan all
    # of history (was `continue`, i.e. O(all reads)). With a cap of 3 and 10
    # distinct reads, files_seen caps at 3 and reads_total reflects the early
    # stop (not all 10).
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    _session(hist, "s.jsonl", [f"/tmp/f{i}.txt" for i in range(10)])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    rep = discover.discover(max_files=3)
    assert rep["files_seen"] == 3
    assert rep["reads_total"] < 10           # short-circuited, didn't scan all


def test_discover_fails_open_when_history_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(tmp_path / "nope"))
    rep = discover.discover()
    assert rep["note"] == "no history dir"
    assert rep["recoverable_tokens"] == 0


def test_discover_ignores_malformed_lines(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    good = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": big_json}}]}})
    (hist / "s.jsonl").write_text("not json\n\n" + good + "\n{bad\n")
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    rep = discover.discover()
    assert rep["files_seen"] == 1
    assert rep["recoverable_tokens"] > 0


def test_format_report_is_readable(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    _session(hist, "s.jsonl", [big_json])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))
    out = discover.format_report(discover.discover())
    assert "recoverable tokens" in out
    assert "json" in out


def test_format_report_surfaces_total_kinds_and_missed_formats(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    # A real-but-unsupported source so it lands in the missed-formats backlog.
    cfg = tmp_path / "settings.toml"
    cfg.write_text("a = 1\n")
    _session(hist, "s.jsonl", [big_json, str(cfg)])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    rep = discover.discover()
    out = discover.format_report(rep)
    # recoverable total is rendered (with thousands separators)
    assert f"{rep['recoverable_tokens']:,} recoverable tokens" in out
    # top kinds section names the kind we compressed
    assert "top kinds by recoverable tokens" in out
    assert "json" in out
    # missed formats are framed as a roadmap, not just "unsupported"
    assert "compressors worth adding" in out
    assert ".toml" in out


def test_format_report_shows_since_last_run_delta():
    prev = {"recoverable_tokens": 100}
    cur = {"recoverable_tokens": 175}
    out = discover.format_report(cur, previous=prev)
    assert "since last run: +75 recoverable tokens" in out
    out2 = discover.format_report({"recoverable_tokens": 40}, previous=prev)
    assert "since last run: -60 recoverable tokens" in out2


def test_newer_than_days_filters_logs_by_mtime(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    _session(hist, "recent.jsonl", [big_json])
    stale = _session(hist, "stale.jsonl", [big_json])
    # Backdate the stale log to 30 days ago; recent.jsonl stays fresh.
    old = time.time() - 30 * 86400
    os.utime(stale, (old, old))
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    windowed = discover.discover(newer_than_days=7)
    assert windowed["sessions"] == 1          # only the recent log survives
    assert windowed["window_days"] == 7

    full = discover.discover()
    assert full["sessions"] == 2              # no window -> both logs scanned


def test_empty_history_renders_graceful_report(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(tmp_path / "nope"))
    rep = discover.discover(newer_than_days=7)
    out = discover.format_report(rep)
    assert "0 recoverable tokens" in out
    assert "no history dir" in out


def test_save_and_load_report_roundtrip(tmp_path, monkeypatch, big_json):
    hist = tmp_path / "projects"
    hist.mkdir(parents=True)
    _session(hist, "s.jsonl", [big_json])
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(hist))

    assert discover.load_last_report() is None    # nothing cached yet
    rep = discover.discover()
    discover.save_report(rep)
    back = discover.load_last_report()
    assert back is not None
    assert back["recoverable_tokens"] == rep["recoverable_tokens"]
