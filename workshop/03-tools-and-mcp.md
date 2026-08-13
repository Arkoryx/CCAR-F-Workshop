# Module 03 — Tool Design & MCP Integration

**Domain 4 · 18% of the exam · ~11 of 60 questions**

Task statements covered: designing effective tool schemas; implementing MCP servers and
clients; integrating external services into Claude-powered applications.

Time: 2–4 hours.

---

## What you're building

An MCP server over your study corpus, exposing three tools: `search_corpus`,
`get_objectives`, and `record_result`. One server, **two consumers** — Claude Code loads
it via `.mcp.json`, and module 04's agent loads it via the Agent SDK. Writing it once and
using it twice is the whole argument for MCP.

---

## Concept brief

### MCP servers expose three kinds of thing

| Capability | What it is | Who initiates |
|---|---|---|
| **Tools** | Functions the model can call | The model |
| **Resources** | File-like data a client can read | The client/app |
| **Prompts** | Reusable templates | The user |

Most servers are mostly tools. The distinction matters on the exam: a resource is *pulled
by the application*, a tool is *called by the model*. If you want the model to decide when
to fetch something, it's a tool.

### The Python server

The current SDK generates the tool schema from your **type hints and docstring**:

```python
from mcp.server import MCPServer

mcp = MCPServer("coach-corpus")

@mcp.tool()
async def search_corpus(query: str, limit: int = 5) -> str:
    """Search the study corpus for passages matching a query.

    Args:
        query: Search terms.
        limit: Maximum passages to return.
    """
    ...

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

That's the entire shape. `httpx2` ships as a dependency of `mcp`, so it's already there
if you need HTTP.

> **Note the import.** It's `from mcp.server import MCPServer`. Earlier material —
> including a lot of blog posts and, frankly, a lot of model output — uses
> `from mcp.server.fastmcp import FastMCP`. Check the import against current docs rather
> than trusting recall, yours or an assistant's.

### Tool descriptions are the highest-leverage thing you write

Detailed descriptions are the single biggest factor in tool performance, and the most
common failure is **under**-description, not over-description. Three or four sentences is
a floor, not a ceiling.

Be **prescriptive about when to call it**, not just what it does. Current models reach for
tools more conservatively than earlier ones, so a description that says only what a tool
does under-triggers. Compare:

> ❌ "Searches the corpus."
> ✅ "Search the study corpus for passages matching a query. Call this whenever you need
> to ground a claim in source material, before writing any question. Returns passages
> with their source file. Does not return the full document — call it again with a
> narrower query if a passage looks truncated."

What does **not** belong in a description: worked examples, fake dialogue, numbered
protocols, and instructions about other tools. Examples constrain the exploration space
and cost tokens on every request. Put teaching material in a skill.

### Naming and matching

MCP tools surface to the harness as `mcp__<server>__<tool>`. So `search_corpus` on a
server named `coach-corpus` becomes `mcp__coach-corpus__search_corpus`. That's the name
you use in permission rules, hook matchers, and `allowed_tools`.

### Large tool output is offloaded

If a tool returns more than **100,000 characters** (~25,000 tokens), the output is
automatically written to a file in the sandbox; the model gets a truncated preview plus
the path and can `read` the rest. No configuration needed. The threshold is in
*characters*, not tokens.

Still: returning 99,000 characters because you can is a bad idea. High-signal responses
beat complete ones.

### Model-supplied paths are untrusted input

Every tool handler that takes a path must resolve it and confine it. This is the same bug
class as module 01's hook, and it recurs here because it's the one that actually gets
exploited.

---

## Build

### Step 1 — Separate the logic from the transport

Put the real work in a plain module with no MCP dependency. The MCP server becomes a thin
adapter. This is better design *and* it makes the logic testable without standing up a
server — which is exactly what the verifier needs.

`app/coach/corpus_index.py`:

```python
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
```

### Step 2 — The MCP server

`app/coach/mcp_server/__init__.py` (empty), and `app/coach/mcp_server/server.py`:

```python
"""MCP server exposing the study corpus.

Thin adapter. All logic lives in coach.corpus_index so it can be tested without
standing up a server.
"""

from __future__ import annotations

from mcp.server import MCPServer

from coach import corpus_index

