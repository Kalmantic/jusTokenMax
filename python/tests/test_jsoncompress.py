import json

from justokenmax.jsoncompress import (
    compress_json,
    compress_ndjson,
    is_uniform_object_array,
    looks_like_json,
    schema_json,
)


def test_schema_mode_collapses_uniform_array():
    data = [{"id": i, "name": f"n{i}", "active": i % 2 == 0}
            for i in range(2000)]
    src = json.dumps(data)
    digest, stats = schema_json(src)
    assert stats["ok"] and stats["mode"] == "schema"
    # The whole array IS the schema node, so it serializes as a JSON string.
    assert digest == '"[2000 x {id:int, name:str, active:bool}]"'
    # Massive reduction: the whole array becomes one schema node.
    assert stats["bytes_after"] < stats["bytes_before"] // 100


def test_schema_mode_via_compress_json_flag():
    src = json.dumps([{"a": 1} for _ in range(50)])
    digest, stats = compress_json(src, schema=True)
    assert stats["mode"] == "schema"
    assert digest == '"[50 x {a:int}]"'


def test_schema_keeps_surrounding_structure():
    data = {"status": "ok", "rows": [{"x": 1, "y": 2} for _ in range(20)]}
    digest, stats = schema_json(json.dumps(data))
    assert '"status":"ok"' in digest
    assert "[20 x {x:int, y:int}]" in digest


def test_schema_merges_heterogeneous_object_keys():
    data = [{"id": 1}, {"id": 2, "extra": "z"}] * 10  # 20 items, varying keys
    digest, _ = schema_json(json.dumps(data))
    assert "id:int" in digest and "extra:str" in digest


def test_schema_mode_non_json_unchanged():
    digest, stats = schema_json("not json at all")
    assert stats["ok"] is False
    assert digest == "not json at all"


def test_is_uniform_object_array():
    assert is_uniform_object_array([{"a": 1}] * 8)
    assert not is_uniform_object_array([{"a": 1}] * 7)   # below threshold
    assert not is_uniform_object_array([1, 2, 3, 4, 5, 6, 7, 8])
    assert not is_uniform_object_array([{"a": 1}, 2, {"b": 3}] * 4)


def test_sample_mode_still_default():
    src = json.dumps({"items": list(range(1000))})
    _, stats = compress_json(src)
    assert stats["mode"] == "sample"


def test_long_array_is_sampled():
    src = json.dumps({"items": list(range(1000))})
    digest, stats = compress_json(src)
    assert stats["ok"]
    assert "more of 1000 items elided" in digest
    assert len(digest) < len(src)
    assert stats["bytes_after"] < stats["bytes_before"]


def test_long_string_truncated():
    src = json.dumps({"blob": "y" * 5000})
    digest, _ = compress_json(src)
    assert "chars)" in digest
    assert len(digest) < 1000


def test_minifies_whitespace():
    src = json.dumps({"a": 1, "b": 2}, indent=4)
    digest, _ = compress_json(src)
    assert digest == '{"a":1,"b":2}'          # whitespace stripped


def test_keeps_head_and_tail_elements():
    src = json.dumps(list(range(100)))
    digest, _ = compress_json(src)
    assert digest.startswith("[0,1,2,")        # head sample kept
    assert digest.rstrip("]").endswith("97,98,99")  # tail sample kept


def test_non_json_unchanged():
    digest, stats = compress_json("this is not json")
    assert stats["ok"] is False
    assert digest == "this is not json"


def test_looks_like_json():
    assert looks_like_json('{"a":1}')
    assert looks_like_json("[1,2,3]")
    assert not looks_like_json("hello")
    assert not looks_like_json("")


def _ndjson(infos=500, errors=200):
    lines = [json.dumps({"ts": i, "level": "info", "msg": f"start {i}"})
             for i in range(infos)]
    lines += [json.dumps({"ts": i, "level": "error", "code": 500, "err": "boom"})
              for i in range(errors)]
    return "\n".join(lines)


def test_ndjson_groups_by_shape():
    digest, stats = compress_ndjson(_ndjson())
    assert stats["ok"]
    assert stats["records"] == 700
    assert stats["shapes"] == 2
    # One summary row per shape, with counts.
    assert "[500 × {level,msg,ts}]" in digest
    assert "[200 × {code,err,level,ts}]" in digest
    assert stats["bytes_after"] < stats["bytes_before"]


def test_ndjson_keeps_a_few_examples_per_shape():
    digest, _ = compress_ndjson(_ndjson(infos=50, errors=50))
    # Representative example records survive (individually shrunk).
    assert '"msg":"start 0"' in digest
    assert '"err":"boom"' in digest


def test_ndjson_tolerates_malformed_lines():
    src = "\n".join([
        json.dumps({"a": 1}),
        "{this is not valid json",
        json.dumps({"a": 2}),
        "   ",                       # blank line ignored
    ])
    digest, stats = compress_ndjson(src)
    assert stats["ok"]               # one bad line does not sink the file
    assert stats["malformed"] == 1
    assert stats["records"] == 3     # 2 valid + 1 malformed (blank skipped)
    assert "<malformed>" in digest


def test_ndjson_whole_file_jsonloads_would_fail():
    # Sanity: the input genuinely is NOT parseable as a single JSON document,
    # which is exactly why compress_json can't handle it but compress_ndjson can.
    src = _ndjson(infos=2, errors=1)
    try:
        json.loads(src)
        parsed = True
    except ValueError:
        parsed = False
    assert parsed is False
    _, stats = compress_ndjson(src)
    assert stats["ok"]


def test_ndjson_non_json_returns_not_ok():
    digest, stats = compress_ndjson("hello\nworld\nnot json here")
    assert stats["ok"] is False
    assert digest == "hello\nworld\nnot json here"
