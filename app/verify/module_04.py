"""Verify Module 04 — Agentic Architecture & Orchestration.

    python verify/module_04.py           # guardrails + wiring, no API spend
    python verify/module_04.py --live    # runs one real batch

Guardrails you can only test by running the agent are guardrails you test rarely.
Everything here except --live runs offline in under a second.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

sys.path.insert(0, str(PROJECT))

LIVE = "--live" in sys.argv

c = Checks("04")

for rel in ("coach/guardrails.py", "coach/agent.py", "tests/test_guardrails.py"):
    c.check(f"{rel} exists", file_exists(rel))


# --- Path classification ------------------------------------------------------
def corpus_paths_detected() -> tuple[bool, str]:
    from coach.guardrails import is_in_corpus

    missed = [
        p for p in ("corpus/exam-blueprint.md", "coach/../corpus/x.md") if not is_in_corpus(p)
    ]
    return not missed, f"failed to classify as corpus: {missed}"


c.check("corpus paths detected, traversal included", corpus_paths_detected)


def non_corpus_paths_allowed() -> tuple[bool, str]:
    """A guard that blocks everything looks identical to one that works."""
    from coach.guardrails import is_in_corpus

    false_positives = [p for p in ("coach/schema.py", "corpus_notes.py", "") if is_in_corpus(p)]
    return not false_positives, f"wrongly classified as corpus: {false_positives}"


c.check("legitimate paths are not blocked", non_corpus_paths_allowed)


# --- Budget -------------------------------------------------------------------
def budget_enforces_ceiling() -> tuple[bool, str]:
    from coach.guardrails import Budget, BudgetExceeded

    budget = Budget(max_turns=2)
    budget.spend()
    budget.spend()
    try:
        budget.spend()
    except BudgetExceeded:
        return True, ""
    return False, "third spend on a 2-turn budget did not raise"


c.check("budget raises when the turn ceiling is passed", budget_enforces_ceiling)


def budget_reports_remaining() -> tuple[bool, str]:
    from coach.guardrails import Budget

    budget = Budget(max_turns=5)
    budget.spend()
    return budget.remaining == 4, f"remaining should be 4, got {budget.remaining}"


c.check("budget reports remaining turns", budget_reports_remaining)


# --- Permission callback ------------------------------------------------------
def callback_denies_corpus_writes() -> tuple[bool, str]:
    from coach.guardrails import Budget, make_permission_callback

    budget = Budget(max_turns=10)
    cb = make_permission_callback(budget)
    result = asyncio.run(cb("Write", {"file_path": "corpus/exam-blueprint.md"}, None))
    denied = type(result).__name__ == "PermissionResultDeny"
    return denied, f"expected a deny, got {type(result).__name__}"


c.check("callback denies writes into corpus/", callback_denies_corpus_writes)


def callback_allows_normal_writes() -> tuple[bool, str]:
    from coach.guardrails import Budget, make_permission_callback

    budget = Budget(max_turns=10)
    cb = make_permission_callback(budget)
    result = asyncio.run(cb("Write", {"file_path": "coach/generated.py"}, None))
    allowed = type(result).__name__ == "PermissionResultAllow"
    return allowed, f"expected an allow, got {type(result).__name__}"


c.check("callback allows writes outside corpus/", callback_allows_normal_writes)


def callback_denies_when_budget_spent() -> tuple[bool, str]:
    from coach.guardrails import Budget, make_permission_callback

    budget = Budget(max_turns=1)
    budget.spend()
    cb = make_permission_callback(budget)
    result = asyncio.run(cb("Read", {"file_path": "coach/schema.py"}, None))
    return type(result).__name__ == "PermissionResultDeny", "exhausted budget still allowed a call"


c.check("callback denies once the budget is spent", callback_denies_when_budget_spent)


# --- Orchestration wiring -----------------------------------------------------
def critic_is_structurally_read_only() -> tuple[bool, str]:
    from coach.agent import CRITIC

    tools = list(CRITIC.tools or [])
    writers = [t for t in tools if t in {"Write", "Edit", "Bash", "NotebookEdit"}]
    if writers:
        return False, f"critic can use {writers} — instruction is not enforcement"
    return bool(tools), "critic has no explicit tool list, so it inherits everything"


c.check("critic subagent cannot write", critic_is_structurally_read_only)


def options_wire_the_guardrails() -> tuple[bool, str]:
    from coach.agent import build_options
    from coach.guardrails import Budget

    budget = Budget(max_turns=7)
    opts = build_options(budget)

    problems = []
    if opts.max_turns != 7:
        problems.append(f"max_turns={opts.max_turns}, expected 7")
    if opts.can_use_tool is None:
        problems.append("can_use_tool is not set")
    if not opts.agents or "question-critic" not in opts.agents:
        problems.append("question-critic is not registered")
    if "coach-corpus" not in (opts.mcp_servers or {}):
        problems.append("the MCP server from module 03 is not wired in")
    return not problems, "; ".join(problems)


c.check("options wire budget, callback, subagent, and MCP", options_wire_the_guardrails)


def callback_is_reachable_for_writes() -> tuple[bool, str]:
    """A guardrail that is attached but never consulted is not a guardrail.

    An `allowed_tools` entry that names a whole tool auto-approves it *before*
    can_use_tool runs, so listing "Write" there silently disables the corpus
    guard. The check above passes in that state -- it only proves the callback
    was assigned. This one proves a write can still reach it.
    """
    from coach.agent import build_options
    from coach.guardrails import WRITE_TOOLS, Budget

    opts = build_options(Budget(max_turns=7))

    def allows_whole_tool(entry: str) -> str | None:
        # Mirrors the CLI rule: no specifier, or an empty / lone-wildcard one.
        entry = entry.strip()
        if not entry:
            return None
        open_index = entry.find("(")
        if open_index == -1:
            return entry
        if open_index == 0 or not entry.endswith(")"):
            return None
        return entry[:open_index] if entry[open_index + 1 : -1] in ("", "*") else None

    shadowed = {
        tool
        for entry in (opts.allowed_tools or [])
        if (tool := allows_whole_tool(entry)) is not None
    }
    blinded = sorted(shadowed & WRITE_TOOLS)
    if blinded:
        return False, (
            f"allowed_tools auto-approves {blinded} before can_use_tool runs, so the "
            "corpus guard never fires for it. Drop it from allowed_tools, or narrow the "
            "entry to a real specifier so other calls fall through to the callback."
        )

    if opts.permission_mode == "bypassPermissions":
        return False, "permission_mode='bypassPermissions' auto-approves everything"

    return True, ""


c.check("a write can actually reach the permission callback", callback_is_reachable_for_writes)


def model_is_current() -> tuple[bool, str]:
    from coach.agent import MODEL

    return MODEL.startswith("claude-"), f"unexpected model id {MODEL!r}"


c.check("orchestrator model id looks valid", model_is_current)


# --- Live (opt-in) ------------------------------------------------------------
def live_batch() -> tuple[bool, str]:
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set"

    from coach.agent import run_batch

    out = PROJECT / "generated" / "verify_batch.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    budget = asyncio.run(run_batch("claude_code_config", 1, str(out)))
    if budget.turns_used == 0:
        return False, "the agent used zero turns — it never ran"
    return out.exists(), f"agent finished in {budget.turns_used} turns but wrote no output"


if LIVE:
    c.check("live: one batch runs and writes output", live_batch)
else:
    print("\n  (skipping live agent run — pass --live to include it)")

raise SystemExit(c.report())
