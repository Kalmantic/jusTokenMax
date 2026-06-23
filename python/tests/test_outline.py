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
    assert "1  " in text                    # line number for first symbol


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
