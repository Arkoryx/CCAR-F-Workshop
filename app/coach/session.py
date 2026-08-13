"""Persist a study session so it survives a restart.

Note what gets stored: the full content blocks, not extracted text. If you enable
compaction, the compaction blocks live in there — dropping them loses the
compacted history.
"""

from __future__ import annotations

import json
from pathlib import Path

SESSIONS = Path(__file__).resolve().parents[1] / ".coach" / "sessions"


def save(session_id: str, messages: list[dict]) -> Path:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    path = SESSIONS / f"{session_id}.json"
    path.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    return path


def load(session_id: str) -> list[dict]:
    path = SESSIONS / f"{session_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
