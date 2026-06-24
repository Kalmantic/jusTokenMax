import os
from pathlib import Path

from justokenmax import cache
from justokenmax.optimize import optimize


def test_pdf_dispatch_produces_markdown(text_pdf):
    res = optimize(text_pdf)
    assert res.ok and res.kind == "pdf"
    assert res.output.endswith(".md")
    assert os.path.exists(res.output)
    assert res.tokens_saved > 0
    assert "Hello jusTokenMax" in Path(res.output).read_text(encoding="utf-8")


def test_pdf_second_run_is_cache_hit(text_pdf):
    first = optimize(text_pdf)
    second = optimize(text_pdf)
    assert first.cached is False
    assert second.cached is True
    assert second.output == first.output


def test_image_dispatch_compresses(big_image):
    res = optimize(big_image)
    assert res.ok and res.kind == "image"
    assert os.path.exists(res.output)
    assert res.tokens_saved > 0


def test_log_dispatch_compresses(big_log):
    res = optimize(big_log)
    assert res.ok and res.kind == "log"
    assert res.output.endswith(".log.txt")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "Build FAILED" in digest          # important line preserved


def test_log_second_run_cache_hit(big_log):
    first = optimize(big_log)
    second = optimize(big_log)
    assert first.cached is False and second.cached is True


def test_notebook_dispatch_elides_images(big_notebook):
    res = optimize(big_notebook)
    assert res.ok and res.kind == "notebook"
    assert res.output.endswith(".ipynb.md")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "[image output elided]" in digest
    assert "P" * 1000 not in digest


def test_csv_dispatch_samples(big_csv):
    res = optimize(big_csv)
    assert res.ok and res.kind == "csv"
    assert res.output.endswith(".csv.md")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "2000 rows" in digest


def test_log_digest_redacts_secret(big_log):
    res = optimize(big_log)
    digest = Path(res.output).read_text(encoding="utf-8")
    # The unmasked secret was "sk-" + 22 L's; after redaction that long run is
    # broken up, so the contiguous run must not survive in the digest.
    assert "L" * 22 not in digest


def test_json_dispatch_compresses(big_json):
    res = optimize(big_json)
    assert res.ok and res.kind == "json"
    assert res.output.endswith(".min.json")
    assert res.tokens_saved > 0


def test_content_sniff_routes_txt_to_json(tmp_path):
    import json as _json
    p = tmp_path / "payload.txt"               # generic extension
    p.write_text(_json.dumps({"items": list(range(3000))}))  # > JSON_MIN_BYTES
    res = optimize(str(p))
    assert res.ok and res.kind == "json"


def test_retrieve_returns_original(big_json):
    res = optimize(big_json)
    assert cache.lookup_origin(res.output) == big_json


def test_small_image_skipped(small_image):
    res = optimize(small_image)
    assert res.ok is False
    assert res.kind == "skip"
    assert res.output is None


def test_unsupported_type_skipped(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("plain text")
    res = optimize(str(p))
    assert res.kind == "skip"
    assert res.output is None


def test_missing_file_skipped(tmp_path):
    res = optimize(str(tmp_path / "ghost.pdf"))
    assert res.ok is False
    assert res.kind == "skip"


def test_ledger_accumulates(text_pdf):
    before = cache.read_ledger().get("total_tokens_saved", 0)
    res = optimize(text_pdf)  # fresh conversion records savings
    after = cache.read_ledger().get("total_tokens_saved", 0)
    assert after - before == res.tokens_saved


def test_cache_hit_does_not_double_count(text_pdf):
    optimize(text_pdf)
    mid = cache.read_ledger().get("total_tokens_saved", 0)
    optimize(text_pdf)  # cache hit must not add again
    end = cache.read_ledger().get("total_tokens_saved", 0)
    assert end == mid
