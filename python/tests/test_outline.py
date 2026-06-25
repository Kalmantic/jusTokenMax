from justokenmax.outline import file_outline
from justokenmax.tokens import text_tokens


PY = (
    'def parse_config(path, strict=False):\n'
    '    """Load and validate config."""\n'
    '    data = {}\n'
    '    for i in range(100):\n'
    '        data[i] = i * 2\n'
    '    return data\n'
    '\n'
    'class Engine:\n'
    '    """The engine."""\n'
    '    def run(self, x, *args, **kw):\n'
    '        return x\n'
)


def test_outline_lists_signatures_with_lines(tmp_path):
    p = tmp_path / "core.py"
    p.write_text(PY)
    text, st = file_outline(str(p))
    assert st["ok"] and st["symbols"] == 3
    assert "def parse_config(path, strict)" in text
    assert "class Engine" in text
    assert "Engine.run(self, x, *args, **kw)" in text
    assert "1-6  " in text                   # start-end span for first symbol


def test_outline_omits_bodies_and_is_cheaper(tmp_path):
    p = tmp_path / "core.py"
    p.write_text(PY)
    text, _ = file_outline(str(p))
    assert "data[i] = i * 2" not in text     # body excluded
    assert text_tokens(text) < text_tokens(PY)


def test_outline_includes_docstring(tmp_path):
    p = tmp_path / "core.py"
    p.write_text(PY)
    text, _ = file_outline(str(p))
    assert "Load and validate config." in text


def test_outline_javascript(tmp_path):
    p = tmp_path / "app.js"
    p.write_text("export function render(props) {}\nclass Widget {}\n")
    text, st = file_outline(str(p))
    assert st["ok"]
    assert "render" in text and "Widget" in text


def test_unsupported_language_skipped(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("just text")
    _, st = file_outline(str(p))
    assert st["ok"] is False


def test_outline_emits_line_end_span(tmp_path):
    p = tmp_path / "core.py"
    p.write_text(PY)
    text, _ = file_outline(str(p))
    # parse_config spans source lines 1-6; the span is a precise pointer.
    assert "1-6" in text
    # Engine spans lines 8-11 (class header through last method body).
    assert "8-11" in text


def test_small_file_not_capped(tmp_path):
    p = tmp_path / "core.py"
    p.write_text(PY)
    text, st = file_outline(str(p))
    assert st["symbols"] == 3
    assert "capped" not in st
    assert "more symbols)" not in text


def test_huge_file_capped_at_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_MAX_READ_TOKENS", "300")
    # 400 top-level functions: way over a 300-token outline budget.
    src = "".join(
        f"def func_{i:04d}(alpha, beta, gamma):\n"
        f'    """Handler number {i}."""\n'
        f"    return alpha + beta + gamma\n\n"
        for i in range(400)
    )
    p = tmp_path / "big.py"
    p.write_text(src)
    text, st = file_outline(str(p))

    assert st["ok"] and st["symbols"] == 400
    assert st.get("capped") is True
    assert text_tokens(text) <= 300
    # The remainder marker is present and accounts for the dropped symbols.
    import re
    m = re.search(r"\.\.\. \((\d+) more symbols\)", text)
    assert m, text[-200:]
    n_more = int(m.group(1))
    assert n_more > 0
    assert st["shown"] + n_more == 400


def test_cap_keeps_top_level_first(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_MAX_READ_TOKENS", "200")
    # A late top-level function must outrank earlier nested methods.
    parts = ["class Big:\n"]
    for i in range(200):
        parts.append(f"    def method_{i:04d}(self):\n        return {i}\n")
    parts.append("\ndef important_entrypoint(config):\n    return config\n")
    p = tmp_path / "ranked.py"
    p.write_text("".join(parts))
    text, st = file_outline(str(p))
    assert st.get("capped") is True
    # The top-level function survives the cap even though it appears last.
    assert "important_entrypoint" in text


def test_cap_disabled_when_budget_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_MAX_READ_TOKENS", "0")
    src = "".join(
        f"def func_{i:04d}(a):\n    return a\n\n" for i in range(400)
    )
    p = tmp_path / "big.py"
    p.write_text(src)
    text, st = file_outline(str(p))
    assert st["symbols"] == 400
    assert "capped" not in st
    assert "more symbols)" not in text
