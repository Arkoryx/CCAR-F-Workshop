# Module 06 — Mock Exam & Gap Analysis

**Capstone.** No new domain — this is where the Coach you built turns around and tests you.

Time: 2 hours to build, 2 hours to sit the mock.

---

## What you're building

An exam runner: draw 60 questions weighted to the blueprint, run a 120-minute timed
session, score against the 720 bar, and produce a gap analysis from your per-domain
results.

Everything before this module produced parts. This one assembles them.

---

## Concept brief

### Weighted sampling, not uniform

A mock that draws evenly across five domains misrepresents the exam. Agentic Architecture
is 27% and Context Management is 15% — nearly double. Draw proportionally or you'll
practice the wrong things.

60 questions at blueprint weights:

| Domain | Weight | Questions |
|---|---:|---:|
| Agentic Architecture & Orchestration | 27% | 16 |
| Claude Code Configuration & Workflows | 20% | 12 |
| Prompt Engineering & Structured Output | 20% | 12 |
| Tool Design & MCP Integration | 18% | 11 |
| Context Management & Reliability | 15% | 9 |
| | | **60** |

Those round to exactly 60, which is convenient and won't be true for every count — the
sampler handles the remainder explicitly rather than hoping.

### Scoring — and an honest caveat

The real exam reports a scaled score from 100 to 1000 with 720 to pass. **It does not
publish its scaling function.** Real certification exams use psychometric scaling where
item difficulty affects the conversion, so a raw percentage does not map linearly to a
scaled score.

This module uses a linear approximation:

```
scaled = 100 + (correct / total) * 900
```

Under which 720 requires about **69%** — roughly 42 of 60. Treat that as a *practice
target*, not a prediction. Aim comfortably above it, because the real conversion could be
harsher on a hard form.

That caveat is worth internalizing: a number your own tool produced is not evidence about
someone else's exam.

### Gap analysis is the actual output

The score is the least interesting result. What you want is: which domains am I weak in,
weighted by how much they're worth?

A 50% score in Agentic Architecture costs you ~8 questions. The same 50% in Context
Management costs ~4.5. **Rank remediation by expected points recovered, not by accuracy.**

---

## Build

`app/coach/exam.py`:

```python
"""Mock exam assembly, scoring, and gap analysis."""

from __future__ import annotations

import random
from dataclasses import dataclass

from coach.schema import WEIGHTS, Domain, Question

PASS_MARK = 720
SCALE_MIN = 100
SCALE_MAX = 1000


def allocate(total: int = 60, weights: dict[Domain, float] | None = None) -> dict[Domain, int]:
    """Split `total` questions across domains by blueprint weight.

    Largest-remainder method: floor everything, then hand out what's left to the
    largest fractional parts. Guarantees the counts sum to `total` exactly —
    naive rounding does not.
    """
    weights = weights or WEIGHTS
    exact = {d: total * w for d, w in weights.items()}
    counts = {d: int(v) for d, v in exact.items()}

    shortfall = total - sum(counts.values())
    by_remainder = sorted(exact, key=lambda d: exact[d] - counts[d], reverse=True)
    for domain in by_remainder[:shortfall]:
        counts[domain] += 1
    return counts


def assemble(
    pool: list[Question], total: int = 60, seed: int | None = None
) -> list[Question]:
    """Draw a weighted exam form from a question pool."""
    rng = random.Random(seed)
    by_domain: dict[Domain, list[Question]] = {}
    for q in pool:
        by_domain.setdefault(q.domain, []).append(q)

    form: list[Question] = []
    for domain, wanted in allocate(total).items():
        available = by_domain.get(domain, [])
        if len(available) < wanted:
            raise ValueError(
                f"{domain.value}: need {wanted} questions, pool has {len(available)}"
            )
        form.extend(rng.sample(available, wanted))

    rng.shuffle(form)
    return form


def scale(correct: int, total: int) -> int:
    """Linear approximation of the 100-1000 scaled score.

    The real exam's scaling function is not published and is not linear. This is a
    practice target, not a prediction.
    """
    if total <= 0:
        return SCALE_MIN
    fraction = max(0.0, min(1.0, correct / total))
    return round(SCALE_MIN + fraction * (SCALE_MAX - SCALE_MIN))


def passed(scaled_score: int) -> bool:
    return scaled_score >= PASS_MARK


@dataclass(frozen=True)
class DomainGap:
    domain: Domain
    accuracy: float
    weight: float
    points_available: float  # scaled points recoverable by fixing this domain

    @property
    def summary(self) -> str:
        return (
            f"{self.domain.value}: {self.accuracy:.0%} accurate, "
            f"{self.weight:.0%} of exam, ~{self.points_available:.0f} points on the table"
        )


def analyze(results: list[tuple[Domain, bool]]) -> list[DomainGap]:
    """Rank domains by recoverable points, worst first.

    Accuracy alone is the wrong ranking: a weak 27% domain costs far more than an
    equally weak 15% domain.
    """
    tally: dict[Domain, list[bool]] = {}
    for domain, correct in results:
        tally.setdefault(domain, []).append(correct)

    gaps = []
    for domain, outcomes in tally.items():
        accuracy = sum(outcomes) / len(outcomes)
        weight = WEIGHTS[domain]
        gaps.append(
            DomainGap(
                domain=domain,
                accuracy=accuracy,
                weight=weight,
                points_available=(1 - accuracy) * weight * (SCALE_MAX - SCALE_MIN),
            )
        )
    return sorted(gaps, key=lambda g: g.points_available, reverse=True)
```

