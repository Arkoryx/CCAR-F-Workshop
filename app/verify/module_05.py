"""Verify Module 05 — Context Management & Reliability.

    python verify/module_05.py           # cache hygiene + ledger math, free
    python verify/module_05.py --live    # two real calls; asserts a cache hit

The headline offline check is prefix byte-stability. That is the prefix-match
invariant written as an assertion: if anyone later interpolates a timestamp into
the cached region, this fails loudly instead of quietly doubling the bill.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

sys.path.insert(0, str(PROJECT))

LIVE = "--live" in sys.argv

c = Checks("05")

for rel in ("coach/cached_client.py", "coach/ledger.py", "coach/session.py"):
    c.check(f"{rel} exists", file_exists(rel))


# --- The prefix invariant -----------------------------------------------------
def prefix_is_byte_stable() -> tuple[bool, str]:
    """Two independent builds of the cached region must be byte-identical."""
    from coach.cached_client import build_system

    corpus = "stable corpus text"
    first = build_system(corpus)
    second = build_system(corpus)

    def cached_region(blocks: list[dict]) -> str:
        out = []
        for block in blocks:
            out.append(block["text"])
            if "cache_control" in block:
                break  # everything after the breakpoint is not cached
        return "".join(out)

    a, b = cached_region(first), cached_region(second)
    if a != b:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return False, f"prefix diverges at char {i}: {a[max(0,i-40):i+40]!r}"
        return False, f"prefix length differs: {len(a)} vs {len(b)}"
    return True, ""


c.check("cached prefix is byte-identical across builds", prefix_is_byte_stable)


def breakpoint_is_on_the_last_stable_block() -> tuple[bool, str]:
    """A breakpoint on a volatile block writes a new entry every request."""
    from coach.cached_client import build_system

    blocks = build_system("corpus text")
    marked = [i for i, b in enumerate(blocks) if "cache_control" in b]
    if not marked:
        return False, "no cache_control breakpoint at all"
    if len(marked) > 4:
        return False, f"{len(marked)} breakpoints; the API allows at most 4"
    return marked[-1] == len(blocks) - 1, (
        f"breakpoint at block {marked[-1]} of {len(blocks)-1} — content after it is uncached"
    )


c.check("breakpoint sits on the last stable block", breakpoint_is_on_the_last_stable_block)


def no_volatile_content_in_cached_region() -> tuple[bool, str]:
    source = (PROJECT / "coach" / "cached_client.py").read_text(encoding="utf-8")
    head = source.split("def ask", 1)[0]
    found = [p for p in ("datetime.now", "time.time", "uuid4", "random.") if p in head]
    return not found, f"cache invalidators in the prefix-building path: {found}"


c.check("no cache invalidators in the prefix path", no_volatile_content_in_cached_region)


# --- Usage accounting ---------------------------------------------------------
def total_input_sums_all_three() -> tuple[bool, str]:
    """input_tokens is the uncached remainder, not the whole prompt."""
    from coach.cached_client import Usage

    u = Usage(uncached_input=100, cache_write=0, cache_read=900, output=50)
    return u.total_input == 1000, f"total_input={u.total_input}, expected 1000"


c.check("total input sums uncached + write + read", total_input_sums_all_three)


def cache_hit_detection() -> tuple[bool, str]:
    from coach.cached_client import Usage

    hit = Usage(uncached_input=10, cache_write=0, cache_read=500, output=5)
    miss = Usage(uncached_input=510, cache_write=500, cache_read=0, output=5)
    return hit.cache_hit and not miss.cache_hit, "cache_hit misreports"


c.check("cache hits are detected from read tokens", cache_hit_detection)


# --- Ledger math --------------------------------------------------------------
def read_is_cheaper_than_uncached() -> tuple[bool, str]:
    """A cached read must price below the same tokens uncached, or the model is wrong."""
    from coach.cached_client import Usage
    from coach.ledger import price

    cached = price(Usage(uncached_input=0, cache_write=0, cache_read=1_000_000, output=0))
    plain = price(Usage(uncached_input=1_000_000, cache_write=0, cache_read=0, output=0))
    return cached.total_usd < plain.total_usd, (
        f"cached read ${cached.total_usd} is not cheaper than uncached ${plain.total_usd}"
    )


c.check("cached reads price below uncached input", read_is_cheaper_than_uncached)


def write_is_dearer_than_uncached() -> tuple[bool, str]:
    from coach.cached_client import Usage
    from coach.ledger import price

    write = price(Usage(uncached_input=0, cache_write=1_000_000, cache_read=0, output=0))
    plain = price(Usage(uncached_input=1_000_000, cache_write=0, cache_read=0, output=0))
    return write.total_usd > plain.total_usd, (
        "cache writes should cost MORE than plain input (1.25x at 5m TTL) — "
        "that premium is why caching needs repeat reads to pay off"
    )


c.check("cache writes carry a premium over plain input", write_is_dearer_than_uncached)


def savings_are_reported() -> tuple[bool, str]:
    from coach.cached_client import Usage
    from coach.ledger import savings_vs_uncached

    saved = savings_vs_uncached(Usage(uncached_input=0, cache_write=0, cache_read=1_000_000, output=0))
    return saved > 0, f"expected positive savings, got {saved}"


c.check("savings versus uncached are computed", savings_are_reported)


# --- Session round trip -------------------------------------------------------
def session_round_trips_content_blocks() -> tuple[bool, str]:
    """Sessions must preserve full content blocks, not flattened text.

    Compaction state lives in those blocks; flattening loses it.
    """
    from coach import session

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    session.save("verify-roundtrip", messages)
    restored = session.load("verify-roundtrip")
    if restored != messages:
        return False, "restored session does not match what was saved"
    block = restored[1]["content"]
    return isinstance(block, list), "assistant content was flattened to a string"


c.check("sessions round-trip full content blocks", session_round_trips_content_blocks)


def missing_session_returns_empty() -> tuple[bool, str]:
    from coach import session

    return session.load("no-such-session-id") == [], "missing session did not return []"


c.check("loading an unknown session returns empty, not an error", missing_session_returns_empty)


# --- Live (opt-in) ------------------------------------------------------------
def live_cache_hit() -> tuple[bool, str]:
    """The only way to prove caching works. Everything else is inference."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set"

    import anthropic

    from coach.cached_client import ask

    corpus = (PROJECT / "corpus" / "exam-blueprint.md").read_text(encoding="utf-8")
    corpus = (corpus + "\n") * 6  # clear the minimum cacheable prefix comfortably

    client = anthropic.Anthropic()
    _, first = ask(corpus, "Reply with the single word: ready.", client=client)
    _, second = ask(corpus, "Reply with the single word: ready.", client=client)

    if not second.cache_hit:
        return False, (
            f"second call read 0 cached tokens "
            f"(first: write={first.cache_write}, read={first.cache_read}). "
            "Either the prefix is below the model minimum, or something in it varies."
        )
    return True, ""


if LIVE:
    c.check("live: the second identical request hits the cache", live_cache_hit)
else:
    print("\n  (skipping live cache check — pass --live to include it)")

raise SystemExit(c.report())
