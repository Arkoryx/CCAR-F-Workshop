"""Verify Module 01 — Claude Code Configuration & Workflows.

Run from the app/ directory:   python verify/module_01.py

The interesting checks are the last three: they execute your hook with synthetic
stdin and assert it actually denies what it should. That turns "ask Claude and
see what happens" into something that either passes or fails, every time.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

HOOK = PROJECT / ".claude" / "hooks" / "protect_corpus.py"
SETTINGS = PROJECT / ".claude" / "settings.json"


def load_settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def run_hook(file_path: str) -> dict | None:
    """Invoke the PreToolUse hook the way Claude Code would. Returns its JSON
    decision, or None if the hook stayed silent (which means 'allow')."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(PROJECT),
        "tool_input": {"file_path": file_path},
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hook exited {proc.returncode}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def denies(file_path: str) -> tuple[bool, str]:
    decision = run_hook(file_path)
    if decision is None:
        return False, f"hook allowed {file_path!r} — it should have denied it"
    got = decision.get("hookSpecificOutput", {}).get("permissionDecision")
    return got == "deny", f"expected permissionDecision 'deny', got {got!r}"


def allows(file_path: str) -> tuple[bool, str]:
    decision = run_hook(file_path)
    return decision is None, f"hook blocked {file_path!r} — it should have allowed it"


c = Checks("01")

# --- Files exist -------------------------------------------------------------
for rel in (
    "CLAUDE.md",
    "pyproject.toml",
    ".claude/settings.json",
    ".claude/hooks/protect_corpus.py",
    ".claude/agents/question-critic.md",
    ".github/workflows/ci.yml",
    "coach/__init__.py",
    "corpus/exam-blueprint.md",
    "tests/test_smoke.py",
):
    c.check(f"{rel} exists", file_exists(rel))

# --- settings.json is well formed and says what it should --------------------
c.check("settings.json is valid JSON", lambda: (load_settings() is not None, ""))

c.check(
    "corpus writes are denied at the permission layer",
    lambda: (
        any("corpus" in rule for rule in load_settings()["permissions"]["deny"]),
        "no deny rule mentions corpus",
    ),
)

c.check(
    "secrets are denied, not merely 'ask'",
    lambda: (
        any(".env" in rule for rule in load_settings()["permissions"]["deny"]),
        "no deny rule covers .env — an 'ask' rule is not a security boundary",
    ),
)

c.check(
    "a PreToolUse hook is registered for Write|Edit",
    lambda: (
        any(
            entry.get("matcher") == "Write|Edit"
            for entry in load_settings().get("hooks", {}).get("PreToolUse", [])
        ),
        "no PreToolUse entry with matcher 'Write|Edit'",
    ),
)

# --- The subagent is defined and read-only -----------------------------------
def critic_is_read_only() -> tuple[bool, str]:
    text = (PROJECT / ".claude" / "agents" / "question-critic.md").read_text(encoding="utf-8")
    if "name: question-critic" not in text:
        return False, "frontmatter is missing 'name: question-critic'"
    tools_line = next((ln for ln in text.splitlines() if ln.startswith("tools:")), "")
    if not tools_line:
        return False, "no 'tools:' line — the critic would inherit every tool"
    forbidden = [t for t in ("Write", "Edit", "Bash") if t in tools_line]
    return not forbidden, f"critic can use {forbidden} — a critic that can edit is not a critic"


c.check("question-critic is defined and read-only", critic_is_read_only)

# --- The hook actually behaves ------------------------------------------------
c.check("hook DENIES a write inside corpus/", lambda: denies("corpus/exam-blueprint.md"))
c.check("hook ALLOWS a write inside coach/", lambda: allows("coach/schema.py"))
c.check(
    "hook DENIES a traversal path into corpus/",
    lambda: denies("coach/../corpus/sneaky.md"),
)

raise SystemExit(c.report())
