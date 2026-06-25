"""Code-skeleton outline compression on the Read path (optimize kind="code")."""

import os
from pathlib import Path

import pytest

from justokenmax import cache
from justokenmax.optimize import optimize
from justokenmax.tokens import text_tokens


@pytest.fixture
def big_py(tmp_path):
    """A source file well above CODE_MIN_BYTES with fat function bodies."""
    parts = ['"""Module docstring."""', "", "import os", ""]
    for i in range(40):
        parts.append(f"def func_{i}(a, b, c):")
        parts.append(f'    """Do thing {i}."""')
        # A heavy body the outline must drop.
        for j in range(20):
            parts.append(f"    x_{j} = a + b + c + {i} + {j}  # filler line")
        parts.append(f"    return x_0 + {i}")
        parts.append("")
    p = tmp_path / "big_module.py"
    p.write_text("\n".join(parts))
    return str(p)


def test_code_dispatch_outlines(big_py):
    res = optimize(big_py)
    assert res.ok and res.kind == "code"
    assert res.output.endswith(".outline.md")
    assert os.path.exists(res.output)
    assert res.tokens_after < res.tokens_before
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    # Signatures kept...
    assert "func_0" in digest
    assert "func_39" in digest
    # ...bodies gone.
    assert "filler line" not in digest
    assert "x_0 = a + b + c" not in digest


def test_code_second_run_cache_hit(big_py):
    first = optimize(big_py)
    second = optimize(big_py)
    assert first.cached is False and second.cached is True
    assert second.output == first.output


def test_code_retrieve_returns_original(big_py):
    res = optimize(big_py)
    assert res.ok
    assert cache.lookup_origin(res.output) == big_py


def test_small_source_skipped(tmp_path):
    p = tmp_path / "tiny.py"
    p.write_text("def f():\n    return 1\n")
    res = optimize(str(p))
    assert res.ok is False
    assert res.kind == "skip"
    assert res.output is None


def test_unparseable_source_falls_back(tmp_path):
    """A big .py file that is not valid Python must not raise; just skip."""
    p = tmp_path / "broken.py"
    # Binary-ish junk, padded past CODE_MIN_BYTES, yields no symbols.
    p.write_bytes(b"\x00\xff not python at all }{ " + b"#" * 8192)
    res = optimize(str(p))
    assert res.ok is False
    assert res.kind == "skip"
    assert res.output is None


def test_code_disabled_by_config(big_py, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_DISABLE", "code")
    res = optimize(big_py)
    assert res.ok is False
    assert res.kind == "skip"
    assert res.note == "disabled by config"


def test_code_savings_recorded(big_py):
    before = cache.read_ledger().get("total_tokens_saved", 0)
    res = optimize(big_py)
    after = cache.read_ledger().get("total_tokens_saved", 0)
    assert res.ok
    assert after - before == res.tokens_saved


def test_outline_token_estimate_matches_artifact(big_py):
    res = optimize(big_py)
    digest = Path(res.output).read_text(encoding="utf-8")
    assert res.tokens_after == text_tokens(digest)
