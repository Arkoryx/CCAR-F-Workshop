"""Verify Module 01 — Claude Code Configuration & Workflows.

Run from the app/ directory:   python verify/module_01.py

The interesting checks are the last three: they execute your hook with synthetic
stdin and assert it actually denies what it should. That turns "ask Claude and
see what happens" into something that either passes or fails, every time.
"""

from __future__ import annotations

import json
import re
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


def denies_corpus_writes() -> tuple[bool, str]:
    """A deny rule must stop *writes*. Denying reads leaves the corpus editable."""
    deny = load_settings()["permissions"]["deny"]
    if any(rule.startswith("Write(") and "corpus" in rule for rule in deny):
        return True, ""
    if any("corpus" in rule for rule in deny):
        return False, (
            "a corpus deny rule exists but it is not a Write rule — denying reads "
            "does not stop writes"
        )
    return False, "no deny rule mentions corpus"


def denies_secret_reads() -> tuple[bool, str]:
    """A deny rule only protects what its *pattern* matches.

    `.env` is a file, not a directory. A pattern like `Read(./.env/**)` targets
    paths inside a directory that does not exist, and in doing so stops matching
    the file itself — a rule that reads as protection and enforces nothing.
    """
    deny = load_settings()["permissions"]["deny"]
    env_reads = [rule for rule in deny if rule.startswith("Read(") and ".env" in rule]
    if not env_reads:
        if any(".env" in rule for rule in deny):
            return False, "a .env deny rule exists but it is not a Read rule"
        return False, "no deny rule covers .env — an 'ask' rule is not a security boundary"
    if all(".env/" in rule for rule in env_reads):
        return False, (
            f"{env_reads[0]} treats .env as a directory; it is a file, so this matches "
            "nothing and no longer covers .env itself"
        )
    return True, ""


# These assert that a rule protects *something*. They cannot certify that your
# patterns cover *everything* — `Read(./.env)` alone passes while `.env.local`
# stays readable. Green is evidence, not proof.
c.check("corpus writes are denied at the permission layer", denies_corpus_writes)
c.check("secrets are denied, not merely 'ask'", denies_secret_reads)


def matcher_groups(event: str) -> tuple[list, str]:
    """hooks.<event> is a LIST of matcher groups, not a single group.

    Collapsing the list to one object is an easy mistake when you only have one
    matcher, and iterating a dict in Python yields its keys, so the failure
    surfaces as an unhelpful AttributeError on a string. Name it instead.
    """
    groups = load_settings().get("hooks", {}).get(event, [])
    if isinstance(groups, dict):
        return [], (
            f"hooks.{event} is a single object; it must be a list of matcher groups: "
            f'"{event}": [ {{ "matcher": ..., "hooks": [...] }} ]'
        )
    if not isinstance(groups, list):
        return [], f"hooks.{event} must be a list, got {type(groups).__name__}"
    return groups, ""


def registered_for(event: str):
    def _check() -> tuple[bool, str]:
        groups, err = matcher_groups(event)
        if err:
            return False, err
        found = any(g.get("matcher") == "Write|Edit" for g in groups)
        return found, f"no {event} entry with matcher 'Write|Edit'"

    return _check


def pre_tool_use_command_resolves() -> tuple[bool, str]:
    """A registration that names a script which does not exist enforces nothing.

    Only the basename is checked, against .claude/hooks/. That catches a typo or
    a missing file; it does not prove the directory in the command is right.
    """
    groups, err = matcher_groups("PreToolUse")
    if err:
        return False, err
    seen: list[str] = []
    for group in groups:
        for hook in group.get("hooks", []):
            command = hook.get("command", "")
            for name in re.findall(r"[\w.-]+\.py", command):
                seen.append(name)
                if (PROJECT / ".claude" / "hooks" / name).exists():
                    return True, ""
    return False, (
        f"no PreToolUse command names a script in .claude/hooks/ — saw {seen or 'no .py file'}"
    )


c.check("a PreToolUse hook is registered for Write|Edit", registered_for("PreToolUse"))
c.check("a PostToolUse hook is registered for Write|Edit", registered_for("PostToolUse"))
c.check("the PreToolUse command names a hook script that exists", pre_tool_use_command_resolves)


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
