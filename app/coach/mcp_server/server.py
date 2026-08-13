"""MCP server exposing the study corpus.

Thin adapter. All logic lives in coach.corpus_index so it can be tested without
standing up a server.
"""

from __future__ import annotations

from mcp.server import FastMCP

from coach import corpus_index

mcp = FastMCP("coach-corpus")


@mcp.tool()
async def search_corpus(query: str, limit: int = 5) -> str:
    """Search the study corpus for passages matching a query.

    Call this whenever you need to ground a claim in source material, before
    writing any question. Returns matching paragraphs with their source filename.
    Does not return whole documents — if a passage looks truncated, call again
    with a narrower query.

    Args:
        query: Space-separated search terms. All terms must appear in a passage.
        limit: Maximum number of passages to return.
    """
    hits = corpus_index.search(query, limit)
    if not hits:
        return f"No passages matched {query!r}. Try fewer or broader terms."
    return "\n\n---\n\n".join(f"[{h.source}]\n{h.text}" for h in hits)


@mcp.tool()
async def get_objectives(domain: str) -> str:
    """Return the exam blueprint section for one domain, including its weight.

    Call this before generating questions for a domain, so the questions match
    what the blueprint actually says the domain covers.

    Args:
        domain: A domain key, e.g. agentic_architecture or claude_code_config.
    """
    return corpus_index.objectives(domain)


@mcp.tool()
async def record_result(domain: str, correct: bool) -> str:
    """Record whether the learner answered a question correctly.

    Call this once per graded answer. The log drives weak-domain analysis, so a
    missing call silently skews future practice toward the wrong topics.

    Args:
        domain: The domain the question belonged to.
        correct: True if the learner answered correctly.
    """
    entry = corpus_index.record(domain, correct)
    return f"Recorded: {entry['domain']} correct={entry['correct']}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