### The runner

`app/coach/run_exam.py` — a timed CLI that presents each question, collects answers,
records results through module 03's `record()`, and prints the analysis:

```python
"""Sit a timed mock exam."""

from __future__ import annotations

import json
import time
from pathlib import Path

from coach import corpus_index
from coach.exam import analyze, assemble, passed, scale
from coach.schema import Question

TIME_LIMIT_SECONDS = 120 * 60


def load_pool(path: Path) -> list[Question]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["questions"] if isinstance(payload, dict) else payload
    return [Question.model_validate(r) for r in rows]


def sit(pool_path: Path, total: int = 60, seed: int | None = None) -> None:
    form = assemble(load_pool(pool_path), total=total, seed=seed)
    started = time.monotonic()
    results = []

    for i, q in enumerate(form, 1):
        remaining = TIME_LIMIT_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            print("\nTime expired.")
            break

        print(f"\n[{i}/{len(form)}]  {remaining/60:.0f} min left\n")
        print(q.stem)
        for choice in q.choices:
            print(f"  {choice.label}. {choice.text}")

        answer = input("\nAnswer (comma-separated for multi-select): ").strip().upper()
        given = {a.strip() for a in answer.split(",") if a.strip()}
        correct = given == set(q.correct_labels)

        results.append((q.domain, correct))
        corpus_index.record(q.domain.value, correct)

    n_correct = sum(1 for _, ok in results if ok)
    score = scale(n_correct, len(results))

    print(f"\n{'='*60}")
    print(f"Raw:    {n_correct}/{len(results)}")
    print(f"Scaled: {score}  (pass mark 720)")
    print(f"Result: {'PASS' if passed(score) else 'FAIL'}")
    print("\nApproximate scaling — the real exam's function is not published.\n")

    print("Where your points are:")
    for gap in analyze(results):
        print(f"  {gap.summary}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=Path("generated/pool.json"))
    parser.add_argument("--total", type=int, default=60)
    parser.add_argument("--seed", type=int, default=None)
    sit(**vars(parser.parse_args()))
```

---

## Checkpoint

```bash
python verify/module_06.py
```

Then build a pool and sit the exam. You need at least 16 questions in the agentic domain,
so generate generously:

```bash
python -m coach.agent --domain agentic_architecture -n 20 --out generated/agentic.json
python -m coach.agent --domain claude_code_config  -n 15 --out generated/claude_code.json
# ...and so on for the remaining three domains
```

Merge them into `generated/pool.json`, then:

```bash
python -m coach.run_exam --pool generated/pool.json --seed 1
```

Two hours, no notes. Then read the gap analysis and go back to the module for whichever
domain is costing you the most points.

---

## What "done" looks like

You've finished this workshop when:

- All six verifiers pass, including the `--live` variants
- You've sat at least two mock forms and scored above 720 on both
- The gap analysis shows no domain below ~70%

The second mock matters more than the first. Scoring well on questions your own generator
wrote, from a corpus you assembled, is a weaker signal than you'd like — you and the
generator share blind spots. If you can, supplement with a third-party question bank and
treat a disagreement between two sources as a flag to go read the actual docs.

That's the same lesson as module 01's hook, one layer up: **don't trust a check that
shares an author with the thing it checks.**

---

## Further reading

- [`references/exam-blueprint.md`](../references/exam-blueprint.md) — the domains and the source caveat
- [Pearson VUE — Anthropic certifications](https://www.pearsonvue.com/us/en/anthropic.html) — booking
- [Anthropic Academy](https://anthropic.academy/) — the official prep path

---

**Back to:** [README](../README.md)
