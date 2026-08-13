# CCAR-F Workshop — Plan

**Status:** Decisions locked. Modules 00–01 built; 02–06 pending.
**Owner:** Scott Miller
**Started:** 2026-08-12

---

## 1. The Concept

A **step-by-step, hands-on workshop** where the learner uses Claude to build a practice
app, and the act of building teaches everything needed to pass the **Claude Certified
Architect – Foundations (CCAR-F)** exam.

Core bet: people retain more from building something with Claude than from reading about
Claude. Every exam concept shows up as something the learner *does*.

---

## 2. Target exam — corrected mid-planning

The workshop originally aimed at the **Associate – Foundations (CCAO-F)**. The
`references/DomainsAndWeights.png` snippet Scott supplied turned out to describe a
*different exam* — the **Architect – Foundations (CCAR-F)**. Both are 60 questions /
120 minutes / 720 to pass, which is why they're routinely conflated, but they share no
content.

| | Associate (CCAO-F) | **Architect (CCAR-F)** ← target |
|---|---|---|
| Cost | $99 | **$125** |
| Audience | Ops, marketing, PM, HR | **Developers / solution architects** |
| Coding | Explicitly not required | **Required** — API, SDK, MCP |
| Domains | 7 (evaluation, governance, workflow) | **5 (agentic, Claude Code, prompting, MCP, context)** |

Architect was chosen because "build a practice app" maps almost 1:1 onto its syllabus,
where it sits in real tension with the Associate's judgment-focused domains.

Full blueprint: [`references/exam-blueprint.md`](references/exam-blueprint.md).

---

## 3. Decisions Log

| # | Decision | Date | Rationale |
|---|---|---|---|
| 1 | Hands-on: learn by building with Claude, not by reading | 2026-08-12 | Retention; matches how the tool is actually used |
| 2 | Plan/brainstorm before implementation | 2026-08-12 | Scott's call |
| 3 | **Target the Architect (CCAR-F)**, not the Associate | 2026-08-12 | The reference PNG was Architect; the build premise fits it 1:1 |
| 4 | App = **Certification Coach** | 2026-08-12 | Recursive: the build teaches the exam and produces a study tool. Exercises all 5 domains without contrivance |
| 5 | Stack = **Python** | 2026-08-12 | Shortest path for MCP servers and the Agent SDK |
| 6 | **One module per domain** (5 core + setup + capstone) | 2026-08-12 | Fewer, meatier units |
| 7 | Audience: Scott first, written to be shareable | 2026-08-12 | Drives the consistent per-module format |
| 8 | Folder renamed `CCAF Workshop` → `CCAR-F Workshop` | 2026-08-12 | Match the exam actually targeted |

---

## 4. Module Structure

Build order is teaching order: configure → prompt → tools → agent → harden.

| # | Module | Domain | Weight |
|---|---|---|---:|
| 00 | Setup | — | — |
| 01 | Claude Code Configuration & Workflows | 2 | 20% |
| 02 | Prompt Engineering & Structured Output | 3 | 20% |
| 03 | Tool Design & MCP Integration | 4 | 18% |
| 04 | Agentic Architecture & Orchestration | 1 | **27%** |
| 05 | Context Management & Reliability | 5 | 15% |
| 06 | Mock exam & gap analysis | — | — |

**Per-module format:** exam mapping → concept brief → build → checkpoint → exam drill
(8–10 questions + key) → further reading.

---

## 5. Findings Worth Keeping

Things discovered while building that aren't obvious from the docs index:

- **The Claude Agent SDK requires the Claude Code CLI.** `claude-agent-sdk` drives the
  CLI process; it is not a standalone HTTP client. Module 04 hard-depends on module 00's
  CLI install.
- **A Pro/Max subscription is not API credit.** Modules 02 and 05 call the API directly
  and need a Console account with credits. That's 35% of the exam behind a separate
  paywall from the CLI.
- **Settings precedence is counterintuitive**: user settings are the *lowest* priority,
  below project. Good drill material, and it's in module 01's key.
- **Hook exit codes**: only exit **2** blocks. Other non-zero codes are non-blocking
  errors that let the action proceed — a genuinely easy thing to get wrong in production.

---

## 6. Verification Approach

Added after a design discussion about AI non-determinism leaking misinformation into the
workshop. The reframe that drove it: **the risk isn't variability, it's unfalsifiability.**
A consistently wrong fact is worse than a variable one, because nothing ever surfaces the
disagreement. So the goal is not determinism — it's making a wrong claim *catchable*.

Three rules that follow:

1. **Rigid about ends, loose about means.** Instructions state goals; artifacts (config,
   schemas) are exact; checkpoints assert end state, never transcript. Scripting prompts
   verbatim would teach copying rather than prompt engineering, and rot on the next model
   release.
2. **Concentrate verification on the answer keys.** Build steps are self-correcting — wrong
   config fails loudly. A wrong drill key fails silently and gets carried into the exam.
   Every key cites a source; docs win over the key.
3. **Free by default, live opt-in.** Verifiers spend nothing unless passed `--live`.

Each module has `app/verify/module_NN.py` on a shared harness (`_harness.py`). Notable
checks: module 01 executes the hook with synthetic stdin; module 05 asserts the cached
prefix is byte-identical across builds; module 06 asserts the seeded sampler is
reproducible.

The approach is self-demonstrating — module 01 teaches hooks as deterministic control over
a non-deterministic agent, and module 05 teaches reliability. Applying that to the workshop
itself is the lesson, not just infrastructure.

---

## 7. Open Items

- [ ] Confirm the blueprint against the official Anthropic Partner Academy exam guide
      (current weightings are third-party, though two sources corroborated)
- [ ] Populate `solutions/` with a reference implementation per module
- [ ] Decide a default model for bulk generation (Opus for quality vs. Haiku for cost)
- [ ] **Blocked:** rename `CCAF Workshop` → `CCAR-F Workshop`. Fails with "Device or
      resource busy" — a process holds a handle on the directory. Needs whatever has it
      open (Explorer window, editor) closed first.

---

## 7. Brainstorm Notes

> Free-form space. Dump thoughts here.

_(empty)_
