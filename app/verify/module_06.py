"""Verify Module 06 — Mock Exam & Gap Analysis.

    python verify/module_06.py

Entirely offline and fully deterministic: the sampler is seeded, so the same seed
must produce the same exam form every run. If it doesn't, the mock isn't
reproducible and comparing two attempts means nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

sys.path.insert(0, str(PROJECT))

c = Checks("06")

for rel in ("coach/exam.py", "coach/run_exam.py"):
    c.check(f"{rel} exists", file_exists(rel))


def fake_pool(per_domain: int = 25):
    """A synthetic pool, so verification never depends on generated content."""
    from coach.schema import Choice, Domain, Question

    pool = []
    for domain in Domain:
        for i in range(per_domain):
            pool.append(
                Question(
                    domain=domain,
                    stem=f"{domain.value} question {i}. Select one.",
                    choices=[Choice(label=lbl, text=f"opt {lbl}") for lbl in "ABCD"],
                    correct_labels=["A"],
                    explanation="A is correct because it is. B, C and D are not.",
                    source="synthetic",
                )
            )
    return pool


# --- Allocation ---------------------------------------------------------------
def allocation_sums_exactly() -> tuple[bool, str]:
    """Naive rounding loses or gains a question. Largest-remainder must not."""
    from coach.exam import allocate

    broken = []
    for total in (60, 30, 45, 7, 100):
        counts = allocate(total)
        if sum(counts.values()) != total:
            broken.append(f"total={total} allocated {sum(counts.values())}")
    return not broken, "; ".join(broken)


c.check("allocation always sums to the requested total", allocation_sums_exactly)


def allocation_matches_blueprint() -> tuple[bool, str]:
    from coach.exam import allocate
    from coach.schema import Domain

    counts = allocate(60)
    expected = {
        Domain.AGENTIC: 16,
        Domain.CLAUDE_CODE: 12,
        Domain.PROMPTING: 12,
        Domain.TOOLS_MCP: 11,
        Domain.CONTEXT: 9,
    }
    wrong = {d.value: (counts[d], want) for d, want in expected.items() if counts[d] != want}
    return not wrong, f"got (actual, expected): {wrong}"


c.check("60-question form matches blueprint weights", allocation_matches_blueprint)


def heaviest_domain_gets_most() -> tuple[bool, str]:
    """Guards against a uniform sampler that quietly ignores the weights."""
    from coach.exam import allocate
    from coach.schema import Domain

    counts = allocate(60)
    if len(set(counts.values())) == 1:
        return False, "every domain got the same count — weights are being ignored"
    return counts[Domain.AGENTIC] > counts[Domain.CONTEXT], (
        "the 27% domain should get more questions than the 15% domain"
    )


c.check("weighting is actually applied", heaviest_domain_gets_most)


# --- Assembly -----------------------------------------------------------------
def form_is_reproducible() -> tuple[bool, str]:
    from coach.exam import assemble

    pool = fake_pool()
    a = [q.stem for q in assemble(pool, seed=42)]
    b = [q.stem for q in assemble(pool, seed=42)]
    return a == b, "same seed produced different forms — attempts aren't comparable"


c.check("the same seed produces the same form", form_is_reproducible)


def different_seeds_differ() -> tuple[bool, str]:
    from coach.exam import assemble

    pool = fake_pool()
    a = [q.stem for q in assemble(pool, seed=1)]
    b = [q.stem for q in assemble(pool, seed=2)]
    return a != b, "different seeds produced identical forms — sampling is not random"


c.check("different seeds produce different forms", different_seeds_differ)


def form_is_the_right_size() -> tuple[bool, str]:
    from coach.exam import assemble

    form = assemble(fake_pool(), total=60, seed=7)
    return len(form) == 60, f"form has {len(form)} questions, expected 60"


c.check("assembled form has exactly 60 questions", form_is_the_right_size)


def thin_pool_fails_loudly() -> tuple[bool, str]:
    """Silently shipping a short exam is worse than refusing to build one."""
    from coach.exam import assemble

    try:
        assemble(fake_pool(per_domain=2), total=60, seed=1)
    except ValueError:
        return True, ""
    return False, "an under-supplied pool produced a form instead of raising"


c.check("an under-supplied pool raises rather than short-changing the form", thin_pool_fails_loudly)


# --- Scoring ------------------------------------------------------------------
def scale_endpoints() -> tuple[bool, str]:
    from coach.exam import scale

    problems = []
    if scale(0, 60) != 100:
        problems.append(f"0 correct -> {scale(0, 60)}, expected 100")
    if scale(60, 60) != 1000:
        problems.append(f"60 correct -> {scale(60, 60)}, expected 1000")
    if scale(5, 0) != 100:
        problems.append("zero-length exam should floor at 100, not divide by zero")
    return not problems, "; ".join(problems)


c.check("scaled score spans 100-1000 and survives edge cases", scale_endpoints)


def pass_mark_behaves() -> tuple[bool, str]:
    from coach.exam import PASS_MARK, passed, scale

    if passed(PASS_MARK - 1) or not passed(PASS_MARK):
        return False, "the 720 boundary is off by one"

    threshold = next(n for n in range(61) if passed(scale(n, 60)))
    return 41 <= threshold <= 43, (
        f"720 needs {threshold}/60 under this scaling; expected ~42. "
        "Check the linear approximation."
    )


c.check("720 is the pass boundary and lands near 42/60", pass_mark_behaves)


# --- Gap analysis -------------------------------------------------------------
def gaps_rank_by_points_not_accuracy() -> tuple[bool, str]:
    """The whole point: a weak heavy domain outranks an equally weak light one."""
    from coach.exam import analyze
    from coach.schema import Domain

    results = []
    # Both domains at 50% accuracy; agentic is worth 27%, context 15%.
    for _ in range(8):
        results.append((Domain.AGENTIC, True))
        results.append((Domain.AGENTIC, False))
        results.append((Domain.CONTEXT, True))
        results.append((Domain.CONTEXT, False))

    ranked = analyze(results)
    if ranked[0].domain is not Domain.AGENTIC:
        return False, (
            f"ranked {ranked[0].domain.value} first; at equal accuracy the heavier "
            "domain must rank first"
        )
    return True, ""


c.check("gap analysis ranks by recoverable points", gaps_rank_by_points_not_accuracy)


def perfect_domain_has_no_gap() -> tuple[bool, str]:
    from coach.exam import analyze
    from coach.schema import Domain

    ranked = analyze([(Domain.AGENTIC, True)] * 10)
    return ranked[0].points_available == 0, (
        f"a 100% domain still reports {ranked[0].points_available} points available"
    )


c.check("a fully correct domain reports no recoverable points", perfect_domain_has_no_gap)

raise SystemExit(c.report())
