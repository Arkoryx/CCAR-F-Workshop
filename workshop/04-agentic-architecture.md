# Module 04 — Agentic Architecture & Orchestration

**Domain 1 · 27% of the exam · ~16 of 60 questions**

The heaviest domain. Task statements covered: designing and implementing agentic systems;
loop management; orchestration patterns; guardrails; the Claude Agent SDK.

Time: 4–6 hours. This is the module to slow down on.

---

## What you're building

The Coach agent proper. A `generate → critique → revise` loop that runs unattended:
a generator drafts questions, a **read-only critic subagent** reviews them, and the
orchestrator revises and saves. With guardrails that stop it before it burns your budget.

---

## Concept brief

### Four ways to build an agent — know which one you're using

This distinction is heavily testable because the names are confusable:

| Approach | You write | Harness | Deployment |
|---|---|---|---|
| **Manual loop** | The `while stop_reason == "tool_use"` loop | yours | yours |
| **Tool Runner** (`client.beta.messages.tool_runner`) | Just the tool functions | SDK | yours |
| **Managed Agents** (REST) | Agent config | Anthropic | **Anthropic** |
| **Claude Agent SDK** (`claude_agent_sdk`) | A prompt + options | Claude Code harness | yours |

Two traps:

1. **Tool Runner ≠ Agent SDK.** The Tool Runner is part of the regular `anthropic` API
   SDK — it loops over tools *you* define, with no built-in tools and no filesystem.
   The Agent SDK is Claude Code packaged as a library: built-in Read/Write/Edit/Bash/
   Grep/Glob, subagents, permissions, sessions.
2. **Only Managed Agents supplies deployment.** Tool Runner and Agent SDK are
   harness-only — you still host them.

We use the **Agent SDK** here, because file access and subagents are what this job needs.

### `query()` vs `ClaudeSDKClient`

| | `query()` | `ClaudeSDKClient` |
|---|---|---|
| Session | new each call | reused |
| Multi-turn | single exchange | multiple in context |
| Interrupts | ✗ | ✓ |
| Continue | manual via options | automatic |

Use `query()` for one-shot tasks; `ClaudeSDKClient` when the next action depends on the
last response. Our loop is multi-turn, so: client.

### The loop and its termination conditions

Every agentic loop needs an answer to "when do I stop?" There are four, and a production
loop handles all four:

1. **Task complete** — the model stops calling tools.
2. **Turn budget exhausted** — `max_turns`.
3. **Cost budget exhausted** — your own accounting.
4. **Unrecoverable error** — a refusal, an auth failure, a tool that keeps failing.

A loop that only handles (1) is the one that runs all night. **This is the single most
common real-world failure in this domain**, and it's why guardrails are their own task
statement.

### Guardrails, concretely

- **`max_turns`** — a hard ceiling on tool-use round trips.
- **`can_use_tool`** — a permission callback. Your code sees every tool call the harness
  would prompt on, and returns allow (optionally with modified input) or deny.
- **`allowed_tools` / `disallowed_tools`** — coarse allowlisting.
- **Subagent tool restriction** — an `AgentDefinition` with `tools=["Read", "Grep"]` is
  structurally incapable of writing.

Note what `can_use_tool` is *not*: it fires only when permission evaluation reaches a
prompt. Tools already auto-approved by a settings `allow` rule don't reach it. If you
want the callback to see everything, don't pre-approve everything.

### Orchestrator–worker

The orchestrator holds the goal and the context. Workers get **self-contained** briefs —
a subagent sees none of the orchestrator's conversation. Anything the worker needs must
be in the message or on disk.

Two direction changes worth knowing, because they invert older advice:

- Current Opus-tier models **delegate more readily** than the previous generation. Older
  guidance said "encourage delegation"; now the risk runs the other way. Each subagent
  re-establishes context, re-explores, and reports back — then you re-read the report.
  Cap it.
- Verification is similar. Current models verify their own work unprompted, so
  instructions telling them to double-check now cause *over*-verification. The critic here
  earns its place because it's a genuinely independent read with a fresh context — not
  because the generator can't self-check.

---

## Build

### Step 1 — The permission callback

Write the guardrail before the loop. It's the part you can test without spending anything.

`app/coach/guardrails.py`:

```python
"""Permission callback and budget tracking for the Coach agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = (ROOT / "corpus").resolve()

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}


class BudgetExceeded(RuntimeError):
    """Raised when the agent exhausts its allotted turns."""


@dataclass
class Budget:
    """Turn accounting. The loop's third termination condition."""

    max_turns: int = 12
    turns_used: int = 0
    denials: list[str] = field(default_factory=list)

    def spend(self) -> None:
        self.turns_used += 1
        if self.turns_used > self.max_turns:
            raise BudgetExceeded(f"exceeded {self.max_turns} turns")

    @property
    def remaining(self) -> int:
        return max(0, self.max_turns - self.turns_used)


def is_in_corpus(raw_path: str) -> bool:
    """Resolve before comparing. Same rule as the module 01 hook."""
    if not raw_path:
        return False
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    return resolved == CORPUS or CORPUS in resolved.parents


def make_permission_callback(budget: Budget):
    """Build a can_use_tool callback bound to a budget.

    Returns PermissionResultAllow / PermissionResultDeny. Imported lazily so this
    module can be unit-tested without the SDK installed.
    """
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any):
        if tool_name in WRITE_TOOLS and is_in_corpus(input_data.get("file_path", "")):
            reason = f"{tool_name} blocked: the corpus is read-only"
            budget.denials.append(reason)
            return PermissionResultDeny(message=reason, interrupt=False)

        if budget.remaining == 0:
            reason = "turn budget exhausted"
            budget.denials.append(reason)
            return PermissionResultDeny(message=reason, interrupt=True)

        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool
```

