# Module 00 — Setup

**Domain coverage:** none directly. This module gets you to a working machine so modules
01–06 don't stall on tooling.

Time: 30–45 minutes.

---

## 1. What you're about to build

The **Certification Coach** — a Python agent that:

- reads your study corpus through an **MCP server** you write
- generates exam-style questions as **schema-valid structured output**
- runs a **generate → critique → revise** agentic loop with a separate critic
- **persists sessions**, caches aggressively, and tracks its own cost
- is built inside a **Claude Code project** you configure with hooks, permissions, and CI

Every one of those bold phrases is a CCAR-F domain.

---

## 2. Prerequisites

### Claude Code CLI — required, and not just for convenience

Install it first. This matters more than it looks: **the Claude Agent SDK drives the
Claude Code CLI process.** The SDK is not a standalone HTTP client — if the CLI isn't
installed and authenticated, module 04 will not run.

**Windows (PowerShell):**
```powershell
irm https://claude.ai/install.ps1 | iex
```

**macOS / Linux / WSL:**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Verify:
```bash
claude --version
```
You should get a version number followed by `(Claude Code)`.

> **On native Windows**, install [Git for Windows](https://git-scm.com/downloads/win) too.
> Without it Claude Code falls back to PowerShell as its shell tool, and several commands
> in this workshop assume a POSIX shell is available.

Then authenticate — run `claude` in any directory and follow the browser prompt.

### Python 3.11+

Check with `python --version`. You need 3.11 or newer.

### A virtual environment

Many Python distributions block installing into the system interpreter, and you want this
project isolated anyway.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
```

---

## 3. Authentication — read this carefully

There are **two separate auth paths**, and conflating them is the most common way to get
stuck later:

| What you're doing | What it uses |
|---|---|
| Running `claude` interactively (modules 01, 03) | Your Claude subscription **or** a Console account |
| Calling the API directly with the `anthropic` SDK (modules 02, 05) | An **API key with credits** |
| Running the Agent SDK (module 04) | The Claude Code CLI's authentication |

**A Claude Pro or Max subscription does not give you API credits.** If you plan to work
through modules 02 and 05 — and you should, they're 35% of the exam — you need a
[Claude Console](https://console.anthropic.com/) account with pre-paid credits, and:

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

Note that if `ANTHROPIC_API_KEY` is set, Claude Code skips the login prompt and asks you
to approve that key instead — so setting it changes CLI behavior too.

---

## 4. Budget expectations

This workshop spends real money. Be deliberate about it.

The bulk of the cost is module 04 (the agentic loop re-runs generation and critique) and
module 06 (generating a full 60-question mock). Question generation is output-heavy, and
output tokens are the expensive half.

**Rough order of magnitude:** low tens of dollars if you run everything on Opus, and
meaningfully less if you generate on a cheaper model. Two ways to control it:

1. **Use a cheaper model for bulk generation.** The default throughout this workshop is
   `claude-opus-5`. For generating many questions where you're exercising the *plumbing*
   rather than the reasoning, `claude-sonnet-5` or `claude-haiku-4-5` will teach you the
   same lesson for less. Module 05 covers the tradeoff properly.
2. **Set a spend limit in the Console** before you start, so a runaway loop in module 04
   can't surprise you. You will write a runaway loop in module 04 — everyone does. That's
   why guardrails are a task statement in the 27% domain.

Module 05 builds real cost tracking into the Coach. Until then, watch the Console.

---

## 5. Scaffold the project

From the workshop root:

```bash
cd app
mkdir -p coach/mcp_server tests corpus
```

Install the dependencies you'll need across the workshop:

```bash
pip install anthropic claude-agent-sdk mcp pydantic pytest ruff
```

| Package | Used in | What for |
|---|---|---|
| `anthropic` | 02, 05 | Direct Claude API access — structured output, caching |
| `claude-agent-sdk` | 04 | The agent loop, subagents, permissions |
| `mcp` | 03 | Building the MCP server |
| `pydantic` | 02 | Schema definitions for structured output |
| `pytest`, `ruff` | 01, 02 | Tests and formatting, wired into hooks and CI |

Create a minimal `app/pyproject.toml`:

```toml
[project]
name = "certification-coach"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100

[tool.ruff.lint]
# Pin the rule set explicitly. Ruff's default selection changes between
# releases, so an unpinned config means `pip install ruff` in CI can turn a
# green build red without anyone touching the code.
select = ["E4", "E7", "E9", "F", "I"]
```

That `select` line is not boilerplate. Module 01 has you write a CI workflow that runs
`ruff check .`, and module 01's `PostToolUse` hook runs `ruff format` on every save — so
the linter's opinion is wired into two places before you've written any application code.
Leaving the rule set to the tool's defaults means both can start failing on a day you
changed nothing. Pin it, and change it deliberately.

### Seed the corpus

The Coach needs something to generate questions *from*. Put the exam blueprint in as the
first corpus document:

```bash
cp ../references/exam-blueprint.md corpus/
```

You'll add more as you go — module 03's MCP server reads whatever is in `corpus/`.

---

## Checkpoint

Run each of these. All four must pass before module 01.

```bash
claude --version                              # → version + "(Claude Code)"
python --version                              # → 3.11 or newer
python -c "import anthropic, mcp, pydantic"   # → no output = success
ls app/corpus/                                # → exam-blueprint.md
```

If `python -c "import claude_agent_sdk"` also succeeds, module 04 will work. If it fails,
that's fine for now — fix it before module 04, not before module 01.

---

## Further reading

- [Claude Code quickstart](https://code.claude.com/docs/en/quickstart)
- [Agent SDK — Python](https://code.claude.com/docs/en/agent-sdk/python)
- [Claude Console](https://console.anthropic.com/) — set your spend limit here

---

**Next:** [Module 01 — Claude Code Configuration & Workflows](01-claude-code-config.md) (20% of the exam)
