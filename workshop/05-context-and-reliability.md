# Module 05 — Context Management & Reliability

**Domain 5 · 15% of the exam · ~9 of 60 questions**

Task statements covered: managing context windows; implementing caching strategies;
handling long conversations; building reliable production systems.

Time: 2–4 hours.

---

## What you're building

Make the Coach survive a long session. Prompt caching on the corpus and system prompt,
session persistence, compaction for long runs, and a cost ledger that tells you what any
of this actually cost.

---

## Concept brief

### Caching is a prefix match. Everything follows from that.

**Any byte change anywhere in the prefix invalidates everything after it.**

Render order is `tools` → `system` → `messages`. A breakpoint on the last system block
caches tools *and* system together.

That single invariant generates most of the domain's exam questions. Design the
prompt-building path around it and caching mostly works for free; get it wrong and no
number of `cache_control` markers will save you.

### Silent invalidators

These produce no error. They just quietly cost you money:

| Pattern | Why it kills the cache |
|---|---|
| `datetime.now()` in the system prompt | Prefix differs every request |
| `uuid4()` / request IDs early in content | Same |
| `json.dumps(d)` without `sort_keys=True` | Non-deterministic key order |
| Interpolating a user ID into the system prompt | Per-user prefix, no sharing |
| `tools=build_tools(user)` varying per user | Tools render at position 0 |
| Conditional system sections | Each flag combination is a distinct prefix |

**Diagnosis:** if `usage.cache_read_input_tokens` is zero across repeated identical-prefix
requests, one of these is in play. Your module 02 verifier already checks the first four —
that check exists because of this module.

### Minimums are model-dependent and *not monotonic*

| Model | Minimum cacheable prefix |
|---|---:|
| Claude Opus 5, Fable 5 | 512 tokens |
| Opus 4.8, Sonnet 5, Sonnet 4.6 | 1024 |
| Opus 4.7 | 2048 |
| Opus 4.6, Opus 4.5, Haiku 4.5 | 4096 |

A 3K-token prompt caches on Opus 5 and silently won't on Haiku 4.5 — with no error, just
`cache_creation_input_tokens: 0`. "Newer means lower" is not a rule you can lean on.

### Economics

Reads cost ~0.1× base input. Writes cost **1.25×** at the 5-minute TTL, **2×** at 1 hour.

So break-even differs by TTL: at 5 minutes, two requests pay for it (1.25 + 0.1 = 1.35
versus 2.0 uncached). At 1 hour you need three. The 1-hour TTL survives gaps in bursty
traffic, but the doubled write cost needs more reads to justify.

### Not everything invalidates everything

| Change | Tools cache | System cache | Messages cache |
|---|:---:|:---:|:---:|
| Tool definitions | ❌ | ❌ | ❌ |
| Model switch | ❌ | ❌ | ❌ |
| System prompt content | ✅ | ❌ | ❌ |
| `tool_choice`, thinking on/off | ✅ | ✅ | ❌ |
| Message content | ✅ | ✅ | ❌ |

Practical read: you can flip `tool_choice` per request without losing the tools+system
cache. Only tool-definition and model changes force a full rebuild.

**The escape hatch for mid-session instructions:** append a `{"role": "system", ...}`
message to `messages[]` instead of editing the top-level `system`. Editing `system`
invalidates the entire conversation history behind it; a system *message* sits after the
cached prefix and leaves it intact. No beta header.

Support is **Opus 5, Opus 4.8, Fable 5 (and Mythos 5) — but *not* Sonnet 5.** That
exception is the whole trap: Sonnet 5 is current and capable, so it reads like it should
be on the list, and the feature is model-gated rather than tier-gated. Unsupported models
return a 400 (`role 'system' is not supported on this model`) — catch it and fall back to
putting the instruction in the user turn.

There's also a placement rule that bites in practice: the system message must **follow a
user message** (or an assistant turn ending in server-tool use), and must be either the
last entry in `messages` or be followed by an assistant turn. It can never be
`messages[0]` — the opening prompt belongs in top-level `system`.

### Compaction vs. context editing — different things

| | Compaction | Context editing |
|---|---|---|
| Does | **Summarizes** earlier context | **Clears** old tool results / thinking |
| Beta header | `compact-2026-01-12` | `context-management-2025-06-27` |
| Edit type | `compact_20260112` | `clear_tool_uses_20250919`, `clear_thinking_20251015` |

**The compaction trap:** you must append `response.content` — the whole thing — back into
`messages`, not just the extracted text. Compaction blocks in the response are what the
API uses to replace the compacted history next turn. Pulling out the text string and
appending that silently loses the compaction state.

### `input_tokens` is the uncached remainder only

Total prompt size = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
An agent that ran for hours showing `input_tokens: 4000` isn't a miracle — the rest was
served from cache. Sum the three.

---

## Build

### Step 1 — A cached client wrapper

`app/coach/cached_client.py`:

```python
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
```

### Step 2 — A cost ledger

`app/coach/ledger.py`:

```python
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
```

### Step 3 — Session persistence

`app/coach/session.py`:

```python
"""Persist a study session so it survives a restart.

Note what gets stored: the full content blocks, not extracted text. If you enable
compaction, the compaction blocks live in there — dropping them loses the
compacted history.
"""

from __future__ import annotations

import json
from pathlib import Path

SESSIONS = Path(__file__).resolve().parents[1] / ".coach" / "sessions"


def save(session_id: str, messages: list[dict]) -> Path:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    path = SESSIONS / f"{session_id}.json"
    path.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    return path


def load(session_id: str) -> list[dict]:
    path = SESSIONS / f"{session_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
```

### Step 4 — Compaction for long sessions

For a study session that runs long, enable server-side compaction:

