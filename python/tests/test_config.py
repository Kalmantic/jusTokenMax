from pathlib import Path

import pytest

from justokenmax import config as cfg
from justokenmax.optimize import optimize


def test_default_all_enabled():
    assert cfg.is_enabled("pdf") and cfg.is_enabled("redact")
    assert cfg.disabled_kinds() == set()


def test_env_disable(monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_DISABLE", "pdf, image")
    assert not cfg.is_enabled("pdf")
    assert not cfg.is_enabled("image")
    assert cfg.is_enabled("log")


def test_file_disable_persists():
    cfg.set_kind("log", enabled=False)
    assert not cfg.is_enabled("log")
    cfg.set_kind("log", enabled=True)
    assert cfg.is_enabled("log")


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        cfg.set_kind("bogus", enabled=False)


def test_optimize_skips_disabled_kind(big_log, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_DISABLE", "log")
    res = optimize(big_log)
    assert res.ok is False and res.note == "disabled by config"


def test_disabling_redact_leaves_secret(big_log, monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_DISABLE", "redact")
    res = optimize(big_log)
    digest = Path(res.output).read_text(encoding="utf-8")
    assert "L" * 22 in digest          # secret NOT masked when redact disabled


def test_max_read_tokens_default():
    assert cfg.max_read_tokens() == cfg.DEFAULT_MAX_READ_TOKENS


def test_max_read_tokens_env_override(monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_MAX_READ_TOKENS", "500")
    assert cfg.max_read_tokens() == 500


def test_max_read_tokens_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("JUSTOKENMAX_MAX_READ_TOKENS", "not-a-number")
    assert cfg.max_read_tokens() == cfg.DEFAULT_MAX_READ_TOKENS


def test_summary_shape():
    s = cfg.summary()
    assert set(s["kinds"]) == set(cfg.KINDS)
    assert all(v is True for v in s["kinds"].values())
