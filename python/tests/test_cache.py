import re

from justokenmax import cache

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_retrieve_handle_is_deterministic_and_shaped():
    key = "a" * 64
    h1 = cache.retrieve_handle(key, "log", "/var/log/build.log")
    h2 = cache.retrieve_handle(key, "log", "/var/log/build.log")
    # No clock/random — same inputs, identical handle.
    assert h1 == h2
    assert h1 == f"<jtm:retrieve id={key} kind=log src=build.log>"


def test_record_origin_indexes_by_key(tmp_path):
    src = tmp_path / "orig.json"
    src.write_text("{}")
    artifact = tmp_path / "art.min.json"
    artifact.write_text("{}")
    key = "b" * 64
    cache.record_origin(str(artifact), str(src), key=key)
    # Path lookup (backward compat) and id lookup both resolve.
    assert cache.lookup_origin(str(artifact)) == str(src)
    assert cache.lookup_by_id(key) == str(src)


def test_record_origin_without_key_keeps_path_lookup(tmp_path):
    src = tmp_path / "orig.txt"
    src.write_text("x")
    artifact = tmp_path / "art.redacted.txt"
    artifact.write_text("y")
    cache.record_origin(str(artifact), str(src))   # no key -> path only
    assert cache.lookup_origin(str(artifact)) == str(src)
    assert cache.lookup_by_id("c" * 64) is None


def test_resolve_handle_arg_accepts_id_forms(tmp_path):
    src = tmp_path / "orig.log"
    src.write_text("x")
    artifact = tmp_path / "art.log.txt"
    artifact.write_text("y")
    key = "d" * 64
    cache.record_origin(str(artifact), str(src), key=key)
    handle = cache.retrieve_handle(key, "log", str(src))
    assert cache.resolve_handle_arg(key) == str(src)
    assert cache.resolve_handle_arg(f"id={key}") == str(src)
    assert cache.resolve_handle_arg(handle) == str(src)
    assert cache.resolve_handle_arg(str(artifact)) == str(src)


def test_resolve_handle_arg_unknown_returns_none():
    assert cache.resolve_handle_arg("e" * 64) is None
    assert cache.resolve_handle_arg("/nope/whatever.txt") is None
