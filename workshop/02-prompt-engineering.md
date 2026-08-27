# Module 02 — Prompt Engineering & Structured Output

**Domain 3 · 20% of the exam · ~12 of 60 questions**

Task statements covered: crafting effective prompts; implementing structured output
patterns; applying prompt engineering techniques for production applications.

Time: 2–4 hours.

---

## What you're building

The question generator. By the end, `python -m coach.generate --domain agentic -n 5`
emits five schema-valid practice questions. Not "usually valid" — the API constrains the
response to your schema, and your code rejects anything that slips through.

---

## Concept brief

### Structured outputs replaced the prefill trick

The old way to force JSON was to prefill the assistant turn with `{` and let the model
continue. **That returns a 400 on current models** — Opus 5, Sonnet 5, Fable 5, and the
whole 4.6/4.7/4.8 family reject a trailing assistant message.

This is the single most likely thing on the exam from this domain, because it's a real
migration people are still doing. The replacement is `output_config.format`:

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    messages=[...],
    output_config={
        "format": {
            "type": "json_schema",
            "schema": {...},
        }
    },
)
```

Two related deprecations worth keeping straight:

| Don't | Do |
|---|---|
| Prefill `{"role": "assistant", "content": "{"}` | `output_config.format` |
| Top-level `output_format=` on `messages.create()` | `output_config={"format": {...}}` |
| Stop sequences + regex extraction + retry-on-parse | Any of the above |

The whole scaffold around prefill — stop sequences guarding JSON, `json.loads` in a retry
loop — is dead code once you migrate. Removing the workaround but keeping its scaffolding
is a half-migration.

### The Pydantic path is shorter

`client.messages.parse()` takes a Pydantic model, generates the schema, and returns a
validated instance:

```python
response = client.messages.parse(
    model="claude-opus-5",
    max_tokens=16000,
    messages=[...],
    output_format=Question,      # a Pydantic BaseModel
)
question = response.parsed_output   # a Question instance, already validated
```

### JSON Schema support is a subset — this bites

Supported: basic types, `enum`, `const`, `anyOf`, `allOf`, `$ref`/`$def`, string
`format` values, and `additionalProperties: false` (**required** on every object).

**Not supported:** recursive schemas, numeric constraints (`minimum`, `maximum`,
`multipleOf`), string length constraints (`minLength`, `maxLength`), most array
constraints. One narrow exception: `minItems` survives when its value is `0` or `1`.

So a schema saying "exactly 4 choices" **cannot be enforced by the API.**

**They are not stripped, though, and the difference matters.** The SDK moves every
unsupported keyword into that field's `description` — creating one if the field had none
— so the model *might* follow it. Verified against `anthropic` 0.122.0, whose own comment
in `anthropic/lib/_parse/_transform.py` says exactly that: *"if there are any props
leftover then they aren't supported, so we add them to the description so that the model
*might* follow them."*

| You write | What is actually sent |
|---|---|
| `Field(min_length=20)` on a `str` | `{"type": "string", "description": "{minLength: 20}"}` |
| `Field(min_length=1)` on a `list` | `{"type": "array", "minItems": 1}` — a real constraint |
| `Field(min_length=4)` on a `list` | `{"type": "array", "description": "{minItems: 4}"}` |

That is a worse failure mode than stripping, and a more useful one to understand: the
constraint does not vanish, it **changes category** — from enforced to suggested. Your
Pydantic validators still run, but on *your* machine after the response arrives.

Practical consequence for this module: constrain what you can in the schema (enums for
domain, required fields), and validate the rest in Python, with a retry when it fails.

### Prompt shape

Current models follow the system prompt closely, so the emphasis dial is different from
what older prompt guides recommend:

- **Say it once, plainly.** `CRITICAL: You MUST...` was written for models that
  under-triggered. On current models it over-triggers.
- **Examples are the strongest signal in a prompt.** The model matches their length,
  tone, and structure. One "gold" example freezes that shape; several varied ones teach
  the range.
- **Describe success, not failure.** A long prohibition list can anchor toward the thing
  you're prohibiting.
- **Give the reason.** Constraints with a stated "because" survive edge cases the rule
  didn't anticipate.

---

## Build

### Step 1 — The schema

`app/coach/schema.py`:

```python
"""Data contract for generated practice questions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Domain(str, Enum):
    """The five CCAR-F exam domains, with their blueprint weights."""

    AGENTIC = "agentic_architecture"
    CLAUDE_CODE = "claude_code_config"
    PROMPTING = "prompt_engineering"
    TOOLS_MCP = "tool_design_mcp"
    CONTEXT = "context_reliability"


WEIGHTS: dict[Domain, float] = {
    Domain.AGENTIC: 0.27,
    Domain.CLAUDE_CODE: 0.20,
    Domain.PROMPTING: 0.20,
    Domain.TOOLS_MCP: 0.18,
    Domain.CONTEXT: 0.15,
}


class Choice(BaseModel):
    label: str = Field(description="Single uppercase letter, A through E.")
    text: str = Field(description="The answer option.")


class Question(BaseModel):
    domain: Domain
    stem: str = Field(description="The question. States how many answers to select.")
    choices: list[Choice]
    correct_labels: list[str] = Field(description="Labels of every correct choice.")
    explanation: str = Field(description="Why the answer is right AND why each distractor is wrong.")
    source: str = Field(description="Doc URL or blueprint domain backing this question.")

    # These validators run client-side, after the response arrives. The API does not
    # enforce them: length and count constraints are not part of the supported
    # JSON Schema subset. This is the gap you close in code.

    @field_validator("choices")
    @classmethod
    def four_or_five_choices(cls, v: list[Choice]) -> list[Choice]:
        if not 4 <= len(v) <= 5:
            raise ValueError(f"expected 4-5 choices, got {len(v)}")
        labels = [c.label for c in v]
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate choice labels: {labels}")
        return v

    @model_validator(mode="after")
    def answers_exist_and_are_not_all(self) -> Question:
        labels = {c.label for c in self.choices}
        unknown = set(self.correct_labels) - labels
        if unknown:
            raise ValueError(f"correct_labels reference missing choices: {sorted(unknown)}")
        if not self.correct_labels:
            raise ValueError("a question with no correct answer is not a question")
        if len(self.correct_labels) == len(self.choices):
            raise ValueError("every choice marked correct")
        return self


class QuestionBatch(BaseModel):
    questions: list[Question]
```

### Step 2 — The prompt

`app/coach/prompts.py`:

```python
"""System prompt for the question generator.

