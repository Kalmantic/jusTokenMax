import json

from justokenmax.lockfile import (
    compress_lockfile,
    is_minified_name,
    lock_flavor,
    looks_minified,
    minified_stub,
)


def test_lock_flavor_by_basename():
    assert lock_flavor("/repo/package-lock.json") == "npm"
    assert lock_flavor("yarn.lock") == "yarn"
    assert lock_flavor("a/b/pnpm-lock.yaml") == "pnpm"
    assert lock_flavor("poetry.lock") == "poetry"
    assert lock_flavor("Cargo.lock") == "cargo"
    assert lock_flavor("Gemfile.lock") == "gemfile"
    assert lock_flavor("regular.json") is None


def test_npm_lock_v3_table():
    src = json.dumps({
        "name": "app", "lockfileVersion": 3,
        "packages": {
            "": {"name": "app"},
            "node_modules/lodash": {"version": "4.17.21",
                                    "resolved": "https://example/lodash",
                                    "integrity": "sha512-" + "A" * 80},
            "node_modules/react": {"version": "18.2.0",
                                   "integrity": "sha512-" + "B" * 80},
        },
    })
    digest, stats = compress_lockfile(src, "npm")
    assert stats["ok"] and stats["packages"] == 2
    assert "lodash@4.17.21" in digest
    assert "react@18.2.0" in digest
    # Integrity hashes and resolved URLs are dropped.
    assert "sha512" not in digest
    assert "https://example" not in digest
    assert len(digest) < len(src)


def test_npm_lock_v1_dependencies():
    src = json.dumps({
        "lockfileVersion": 1,
        "dependencies": {
            "left-pad": {"version": "1.3.0", "integrity": "sha512-x"},
            "ms": {"version": "2.1.3"},
        },
    })
    digest, stats = compress_lockfile(src, "npm")
    assert stats["packages"] == 2
    assert "left-pad@1.3.0" in digest and "ms@2.1.3" in digest


def test_yarn_lock_table():
    src = ('# yarn lockfile v1\n'
           'lodash@^4.17.21:\n'
           '  version "4.17.21"\n'
           '  resolved "https://registry/lodash"\n'
           '  integrity sha512-AAA\n\n'
           'react@^18.0.0:\n'
           '  version "18.2.0"\n'
           '  integrity sha512-BBB\n')
    digest, stats = compress_lockfile(src, "yarn")
    assert stats["packages"] == 2
    assert "lodash@4.17.21" in digest and "react@18.2.0" in digest
    assert "sha512" not in digest


def test_yarn_lock_keeps_scoped_packages():
    # Regression: scoped packages (@scope/name) must NOT be dropped. The entry
    # header starts with `@`, which the original name regex forbade — so every
    # scoped dependency silently vanished from the digest.
    src = ('# yarn lockfile v1\n'
           '"@types/node@^20.0.0":\n'
           '  version "20.11.5"\n'
           '  integrity sha512-AAA\n\n'
           '"@babel/core@^7.0.0":\n'
           '  version "7.23.9"\n'
           '  integrity sha512-BBB\n\n'
           'lodash@^4.17.21:\n'
           '  version "4.17.21"\n'
           '  integrity sha512-CCC\n')
    digest, stats = compress_lockfile(src, "yarn")
    assert stats["packages"] == 3                      # all three, not 1
    assert "@types/node@20.11.5" in digest
    assert "@babel/core@7.23.9" in digest
    assert "lodash@4.17.21" in digest


def test_pnpm_lock_table():
    src = ("lockfileVersion: '6.0'\n"
           "packages:\n"
           "  /lodash@4.17.21:\n"
           "    resolution: {integrity: sha512-AAA}\n"
           "  /react@18.2.0:\n"
           "    resolution: {integrity: sha512-BBB}\n")
    digest, stats = compress_lockfile(src, "pnpm")
    assert stats["packages"] == 2
    assert "lodash@4.17.21" in digest and "react@18.2.0" in digest


def test_cargo_lock_table():
    src = ('[[package]]\nname = "serde"\nversion = "1.0.197"\n'
           'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
           'checksum = "abcd"\n\n'
           '[[package]]\nname = "tokio"\nversion = "1.36.0"\nchecksum = "ef01"\n')
    digest, stats = compress_lockfile(src, "cargo")
    assert stats["packages"] == 2
    assert "serde@1.0.197" in digest and "tokio@1.36.0" in digest
    assert "checksum" not in digest


def test_poetry_lock_table():
    src = ('[[package]]\nname = "requests"\nversion = "2.31.0"\n'
           'description = "x"\noptional = false\n\n'
           '[[package]]\nname = "urllib3"\nversion = "2.0.7"\n')
    digest, stats = compress_lockfile(src, "poetry")
    assert stats["packages"] == 2
    assert "requests@2.31.0" in digest and "urllib3@2.0.7" in digest


def test_gemfile_lock_table():
    src = ("GEM\n  remote: https://rubygems.org/\n  specs:\n"
           "    rake (13.0.6)\n    rails (7.1.0)\n")
    digest, stats = compress_lockfile(src, "gemfile")
    assert stats["packages"] == 2
    assert "rake@13.0.6" in digest and "rails@7.1.0" in digest


def test_lockfile_fail_open_on_garbage():
    digest, stats = compress_lockfile("{ not valid json", "npm")
    assert stats["ok"] is False
    assert digest == "{ not valid json"          # passed through untouched


def test_lockfile_deterministic_sorted():
    src = json.dumps({"dependencies": {
        "zeta": {"version": "1.0.0"}, "alpha": {"version": "2.0.0"}}})
    first, _ = compress_lockfile(src, "npm")
    second, _ = compress_lockfile(src, "npm")
    assert first == second
    assert first.index("alpha@2.0.0") < first.index("zeta@1.0.0")


def test_is_minified_name():
    assert is_minified_name("bundle.min.js")
    assert is_minified_name("styles.min.css")
    assert not is_minified_name("app.js")


def test_looks_minified_by_name_and_longline():
    assert looks_minified("short", "vendor.min.js")
    assert looks_minified("x" * 6000)               # single line > 5KB
    assert not looks_minified("a\nb\nc")
    assert not looks_minified("")


def test_minified_stub_is_terse_and_deterministic():
    digest, stats = minified_stub(123456)
    assert stats["ok"] and stats["bytes"] == 123456
    assert "123456 bytes" in digest and "retrieve" in digest
    assert minified_stub(123456)[0] == digest       # deterministic
