"""Cost accounting. Rates are per million tokens."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / ".coach" / "ledger.jsonl"

# Claude Opus 5, USD per million tokens.
INPUT_RATE = 5.00
OUTPUT_RATE = 25.00
CACHE_WRITE_MULTIPLIER = 1.25   # 5-minute TTL; 1-hour is 2.0
CACHE_READ_MULTIPLIER = 0.10


@dataclass(frozen=True)
class Cost:
    uncached_input_usd: float
    cache_write_usd: float
    cache_read_usd: float
    output_usd: float

    @property
    def total_usd(self) -> float:
        return round(
            self.uncached_input_usd + self.cache_write_usd + self.cache_read_usd + self.output_usd,
            6,
        )


def price(usage) -> Cost:
    per_input_token = INPUT_RATE / 1_000_000
    per_output_token = OUTPUT_RATE / 1_000_000
    return Cost(
        uncached_input_usd=usage.uncached_input * per_input_token,
        cache_write_usd=usage.cache_write * per_input_token * CACHE_WRITE_MULTIPLIER,
        cache_read_usd=usage.cache_read * per_input_token * CACHE_READ_MULTIPLIER,
        output_usd=usage.output * per_output_token,
    )


def savings_vs_uncached(usage) -> float:
    """What the cached reads saved, versus paying full input price for them."""
    per_input_token = INPUT_RATE / 1_000_000
    full = usage.cache_read * per_input_token
    paid = usage.cache_read * per_input_token * CACHE_READ_MULTIPLIER
    return round(full - paid, 6)


def append(label: str, usage, cost: Cost) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"label": label, "usage": asdict(usage), "cost": asdict(cost), "total": cost.total_usd}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def running_total() -> float:
    if not LEDGER.exists():
        return 0.0
    return round(
        sum(json.loads(line)["total"] for line in LEDGER.read_text().splitlines() if line.strip()),
        6,
    )