mcp = MCPServer("coach-corpus")


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
```

### Step 3 — Register it with Claude Code

`app/.mcp.json`:

```json
{
  "mcpServers": {
    "coach-corpus": {
      "command": "python",
      "args": ["-m", "coach.mcp_server.server"]
    }
  }
}
```

`.mcp.json` is project-scoped and committed, so anyone cloning the repo gets the server.

Then allow its tools in `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__coach-corpus__search_corpus",
      "mcp__coach-corpus__get_objectives"
    ],
    "ask": [
      "mcp__coach-corpus__record_result"
    ]
  }
}
```

Note `record_result` is on `ask` — it writes state. Read-only tools auto-approve; anything
with a side effect gets a prompt. That gradient is the point of having three lists.

---

## Checkpoint

```bash
python verify/module_03.py
```

Then confirm the second consumer works. Run `claude` in `app/` and ask:

> Use the corpus search tool to find what the blueprint says about context management

Claude should call `mcp__coach-corpus__search_corpus`. If the server doesn't appear, run
`/mcp` to see connection status — a server that fails to start shows there, and the reason
lands in `mcp-server-coach-corpus.log`.

---

## Exam drill

**1.** Which MCP capability is fetched by the **application**, not called by the model?

A. Tools B. Resources C. Prompts D. Sampling

**2.** How does the Python MCP SDK derive a tool's input schema?

A. From an explicit `input_schema` dict you pass to the decorator
B. From the function's type hints and docstring
C. From a separate `.schema.json` file
D. It doesn't — MCP tools are untyped

**3.** A server named `coach-corpus` exposes `search_corpus`. What name do you use in a
permission rule?

A. `search_corpus` B. `coach-corpus.search_corpus`
C. `mcp__coach-corpus__search_corpus` D. `mcp://coach-corpus/search_corpus`

**4.** A tool returns 150,000 characters. What happens?

A. The request fails with a token-limit error
B. Output is truncated to the limit and the rest is lost
C. Output is offloaded to a file; the model gets a preview plus the path
D. Output is automatically summarized by a second model call

**5.** Your tool under-triggers — the model answers from memory instead of calling it. The
**most** effective fix is:

A. Add `CRITICAL: You MUST use this tool` to the description
B. Make the description prescriptive about *when* to call it
C. Reduce the number of parameters
D. Force it with `tool_choice: {"type": "tool"}` on every request

**6.** Which belongs in a tool description? *(Select two.)*

A. What each parameter means and its constraints
B. A worked example dialogue showing a call
C. When to use it, and when not to
D. A numbered protocol the model must follow after calling it

**7.** A tool takes a filename from the model. Which check is sound?

A. Reject the call if the string contains `..`
B. Resolve to an absolute path, then verify the allowed directory is the path or one of
   its parents
C. Reject any absolute path
D. Escape the string before joining it

**8.** Where does a project-scoped MCP server configuration live?

A. `.claude/settings.json` under `mcpServers`
B. `.mcp.json` at the project root
C. `~/.claude.json` D. `.claude/mcp/servers.json`

**9.** You want read-only MCP tools to run without prompting, but the state-writing one to
prompt. Best configuration?

A. Put all three in `allow` and add a `PreToolUse` hook to block the writer
B. Put the read-only tools in `allow` and the writer in `ask`
C. Put all three in `ask`
D. Put the writer in `deny` and call it out-of-band

**10.** Why put the search logic in `corpus_index.py` rather than in the `@mcp.tool()`
function body?

A. MCP forbids logic inside tool functions
B. It can be tested and reused without starting a server, and module 04's agent imports
   it directly
C. Decorated functions can't be imported
D. It reduces the generated schema size

<details>
<summary><b>Answer key</b></summary>

**1 — B.** Resources are file-like data read by the client/application. Tools are called
by the model. If you want the model to decide when to fetch, make it a tool.

**2 — B.** Type hints and the docstring. Which is why a vague docstring is a vague schema.

**3 — C.** `mcp__<server>__<tool>`. Same form in hook matchers and `allowed_tools`.

**4 — C.** Over ~100,000 characters, output is offloaded to a file and the model gets a
preview plus the path. Note the threshold is characters, not tokens.

**5 — B.** Prescriptive "call this when…" descriptions give measurable lift on current
models, which reach for tools conservatively. A is the trap — that emphasis style was for
older models and now over-triggers. D is a sledgehammer that breaks every other request.

**6 — A and C.** Parameter semantics and when/when-not. Worked examples and post-call
protocols belong in a skill; in a description they cost tokens on every request and
constrain exploration.

**7 — B.** Resolve then check containment. A misses symlinks and URL-encoded traversal;
C breaks legitimate absolute paths; D solves a different problem entirely.

**8 — B.** `.mcp.json` at the project root, committed to the repo.

**9 — B.** That's what the three lists are for. A works but puts the boundary in a place
nobody reading `settings.json` will find.

**10 — B.** Testability and reuse. The verifier exercises the logic with no server
running, and module 04's agent imports `weakest_domains()` directly. Keeping the MCP layer
thin is a design choice, not a requirement — but it's the one that pays.

</details>

---

## Further reading

- [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP server concepts](https://modelcontextprotocol.io/docs/learn/server-concepts)
- [Claude Code — MCP](https://code.claude.com/docs/en/mcp)

---

**Next:** [Module 04 — Agentic Architecture & Orchestration](04-agentic-architecture.md) (27% — the big one)
