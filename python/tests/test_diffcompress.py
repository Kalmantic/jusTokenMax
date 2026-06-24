from justokenmax.diffcompress import compress_diff


def _lockfile_section(n=4000):
    lines = ["diff --git a/package-lock.json b/package-lock.json",
             "index 1111111..2222222 100644",
             "--- a/package-lock.json",
             "+++ b/package-lock.json",
             "@@ -1,4 +1,%d @@" % (n + 4)]
    lines += [f'+        "dep-{i}": "^1.2.{i}",' for i in range(n)]
    return "\n".join(lines)


def _code_section():
    return "\n".join([
        "diff --git a/src/app.py b/src/app.py",
        "index aaa..bbb 100644",
        "--- a/src/app.py",
        "+++ b/src/app.py",
        "@@ -10,3 +10,4 @@ def handler():",
        " context line",
        "-    return None",
        "+    log.info('handled')",
        "+    return ok",
    ])


def test_elides_lockfile_keeps_code():
    diff = _lockfile_section() + "\n" + _code_section()
    digest, st = compress_diff(diff)
    # lockfile body gone, summarized
    assert '"dep-1000"' not in digest
    assert "lockfile/generated — diff elided" in digest
    assert st["files_elided"] == 1
    assert st["files_total"] == 2
    # real code change preserved
    assert "log.info('handled')" in digest
    assert st["lines_after"] < st["lines_before"]


def test_minified_and_generated_elided():
    diff = "\n".join([
        "diff --git a/web/bundle.min.js b/web/bundle.min.js",
        "--- a/web/bundle.min.js",
        "+++ b/web/bundle.min.js",
        "@@ -1 +1 @@",
        "+" + "a" * 5000,
        "diff --git a/api/schema.pb.go b/api/schema.pb.go",
        "--- a/api/schema.pb.go",
        "+++ b/api/schema.pb.go",
        "@@ -1,2 +1,3 @@",
        "+generated code",
    ])
    digest, st = compress_diff(diff)
    assert st["files_elided"] == 2
    assert "a" * 5000 not in digest


def test_small_normal_diff_passes_through():
    digest, st = compress_diff(_code_section())
    assert st["files_elided"] == 0
    assert "log.info('handled')" in digest


def test_large_real_file_truncated():
    big = ["diff --git a/src/huge.py b/src/huge.py",
           "--- a/src/huge.py", "+++ b/src/huge.py",
           "@@ -1,1 +1,2000 @@"]
    big += [f"+line {i}" for i in range(2000)]
    digest, st = compress_diff("\n".join(big))
    assert "large diff truncated" in digest
    assert st["files_elided"] == 0
