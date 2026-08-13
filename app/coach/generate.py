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


def load_corpus(limit_chars: int = 20_000) -> str:
    docs = sorted(CORPUS.glob("*.md"))
    if not docs:
        raise FileNotFoundError(f"no corpus documents in {CORPUS}")
    joined = "\n\n---\n\n".join(d.read_text(encoding="utf-8") for d in docs)
    return joined[:limit_chars]


def generate(domain: Domain, n: int = 5) -> QuestionBatch:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=GENERATOR_SYSTEM,
        messages=[{"role": "user", "content": user_prompt(domain.value, n, load_corpus())}],
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
