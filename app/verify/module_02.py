"""Verify Module 02 — Prompt Engineering & Structured Output.

    python verify/module_02.py           # free: schema, fixtures, prompt hygiene
    python verify/module_02.py --live    # + one real generation call

The default run spends nothing. A verification suite you can't afford to run is a
verification suite you won't run.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

sys.path.insert(0, str(PROJECT))

LIVE = "--live" in sys.argv
FIXTURES = PROJECT / "tests" / "fixtures"

c = Checks("02")

for rel in (
    "coach/schema.py",
    "coach/prompts.py",
    "coach/generate.py",
    "tests/fixtures/valid_question.json",
    "tests/test_schema.py",
):
    c.check(f"{rel} exists", file_exists(rel))


# --- Schema shape -------------------------------------------------------------
def domains_match_blueprint() -> tuple[bool, str]:
    from coach.schema import WEIGHTS, Domain

    if len(Domain) != 5:
        return False, f"expected 5 domains, found {len(Domain)}"
    total = round(sum(WEIGHTS.values()), 4)
    return total == 1.0, f"domain weights sum to {total}, not 1.0"


c.check("five domains, weights sum to 1.0", domains_match_blueprint)


def valid_fixture_parses() -> tuple[bool, str]:
    from coach.schema import Question

    payload = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    q = Question.model_validate(payload)
    return bool(q.source), "the fixture has an empty source field"


c.check("the golden fixture parses", valid_fixture_parses)


def invalid_payloads_rejected() -> tuple[bool, str]:
    """The schema must reject broken questions, not just accept good ones.

    A validator that only ever sees valid input is untested.
    """
    from pydantic import ValidationError

    from coach.schema import Question

    base = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    mutations = {
        "no correct answer": lambda p: p.update(correct_labels=[]),
        "answer points at a missing choice": lambda p: p.update(correct_labels=["Z"]),
        "every choice marked correct": lambda p: p.update(
            correct_labels=[ch["label"] for ch in p["choices"]]
        ),
        "only three choices": lambda p: p["choices"].pop(),
        "duplicate choice label": lambda p: p["choices"].append({"label": "A", "text": "x"}),
    }

    leaked = []
    for name, mutate in mutations.items():
        payload = json.loads(json.dumps(base))
        mutate(payload)
        try:
            Question.model_validate(payload)
        except ValidationError:
            continue
        leaked.append(name)

    return not leaked, f"schema accepted broken questions: {leaked}"


c.check("broken questions are rejected", invalid_payloads_rejected)


# --- Prompt hygiene -----------------------------------------------------------
def system_prompt_is_substantive() -> tuple[bool, str]:
    from coach.prompts import GENERATOR_SYSTEM

    return len(GENERATOR_SYSTEM) > 300, "system prompt looks like a stub"


c.check("system prompt is substantive", system_prompt_is_substantive)


def system_prompt_is_cacheable() -> tuple[bool, str]:
    """A system prompt that changes per request can never be cached.

    Module 05 covers this properly, but the mistake is cheaper to catch now:
    the prompt is a module-level constant, so anything time- or
    identity-dependent baked into it silently kills every cache hit downstream.
    """
    source = (PROJECT / "coach" / "prompts.py").read_text(encoding="utf-8")
    header = source.split("def user_prompt", 1)[0]
    invalidators = [
        pattern
        for pattern in ("datetime.now", "time.time", "uuid4", "random.", "os.urandom")
        if pattern in header
    ]
    return not invalidators, f"volatile content in the cached prefix: {invalidators}"


c.check("system prompt has no cache invalidators", system_prompt_is_cacheable)


def prompt_uses_delimiters() -> tuple[bool, str]:
    from coach.prompts import user_prompt

    rendered = user_prompt("agentic_architecture", 3, "# A heading that could confuse things")
    tagged = re.search(r"<\w+>.*</\w+>", rendered, re.DOTALL)
    return bool(tagged), "interpolated corpus is not delimited — markdown in it can bleed into instructions"


c.check("user prompt delimits interpolated corpus", prompt_uses_delimiters)


def generate_imports_without_calling_api() -> tuple[bool, str]:
    """Importing the module must not construct a client or make a request.

    If it does, every test run and every CI job costs money.
    """
    import coach.generate as g

    return hasattr(g, "generate") and g.MODEL.startswith("claude-"), f"unexpected MODEL={g.MODEL!r}"


c.check("coach.generate imports without side effects", generate_imports_without_calling_api)


# --- Live check (opt-in) ------------------------------------------------------
def live_generation() -> tuple[bool, str]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set"
    from coach.generate import generate
    from coach.schema import Domain

    batch = generate(Domain.CLAUDE_CODE, n=1)
    if not batch.questions:
        return False, "the model returned an empty batch"
    q = batch.questions[0]
    return q.domain == Domain.CLAUDE_CODE, f"asked for claude_code, got {q.domain}"


if LIVE:
    c.check("live: one generation call returns a valid question", live_generation)
else:
    print("\n  (skipping live API check — pass --live to include it)")

raise SystemExit(c.report())
