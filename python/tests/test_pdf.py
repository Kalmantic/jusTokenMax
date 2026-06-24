from justokenmax import pdf as pdfmod


def test_extracts_text_and_page_header(text_pdf):
    md, pages = pdfmod.pdf_to_markdown(text_pdf)
    assert pages == 1
    assert "## Page 1" in md
    assert "Hello jusTokenMax" in md
    assert "Second line of the spec" in md


def test_output_is_markdown_string(text_pdf):
    md, _ = pdfmod.pdf_to_markdown(text_pdf)
    assert isinstance(md, str)
    assert md.endswith("\n")


def test_output_size_cap_truncates(text_pdf, monkeypatch):
    # Safety cap: a tiny limit forces the truncation marker, proving a
    # decompression-bomb PDF can't write unbounded output.
    monkeypatch.setattr(pdfmod, "MAX_OUTPUT_CHARS", 5)
    md, _ = pdfmod.pdf_to_markdown(text_pdf)
    assert "truncated" in md
