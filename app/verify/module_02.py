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
    return bool(
        tagged
    ), "interpolated corpus is not delimited — markdown in it can bleed into instructions"


c.check("user prompt delimits interpolated corpus", prompt_uses_delimiters)


# Stands in for the corpus excerpt. It carries no tags of its own, so every tag in
# the rendered prompt is one user_prompt() wrote rather than one that arrived with
# the material.
SENTINEL = "CORPUS-EXCERPT-PLACEHOLDER"


def delimiter_does_not_collide() -> tuple[bool, str]:
    """The delimiter must not occur inside the material it delimits.

    The check above asserts a delimiter exists. This one asserts it can work: a
    tag that also appears in the corpus is not a boundary, because an early
    closing tag inside the excerpt ends the delimited region and everything after
    it reads as instruction.

    Not hypothetical. Anthropic's prompting guide recommends <instructions>,
    <context> and <input> -- and once that guide is in the corpus, all three
    collide with it.
    """
    from coach.prompts import user_prompt

    rendered = user_prompt("prompt_engineering", 3, SENTINEL)
    tags = sorted(set(re.findall(r"</?(\w+)>", rendered)))
    if not tags:
        return False, "no delimiter to check — see 'user prompt delimits interpolated corpus'"

    docs = sorted((PROJECT / "corpus").glob("*.md"))
    if not docs:
        # Vacuous, and honestly so: the workshop's starting corpus is the blueprint
        # alone, which contains no XML-like tags at all.
        return True, ""

    for doc in docs:
        text = doc.read_text(encoding="utf-8", errors="replace")
        for tag in tags:
            if f"<{tag}>" in text or f"</{tag}>" in text:
                return False, (
                    f"delimiter <{tag}> also occurs in corpus/{doc.name} — "
                    f"an early </{tag}> in the excerpt ends your delimited region"
                )
    return True, ""


c.check("user prompt delimiter does not collide with the corpus", delimiter_does_not_collide)


def generate_imports_without_calling_api() -> tuple[bool, str]:
    """Importing the module must not construct a client or make a request.

    If it does, every test run and every CI job costs money.

    Each condition reports itself. An assertion that ands several tests together
    and prints only one of them sends the reader to inspect a line that is
    already correct — which is worse than no message at all.
    """
    import coach.generate as g

    absent = [name for name in ("MODEL", "generate") if not hasattr(g, name)]
    if absent:
        return False, f"coach.generate defines no {', '.join(absent)}"
    if not g.MODEL.startswith("claude-"):
        return False, f"unexpected MODEL={g.MODEL!r}"
    return True, ""


c.check("coach.generate imports without side effects", generate_imports_without_calling_api)


def corpus_selection_is_domain_scoped() -> tuple[bool, str]:
    """Asking for one domain must not hand the model another domain's material.

    Two failures live here and only the first is obvious. A loader that ignores
    the domain sends whatever sorts first, so the prompt says "prompt_engineering"
    over agentic-architecture docs. A loader that filters correctly but truncates
    one long concatenation sends only the first file of the domain, and the rest
    of the material is never seen — output that looks entirely reasonable and is
    drawn from a fraction of the sources.
    """
    from coach.generate import DOMAIN_PREFIX, load_corpus
    from coach.schema import Domain

    corpus = PROJECT / "corpus"
    populated = {d: sorted(corpus.glob(f"{DOMAIN_PREFIX[d]}-*.md")) for d in Domain}
    populated = {d: docs for d, docs in populated.items() if docs}
    if len(populated) < 2:
        # Vacuous: the starting corpus is the blueprint alone, and a filter
        # cannot be observed until at least two domains have documents.
        return True, ""

    samples = {d: load_corpus(d) for d in populated}
    if len(set(samples.values())) != len(samples):
        return (
            False,
            "load_corpus returns identical text for different domains — it is not filtering",
        )

    for domain, docs in populated.items():
        absent = [
            d.name for d in docs if d.read_text(encoding="utf-8")[:200] not in samples[domain]
        ]
        if absent:
            return False, f"{domain.value} never reaches these documents: {absent}"
    return True, ""


c.check("load_corpus selects material for the requested domain", corpus_selection_is_domain_scoped)


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


# Minimum cacheable prefix, per model. Non-monotonic across generations, which is
# why this cannot be one hardcoded number: module 00 recommends Sonnet or Haiku for
# bulk generation, and Haiku's minimum is 8x Opus 5's.
CACHE_MINIMUMS = {
    "claude-opus-5": 512,
    "claude-fable-5": 512,
    "claude-sonnet-5": 1024,
    "claude-opus-4-8": 1024,
    "claude-sonnet-4-6": 1024,
    "claude-opus-4-7": 2048,
    "claude-haiku-4-5": 4096,
    "claude-opus-4-6": 4096,
}


def system_prompt_clears_cache_minimum() -> tuple[bool, str]:
    """A prompt below the minimum never caches -- silently, with no error.

    Live because an accurate count needs the model's own tokenizer. A character
    estimate is the same class of approximation this module warns about.

    The limit of this check: it asks whether the system prompt *alone* clears the
    floor. Where the cache_control breakpoint actually goes is module 05's call,
    and a breakpoint placed after the corpus excerpt makes the prefix far larger.
    This is a floor on the simplest arrangement, not a verdict on that design.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set"
    from anthropic import Anthropic

    from coach.generate import MODEL
    from coach.prompts import GENERATOR_SYSTEM

    minimum = CACHE_MINIMUMS.get(MODEL)
    if minimum is None:
        # A wrong threshold is worse than no threshold.
        return True, ""

    client = Anthropic()
    probe = [{"role": "user", "content": "."}]
    # The endpoint is stateless, so subtracting a baseline gives the marginal cost
    # of the system prompt rather than the prompt plus envelope overhead.
    with_system = client.messages.count_tokens(
        model=MODEL, system=GENERATOR_SYSTEM, messages=probe
    ).input_tokens
    baseline = client.messages.count_tokens(model=MODEL, messages=probe).input_tokens
    tokens = with_system - baseline

    return tokens >= minimum, (
        f"GENERATOR_SYSTEM is {tokens} tokens; {MODEL} needs {minimum} to cache at all. "
        "Below the floor there is no error, just cache_creation_input_tokens: 0."
    )


if LIVE:
    c.check("live: one generation call returns a valid question", live_generation)
    c.check(
        "live: the system prompt clears the model's cache minimum",
        system_prompt_clears_cache_minimum,
    )
else:
    print("\n  (skipping live API check — pass --live to include it)")

raise SystemExit(c.report())
