from justokenmax.logs import compress_log


def _noisy_log():
    lines = ["\x1b[32mINFO\x1b[0m starting build"]
    lines += [f"\x1b[2mcompiling module {i}\x1b[0m" for i in range(200)]
    lines += ["downloading dep"] * 50          # exact repeats
    lines += [
        'Traceback (most recent call last):',
        '  File "a.py", line 1, in <module>',
        '  File "b.py", line 2, in foo',
        '  File "c.py", line 3, in bar',
        '  File "d.py", line 4, in baz',
        '  File "e.py", line 5, in qux',
        "ValueError: boom",
    ]
    lines += [f"cleanup step {i}" for i in range(40)]
    lines += ["WARNING: deprecated flag used", "Build FAILED"]
    return "\n".join(lines)


def test_strips_ansi_and_shrinks():
    raw = _noisy_log()
    digest, stats = compress_log(raw)
    assert "\x1b[" not in digest                     # ANSI gone
    assert stats["lines_after"] < stats["lines_before"]
    assert len(digest) < len(raw)


def test_keeps_errors_and_warnings():
    digest, _ = compress_log(_noisy_log())
    assert "ValueError: boom" in digest
    assert "Build FAILED" in digest
    assert "WARNING: deprecated flag used" in digest


def test_collapses_repeats_with_count():
    digest, _ = compress_log(_noisy_log())
    assert "(x" in digest                            # repeated lines collapsed


def test_folds_stack_frames():
    digest, _ = compress_log(_noisy_log())
    assert "stack frames elided" in digest
    # first and last frame preserved
    assert 'File "a.py"' in digest
    assert 'File "e.py"' in digest


def test_small_log_passthrough_shape():
    digest, stats = compress_log("line one\nline two\n")
    assert "line one" in digest and "line two" in digest
    assert stats["kind"] == "log"


def _lint_log(n=5000):
    """A long lint/typecheck log: the same complaint on thousands of files."""
    lines = ["INFO: type-checking project"]
    for i in range(n):
        lines.append(
            f'src/pkg/module{i}.py:{i % 90 + 1}:{i % 12 + 1}: '
            'error: Name "foo" is not defined  [name-defined]')
    lines += ["Found errors", "FAILED"]
    return "\n".join(lines)


def test_repetitive_lint_lines_group_to_signature():
    raw = _lint_log()
    digest, stats = compress_log(raw)
    # 5000 near-identical lines collapse to a handful of grouped rows.
    assert stats["lines_after"] < 60
    assert "(×" in digest                            # grouped marker present
    # The grouped row carries the count of the dominant signature.
    rows = [ln for ln in digest.splitlines() if "(×" in ln]
    assert rows, "expected at least one grouped signature row"
    assert any("name-defined" in r for r in rows)
    # Paths and line numbers are normalized away in the signature.
    assert any("<path>" in r or "<n>" in r for r in rows)


def test_grouping_keeps_distinct_signatures_separate():
    lines = ["INFO start"]
    lines += [f"src/a{i}.py:{i}: error: undefined name 'x'" for i in range(40)]
    lines += [f"src/b{i}.py:{i}: warning: unused import 'os'" for i in range(40)]
    lines += [f"filler line {i}" for i in range(40)]
    lines += ["done"]
    digest, _ = compress_log("\n".join(lines))
    # Two distinct complaint signatures -> two distinct grouped rows.
    assert "undefined name 'x'" in digest
    assert "unused import 'os'" in digest
    rows = [ln for ln in digest.splitlines() if "(×" in ln]
    assert len(rows) >= 2
