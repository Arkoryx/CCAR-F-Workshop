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
