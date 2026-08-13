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