Note `interrupt=True` on the budget denial and `False` on the corpus denial. A corpus
write is a mistake the agent can recover from by writing elsewhere; an exhausted budget
means stop entirely.

### Step 2 — The agent

`app/coach/agent.py`:

```python
"""The Certification Coach agent: generate → critique → revise."""

from __future__ import annotations

import asyncio

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ClaudeSDKClient

from coach.guardrails import Budget, BudgetExceeded, make_permission_callback

MODEL = "claude-opus-5"

ORCHESTRATOR_PROMPT = """\
You produce vetted practice questions for the CCAR-F exam.

Your loop for each batch:
1. Ground yourself: call the corpus search tool before writing anything.
2. Draft the questions.
3. Delegate review to the question-critic subagent. Give it a self-contained brief —
   it cannot see this conversation.
4. Apply the critic's findings. If a question has more than one defensible answer,
   fix it or drop it. Dropping is fine; shipping an ambiguous question is not.
5. Save the surviving questions to the path you were given.

Never edit anything under corpus/. It is source material, not workspace.

Delegate once per batch. Do not spawn a subagent per question — the review overhead
exceeds the work.
"""

CRITIC = AgentDefinition(
    description=(
        "Reviews draft exam questions for ambiguity, multiple defensible answers, and "
        "traceability to the blueprint. Use after drafting, before saving."
    ),
    prompt=(
        "You review draft CCAR-F practice questions. For each: confirm exactly one "
        "defensible answer (or that the stem says how many to select), confirm it maps "
        "to a blueprint domain, and judge whether distractors are plausible. Report "
        "findings per question. Do not rewrite questions — that is the orchestrator's "
        "job. You are read-only by design."
    ),
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
    maxTurns=6,
)


def build_options(budget: Budget) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=ORCHESTRATOR_PROMPT,
        max_turns=budget.max_turns,
        can_use_tool=make_permission_callback(budget),
        agents={"question-critic": CRITIC},
        allowed_tools=[
            "Read",
            "Grep",
            "Glob",
            "Write",
            "mcp__coach-corpus__search_corpus",
            "mcp__coach-corpus__get_objectives",
        ],
        mcp_servers={
            "coach-corpus": {
                "command": "python",
                "args": ["-m", "coach.mcp_server.server"],
            }
        },
    )


async def run_batch(domain: str, n: int, out_path: str) -> Budget:
    """Run one generate → critique → revise cycle. Returns the spent budget."""
    budget = Budget(max_turns=12)
    options = build_options(budget)

    prompt = (
        f"Produce {n} vetted questions for the {domain} domain. "
        f"Save the final set as JSON to {out_path}."
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                budget.spend()
                print(message)
    except BudgetExceeded as exc:
        print(f"[guardrail] {exc}")

    return budget


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="claude_code_config")
    parser.add_argument("-n", type=int, default=3)
    parser.add_argument("--out", default="generated/batch.json")
    args = parser.parse_args()

    spent = asyncio.run(run_batch(args.domain, args.n, args.out))
    print(f"\nturns used: {spent.turns_used}/{spent.max_turns}")
    if spent.denials:
        print(f"guardrail denials: {spent.denials}")
```

### Step 3 — Test the guardrail before you run the agent

`app/tests/test_guardrails.py`:

```python
import pytest

from coach.guardrails import Budget, BudgetExceeded, is_in_corpus


def test_corpus_paths_detected():
    assert is_in_corpus("corpus/exam-blueprint.md")
    assert is_in_corpus("coach/../corpus/sneaky.md")


def test_non_corpus_paths_allowed():
    assert not is_in_corpus("coach/schema.py")
    assert not is_in_corpus("corpus_notes.py")   # substring, not the directory


def test_budget_raises_when_exhausted():
    budget = Budget(max_turns=2)
    budget.spend()
    budget.spend()
    with pytest.raises(BudgetExceeded):
        budget.spend()
```

That `corpus_notes.py` case is the one a naive substring check gets wrong in the
permissive direction — it blocks a legitimate file. The traversal case gets it wrong in
the dangerous direction. Both come from the same missing `.resolve()`.

---

## Checkpoint

```bash
python verify/module_04.py          # guardrails + options wiring, no API spend
python verify/module_04.py --live   # runs one real batch
```

