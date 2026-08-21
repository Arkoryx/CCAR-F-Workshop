# CCAR-F Workshop — Learn the Architect exam by building an agent

A hands-on workshop for the **Claude Certified Architect – Foundations (CCAR-F)** exam.
You don't read about the Agent SDK, MCP, and Claude Code — you build a working agent with
them, and the build *is* the syllabus.

**What you build:** the **Certification Coach** — a Python agent that ingests study
material through an MCP server, generates exam-style practice questions with schema-valid
structured output, critiques its own work in an agentic loop, and tracks which domains
you're weakest in across sessions.

It's recursive on purpose. The thing you build to learn the exam is the thing that drills
you for the exam. By module 06 you sit a full 60-question mock on the tool you wrote.

---

## Why this exists

The exam's target candidate has roughly six months of hands-on experience with the Claude
API, the Agent SDK, Claude Code, and MCP. Most prep advice suggests 40–100 hours. You
cannot read your way to that. Every domain in the blueprint is something you *do*, so
every module here ends with something that runs.

---

## The exam, briefly

60 questions, 120 minutes, **720 out of 1000 to pass**, $125. Five domains:

| Domain | Weight | Module |
|---|---:|---|
| Agentic Architecture & Orchestration | 27% | [04](workshop/04-agentic-architecture.md) |
| Claude Code Configuration & Workflows | 20% | [01](workshop/01-claude-code-config.md) |
| Prompt Engineering & Structured Output | 20% | [02](workshop/02-prompt-engineering.md) |
| Tool Design & MCP Integration | 18% | [03](workshop/03-tools-and-mcp.md) |
| Context Management & Reliability | 15% | [05](workshop/05-context-and-reliability.md) |

Full blueprint and source caveats: [`references/exam-blueprint.md`](references/exam-blueprint.md).

> **This is the Architect exam, not the Associate.** The Associate (CCAO-F) is a separate
> $99 non-technical credential with seven completely different domains. Both are 60 Q /
> 120 min / 720 to pass, which is why they get confused. If you want the non-technical
> one, this workshop is the wrong material.

---

## Modules

Build order is teaching order: configure the environment → write the prompts → build the
tools → wrap it in an agent → harden it.

| # | Module | Domain | You end with |
|---|---|---|---|
| 00 | [Setup](workshop/00-setup.md) | — | A configured machine and an empty project |
| 01 | [Claude Code Configuration](workshop/01-claude-code-config.md) | 20% | A project with scoped permissions, working hooks, a subagent, and CI |
| 02 | [Prompt Engineering & Structured Output](workshop/02-prompt-engineering.md) | 20% | A generator that emits schema-valid questions |
| 03 | [Tool Design & MCP](workshop/03-tools-and-mcp.md) | 18% | An MCP server both Claude Code and your agent can use |
| 04 | [Agentic Architecture](workshop/04-agentic-architecture.md) | 27% | A generate→critique→revise loop that runs unattended |
| 05 | [Context & Reliability](workshop/05-context-and-reliability.md) | 15% | Caching, compaction, session persistence, cost tracking |
| 06 | [Mock Exam](workshop/06-mock-exam.md) | — | A scored 60-question mock and a gap analysis |

Each module has the same shape: **exam mapping → concept brief → build → checkpoint →
exam drill → further reading**. The checkpoint is a command you run; if it produces the
stated result, move on.

---

## How to use this

Work through the modules in order. Each one builds on the last — module 04's agent calls
module 03's MCP server using module 02's prompts, inside module 01's Claude Code setup.

### Two skills drive the workshop

Reading a module and copying its code blocks teaches you that the file looks like that. It
doesn't teach you why it couldn't look otherwise. So the build steps are delivered by a
skill that makes you attempt each piece **before** showing you the answer:

