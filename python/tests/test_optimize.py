import json as _json
import os
import re
from pathlib import Path

from justokenmax import cache
from justokenmax.optimize import optimize

_HANDLE_RE = re.compile(r"<jtm:retrieve id=([0-9a-f]{64}) kind=(\w+) src=([^>]+)>")


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


def test_pdf_artifact_masks_secrets(secret_pdf):
    # Regression: the PDF->markdown branch must route through _redact like every
    # other compressor, so a credential in a PDF is never written to the cache.
    path, secret = secret_pdf
    res = optimize(path)
    assert res.ok and res.kind == "pdf"
    assert secret not in Path(res.output).read_text(encoding="utf-8")


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


def test_ndjson_dispatch_groups_by_shape(big_ndjson):
    res = optimize(big_ndjson)
    assert res.ok and res.kind == "ndjson"
    assert res.output.endswith(".ndjson.txt")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "[800 × {level,msg,ts}]" in digest
    assert "[300 × {code,err,level,ts}]" in digest


def test_ndjson_second_run_cache_hit(big_ndjson):
    first = optimize(big_ndjson)
    second = optimize(big_ndjson)
    assert first.cached is False and second.cached is True
    assert second.output == first.output


def test_ndjson_retrieve_returns_original(big_ndjson):
    res = optimize(big_ndjson)
    assert cache.lookup_origin(res.output) == big_ndjson


def test_content_sniff_routes_txt_to_json(tmp_path):
    import json as _json
    p = tmp_path / "payload.txt"               # generic extension
    p.write_text(_json.dumps({"items": list(range(3000))}))  # > JSON_MIN_BYTES
    res = optimize(str(p))
    assert res.ok and res.kind == "json"


def test_retrieve_returns_original(big_json):
    res = optimize(big_json)
    assert cache.lookup_origin(res.output) == big_json


def test_uniform_json_uses_schema_mode(uniform_json_2mb):
    res = optimize(uniform_json_2mb)
    assert res.ok and res.kind == "json"
    digest = Path(res.output).read_text(encoding="utf-8")
    # The whole 2MB array collapses to a single schema node.
    assert "30000 x {" in digest
    assert "id:int" in digest and "name:str" in digest
    # Huge reduction and reversibility preserved.
    assert res.tokens_after < res.tokens_before // 100
    assert cache.lookup_origin(res.output) == uniform_json_2mb


def test_lockfile_dispatch_table(package_lock):
    res = optimize(package_lock)
    assert res.ok and res.kind == "lockfile"
    assert res.output.endswith(".lock.txt")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "lodash@4.17.21" in digest
    assert "react@18.2.0" in digest
    assert "typescript@5.4.2" in digest
    # Integrity hashes / resolved URLs are gone.
    assert "sha512" not in digest
    assert "registry" not in digest
    assert cache.lookup_origin(res.output) == package_lock


def test_lockfile_second_run_cache_hit(package_lock):
    first = optimize(package_lock)
    second = optimize(package_lock)
    assert first.cached is False and second.cached is True
    assert second.output == first.output


def test_minified_dispatch_stub(min_js):
    res = optimize(min_js)
    assert res.ok and res.kind == "minified"
    assert res.output.endswith(".min.txt")
    assert res.tokens_saved > 0
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "minified asset" in digest
    assert "retrieve" in digest
    # Source bytes do not survive in the stub.
    assert "var x=1;" not in digest
    assert cache.lookup_origin(res.output) == min_js


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


def test_text_digest_carries_inband_handle(big_log):
    # A compressed TEXT digest must carry a one-line, self-describing retrieve
    # handle whose id is the cache key, surfaced in-band to the agent.
    res = optimize(big_log)
    assert res.handle and res.handle.startswith("<jtm:retrieve id=")
    body = Path(res.output).read_text(encoding="utf-8")
    m = _HANDLE_RE.search(body)
    assert m, "no retrieve handle in the digest body"
    key, kind, src = m.groups()
    assert kind == "log"
    assert src == os.path.basename(big_log)
    # Handle on the result matches the one written in-band.
    assert res.handle == f"<jtm:retrieve id={key} kind=log src={src}>"
    # The leading comment line keeps the digest's important content intact.
    assert "Build FAILED" in body


def test_retrieve_by_inband_id_returns_original(big_log):
    res = optimize(big_log)
    key = _HANDLE_RE.search(res.handle).group(1)
    # The agent can retrieve with the raw id, the "id=<key>" form, or the whole
    # handle line it saw in the digest.
    assert cache.lookup_by_id(key) == big_log
    assert cache.resolve_handle_arg(key) == big_log
    assert cache.resolve_handle_arg(f"id={key}") == big_log
    assert cache.resolve_handle_arg(res.handle) == big_log
    # Artifact-path lookup still works (backward compat).
    assert cache.resolve_handle_arg(res.output) == big_log


def test_json_artifact_stays_valid_and_handle_off_body(big_json):
    # Strict JSON: the handle must NOT be injected into the body (would break
    # json.loads) but the result/meta still carries it.
    res = optimize(big_json)
    assert res.kind == "json"
    body = Path(res.output).read_text(encoding="utf-8")
    assert "<jtm:retrieve" not in body
    _json.loads(body)  # still valid JSON
    assert res.handle.startswith("<jtm:retrieve id=")
    key = _HANDLE_RE.search(res.handle).group(1)
    # Resolvable by the in-band id even though it isn't in the body.
    assert cache.lookup_by_id(key) == big_json


def test_handle_is_deterministic(big_log):
    first = optimize(big_log).handle
    # Re-run (cache hit) yields the identical content-derived handle.
    second = optimize(big_log).handle
    assert first == second and first != ""


def test_cache_hit_result_carries_handle(big_json):
    first = optimize(big_json)
    second = optimize(big_json)
    assert second.cached is True
    assert second.handle == first.handle


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
