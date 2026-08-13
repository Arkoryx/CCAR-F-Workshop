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

- **`app/`** is where *you* build the Coach. It starts near-empty by design.
- **`solutions/`** holds a reference implementation per module. Use it when you're stuck,
  or to diff against what you wrote. Don't read ahead — building it wrong first and then
  comparing is most of the learning.
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
`solutions/` is not yet populated.

The exam blueprint is corroborated by two independent third-party sources but is **not**
from Anthropic directly — see the caveat in
[`references/exam-blueprint.md`](references/exam-blueprint.md).