Kept in one module so the string is stable byte-for-byte across calls. That matters
in module 05: any change to this text invalidates the prompt cache for everything
after it.
"""

GENERATOR_SYSTEM = """\
You write practice questions for the Claude Certified Architect – Foundations exam.

<what_makes_a_good_question>
Test judgment and mechanism, not recall of version strings. A candidate who
understands *why* a mechanism exists should answer correctly; one who has only
skimmed the docs should not.

Distractors are plausible to someone who half-knows the material. An obviously
wrong option teaches nothing and wastes a slot.

Exactly one defensible answer, unless the stem says "Select two" or "Select three".
If a distractor is arguably correct under some reading, it is a broken question.
</what_makes_a_good_question>

<grounding>
Every question must trace to the supplied source material. Put the doc URL or the
blueprint domain in the `source` field. If you cannot ground a question, do not
write it — a plausible-sounding invention is worse than one fewer question,
because the learner cannot tell the difference.
</grounding>

<explanations>
Explain why the answer is right AND why each distractor is wrong. The explanation
is what the learner actually studies from.
</explanations>
"""


def user_prompt(domain_label: str, n: int, corpus_excerpt: str) -> str:
    return f"""\
<source_material>
{corpus_excerpt}
</source_material>

Write {n} questions on the {domain_label} domain, grounded in the source material above.
"""
```

Note the XML tags. They delimit sections unambiguously, which matters when the corpus
excerpt you interpolate might itself contain markdown headers.

They are not, however, parsed. No XML reader runs over your prompt; the model receives one
flat sequence of tokens and treats `<source_material>` as a boundary because it has been
trained to, not because anything enforces it. That distinction — **structure that is
enforced versus structure that is conventional** — is the testable idea here. Your Pydantic
schema is enforced: the API constrains generation to it. Your tags are a convention.

Which leads to the rule that actually decides your tag name: **a delimiter has to come from
an alphabet the delimited content doesn't use.** Same reason you pick a quote character the
string doesn't contain, or choose a heredoc terminator. Markdown headers fail that test
immediately — the corpus is markdown, so `## Source material` is written in the very syntax
it is trying to bound. XML tags pass it, because prose markdown rarely contains them.

Rarely is not never, and the gap is bigger than it looks. Measured against a corpus holding
the current Claude docs:

```
<source>        collides    <instructions>  collides
<document>      collides    <context>       collides
<documents>     collides    <input>         collides
```

`<instructions>`, `<context>` and `<input>` are the three tag names Anthropic's own
prompting guide recommends — and that guide is *in* the corpus, so following its advice
collides with it. The failure is quiet and total: one `</source>` inside an excerpt closes
your region early, and every byte after it reads as instruction rather than material.

`verify/module_02.py` checks this, so pick a name distinctive enough to survive. And note
what the check cannot do for you: for genuinely untrusted input — a document a user
uploaded rather than a corpus you assembled — the delimiter must be stripped or escaped
from the content before interpolation. `user_prompt` doesn't do that, because everything in
`corpus/` is first-party. Change that assumption and the code has to change with it.

### Step 3 — The generator

`app/coach/generate.py`:

```python
"""Generate schema-valid practice questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import anthropic

