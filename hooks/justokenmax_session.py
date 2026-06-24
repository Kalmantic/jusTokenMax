#!/usr/bin/env python3
"""Stop hook — record this Claude Code session's jusTokenMax savings.

At the end of every session, append one row to ~/.justokenmax/sessions.jsonl
capturing how many tokens jusTokenMax saved during it (delta since the last
session), so you can analyze the plugin's effectiveness over time
(`justokenmax sessions`). Fails open — never blocks the session ending.
"""

import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "python"))


def main() -> None:
    session_id = None
    try:
        payload = json.load(sys.stdin)
        session_id = payload.get("session_id")
    except Exception:
        pass
    try:
        from justokenmax import sessions
        sessions.record(session_id=session_id)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
