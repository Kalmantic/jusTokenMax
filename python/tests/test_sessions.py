import json
import threading

import pytest

from justokenmax import cache, sessions


def _good_row(ended, tok, kind="log"):
    return json.dumps(
        {"ended": ended, "tokens_saved": tok, "runs": 1, "by_kind": {kind: tok}}
    )


def test_records_delta_since_last_snapshot():
    cache.record_savings(1000, "log")
    row1 = sessions.record(session_id="s1")
    assert row1["tokens_saved"] == 1000 and row1["runs"] == 1
    assert row1["by_kind"] == {"log": 1000}
    assert row1["session_id"] == "s1"

    # second session only counts what happened since
    cache.record_savings(400, "csv")
    row2 = sessions.record()
    assert row2["tokens_saved"] == 400
    assert row2["by_kind"] == {"csv": 400}


def test_no_activity_records_nothing():
    sessions.record()                 # snapshot baseline
    assert sessions.record() is None   # nothing happened since


def test_summary_aggregates():
    cache.record_savings(1000, "log")
    sessions.record()
    cache.record_savings(500, "log")
    cache.record_savings(300, "csv")
    sessions.record()
    s = sessions.summary()
    assert s["sessions"] == 2
    assert s["tokens_saved"] == 1800
    assert s["avg_per_session"] == 900
    assert s["by_kind"]["log"] == 1500 and s["by_kind"]["csv"] == 300


def test_read_limit():
    for i in range(4):
        cache.record_savings(100, "log")
        sessions.record()
    assert len(sessions.read(limit=2)) == 2
    assert len(sessions.read()) == 4


def test_read_skips_corrupt_lines():
    cache.record_savings(100, "log")
    sessions.record()
    cache.record_savings(100, "log")
    sessions.record()
    # Splice a garbage line between two good rows; read() must skip it, not crash.
    p = sessions._sessions_path()
    good = p.read_text(encoding="utf-8").splitlines()
    p.write_text(good[0] + "\ngarbage\n" + good[1] + "\n", encoding="utf-8")
    assert len(sessions.read()) == 2


def test_record_appends_row():
    cache.record_savings(700, "log")
    row = sessions.record(session_id="s1")
    assert row is not None and row["tokens_saved"] == 700
    rows = sessions.read()
    assert any(r.get("session_id") == "s1" and r["tokens_saved"] == 700
               for r in rows)


def test_crash_before_snapshot_keeps_row(monkeypatch):
    """Crash AFTER appending the row but BEFORE advancing the snapshot: the row
    must survive on disk, and a later record() must not silently lose it (worst
    case a recoverable double-count)."""
    cache.record_savings(1000, "log")

    def boom(_led):
        raise RuntimeError("crash before snapshot")

    monkeypatch.setattr(sessions, "_write_snapshot", boom)
    with pytest.raises(RuntimeError):
        sessions.record(session_id="s1")

    rows = sessions.read()
    assert len(rows) == 1
    assert rows[0]["tokens_saved"] == 1000
    assert rows[0]["session_id"] == "s1"
    assert not sessions._snapshot_path().exists()

    monkeypatch.undo()
    row2 = sessions.record(session_id="s2")
    assert row2 is not None and row2["tokens_saved"] == 1000
    all_rows = sessions.read()
    assert len(all_rows) == 2
    assert sum(r["tokens_saved"] for r in all_rows) == 2000


def test_old_ordering_would_lose_the_row(monkeypatch):
    """OLD ordering (snapshot BEFORE append) permanently loses a row if it
    crashes between the two steps. Proves the fix's reordering matters."""

    def old_record(session_id=None):
        led = cache.read_ledger()
        snap = sessions._load_snapshot()
        delta_total = led.get("total_tokens_saved", 0) - snap.get(
            "total_tokens_saved", 0
        )
        delta_runs = led.get("runs", 0) - snap.get("runs", 0)
        if delta_total <= 0 and delta_runs <= 0:
            sessions._write_snapshot(led)
            return None
        sessions._write_snapshot(led)  # OLD: advance snapshot FIRST
        raise RuntimeError("crash before append")

    cache.record_savings(1000, "log")
    with pytest.raises(RuntimeError):
        old_record(session_id="s1")

    assert sessions._load_snapshot().get("total_tokens_saved") == 1000
    assert sessions.record() is None
    assert sessions.read() == []  # 1000 tokens permanently lost under old order


def test_concurrent_record_no_torn_rows():
    """Interleaved record() calls must keep sessions.jsonl as valid NDJSON."""

    def worker(i):
        cache.record_savings(100 + i, "log")
        sessions.record(session_id=f"s{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    raw = sessions._sessions_path().read_text(encoding="utf-8")
    assert raw == "" or raw.endswith("\n")  # no half-written final line
    for ln in raw.splitlines():
        if ln.strip():
            json.loads(ln)  # every non-blank line parses; no torn rows
    valid = sum(1 for ln in raw.splitlines() if ln.strip())
    assert len(sessions.read()) == valid


def test_read_empty_file_returns_nothing():
    sessions._sessions_path().parent.mkdir(parents=True, exist_ok=True)
    sessions._sessions_path().write_text("")
    assert sessions.read() == []
    assert sessions.summary()["sessions"] == 0


def test_read_skips_blanks_garbage_and_truncated_last_line():
    p = sessions._sessions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    content = (
        _good_row("t1", 100) + "\n"
        + "\n"
        + "   \n"
        + "this is not json {" + "\n"
        + _good_row("t2", 200) + "\n"
        + '{"ended": "t3", "tokens_saved": 300'  # truncated, no newline
    )
    p.write_text(content, encoding="utf-8")
    rows = sessions.read()
    assert [r["tokens_saved"] for r in rows] == [100, 200]


def test_summary_ignores_corrupt_line():
    p = sessions._sessions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        _good_row("t1", 100) + "\n"
        + "CORRUPT\n"
        + _good_row("t2", 250, kind="csv") + "\n",
        encoding="utf-8",
    )
    s = sessions.summary()  # must not raise
    assert s["sessions"] == 2
    assert s["tokens_saved"] == 350
    assert s["by_kind"] == {"log": 100, "csv": 250}


def test_read_handles_leading_bom_without_losing_first_row():
    """A leading UTF-8 BOM must not cause the first valid row to be dropped."""
    p = sessions._sessions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "﻿" + _good_row("t1", 100) + "\n" + _good_row("t2", 200) + "\n",
        encoding="utf-8",
    )
    rows = sessions.read()
    assert [r["tokens_saved"] for r in rows] == [100, 200]