```python
response = client.beta.messages.create(
    betas=["compact-2026-01-12"],
    model="claude-opus-5",
    max_tokens=16000,
    messages=messages,
    context_management={"edits": [{"type": "compact_20260112"}]},
)

# Append the FULL content. Extracting just the text loses compaction state.
messages.append({"role": "assistant", "content": response.content})
```

---

## Checkpoint

```bash
python verify/module_05.py          # cache hygiene + ledger math, free
python verify/module_05.py --live   # two real calls; asserts the second is a cache hit
```

The offline checks include the one that matters most for this domain: **the system prefix
is byte-identical across two independent builds.** That's the prefix-match invariant
expressed as an assertion. If someone later interpolates a timestamp into the system
prompt, this fails immediately instead of quietly doubling your bill.

The `--live` run makes two identical requests and asserts `cache_read_input_tokens > 0` on
the second. That's the only way to *prove* caching works — everything else is inference.

---

## Exam drill

**1.** You add `cache_control` to your system prompt but `cache_read_input_tokens` stays
zero across repeated requests. Most likely cause?

A. The wrong TTL B. Something volatile earlier in the prefix
C. Too few breakpoints D. The model doesn't support caching

**2.** What is the render order for cache-prefix purposes?

A. `system` → `tools` → `messages` B. `tools` → `system` → `messages`
C. `messages` → `system` → `tools` D. Order doesn't matter; each is keyed separately

**3.** Cache write cost at the **1-hour** TTL is what multiple of base input?

A. 0.1× B. 1.25× C. 2× D. 3×

**4.** A 3,000-token prompt with `cache_control` caches on Opus 5 but not Haiku 4.5. Why?

A. Haiku doesn't support prompt caching
B. Minimum cacheable prefix is model-dependent — 512 on Opus 5, 4096 on Haiku 4.5
C. Haiku requires an explicit TTL
D. The prompt must exceed 4096 tokens on every model

**5.** Which change invalidates the **tools** cache? *(Select two.)*

A. Changing `tool_choice` B. Adding a tool definition
C. Switching models D. Editing the system prompt
E. Appending a user message

**6.** You must inject a mode change mid-conversation without losing the cached history.
Best approach on a supporting model?

A. Edit the top-level `system` field
B. Append a `{"role": "system", ...}` message to `messages[]`
C. Prepend it to the next user message
D. Start a new conversation

**7.** Using compaction, you append only the extracted text of the response to `messages`.
What breaks?

A. Nothing B. Compaction state is lost — the API can't replace the compacted history
C. The next request 400s D. Token counts become inaccurate

**8.** Which pair correctly matches feature to beta header? *(Select two.)*

A. Compaction → `compact-2026-01-12`
B. Compaction → `context-management-2025-06-27`
C. Context editing → `context-management-2025-06-27`
D. Context editing → `compact_20260112`

**9.** A long agent run reports `usage.input_tokens: 4000`. What does that tell you about
total prompt size?

A. The prompt was 4,000 tokens
B. Only that 4,000 were uncached — add cache write and read for the total
C. The context window was nearly exhausted
D. Caching was disabled

**10.** Ten parallel requests share an identical large prefix. What happens on the first
batch, and what's the fix?

A. All ten read from cache; no fix needed
B. All ten pay full price — a cache entry isn't readable until the first response begins
   streaming. Fire one, await first token, then the rest
C. Nine read from cache; the tenth writes
D. The API serializes them automatically

<details>
<summary><b>Answer key</b></summary>

**1 — B.** A silent invalidator earlier in the prefix — a timestamp, a UUID, unsorted
`json.dumps`, a per-user value. There's no error; the only signal is the zero.

**2 — B.** `tools` → `system` → `messages`. Which is why a breakpoint on the last system
block covers tools too.

**3 — C.** 2× at 1-hour TTL, 1.25× at 5-minute. Reads are ~0.1× under both.

**4 — B.** Minimums are model-dependent and not monotonic: 512 on Opus 5, 1024 on Opus 4.8
and Sonnet 5, 2048 on Opus 4.7, 4096 on Opus 4.6 / 4.5 / Haiku 4.5. Below the minimum
nothing caches and nothing warns you.

**5 — B and C.** Tool definitions and model switches force a full rebuild. `tool_choice`
and system-prompt edits leave the tools cache intact; appending a message leaves both
tools and system intact.

**6 — B.** A mid-conversation system message sits after the cached prefix. Editing
top-level `system` changes the prefix ahead of the entire history and re-processes all of
it. No beta header.

Note the qualifier in the question — *"on a supporting model"* — because the support list
is the examinable part: **Opus 5, Opus 4.8, Fable 5, Mythos 5 — and not Sonnet 5.** It is
gated per model, not per tier, so the current Sonnet being excluded is exactly the kind of
detail a question is built on. On an unsupported model you get a 400
(`role 'system' is not supported on this model`), so C is the real fallback there: put the
instruction in the user turn. It caches identically, but it is spoofable by anything that
writes user-visible content, whereas the system role is not.

**7 — B.** The compaction blocks in `response.content` are what the API uses to replace
compacted history. Append the full content, not the extracted string.

**8 — A and C.** Compaction is `compact-2026-01-12` (edit type `compact_20260112`);
context editing is `context-management-2025-06-27` (edit types `clear_tool_uses_20250919`,
`clear_thinking_20251015`). D swaps an edit type in for a header.

**9 — B.** `input_tokens` is the uncached remainder only. Total =
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.

**10 — B.** A cache entry becomes readable only once the first response begins streaming.
Ten concurrent identical requests all pay full price. Send one, await the first streamed
token, then fan out the rest.

</details>

---

## Further reading

- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [Context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows)

---

**Next:** [Module 06 — Mock Exam & Gap Analysis](06-mock-exam.md)