from coach.prompts import GENERATOR_SYSTEM, user_prompt
from coach.schema import Domain, QuestionBatch

MODEL = "claude-opus-5"
CORPUS = Path(__file__).resolve().parents[1] / "corpus"

# Which corpus documents belong to which domain. Explicit rather than derived
# from the enum's declaration order — that order matches the blueprint today,
# and nothing would tell you the day it stopped.
DOMAIN_PREFIX: dict[Domain, str] = {
    Domain.AGENTIC: "d1",
    Domain.CLAUDE_CODE: "d2",
    Domain.PROMPTING: "d3",
    Domain.TOOLS_MCP: "d4",
    Domain.CONTEXT: "d5",
}

# Framing material: what the domains are and how the exam weights them. Small,
# and relevant to every request, so it is exempt from the domain filter.
SHARED_DOC = "exam-blueprint.md"


def load_corpus(domain: Domain, limit_chars: int = 20_000) -> str:
    """Sample this domain's documents, giving each of them a share of the budget.

    Both halves earn their keep. Without the prefix filter the model is handed
    some other domain's material and told to ground its questions in it. Without
    the per-document split, truncating one long concatenation lets whichever file
    sorts first consume the whole budget while the rest are never sent at all.
    """
    shared = CORPUS / SHARED_DOC
    docs = sorted(CORPUS.glob(f"{DOMAIN_PREFIX[domain]}-*.md"))
    if not docs:
        # No domain-prefixed documents yet — fall back to whatever else is there.
        docs = sorted(q for q in CORPUS.glob("*.md") if q != shared)
    if not docs and not shared.exists():
        raise FileNotFoundError(f"no corpus documents in {CORPUS}")

    parts = [shared.read_text(encoding="utf-8")] if shared.exists() else []
    budget = max(limit_chars - sum(len(part) for part in parts), 0)
    per_doc = budget // len(docs) if docs else 0
    parts += [d.read_text(encoding="utf-8")[:per_doc] for d in docs]
    return "\n\n---\n\n".join(parts)


