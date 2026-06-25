import os

import pytest

from justokenmax import codeindex


@pytest.fixture
def sample_repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text(
        'def parse_config(path, strict=False):\n'
        '    """Load and validate config."""\n'
        '    return {}\n'
        '\n'
        'class Engine:\n'
        '    """The engine."""\n'
        '    def run(self, x, *args, **kw):\n'
        '        return x\n'
    )
    (tmp_path / "web.js").write_text(
        "export function renderPage(props) {}\n"
        "const handleClick = (e) => {}\n"
        "class Widget {}\n"
    )
    # a dir that must be skipped
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("function shouldNotIndex(){}\n")
    return str(tmp_path)


def test_build_index_python_symbols(sample_repo):
    idx = codeindex.build_index(sample_repo)
    names = {s["name"] for s in idx["symbols"]}
    assert {"parse_config", "Engine", "run", "renderPage", "Widget"} <= names
    # skip dir respected
    assert "shouldNotIndex" not in names
    # index file written
    assert os.path.exists(os.path.join(sample_repo, ".justokenmax", "index.json"))


def test_python_signature_and_kind(sample_repo):
    codeindex.build_index(sample_repo)
    hits = codeindex.query(sample_repo, "parse_config")
    assert hits[0]["kind"] == "func"
    assert hits[0]["sig"] == "def parse_config(path, strict)"
    assert hits[0]["doc"] == "Load and validate config."
    assert hits[0]["file"].endswith("core.py")


def test_method_is_qualified(sample_repo):
    codeindex.build_index(sample_repo)
    hits = codeindex.query(sample_repo, "run", kind="method")
    assert hits and hits[0]["sig"] == "Engine.run(self, x, *args, **kw)"


def test_query_exact_match_ranks_first(sample_repo):
    codeindex.build_index(sample_repo)
    hits = codeindex.query(sample_repo, "Widget")
    assert hits[0]["name"] == "Widget"
    assert hits[0]["kind"] == "class"


def test_query_without_index_returns_empty(tmp_path):
    assert codeindex.query(str(tmp_path), "anything") == []


def test_format_hits_compact(sample_repo):
    codeindex.build_index(sample_repo)
    out = codeindex.format_hits(codeindex.query(sample_repo, "parse_config"))
    assert "core.py:1" in out and "[func]" in out


# --------------------------- .gitignore awareness ------------------------- #
def test_gitignore_excludes_files_and_dirs(tmp_path):
    (tmp_path / "keep.py").write_text("def keep_me(): pass\n")
    (tmp_path / "generated.py").write_text("def generated_sym(): pass\n")
    (tmp_path / "buildout").mkdir()
    (tmp_path / "buildout" / "g.py").write_text("def vendored_sym(): pass\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def app_sym(): pass\n")
    (tmp_path / ".gitignore").write_text("generated.py\nbuildout/\n")

    idx = codeindex.build_index(str(tmp_path))
    names = {s["name"] for s in idx["symbols"]}
    assert "keep_me" in names
    assert "app_sym" in names
    assert "generated_sym" not in names   # file-pattern ignored
    assert "vendored_sym" not in names     # dir-pattern pruned


def test_gitignore_glob_pattern(tmp_path):
    (tmp_path / "real.py").write_text("def real_fn(): pass\n")
    (tmp_path / "thing.gen.py").write_text("def gen_fn(): pass\n")
    (tmp_path / ".gitignore").write_text("*.gen.py\n")
    idx = codeindex.build_index(str(tmp_path))
    names = {s["name"] for s in idx["symbols"]}
    assert "real_fn" in names and "gen_fn" not in names


def test_gitignore_anchored_dir_only_matches_root(tmp_path):
    # Regression: an anchored `/dist/` is pinned to the repo root. It must prune
    # ./dist but NOT a nested ./packages/foo/dist (common in monorepos) — the
    # original matcher checked every path segment and dropped the sub-package.
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "top.py").write_text("def top_sym(): pass\n")
    (tmp_path / "packages" / "foo" / "dist").mkdir(parents=True)
    (tmp_path / "packages" / "foo" / "dist" / "sub.py").write_text(
        "def nested_dist_sym(): pass\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text("def keep_sym(): pass\n")
    (tmp_path / ".gitignore").write_text("/dist/\n")

    idx = codeindex.build_index(str(tmp_path))
    names = {s["name"] for s in idx["symbols"]}
    assert "keep_sym" in names
    assert "nested_dist_sym" in names      # nested dist must survive
    assert "top_sym" not in names          # root-level dist still pruned


# --------------------------- incremental rebuild -------------------------- #
def test_build_index_reuses_cache_for_unchanged(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("def alpha(): pass\n")
    (tmp_path / "b.py").write_text("def beta(): pass\n")

    calls = []
    real_parse = codeindex.parse_file

    def spy(path, rel, lang):
        calls.append(rel)
        return real_parse(path, rel, lang)

    monkeypatch.setattr(codeindex, "parse_file", spy)

    codeindex.build_index(str(tmp_path))
    first = sorted(c for c in calls if c.endswith(".py"))
    assert "a.py" in first and "b.py" in first

    # Nothing changed: a second build must NOT re-parse either file.
    calls.clear()
    idx = codeindex.build_index(str(tmp_path))
    assert calls == []
    names = {s["name"] for s in idx["symbols"]}
    assert {"alpha", "beta"} <= names


def test_build_index_reparses_only_changed(tmp_path, monkeypatch):
    fa = tmp_path / "a.py"
    fb = tmp_path / "b.py"
    fa.write_text("def alpha(): pass\n")
    fb.write_text("def beta(): pass\n")
    codeindex.build_index(str(tmp_path))

    calls = []
    real_parse = codeindex.parse_file

    def spy(path, rel, lang):
        calls.append(rel)
        return real_parse(path, rel, lang)

    monkeypatch.setattr(codeindex, "parse_file", spy)

    # Bump only b.py's mtime + content; a.py must come from cache.
    st = os.stat(str(fb))
    fb.write_text("def beta(): pass\ndef gamma(): pass\n")
    os.utime(str(fb), (st.st_atime + 10, st.st_mtime + 10))

    idx = codeindex.build_index(str(tmp_path))
    assert calls == ["b.py"]
    names = {s["name"] for s in idx["symbols"]}
    assert {"alpha", "beta", "gamma"} <= names
