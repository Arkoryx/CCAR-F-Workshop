"""Anthropic client wrapper with cache breakpoints in the right place.

The corpus is large and stable; the question varies. So: corpus in the system
block with a cache breakpoint, question in the user turn after it.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from coach.prompts import GENERATOR_SYSTEM

MODEL = "claude-opus-5"


@dataclass
class Usage:
    """One request's token accounting."""

    uncached_input: int
    cache_write: int
    cache_read: int
    output: int

    @property
    def total_input(self) -> int:
        """input_tokens is only the uncached remainder — sum all three."""
        return self.uncached_input + self.cache_write + self.cache_read

    @property
    def cache_hit(self) -> bool:
        return self.cache_read > 0


def build_system(corpus: str) -> list[dict]:
    """System blocks with the cache breakpoint on the LAST stable block.

    Order matters: the instructions and corpus never change within a run, so both
    sit before the breakpoint. Anything volatile must come after it, in the user
    turn — never here.
    """
    return [
        {"type": "text", "text": GENERATOR_SYSTEM},
        {
            "type": "text",
            "text": f"<source_material>\n{corpus}\n</source_material>",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def read_usage(response) -> Usage:
    u = response.usage
    return Usage(
        uncached_input=u.input_tokens,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        output=u.output_tokens,
    )


def ask(corpus: str, question: str, client: anthropic.Anthropic | None = None):
    client = client or anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=build_system(corpus),
        messages=[{"role": "user", "content": question}],
    )
    return response, read_usage(response)