def generate(domain: Domain, n: int = 5) -> QuestionBatch:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=GENERATOR_SYSTEM,
        messages=[
            {"role": "user", "content": user_prompt(domain.value, n, load_corpus(domain))}
        ],
        output_format=QuestionBatch,
    )
    batch = response.parsed_output
    if batch is None:
        raise RuntimeError(f"no parsed output; stop_reason={response.stop_reason}")
    return batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, choices=[d.name.lower() for d in Domain])
    parser.add_argument("-n", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    batch = generate(Domain[args.domain.upper()], args.n)
    payload = batch.model_dump(mode="json")

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {len(batch.questions)} questions to {args.out}")
    else:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
```

`load_corpus` is the least glamorous function in this module and the one that decides
whether any of the rest matters. Your prompt has a hole in it — `user_prompt` takes the
material as a parameter — and whatever fills that hole determines the output more than any
wording you choose. A perfect prompt over the wrong documents produces confident,
well-formed, off-topic questions.

Two failures live in the naive version of it, and only the first announces itself.

**Ignore the domain and alphabetical order decides your curriculum.** Concatenate
everything, take the first 20,000 characters, and a corpus of any real size never gets past
its first file. Asking for `prompt_engineering` then sends agentic-architecture docs under
an instruction to write prompt-engineering questions — and your own system prompt says *"if
you cannot ground a question, do not write it."* You have built a request the model cannot
satisfy honestly.

**Filter correctly and the second one is still there.** One domain here is four documents
and 215,000 characters against a 20,000-character budget; truncating their concatenation
reaches 9% of the domain, all of it from whichever file sorts first. The output looks
completely reasonable. It is drawn from a quarter of the sources, and you cannot tell by
reading it. Splitting the budget per document is what makes the sample representative
rather than merely on-topic.

The mapping is spelled out rather than computed. `list(Domain).index(d) + 1` would work
today, because the enum's declaration order happens to match the blueprint's numbering —
and it would break in silence the first time someone reordered the enum. Write the
correspondence down where a reader can check it.

Note `stop_reason` in the error path. `parsed_output` is `None` when the model refused or
hit `max_tokens` — reporting which is the difference between a five-minute fix and an
afternoon.

### Step 4 — Golden fixtures

Your schema is a contract. Test it against known-good and known-bad payloads so you find
out when you break it — without spending a token.

`app/tests/fixtures/valid_question.json`:

```json
{
  "domain": "claude_code_config",
  "stem": "Which settings scope has the LOWEST precedence?",
  "choices": [
    {"label": "A", "text": "Managed policy settings"},
    {"label": "B", "text": "Project settings (.claude/settings.json)"},
    {"label": "C", "text": "User settings (~/.claude/settings.json)"},
    {"label": "D", "text": "Local settings (.claude/settings.local.json)"}
  ],
  "correct_labels": ["C"],
  "explanation": "Precedence runs Managed > CLI args > Local > Project > User. User settings are lowest, which inverts most people's intuition. A is highest, D and B sit between.",
  "source": "https://code.claude.com/docs/en/settings"
}
```

`app/tests/test_schema.py`:

```python
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from coach.schema import Question

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_question_parses():
    payload = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    q = Question.model_validate(payload)
    assert q.correct_labels == ["C"]


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda p: p.update(correct_labels=[]), "no correct answer"),
        (lambda p: p.update(correct_labels=["Z"]), "answer references a missing choice"),
        (lambda p: p.update(correct_labels=["A", "B", "C", "D"]), "every choice correct"),
        (lambda p: p["choices"].pop(), "only three choices"),
        (lambda p: p["choices"].append({"label": "A", "text": "dupe"}), "duplicate label"),
    ],
)
def test_invalid_questions_rejected(mutate, reason):
    payload = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    mutate(payload)
    with pytest.raises(ValidationError):
        Question.model_validate(payload)
