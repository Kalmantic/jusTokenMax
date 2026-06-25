import importlib

import pytest

from justokenmax import tokens


def test_text_tokens_fallback_is_quarter_of_chars(monkeypatch):
    # Force the fallback path regardless of whether tiktoken is installed.
    monkeypatch.setattr(tokens, "_encoder", lambda: None)
    assert tokens.text_tokens("x" * 400) == 100
    assert tokens.text_tokens("") == 1  # never zero


def test_text_tokens_empty_is_at_least_one():
    # Holds on both paths (fallback and real tokenizer).
    assert tokens.text_tokens("") >= 1


def test_text_tokens_accurate_counts_symbol_dense_json():
    # When tiktoken is available, punctuation/symbol-dense JSON tokenizes into
    # MORE tokens than the naive len//4 heuristic would claim. This locks the
    # accuracy direction. Skipped when the optional extra is not installed.
    if tokens._encoder() is None:
        pytest.skip("tiktoken not installed; accurate path unavailable")
    text = '{"a":1,"b":[true,false,null],"c":{"d":-3.14,"e":"x"}}' * 8
    naive = max(1, len(text) // 4)
    assert tokens.text_tokens(text) > naive


def test_text_tokens_fallback_when_tiktoken_import_fails(monkeypatch):
    # Simulate tiktoken being unimportable and reload the module: text_tokens
    # must still work and return the len//4 estimate.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tiktoken" or name.startswith("tiktoken."):
            raise ImportError("forced: tiktoken unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    reloaded = importlib.reload(tokens)
    try:
        assert reloaded.tiktoken is None
        assert reloaded._encoder() is None
        assert reloaded.text_tokens("x" * 400) == 100
        assert reloaded.text_tokens("") == 1
    finally:
        # Restore the real module state for any later tests.
        monkeypatch.undo()
        importlib.reload(tokens)


def test_image_tokens_clamp_to_max_edge():
    # Beyond MAX_EDGE the long edge is clamped, so a 4x-bigger image does not
    # cost 4x tokens.
    small = tokens.image_tokens(1568, 1000)
    huge = tokens.image_tokens(6272, 4000)  # 4x linear, same aspect
    assert huge == pytest.approx(small, rel=0.02)


def test_bytes_to_tokens_scales_with_bytes():
    assert tokens.bytes_to_tokens(3000) == 1000
    assert tokens.bytes_to_tokens(0) == 0
    assert tokens.bytes_to_tokens(900) < tokens.bytes_to_tokens(9000)


def test_pdf_page_cost_is_per_page():
    assert tokens.pdf_image_tokens(10) == 10 * tokens.PDF_PAGE_IMAGE_TOKENS
