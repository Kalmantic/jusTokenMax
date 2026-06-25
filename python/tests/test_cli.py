import json

from justokenmax.cli import main


def test_optimize_json_pdf(text_pdf, capsys):
    rc = main(["optimize", "--json", text_pdf])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert out["kind"] == "pdf"
    assert out["tokens_saved"] > 0


def test_optimize_multiple_returns_list(text_pdf, big_image, capsys):
    rc = main(["optimize", "--json", text_pdf, big_image])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert isinstance(out, list) and len(out) == 2


def test_stats_json_reflects_runs(text_pdf, capsys):
    main(["optimize", "--json", text_pdf])
    capsys.readouterr()  # discard the optimize output
    main(["stats", "--json"])
    led = json.loads(capsys.readouterr().out)
    assert led["runs"] >= 1
    assert led["total_tokens_saved"] > 0


def test_optimize_unsupported_returns_nonzero(tmp_path, capsys):
    p = tmp_path / "x.txt"
    p.write_text("hi")
    rc = main(["optimize", "--json", str(p)])
    capsys.readouterr()
    assert rc == 1  # nothing optimized


def test_discover_json_over_fake_history(tmp_path, big_json, capsys):
    hist = tmp_path / "projects" / "p"
    hist.mkdir(parents=True)
    msg = {"content": [{"type": "tool_use", "name": "Read",
                        "input": {"file_path": big_json}}]}
    (hist / "s.jsonl").write_text(json.dumps({"message": msg}) + "\n")
    rc = main(["discover", "--root", str(tmp_path / "projects"), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["recoverable_tokens"] > 0
    assert "json" in out["by_kind"]
