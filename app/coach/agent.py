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
        # Read-only tools are pre-approved. Write is deliberately absent: an
        # allowed_tools entry naming a whole tool auto-approves it before
        # can_use_tool runs, which would silently disable the corpus guard.
        allowed_tools=[
            "Read",
            "Grep",
            "Glob",
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