| Command | What it does |
|---|---|
| `/teach` | Resume the current step. Sub-steps, each with its reasoning and an exam note; you write, then compare. |
| `/teach 01.4` | Open a specific step. Invoke **once per step** — sub-steps happen in conversation after that. |
| `/check 01.2` | Grade one step against the module's real verifier checks. Call it as often as you like. |
| `/check 01` | Run the whole module checkpoint. |
| `/drill 01` | Sit the module's ten drill questions. All ten answered before any verdict, then walked one at a time. |
| `/drill 01 --missed` | Re-drill only the questions you got wrong last time. |

**`/teach` never decides you're done and never writes progress — `/check` does.** That
split is deliberate: if the thing that taught you a step also graded it, your progress
would rest on a judgement about the conversation instead of on an executable assertion.
It's the same reason the verifiers assert end state rather than transcript.

`/check` records to a gitignored `.teach-progress.json`, and **only on a genuine pass**.
Unearned state is worse than no state. `/drill` keeps its own gitignored
`.drill-results.json`, which is what makes `--missed` possible — re-drilling your own
errors is the highest-value thing here for an exam.

`/drill` also validates a drill against itself before running it: ten questions against ten
key entries, and every `(Select N)` marker against the arity of its key. That check found a
real defect in module 04 the first time it was run.

The honest limit: these checks assert *state, not understanding*. `CLAUDE.md exists`
passes whether you derived the file or pasted it. `/check` says so when a step passes on
file-existence alone.

Skills live in `.claude/skills/`. **After a fresh clone, restart Claude Code once** — a
top-level skills directory that didn't exist when the session started isn't picked up
until restart.

- **`app/`** is where *you* build the Coach. It starts near-empty by design.
- **The `solutions` branch** holds a working reference implementation — the same
  `app/coach/` you're about to write, with every verifier passing against it. It is a
  *branch*, not a folder, so it isn't sitting in your working tree tempting you. Reach
  for it when you're stuck:

  ```bash
  git show solutions:app/coach/schema.py     # read one file
  git diff main solutions -- app/coach       # everything at once
  git checkout solutions -- app/coach/exam.py  # pull one file into your tree
  ```

  Building it wrong first and then comparing is most of the learning.
- **Drill questions** at the end of each module are in exam format. Answer them before
  looking at the key.

**Prerequisites:** start at [module 00](workshop/00-setup.md). It covers what to install
and — importantly — what this will cost you in API spend.

---

## Verification

Every module ends with an executable checkpoint:

```bash
cd app
python verify/module_01.py
```

Each verifier asserts the module's **end state**, not the path you took to get there. That
matters because you're building this *with* a non-deterministic assistant: Claude may
reach the same destination by a different route, and a checkpoint that asserts on
transcript would fail for no reason. One that asserts on state doesn't care.

The verifiers also catch the more dangerous direction — a checkpoint that quietly stopped
being true. Module 01's, for example, runs your hook with synthetic stdin and asserts it
denies a corpus write, allows a `coach/` write, and blocks `coach/../corpus/x.md`. That
either passes or it doesn't.

Verifiers exit non-zero on failure, so they work in CI.

**Live checks are opt-in.** Modules 02, 04, and 05 have checks that spend money:

```bash
python verify/module_02.py          # free
python verify/module_02.py --live   # + one real API call
```

The default run costs nothing, on the theory that a verification suite you can't afford to
run is one you won't run.

### A note on trusting this material

The workshop was researched against live documentation, and every drill answer cites a
source. But the build steps and the drills fail differently: **if a build step is wrong,
your code breaks and you find out in minutes. If a drill answer is wrong, nothing errors —
you just learn it wrong.**

So the answer keys carry the real risk. They're linked to sources for exactly that reason.
If a key and the docs ever disagree, **the docs win.** Module 06 makes the same point one
level up: don't lean solely on questions your own generator wrote from a corpus you
assembled, because you and it share blind spots.

---

## Status

All seven modules (00–06) written, each with an executable verifier in `app/verify/`.
A full reference implementation lives on the `solutions` branch, and **all six verifiers
pass against it** (20/20, 12/12, 13/13, 13/13, 13/13, 13/13), along with `pytest` and
`ruff`. Every build step in these modules has been executed, not just written.

