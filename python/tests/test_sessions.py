from justokenmax import cache, sessions


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