The offline run proves the guardrail denies corpus writes, allows legitimate writes,
enforces the budget, and that the critic is structurally read-only. **All of that is
testable without an agent running**, which is the point — guardrails you can only test by
running the agent are guardrails you test rarely.

Then the real thing:

```bash
python -m coach.agent --domain claude_code_config -n 3 --out generated/batch.json
```

Watch the turn count. If it hits the ceiling, that's the guardrail working, not a bug.

---

## Exam drill

**1.** Which supplies both the agent harness **and** managed deployment?

A. Claude Agent SDK B. Tool Runner
C. Managed Agents D. A manual loop over `messages.create()`

**2.** What does the Tool Runner give you that a manual loop doesn't?

A. Built-in file and bash tools
B. The request → execute → loop cycle over tools you define
C. A hosted sandbox
D. Subagent orchestration

**3.** You need interrupts and a session that persists across turns. Which entry point?

A. `query()` B. `ClaudeSDKClient`
C. `create_sdk_mcp_server()` D. `messages.create()`

**4.** `can_use_tool` isn't firing for a tool you expected to gate. Most likely cause:

A. The callback must be synchronous
B. The tool is auto-approved, so evaluation never reaches a prompt
C. `can_use_tool` only fires for MCP tools
D. It requires `permission_mode="ask"`

**5.** Which are valid returns from a `can_use_tool` callback? *(Select two.)*

A. `PermissionResultAllow(updated_input=...)` B. `True`
C. `PermissionResultDeny(message=...)` D. `{"decision": "allow"}`

**6.** A subagent needs a file path the orchestrator discovered three turns ago. What
must happen?

A. Nothing — subagents inherit the parent conversation
B. The path must be in the delegated message or on disk
C. Set `share_context=True`
D. The subagent re-runs the orchestrator's tool calls automatically

**7.** Which four conditions should terminate a production agent loop? *(Select all that
apply — four are correct.)*

A. Model stops calling tools B. `max_turns` reached
C. Cost budget exhausted D. Unrecoverable error
E. The first tool failure

**8.** You restrict a critic subagent with `tools=["Read", "Grep"]`. What does this buy
over instructing it not to edit?

A. Nothing; both are equivalent
B. Structural enforcement — the tools aren't available, so no prompt can talk it into
   editing
C. Lower token cost only
D. It makes the subagent run faster

**9.** Your agent spawns a subagent per item across 30 items and costs balloon. On a
current Opus-tier model, the best first fix is:

A. Add "you may delegate" to the prompt
B. Cap delegation explicitly and reserve subagents for genuinely independent tracks
C. Increase `max_turns` so each subagent finishes
D. Switch every subagent to Opus for fewer turns

**10.** Which best describes the relationship between the Agent SDK and Claude Code?

A. Unrelated products that share a name
B. The Agent SDK is Claude Code packaged as a library; it drives the Claude Code CLI
C. Claude Code is built on the Agent SDK, which is a thin wrapper over `messages.create()`
D. The Agent SDK is the Managed Agents REST client

<details>
<summary><b>Answer key</b></summary>

**1 — C.** Managed Agents. The Agent SDK and Tool Runner are harness-only — you still host
and deploy them. This split (who supplies the harness vs. who supplies deployment) is the
cleanest way to keep the four approaches straight.

**2 — B.** The Tool Runner automates the loop over *your* tools. It has no built-in tools
and no sandbox — those are A and C, which belong to the Agent SDK and Managed Agents.

**3 — B.** `ClaudeSDKClient`. `query()` creates a new session per call and doesn't support
interrupts.

**4 — B.** The callback fires only when permission evaluation reaches a prompt. A tool
already auto-approved by an `allow` rule or `allowed_tools` never gets there. Pre-approving
everything and then wondering why the callback is silent is a common self-inflicted wound.

**5 — A and C.** The typed results from `claude_agent_sdk.types`. Bare booleans and dicts
aren't the contract.

**6 — B.** Subagents get a fresh context and see none of the parent conversation. Briefs
must be self-contained — everything the worker needs is in the message or on disk.

**7 — A, B, C, D.** All four. E is wrong: a single tool failure should usually be retried
or worked around, not fatal. A loop that only handles A is the one that runs all night.

**8 — B.** Structural enforcement beats instruction. Same principle as module 01's `deny`
rule versus a `CLAUDE.md` sentence — it recurs across every domain on this exam because
it's the core architectural idea.

**9 — B.** Current Opus-tier models delegate *more* readily than the previous generation,
so the fix is a cap, not encouragement. A is exactly backwards and reflects advice written
for an earlier model.

**10 — B.** The Agent SDK is Claude Code as a library and drives the CLI process — which
is why module 00 makes the CLI a hard prerequisite. C describes the Tool Runner.

</details>

---

## Further reading

- [Agent SDK — Python](https://code.claude.com/docs/en/agent-sdk/python)
- [Agent SDK — permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
- [Agent SDK — subagents](https://code.claude.com/docs/en/agent-sdk/subagents)
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

---

**Next:** [Module 05 — Context Management & Reliability](05-context-and-reliability.md) (15%)
