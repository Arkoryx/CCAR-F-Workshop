"""Corpus search and result tracking. No MCP dependency — pure logic."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
RESULTS = ROOT / ".coach" / "results.jsonl"


class PathOutsideCorpus(ValueError):
    """Raised when a model-supplied path escapes the corpus directory."""


@dataclass(frozen=True)
class Passage:
    source: str
    text: str


def resolve_in_corpus(name: str) -> Path:
    """Resolve a model-supplied filename, confined to the corpus directory.

    Model output is untrusted input. Resolve first, then check containment —
    a substring check on the raw string is defeated by '../' and false-positives
    on names like 'corpus_notes.md'.
    """
    candidate = (CORPUS / name).resolve()
    corpus = CORPUS.resolve()
    if corpus != candidate and corpus not in candidate.parents:
        raise PathOutsideCorpus(f"{name!r} resolves outside the corpus")
    return candidate


def search(query: str, limit: int = 5) -> list[Passage]:
    """Return paragraphs matching every whitespace-separated term."""
    terms = [t.lower() for t in query.split() if t]
    if not terms:
        return []

    hits: list[Passage] = []
    for doc in sorted(CORPUS.glob("*.md")):
        for para in re.split(r"\n\s*\n", doc.read_text(encoding="utf-8")):
            blob = para.lower()
            if all(term in blob for term in terms):
                hits.append(Passage(source=doc.name, text=para.strip()))
                if len(hits) >= limit:
                    return hits
    return hits


def objectives(domain: str) -> str:
    """Return the blueprint section for a domain."""
    blueprint = resolve_in_corpus("exam-blueprint.md").read_text(encoding="utf-8")
    needle = domain.replace("_", " ").lower()
    for section in blueprint.split("\n### "):
        if needle in section.lower():
            return section.strip()
    return f"No blueprint section matched {domain!r}."


def record(domain: str, correct: bool) -> dict:
    """Append one graded answer to the result log."""
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "domain": domain,
        "correct": bool(correct),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def weakest_domains(minimum: int = 1) -> list[tuple[str, float]]:
    """Domains sorted worst-first by accuracy. Feeds module 06's gap analysis."""
    if not RESULTS.exists():
        return []
    tally: dict[str, list[int]] = {}
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tally.setdefault(row["domain"], []).append(1 if row["correct"] else 0)
    scored = [
        (domain, sum(vals) / len(vals)) for domain, vals in tally.items() if len(vals) >= minimum
    ]
    return sorted(scored, key=lambda pair: pair[1])
