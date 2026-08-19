"""Verify Module 03 — Tool Design & MCP Integration.

    python verify/module_03.py

No API spend and no server process. Because the logic lives in coach.corpus_index
rather than inside the decorated tool functions, it can be exercised directly —
which is the practical payoff of keeping the MCP layer thin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PROJECT, Checks, file_exists  # noqa: E402

sys.path.insert(0, str(PROJECT))

c = Checks("03")

for rel in (
    "coach/corpus_index.py",
    "coach/mcp_server/__init__.py",
    "coach/mcp_server/server.py",
    ".mcp.json",
):
    c.check(f"{rel} exists", file_exists(rel))


# --- .mcp.json ----------------------------------------------------------------
def mcp_json_registers_server() -> tuple[bool, str]:
    cfg = json.loads((PROJECT / ".mcp.json").read_text(encoding="utf-8"))
    servers = cfg.get("mcpServers", {})
    if "coach-corpus" not in servers:
        return False, f"no 'coach-corpus' entry; found {list(servers)}"
    entry = servers["coach-corpus"]
    return bool(entry.get("command")), "server entry has no 'command'"


c.check(".mcp.json registers coach-corpus", mcp_json_registers_server)


# --- Path safety --------------------------------------------------------------
def traversal_is_rejected() -> tuple[bool, str]:
    """The security property, tested directly rather than hoped for."""
    from coach.corpus_index import PathOutsideCorpus, resolve_in_corpus

    escapes = ["../secrets.md", "../../.env", "sub/../../outside.md"]
    leaked = []
    for attempt in escapes:
        try:
            resolve_in_corpus(attempt)
        except PathOutsideCorpus:
            continue
        except FileNotFoundError:
            continue  # resolution rejected it before touching disk is also fine
        leaked.append(attempt)
    return not leaked, f"these escaped the corpus: {leaked}"


c.check("traversal paths are rejected", traversal_is_rejected)


def legitimate_path_is_allowed() -> tuple[bool, str]:
    """Guards against a check that rejects everything and looks secure."""
    from coach.corpus_index import resolve_in_corpus

    resolved = resolve_in_corpus("exam-blueprint.md")
    return resolved.exists(), f"{resolved} should resolve and exist"


c.check("a legitimate corpus path is allowed", legitimate_path_is_allowed)


# --- Search and objectives ----------------------------------------------------
def search_finds_and_misses_correctly() -> tuple[bool, str]:
    from coach.corpus_index import search

    hits = search("domain")
    if not hits:
        return False, "search('domain') found nothing in the blueprint"
    if not all(h.source for h in hits):
        return False, "a passage came back without its source filename"

    nonsense = search("zzzz-no-such-term-anywhere")
    return not nonsense, f"search matched nonsense terms: {len(nonsense)} hits"


c.check("search finds real terms and rejects nonsense", search_finds_and_misses_correctly)


def search_respects_limit() -> tuple[bool, str]:
    from coach.corpus_index import search

    hits = search("the", limit=2)
    return len(hits) <= 2, f"limit=2 returned {len(hits)} passages"


c.check("search respects its limit", search_respects_limit)


def objectives_returns_a_section() -> tuple[bool, str]:
    from coach.corpus_index import objectives

    text = objectives("agentic_architecture")
    return "27" in text, "the agentic domain section should mention its 27% weight"


c.check("get_objectives returns the right blueprint section", objectives_returns_a_section)


# --- Result recording ---------------------------------------------------------
def recording_round_trips() -> tuple[bool, str]:
    from coach.corpus_index import record, weakest_domains

    record("prompt_engineering", correct=False)
    record("prompt_engineering", correct=False)
    record("claude_code_config", correct=True)

    ranked = weakest_domains()
    if not ranked:
        return False, "no domains scored after recording"
    worst = ranked[0][0]
    return (
        worst == "prompt_engineering",
        f"weakest domain should be prompt_engineering, got {worst}",
    )


c.check("results record and rank weakest-first", recording_round_trips)


# --- Tool descriptions --------------------------------------------------------
def descriptions_are_substantive() -> tuple[bool, str]:
    """Under-description is the most common tool-design failure.

    Checked against the source rather than the registered schema so this works
    regardless of how the SDK version stores tool metadata.
    """
    source = (PROJECT / "coach" / "mcp_server" / "server.py").read_text(encoding="utf-8")
    thin = []
    for name in ("search_corpus", "get_objectives", "record_result"):
        after = source.split(f"async def {name}", 1)[-1]
        doc = after.split('"""', 2)
        body = doc[1] if len(doc) > 2 else ""
        if len(body) < 200 or "Args:" not in body:
            thin.append(name)
    return not thin, f"these tool docstrings are too thin or lack Args: {thin}"


c.check("tool descriptions are substantive", descriptions_are_substantive)


def descriptions_say_when_to_call() -> tuple[bool, str]:
    source = (PROJECT / "coach" / "mcp_server" / "server.py").read_text(encoding="utf-8").lower()
    return "call this" in source, "no docstring says when to call the tool"


c.check("descriptions are prescriptive about when to call", descriptions_say_when_to_call)

raise SystemExit(c.report())
