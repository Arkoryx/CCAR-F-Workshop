#!/usr/bin/env python3
"""Block any write or edit targeting the read-only corpus directory."""
import json
import sys
from pathlib import Path

payload = json.load(sys.stdin)
target = payload.get("tool_input", {}).get("file_path", "")

if target:
    # Resolve against the cwd the payload gives us, never the hook process's own
    # cwd. Joining an absolute target discards the left side, so this is correct
    # whether Claude Code sends an absolute path or a relative one.
    cwd = Path(payload["cwd"])
    resolved = (cwd / target).resolve()
    corpus = (cwd / "corpus").resolve()
    if resolved == corpus or corpus in resolved.parents:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{resolved.name} is in the read-only corpus. "
                    "Generated artifacts belong in coach/ or tests/."
                ),
            }
        }, sys.stdout)

sys.exit(0)
