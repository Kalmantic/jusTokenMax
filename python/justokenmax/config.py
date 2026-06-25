"""User configuration — turn individual levers on/off.

jusTokenMax optimizes everything by default, but you should be able to tune it
to your project. A lever can be disabled two ways (either wins):

  * env:   JUSTOKENMAX_DISABLE=pdf,image      (comma-separated kinds)
  * file:  ~/.justokenmax/config.json  ->  {"disabled": ["pdf", "image"]}

Kinds: pdf, image, log, json, notebook, csv, diff, code, redact. Disabling a kind
makes optimize() skip it (the Read hook then leaves those files untouched);
disabling `redact` stops the secret/blob masking pass inside text digests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Set

from . import cache

KINDS = ("pdf", "image", "log", "json", "notebook", "csv", "diff", "code", "redact")


def config_path() -> str:
    return os.environ.get("JUSTOKENMAX_CONFIG") or str(cache.ROOT / "config.json")


def load() -> dict:
    path = config_path()
    if os.path.exists(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def disabled_kinds() -> Set[str]:
    out = set(load().get("disabled", []))
    env = os.environ.get("JUSTOKENMAX_DISABLE", "")
    out.update(k.strip() for k in env.split(",") if k.strip())
    return out


def is_enabled(kind: str) -> bool:
    return kind not in disabled_kinds()


def set_kind(kind: str, enabled: bool) -> dict:
    """Persist a lever's on/off state to the config file; returns the new config."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind} (choose from {', '.join(KINDS)})")
    cfg = load()
    disabled = set(cfg.get("disabled", []))
    if enabled:
        disabled.discard(kind)
    else:
        disabled.add(kind)
    cfg["disabled"] = sorted(disabled)
    cache.ROOT.mkdir(parents=True, exist_ok=True)
    cache._harden(cache.ROOT)
    Path(config_path()).write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return cfg


def summary() -> dict:
    dis = disabled_kinds()
    return {"config_file": config_path(),
            "kinds": {k: (k not in dis) for k in KINDS}}
