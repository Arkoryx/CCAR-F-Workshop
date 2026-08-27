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
