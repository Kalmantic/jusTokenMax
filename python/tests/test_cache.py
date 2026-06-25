"""Audited reversible redaction: sidecar map storage, unmask + audit log, and
the guarantee that the default (irreversible) path is unchanged."""

import importlib
import json
import os

import pytest

from justokenmax import cache
from justokenmax.redact import redact_with_map


SECRET = "s" + "k-" + "Z" * 22          # OpenAI sk- shape


def test_save_and_load_redaction_map_round_trips():
    masked, mapping = redact_with_map(f"token={SECRET}")
    cache.save_redaction_map("k1", mapping)
    assert cache.load_redaction_map("k1") == mapping


def test_redaction_map_sidecar_is_owner_only(tmp_path):
    cache.save_redaction_map("k2", {"⟦jtm:s1⟧": SECRET})
    p = cache.redaction_map_path("k2")
    assert p.exists()
    mode = os.stat(p).st_mode & 0o777
    assert mode == 0o600, f"map sidecar must be 0600, got {oct(mode)}"


def test_load_redaction_map_absent_is_none():
    assert cache.load_redaction_map("never-written") is None


def test_unmask_restores_and_writes_audit_entry():
    masked, mapping = redact_with_map(f"token={SECRET}")
    cache.save_redaction_map("k3", mapping)
    restored = cache.unmask("k3", masked, audit_actor="alice")
    assert SECRET in restored
    rows = cache.read_audit_log()
    assert rows[-1] == {"key": "k3", "n_unmasked": 1, "actor": "alice"}


def test_unmask_without_map_returns_text_unchanged_and_audits_zero():
    restored = cache.unmask("no-map", "plain digest", audit_actor="bob")
    assert restored == "plain digest"
    assert cache.read_audit_log()[-1] == {"key": "no-map", "n_unmasked": 0,
                                          "actor": "bob"}


def test_audit_log_content_is_deterministic():
    # No clock/random in the stored row — test-stable.
    cache.save_redaction_map("k4", {"⟦jtm:s1⟧": SECRET})
    cache.unmask("k4", f"sk-Z…ZZZZ⟦jtm:s1⟧", audit_actor=None)
    cache.unmask("k4", f"sk-Z…ZZZZ⟦jtm:s1⟧", audit_actor=None)
    rows = [r for r in cache.read_audit_log() if r["key"] == "k4"]
    assert rows == [{"key": "k4", "n_unmasked": 1, "actor": None},
                    {"key": "k4", "n_unmasked": 1, "actor": None}]


def test_default_optimize_writes_no_map_and_is_irreversible(big_log):
    # Default mode (no JUSTOKENMAX_REDACT_AUDIT) must not produce a map sidecar.
    from justokenmax.optimize import optimize
    res = optimize(big_log)
    assert res.ok
    # The cache key is derivable; no .redmap.json should exist anywhere.
    redmaps = list(cache.CACHE_DIR.glob("*.redmap.json"))
    assert redmaps == [], "default mode leaked a redaction map sidecar"


def test_audited_optimize_writes_map_but_keeps_digest_secret_safe(
    big_log, monkeypatch
):
    monkeypatch.setenv("JUSTOKENMAX_REDACT_AUDIT", "1")
    from justokenmax.optimize import optimize
    res = optimize(big_log)
    assert res.ok and res.output
    digest = open(res.output, encoding="utf-8").read()
    secret = "s" + "k-" + "L" * 22          # the token planted in big_log
    # The original secret must NOT be in the digest...
    assert secret not in digest
    # ...but a placeholder must, and a map sidecar must exist holding the secret.
    assert "⟦jtm:" in digest
    redmaps = list(cache.CACHE_DIR.glob("*.redmap.json"))
    assert len(redmaps) == 1
    mapping = json.loads(redmaps[0].read_text())
    assert secret in mapping.values()
    # And an audited unmask recovers it.
    key = redmaps[0].name[: -len(".redmap.json")]
    restored = cache.unmask(key, digest, audit_actor="auditor")
    assert secret in restored