```

---

## Checkpoint

```bash
python verify/module_02.py          # schema + prompt checks, no API spend
python verify/module_02.py --live   # adds one real generation call
```

The default run costs nothing. `--live` makes exactly one API call and asserts the
response parses into your schema.

That split is deliberate and worth copying in your own work: **a verification suite you
can't afford to run is a verification suite you won't run.** Keep the fast, free checks
as the default and gate the expensive ones behind a flag.

Then the real thing:

```bash
python -m coach.generate --domain claude_code --n 3
```

You should get three questions as JSON. Read them. If they're bad questions — vague,
two-defensible-answers, testing trivia — that's a prompt problem, and fixing it is the
actual exercise of this module. Iterate on `prompts.py` until the output is worth studying.

---

## Exam drill

**1.** You migrate a JSON-extraction pipeline to `claude-opus-5`. It prefills the
assistant turn with `{`. What happens?

A. It works; prefill is still supported
B. HTTP 400 — prefill is not supported on this model
C. It works but emits a deprecation warning
D. The prefill is silently ignored and normal text is returned

**2.** Which parameter is the current, non-deprecated way to constrain response format?

A. `output_format` at the top level of `messages.create()`
B. `output_config={"format": {...}}`
C. `response_format={"type": "json"}`
D. `stop_sequences=["}"]`

**3.** Your schema sets `"minLength": 20` on a string field. What happens?

A. The API enforces it during generation
B. The API returns 400 for an unsupported keyword
C. The SDK moves it into the field's `description`, and validates it client-side
D. It is passed through and silently ignored by everything

**4.** Which is **required** on every object in a structured-output schema?

A. `"additionalProperties": false` B. `"minProperties": 1`
C. `"$schema"` D. `"strict": true`

**5.** Which are **not** supported in structured-output JSON Schema? *(Select two.)*

A. `enum` B. Recursive schemas C. `anyOf` D. `maximum` E. `$ref`

**6.** `response.parsed_output` is `None`. Which is the most useful next thing to inspect?

A. `response.id` B. `response.stop_reason`
C. `response.model` D. `response.usage.input_tokens`

**7.** A prompt written for an older model says `CRITICAL: You MUST always call the
search tool.` On a current model, the likely effect is:

A. Correct triggering; the emphasis is necessary
B. Over-triggering — the tool fires when it shouldn't
C. No effect; emphasis is ignored
D. A 400 for prohibited prompt language

**8.** You want structured output *and* citations on the same request. Result?

A. Both work B. 400 — they're incompatible
C. Citations are silently dropped D. Structured output is silently dropped

**9.** For strict tool use, which combination is required? *(Select two.)*

A. `strict: true` on the tool definition
B. `strict: true` inside `tool_choice`
C. `additionalProperties: false` plus `required` in the schema
D. `output_config.format` on the request

**10.** A generator produces one excellent example question and you paste it into the
prompt as the gold standard. What is the most likely downside?

A. Increased token cost only
B. The model matches its length, tone, and structure, collapsing output variety
C. The example is ignored unless tagged `<example>`
D. It causes a schema validation failure

<details>
<summary><b>Answer key</b></summary>

**1 — B.** Prefills on the final assistant turn return 400 on Opus 5, Sonnet 5, Fable 5,
and the 4.6/4.7/4.8 family. Assistant messages *elsewhere* in the conversation (few-shot)
are still fine — only the trailing one is a prefill.

**2 — B.** `output_config.format`. The top-level `output_format` parameter is deprecated
API-wide (note: `messages.parse()` still accepts `output_format=` as an SDK convenience —
that's the helper, not the wire parameter).

**3 — C.** String and numeric constraints aren't in the supported subset, but the SDK does
not drop them: it appends each one to that field's `description` (creating one if the
field had none) so the model may still follow it, then your Pydantic validators reject
client-side once the response arrives. D is wrong on the second half — the keyword *is*
passed through, but not ignored by everything.

Verified against `anthropic` 0.122.0; the transform lives in
`anthropic/lib/_parse/_transform.py`. A key pinned to a moving SDK needs a version, so
that is the version this one was checked against. The practical takeaway is unchanged:
`minLength` is a hint, not a guarantee.

**4 — A.** `additionalProperties: false` is required on all objects.

**5 — B and D.** Recursive schemas and numeric constraints. `enum`, `anyOf`, and `$ref`
are all supported.

**6 — B.** `stop_reason` distinguishes a refusal from `max_tokens` truncation — different
problems with different fixes.

**7 — B.** Current models follow the system prompt closely. Emphasis written to overcome
an older model's reluctance now overshoots. The fix is to dial the language back, not to
add guardrails on top.

**8 — B.** Structured outputs and citations are incompatible; the request returns 400.

**9 — A and C.** `strict: true` goes on the tool definition — *not* inside `tool_choice`,
which is B's trap — and the schema needs `additionalProperties: false` plus `required`.

**10 — B.** Examples are the strongest signal in a prompt; the model matches their shape.
A single gold example freezes that shape. Several deliberately varied ones teach the range.

</details>

---

## Further reading

- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)
- [Tool use — strict mode](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

---

**Next:** [Module 03 — Tool Design & MCP Integration](03-tools-and-mcp.md) (18%)