**What is not yet verified — read this before trusting a module end to end:**

| Unverified | Why it matters |
|---|---|
| ~~**Drill answer keys**~~ — **audited**, all 50 checked against primary sources | Found 2 wrong/broken questions and 3 over-claiming explanations, all fixed. Also surfaced a live bug in module 04's build code. Details below. |
| **Every `--live` check** — no API call has ever been made | Module 05's whole claim (caching works) rests on `cache_read_input_tokens > 0`, which only a live run can show. The offline checks prove the code is *shaped* right, not that it *works*. |
| **The MCP server has never been started** | Module 03's checkpoint says "one server, both consumers." The logic is tested; the stdio transport and Claude Code's connection to it are not. |
| ~~**No hook has ever fired in a live session**~~ — **done**, and it found a defect | The first live run failed: the module shipped `python ${CLAUDE_PROJECT_DIR}/...` unquoted, which splits on any path containing a space. The hook died with a *non-blocking* error and the corpus write went through, with every checkpoint green. Fixed, plus a verifier check. |
| **The agent has never run a batch** | Module 04's guardrails are tested directly; the loop they guard has not executed. |
| **Blueprint weightings** | Third-party sources, not Anthropic. See the caveat in `references/exam-blueprint.md`. |

### What the answer-key audit found

All 50 drill questions were checked against primary sources — the installed Claude Code
binary, the installed `mcp` and `claude-agent-sdk` packages, and the current API
reference. Six defects:

| Where | Defect |
|---|---|
| 01 Q8 | Key taught `permissionDecision: "escalate"` — **no such value**. It's `ask`, which wasn't even among the options. |
| 01 Q4 | **Two correct answers** — `"Bash\|Edit"` and `"^(Bash\|Edit)$"` both fire on exactly those tools, and the key admitted it while marking one wrong. |
| 01 Q7, Q3 | Explanations asserted more than the docs support (`env` reload behaviour; "silence is consent"). |
| 03 Q2 | Conflated schema with description — type hints alone build the schema; `Args:` lines never reach `properties.*.description`. |
| 03 Q4 | Cited a 100,000-character threshold documented for **Managed Agents**, not Claude Code. |
| 05 Q6 | Omitted that Sonnet 5 is **excluded** from mid-conversation system messages. |

### Second pass — the audit's own blind spot

The audit above checked the **drill questions**. It did not check the **concept briefs**,
and that gap had already cost something:

| Where | Defect |
|---|---|
| 01 concept brief | Still taught `permissionDecision: "escalate"` — the *same* wrong value the Q8 fix removed. The key was corrected; the prose three sections above it was not. A reader met the wrong value first. |
| 01 Q8 | `defer` was offered as a distractor and the key called it invented. `claude-agent-sdk` 0.2.137 types `permissionDecision` as `Literal["allow", "deny", "ask", "defer"]`. Four correct answers on a "select three" — the Q4 defect again. Option replaced, question scoped to Claude Code. |

Two lessons worth more than the facts. **A fact fixed in one place goes stale in the
other** — grep for the wrong value everywhere before calling it fixed. And **a key can rot
without being wrong when written**: `defer` genuinely didn't exist when that key was
written. Answers pinned to a moving SDK need a version, not just a source.

Checked and found **clean** on the same pass: module 01's hook event list (all ten names
real; the docs list 31, but "events you should know" is a fair subset) and its exit-code
table (0 / 2 / other).

**And one live bug, found while auditing a key that was correct:** module 04 listed
`"Write"` in `allowed_tools` alongside `can_use_tool`, which auto-approves the tool
*before* the callback runs. The corpus guardrail never fired. Fixed, plus a new verifier
check that fails on the old code.

Modules **02 and 05 were clean** — 20/20 between them.

The exam blueprint is corroborated by two independent third-party sources but is **not**
from Anthropic directly — see the caveat in
[`references/exam-blueprint.md`](references/exam-blueprint.md).
