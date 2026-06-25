"""Shared fixtures: deterministically built PDF and image attachments.

We build a real (tiny) PDF with a correct cross-reference table so pypdf can
extract its text, and real PNGs via Pillow. No binary fixtures committed.
"""

import os

import pytest


def _build_text_pdf(path: str, lines):
    """Write a minimal, valid single-page PDF whose text is extractable."""
    body = ["BT", "/F1 24 Tf", "72 720 Td"]
    for i, ln in enumerate(lines):
        if i:
            body.append("0 -30 Td")
        esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        body.append(f"({esc}) Tj")
    body.append("ET")
    content = ("\n".join(body)).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        + b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
        + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"

    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += b"trailer\n"
    out += f"<< /Size {size} /Root 1 0 R >>\n".encode("latin-1")
    out += b"startxref\n" + f"{xref_pos}\n".encode("latin-1") + b"%%EOF"

    with open(path, "wb") as f:
        f.write(out)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point justokenmax's cache/ledger at a throwaway dir for every test."""
    monkeypatch.setenv("JUSTOKENMAX_HOME", str(tmp_path / ".justokenmax"))
    # Reload cache module paths since they read the env at import time.
    import importlib

    from justokenmax import cache as cache_mod
    importlib.reload(cache_mod)
    yield


@pytest.fixture
def text_pdf(tmp_path):
    p = tmp_path / "spec.pdf"
    _build_text_pdf(str(p), ["Hello jusTokenMax", "Second line of the spec"])
    return str(p)


@pytest.fixture
def big_image(tmp_path):
    """A large, hard-to-compress PNG (random noise) above the skip threshold."""
    from PIL import Image

    w, h = 3000, 2000
    data = os.urandom(w * h * 3)
    img = Image.frombytes("RGB", (w, h), data)
    p = tmp_path / "diagram.png"
    img.save(str(p), "PNG")
    return str(p)


@pytest.fixture
def small_image(tmp_path):
    from PIL import Image

    img = Image.new("RGB", (40, 40), (123, 200, 50))
    p = tmp_path / "icon.png"
    img.save(str(p), "PNG")
    return str(p)


@pytest.fixture
def big_json(tmp_path):
    import json
    data = {
        "status": "ok",
        "items": [{"id": i, "name": f"item-{i}", "active": i % 2 == 0}
                  for i in range(500)],
        "note": "x" * 2000,
    }
    p = tmp_path / "response.json"
    p.write_text(json.dumps(data, indent=2))
    return str(p)


@pytest.fixture
def big_log(tmp_path):
    lines = ["INFO starting"]
    lines += [f"compiling module {i}" for i in range(400)]
    lines += ["fetching dependency"] * 80
    # Secret-shaped token built at runtime (no literal key in source); the
    # redaction pass should mask it in the digest.
    secret = "s" + "k-" + "L" * 22
    lines += [f"DEBUG auth token={secret}",
              "ERROR: build failed", "Build FAILED"]
    p = tmp_path / "build.log"
    p.write_text("\n".join(lines))
    return str(p)


@pytest.fixture
def big_notebook(tmp_path):
    import json
    nb = {"cells": [
        {"cell_type": "markdown", "source": ["# Analysis\n"]},
        {"cell_type": "code", "source": ["plot(data)\n"],
         "outputs": [{"output_type": "display_data",
                      "data": {"image/png": "P" * 200000}}]},
    ], "metadata": {}, "nbformat": 4}
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb))
    return str(p)


@pytest.fixture
def uniform_json_2mb(tmp_path):
    """A ~2MB top-level uniform array of objects — schema-mode bait."""
    import json
    data = [{"id": i, "name": f"item-{i}", "active": i % 2 == 0,
             "score": i * 1.5} for i in range(30000)]
    p = tmp_path / "rows.json"
    p.write_text(json.dumps(data))
    assert p.stat().st_size > 1_000_000
    return str(p)


@pytest.fixture
def package_lock(tmp_path):
    import json
    data = {"name": "app", "lockfileVersion": 3, "packages": {
        "": {"name": "app"},
        "node_modules/lodash": {"version": "4.17.21",
                                "resolved": "https://registry/lodash",
                                "integrity": "sha512-" + "A" * 90},
        "node_modules/react": {"version": "18.2.0",
                               "integrity": "sha512-" + "B" * 90},
        "node_modules/typescript": {"version": "5.4.2",
                                    "integrity": "sha512-" + "C" * 90},
    }}
    p = tmp_path / "package-lock.json"
    # Pad with bulk so it clears the JSON_MIN_BYTES floor comfortably.
    data["packages"]["node_modules/filler"] = {
        "version": "1.0.0", "integrity": "sha512-" + "D" * 6000}
    p.write_text(json.dumps(data, indent=2))
    return str(p)


@pytest.fixture
def min_js(tmp_path):
    """A .min.js asset: one giant line of opaque generated code."""
    p = tmp_path / "bundle.min.js"
    p.write_text("!function(e){" + "var x=1;" * 4000 + "}(window);")
    return str(p)


@pytest.fixture
def big_csv(tmp_path):
    rows = ["id,name,score"]
    rows += [f"{i},name{i},{i * 1.5}" for i in range(2000)]
    p = tmp_path / "data.csv"
    p.write_text("\n".join(rows) + "\n")
    return str(p)
