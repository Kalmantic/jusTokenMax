from justokenmax.redact import mask_secrets, redact


def test_elides_base64_blob():
    blob = "A" * 400
    clean, st = redact(f"image = {blob} end")
    assert blob not in clean
    assert "base64 blob elided" in clean
    assert st["blobs_elided"] >= 1


def test_elides_data_uri():
    clean, st = redact("src=data:image/png;base64," + "Q" * 100)
    assert "data-uri elided" in clean
    assert st["blobs_elided"] >= 1


def test_masks_known_secret_shapes():
    # Secret-shaped strings are assembled at runtime so the full literal never
    # appears in this source file — it's test data, not a real key, and we don't
    # want to trip secret scanners. Distinctive prefixes are split across `+`.
    secrets = [
        "s" + "k-" + "Z" * 22,          # OpenAI sk- shape
        "AK" + "IA" + "Z" * 16,         # AWS access key id shape
        "gh" + "p_" + "Z" * 36,         # GitHub token shape
        "AI" + "za" + "Z" * 35,         # Google AIza shape
    ]
    for s in secrets:
        clean, st = redact(f"key={s}")
        assert s not in clean, "secret leaked"
        assert st["secrets_masked"] >= 1


def test_masks_key_value_secret():
    clean, st = redact('password = "hunter2hunter2"')
    assert "hunter2hunter2" not in clean
    assert st["secrets_masked"] >= 1


def test_plain_text_untouched():
    clean, st = redact("just normal text with no secrets")
    assert clean == "just normal text with no secrets"
    assert st["secrets_masked"] == 0 and st["blobs_elided"] == 0


def test_mask_secrets_masks_without_eliding_blobs():
    # mask_secrets is the safety-only half: it masks secrets but leaves base64
    # blobs in place (no token-cutting elision).
    secret = "s" + "k-" + "Z" * 22
    blob = "A" * 400
    clean, n = mask_secrets(f"key={secret} blob={blob}")
    assert secret not in clean and n >= 1
    assert blob in clean                      # blob NOT elided by mask_secrets


def test_optimize_redact_masks_secrets_even_when_redact_disabled(monkeypatch):
    # Security regression: even with the `redact` kind disabled, a live secret
    # must never be written to a cache artifact. _redact falls back to
    # mask_secrets rather than returning the text untouched.
    import importlib
    opt = importlib.import_module("justokenmax.optimize")
    monkeypatch.setattr(opt, "is_enabled", lambda kind: False)
    secret = "AK" + "IA" + "Z" * 16          # AWS access key id shape
    out = opt._redact(f"aws_key = {secret}")
    assert secret not in out                  # masked despite redact disabled
