"""jusTokenMax command line (`justokenmax`, also installed as `justokenmax`).

    justokenmax optimize FILE...    # auto-dispatch attachments/logs by type
    justokenmax pdf FILE            # force PDF -> markdown
    justokenmax image FILE          # force image / screenshot compression
    justokenmax logs FILE           # compress a verbose log
    justokenmax index [PATH]        # build the code symbol index
    justokenmax query TERM          # look up a symbol -> file:line + signature
    justokenmax stats               # lifetime savings ledger

Add --json for machine-readable output (used by the Claude Code hooks).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, cache
from .optimize import optimize


def _print(result_dict: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result_dict))
        return
    r = result_dict
    if not r["ok"]:
        print(f"skip  {r['source']}  ({r['note']})")
        return
    saved = r["tokens_saved"]
    pct = (100 * saved // r["tokens_before"]) if r["tokens_before"] else 0
    tag = "cache" if r["cached"] else r["kind"]
    print(f"ok    {r['source']}")
    print(f"      -> {r['output']}")
    print(f"      {r['tokens_before']} -> {r['tokens_after']} tokens "
          f"(-{saved}, -{pct}%)  [{tag}]  {r['note']}")


def _run_optimize(args) -> int:
    results = [optimize(f, quality=args.quality, max_edge=args.max_edge).to_dict()
               for f in args.files]
    if getattr(args, "json", False):
        print(json.dumps(results if len(results) > 1 else results[0]))
    else:
        for r in results:
            _print(r, as_json=False)
    return 0 if any(r["ok"] for r in results) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="justokenmax",
                                description="jusTokenMax — token-reduction toolkit.")
    p.add_argument("--version", action="version", version=f"justokenmax {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--quality", type=int, default=80, help="image JPEG quality")
    common.add_argument("--max-edge", type=int, default=None,
                        help="override max image long edge (px)")

    for name in ("optimize", "pdf", "image", "logs", "json"):
        sub.add_parser(name, parents=[common]).add_argument("files", nargs="+")

    pr = sub.add_parser("retrieve", help="get the original behind an optimized artifact")
    pr.add_argument("artifact")
    pr.add_argument("--json", action="store_true")

    pd = sub.add_parser("delta", help="return only what changed since last read")
    pd.add_argument("files", nargs="+")
    pd.add_argument("--json", action="store_true")

    prd = sub.add_parser("redact", help="strip base64 blobs and mask secrets")
    prd.add_argument("files", nargs="+")
    prd.add_argument("--json", action="store_true")

    pdf_ = sub.add_parser("diff", help="compress a git diff (elide lockfile/generated noise)")
    pdf_.add_argument("path", nargs="?", default="-",
                      help="diff file, or '-'/omitted to read stdin")
    pdf_.add_argument("--json", action="store_true")

    pi = sub.add_parser("index", help="build the code symbol index")
    pi.add_argument("path", nargs="?", default=".")
    pi.add_argument("--json", action="store_true")

    pq = sub.add_parser("query", help="look up a symbol in the index")
    pq.add_argument("term")
    pq.add_argument("--root", default=".")
    pq.add_argument("--kind", default=None)
    pq.add_argument("--limit", type=int, default=50)
    pq.add_argument("--json", action="store_true")

    sub.add_parser("stats").add_argument("--json", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "stats":
        led = cache.read_ledger()
        if args.json:
            print(json.dumps(led))
        else:
            total = led.get("total_tokens_saved", 0)
            print(f"justokenmax: {total:,} tokens saved across {led.get('runs', 0)} runs")
            for kind, n in sorted(led.get("by_kind", {}).items()):
                print(f"  {kind:6} {n:,}")
        return 0

    if args.cmd == "index":
        from .codeindex import build_index
        idx = build_index(args.path)
        if args.json:
            print(json.dumps({"files": idx["files"],
                              "symbols": len(idx["symbols"]),
                              "root": idx["root"]}))
        else:
            print(f"indexed {len(idx['symbols'])} symbols across "
                  f"{idx['files']} files -> "
                  f"{os.path.join(idx['root'], '.justokenmax', 'index.json')}")
        return 0

    if args.cmd == "query":
        from .codeindex import query, format_hits
        hits = query(args.root, args.term, kind=args.kind, limit=args.limit)
        if args.json:
            print(json.dumps(hits))
        else:
            print(format_hits(hits))
        return 0 if hits else 1

    if args.cmd == "delta":
        from .delta import delta
        rc = 1
        for f in args.files:
            artifact, st = delta(f)
            if args.json:
                print(json.dumps({"file": f, **st}))
            else:
                saved = max(0, st["tokens_full"] - st["tokens_delta"])
                pct = (100 * saved // st["tokens_full"]) if st["tokens_full"] else 0
                tag = "first read (full)" if not st["had_prior"] else \
                      ("no change" if not st["changed"] else f"diff -{pct}%")
                print(f"# {f}  [{tag}]  "
                      f"{st['tokens_full']}->{st['tokens_delta']} tokens")
                print(artifact)
            if st["had_prior"]:
                rc = 0
        return rc

    if args.cmd == "redact":
        from .redact import redact
        results = []
        for f in args.files:
            raw = open(f, encoding="utf-8", errors="replace").read()
            clean, st = redact(raw)
            key, out = cache.cache_paths(f, {"kind": "redact"}, ".redacted.txt")
            out.write_text(clean, encoding="utf-8")
            cache.record_origin(str(out), f)
            st.update({"file": f, "output": str(out)})
            results.append(st)
            if not args.json:
                print(f"ok    {f} -> {out}")
                print(f"      {st['secrets_masked']} secrets masked, "
                      f"{st['blobs_elided']} blobs elided")
        if args.json:
            print(json.dumps(results if len(results) > 1 else results[0]))
        return 0

    if args.cmd == "diff":
        from .diffcompress import compress_diff
        raw = (sys.stdin.read() if args.path == "-"
               else open(args.path, encoding="utf-8", errors="replace").read())
        digest, st = compress_diff(raw)
        if args.json:
            print(json.dumps({**st, "diff": digest}))
        else:
            sys.stdout.write(digest)
        return 0

    if args.cmd == "retrieve":
        origin = cache.lookup_origin(args.artifact)
        if args.json:
            print(json.dumps({"artifact": args.artifact, "origin": origin}))
        elif origin:
            print(origin)
        else:
            print("no recorded original for that artifact")
        return 0 if origin else 1

    return _run_optimize(args)


if __name__ == "__main__":
    sys.exit(main())
