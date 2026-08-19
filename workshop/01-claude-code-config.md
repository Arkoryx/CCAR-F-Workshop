# Module 01 — Claude Code Configuration & Workflows

**Domain 2 · 20% of the exam · ~12 of 60 questions**

Task statements covered: configuring Claude Code for development workflows; managing
settings; implementing hooks; scoping permissions; integrating with CI/CD.

Time: 2–4 hours.

---

## Why this module is first

You build the rest of the Coach *inside* this configuration. Module 03's MCP server gets
registered here. Module 02's formatting is enforced by a hook you write here. And the
20% weighting means roughly one exam question in five is about the thing you're setting
up right now.

---

## Concept brief

### Settings live in four places, and precedence is not alphabetical

| Scope | File | Applies to | In git? |
|---|---|---|---|
| Managed | org-deployed policy | everyone in the org | deployed by IT |
| User | `~/.claude/settings.json` | you, every project | no |
| Project | `.claude/settings.json` | everyone on the repo | **yes** |
| Local | `.claude/settings.local.json` | you, this repo | no (gitignored) |

**Precedence, highest first:** Managed → command-line args → Local → Project → User.

Two things trip people up:

1. **User settings are the *lowest* priority**, not the highest. Your personal
   `~/.claude/settings.json` loses to anything the project defines.
2. **Permission rules merge across scopes** rather than overriding wholesale. A project
   `deny` rule isn't erased by a user-level `allow`.

### Permissions: allow / ask / deny

Rules are `Tool(pattern)`:

```json
{
  "permissions": {
    "allow": ["Bash(pytest *)", "Read(./src/**)"],
    "ask":   ["Write(./config.json)"],
    "deny":  ["Read(./.env)", "Bash(curl *)"]
  }
}
```

`*` matches any string, `**` matches any directory depth, `~` expands to home. **`deny`
is the one that matters for safety** — it's the rule that can't be talked around by the
model, which is why secrets belong there and not in a `CLAUDE.md` sentence asking nicely.

### Hooks: deterministic control over a non-deterministic agent

A hook is a command the harness runs at a lifecycle point. It is *not* Claude deciding to
do something — it's your code, running every time, regardless of what the model wants.
That distinction is the whole point, and it's what the exam tests.

Events you should know: `PreToolUse` (can block), `PostToolUse`, `PostToolUseFailure`,
`UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`, `PreCompact`/`PostCompact`,
`SubagentStart`/`SubagentStop`.

**How a hook blocks:**

- **Exit code 2** → blocking error. The action is blocked.
- **Exit code 0** → success; stdout is read for a JSON decision. No JSON means normal flow.
- **Any other code** → non-blocking error. The action proceeds, the error is logged.

For `PreToolUse`, the JSON decision looks like:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Corpus files are read-only"
  }
}
```

`permissionDecision` is `"allow"`, `"deny"`, or `"ask"`. `"ask"` is the middle setting:
the hook declines to decide and hands the call back to the normal permission flow, which
prompts the user. Contrast that with exiting 0 and printing nothing, which is *no
opinion* — see drill Q3.

> **A fourth value exists in the Agent SDK.** `claude-agent-sdk` 0.2.137 types
> `permissionDecision` as `Literal["allow", "deny", "ask", "defer"]`
> (`types.py`, `PreToolUseHookSpecificOutput`). `"defer"` halts the run and returns the
> tool call to your code as a `DeferredToolUse`, so the caller can inspect it and decide
> whether to resume — which requires a programmatic caller that *can* resume. For
> Claude Code CLI hooks, the set to know is **allow / deny / ask**.

### Matchers

The `matcher` field decides when a hook fires. Its syntax is subtle:

| Matcher | Interpreted as |
|---|---|
| `"*"`, `""`, or omitted | match everything |
| Letters, digits, `_`, `-`, spaces, `,`, `\|` | exact string(s) — `Bash`, `Edit\|Write` |
| Anything else | **regex**, unanchored — `^Notebook`, `mcp__memory__.*` |

So `Edit|Write` is two exact names, but `.*Edit` is a regex. MCP tools are matched as
`mcp__<server>__<tool>`.

---

## Build

### Step 1 — `CLAUDE.md`

This is project memory, loaded into every session. Keep it to what only you know — the
model already knows Python.

Create `app/CLAUDE.md`:

```markdown
# Certification Coach

A study agent for the Claude Certified Architect – Foundations (CCAR-F) exam. It reads a
corpus of study material, generates exam-format practice questions, critiques them, and
tracks weak domains across sessions.

## Layout
- `coach/` — the package
- `coach/mcp_server/` — MCP server exposing the study corpus
- `corpus/` — source material. **Read-only.** Never edit or delete files here.
- `tests/` — pytest

## Conventions
- Questions are Pydantic models, never raw dicts. Schema lives in `coach/schema.py`.
- Every generated question must map to a domain in `corpus/exam-blueprint.md`.
- Format with `ruff` before committing.
```

Two things to notice about what you just wrote, because both recur.

**Every path in that file resolves relative to `app/`,** where `CLAUDE.md` lives. The
blueprint line points at `corpus/exam-blueprint.md` — the copy you made in module 00 —
not at `../references/exam-blueprint.md`, the canonical file at the repo root. Both exist
and both contain the same text, so the distinction looks pedantic until module 03, when
the MCP server starts serving the corpus and the Coach has exactly one supported way to
reach its material. Project memory should describe the architecture you're building, not
a shortcut around it.

**`Format with ruff before committing` is about to become redundant.** Step 4's
`PostToolUse` hook runs `ruff format` on every write, whether or not the model read this
line. Keep it — it's useful to a human reading the repo — but watch what happened: an
instruction *asking* the model to cooperate got superseded by a mechanism that doesn't
need it to. That is this module's entire thesis, and `corpus/` is about to get the same
treatment three times over.

### Step 2 — Permissions

Create `app/.claude/settings.json`:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(pytest *)",
      "Bash(ruff *)",
      "Bash(python -m coach *)",
      "Read(./corpus/**)",
      "Write(./coach/**)",
      "Write(./tests/**)"
    ],
    "ask": [
      "Bash(pip install *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Write(./corpus/**)"
    ]
  }
}
```

Note what's happening: the corpus is readable but **denied for writes at the permission
layer**, and separately protected by a hook in step 3. That redundancy is deliberate —
you'll see why in the drill.

Two details in the `deny` list are worth more than they look.

**`.env` is a file, not a directory.** Your own `.gitignore` makes the distinction —
`.venv/` has a trailing slash, `.env` doesn't. So `Read(./.env/**)` would match paths
inside a directory that doesn't exist *and stop matching the file itself*: a rule that
reads as protection and enforces nothing. The verifier now rejects that specific mistake,
because it is an easy one to make and impossible to notice.

**Two `.env` rules, because the gap is siblings, not nesting.** Real projects accumulate
`.env.local`, `.env.production`, `.env.development` — separate files in the same
directory. `Read(./.env)` catches one of them. `Read(./.env.*)` is a literal dot then
anything, deliberately narrower than `.env*`, which would also swallow `.envrc`.

The general lesson, and it outlives this config: a `deny` rule protects exactly what its
*pattern* matches. Getting the mechanism right and the pattern wrong buys you the
confidence of enforcement with the coverage of nothing.

### Step 3 — A `PreToolUse` hook that protects the corpus

Hooks can be any executable. This project is Python, so write the hook in Python rather
than bash — it works identically on Windows and POSIX.

Create `app/.claude/hooks/protect_corpus.py`:

```python
#!/usr/bin/env python3
"""Block any write or edit targeting the read-only corpus directory."""
import json
import sys
from pathlib import Path

payload = json.load(sys.stdin)
target = payload.get("tool_input", {}).get("file_path", "")

if target:
    # Resolve against the cwd the payload gives us, never the hook process's own
    # cwd. Joining an absolute target discards the left side, so this is correct
    # whether Claude Code sends an absolute path or a relative one.
    cwd = Path(payload["cwd"])
    resolved = (cwd / target).resolve()
    corpus = (cwd / "corpus").resolve()
    if resolved == corpus or corpus in resolved.parents:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{resolved.name} is in the read-only corpus. "
                    "Generated artifacts belong in coach/ or tests/."
                ),
            }
        }, sys.stdout)

sys.exit(0)
```

Note it resolves paths before comparing. A hook that string-matches `"corpus"` is trivially
defeated by `./coach/../corpus/notes.md`.

### Step 4 — A `PostToolUse` hook that formats on save

Add both hooks to `app/.claude/settings.json`. **`hooks` is a sibling of `permissions`,
not a replacement for it** — merge the block below into the file from step 2. Pasting it
over the file drops your permission rules, and because a settings file that parses is
never reported as wrong, nothing will tell you. Your finished file has three top-level
keys: `$schema`, `permissions`, `hooks`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/protect_corpus.py\"",
            "statusMessage": "Checking corpus protection..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "ruff format \"${CLAUDE_PROJECT_DIR}\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

`Write|Edit` is an exact-string matcher listing two tools — not a regex, because it
contains only letters and a pipe.

### Two ways a correct hook silently does nothing

**Quote the path.** `${CLAUDE_PROJECT_DIR}` expands to a real directory, and real
directories contain spaces — `C:\Users\Jane Smith\...`, `~/Library/Application Support/...`.
The shell splits arguments on whitespace before the program sees them, so an unquoted path
arrives as several fragments:

```
PreToolUse:Write hook error
Failed with non-blocking status code:
  python.exe: can't find '__main__' module in 'C:\Users\Jane'
```

Note **non-blocking**. The hook crashed, so it returned no decision, so **the write went
through**. Corpus protection registered, visible in `/hooks`, and completely inert. Both
commands above are quoted for exactly this reason.

**Hooks inherit the environment of the Claude Code process, not your shell's.** Launch
`claude` from a terminal where the virtualenv isn't active and the hook's `python` resolves
to the system interpreter, while `ruff` isn't on `PATH` at all:

```
PostToolUse:Write hook error
Failed with non-blocking status code: bash: line 1: ruff: command not found
```

Activate the venv *before* launching `claude`. The corpus hook survives an inactive venv
only because it imports nothing but `json`, `sys`, and `pathlib` — keep it that way, and
keep any hook that guards something dependency-free.

> **Neither failure produces a red checkpoint.** The verifier executes your hook directly
> with a synthetic payload, which proves the *script* is correct and says nothing about
> whether Claude Code can invoke it. The only test for that is a real corpus write in a
> session rooted at `app/` — do it once at the end of this module, and watch for your own
> `permissionDecisionReason` coming back.

### Step 5 — A subagent

Subagents live in `.claude/agents/`. You'll use this one in module 04, but define it now
so you can see how the harness-level and SDK-level definitions differ.

Create `app/.claude/agents/question-critic.md`:

```markdown
---
name: question-critic
description: Reviews draft exam questions for ambiguity, multiple defensible answers, and blueprint traceability. Use after generating questions, before saving them.
tools: Read, Grep, Glob
---

You review draft CCAR-F practice questions. For each question, check:

1. **Exactly one defensible answer.** If a distractor is arguably correct under some
   reading, say so and quote the ambiguity.
2. **Traceability.** The question must map to a domain in the blueprint. Name the domain
   or flag it as untraceable.
3. **Distractor quality.** Distractors should be plausible to someone who half-knows the
   material, not obviously wrong.
4. **No trivia.** Test judgment and mechanism, not memorized version strings.

Report findings per question. Do not rewrite the questions — that's the generator's job.
You are read-only by design.
```

The `tools:` line restricts it to read-only tools. A critic that can edit the thing it's
critiquing is not a critic.

### Step 6 — CI

Create `app/.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e . && pip install pytest ruff
      - run: ruff check .
      - run: pytest -q
```

Add a placeholder test so CI has something to run — `app/tests/test_smoke.py`:

```python
def test_imports():
    import coach  # noqa: F401
```

And `app/coach/__init__.py` (empty file).

---

## Checkpoint

You should now have this:

```
app/
  CLAUDE.md
  pyproject.toml
  .claude/
    settings.json
    hooks/protect_corpus.py
    agents/question-critic.md
  .github/workflows/ci.yml
  coach/__init__.py
  corpus/exam-blueprint.md
  tests/test_smoke.py
  verify/_harness.py
  verify/module_01.py
```

Run the verifier from `app/`:

```bash
python verify/module_01.py
```

Every line must read `PASS`. The script exits non-zero if any check fails, so it works in
CI too.

What it checks, and why these and not others:

| Check | Why it's here |
|---|---|
| Files exist | Cheap, catches typos in paths |
| `settings.json` parses | A malformed settings file fails *silently* — Claude Code just runs without it |
| A **`Write`** `deny` rule covers `corpus/` | Asserts the boundary is a rule, not a `CLAUDE.md` sentence — and that it stops *writes*. A `Read` deny on `corpus/` inverts the intent and used to pass |
| A **`Read`** `deny` rule covers `.env`, and doesn't treat it as a directory | `Read(./.env/**)` matches paths inside a directory that doesn't exist, and stops covering the file. It reads as protection and enforces nothing |
| `PreToolUse` **and** `PostToolUse` matchers are `Write\|Edit` | Catches the classic wrong-matcher bug, and that `hooks.<event>` is a *list* of matcher groups — collapsing it to one object is easy and fails with an unhelpful error |
| The `PreToolUse` command names a script that exists | A registration pointing at a missing file enforces nothing. Basename only — it does not prove the directory is right |
| `question-critic` exists and has no `Write`/`Edit`/`Bash` | A critic that can edit its own subject isn't a critic |
| **The hook denies a corpus write** | Executes your hook with synthetic stdin and asserts the decision |
| **The hook allows a `coach/` write** | Guards against a hook that denies everything and looks like it works |
| **The hook denies `coach/../corpus/x.md`** | The path-traversal case a string match misses |

Those last three matter most. Previously this checkpoint said "ask Claude to edit a corpus
file and see if it's denied" — which depends on how Claude phrases the request, which tool
it picks, and whether it decides to try at all. The verifier calls your hook directly with
a fixed payload, so the answer is the same every run. **That's the module's own lesson
applied to the module: deterministic control over a non-deterministic agent.**

Also confirm CI passes locally:

```bash
ruff check . && pytest -q
```

### Optional: wire the verifier into CI

Add to `.github/workflows/ci.yml`, after the `pytest` step:

```yaml
      - run: python verify/module_01.py
```

Now a change that breaks your hook fails the build.

---

## Exam drill

Ten questions in exam format. Answer before scrolling.

**1.** A project's `.claude/settings.json` sets `"model": "claude-sonnet-5"`. Your
`~/.claude/settings.json` sets `"model": "claude-opus-5"`. Which applies?

A. `claude-opus-5` — user settings are most specific to you
B. `claude-sonnet-5` — project settings outrank user settings
C. Neither; conflicting model settings are an error
D. Whichever file was modified most recently

**2.** Which exit code from a `PreToolUse` hook blocks the tool call?

A. 0 B. 1 C. 2 D. Any non-zero code

**3.** A hook exits 0 and prints nothing to stdout. What happens?

A. The tool call is blocked
B. The tool call proceeds normally
C. The user is prompted to approve
D. The hook is retried once

**4.** Which matcher fires on **exactly** the `Bash` and `Edit` tools, and nothing else?

A. `"Bash.*Edit"` B. `"Bash|Edit"` C. `"(Bash|Edit)"` D. `"*"`

**5.** Where do project-scoped subagent definitions live?

A. `.claude/settings.json` under `agents`
B. `.claude/agents/`
C. `~/.claude/agents/`
D. `.mcp.json`

**6.** You want a secret file unreadable by Claude Code in a shared repo. Best mechanism?

A. A sentence in `CLAUDE.md` saying not to read it
B. A `deny` rule in `.claude/settings.json`
C. An `ask` rule in `.claude/settings.local.json`
D. A `PostToolUse` hook that logs reads

**7.** Which two settings require a restart or `/clear` rather than reloading live?
*(Select two.)*

A. `permissions` B. `model` C. `hooks` D. `outputStyle` E. `env`

**8.** In a **Claude Code** `PreToolUse` hook's JSON output, which values are valid for
`permissionDecision`? *(Select three.)*

A. `allow` B. `deny` C. `ask` D. `escalate` E. `confirm`

**9.** Which file should be committed to git so the whole team shares the configuration?

A. `.claude/settings.local.json`
B. `.claude/settings.json`
C. `~/.claude/settings.json`
D. `~/.claude.json`

**10.** A hook must protect `./corpus/`. Which implementation is sound?

A. Reject any `file_path` whose string contains `corpus`
B. Resolve `file_path` to an absolute path and check whether the corpus directory is the
   path or one of its parents
C. Reject writes when the session's cwd is `corpus`
D. Check the file extension against an allowlist

<details>
<summary><b>Answer key</b></summary>

**1 — B.** Precedence is Managed → CLI args → Local → Project → User. User settings are
the *lowest* priority. This inverts most people's intuition.

**2 — C.** Exit 2 is the blocking error. Exit 0 means success (and stdout is checked for a
JSON decision); any other non-zero code is a *non-blocking* error — the action proceeds
and the error is logged. D is the trap: only 2 blocks.

**3 — B.** Exit 0 with no JSON on stdout means the hook reports *no decision*, and the
action continues through the normal permission flow. Hooks are opt-in interference.

Precisely: silence is not "approved", it's "no opinion" — whatever your `permissions`
rules would have done still happens, prompt included. C is wrong because the *hook*
didn't cause a prompt, not because a prompt is impossible.

**4 — B.** A matcher containing only letters, digits, `_`, `-`, spaces, `,`, and `|` is
treated as exact string(s). Add **any** other character and the whole matcher becomes a
JavaScript regex tested with `RegExp.prototype.test` — which succeeds on a match
*anywhere* in the tool name, not just a whole-string match.

That unanchored behaviour is what makes C wrong: the parentheses tip it onto the regex
path, and `(Bash|Edit)` then also fires on `NotebookEdit`, because `Edit` appears inside
it. A is a regex too, and matches neither tool — it needs `Bash` and `Edit` in the *same*
name, like `BashEdit`. To get whole-string matching out of a regex you must anchor it
yourself: `^(Bash|Edit)$`.

> Verified against Claude Code's hooks reference. This question originally offered
> `^(Bash|Edit)$` as option C — which is *also* correct, making the question unanswerable.
> Caught during an audit of these keys, not by a reader.

**5 — B.** `.claude/agents/` for project scope, `~/.claude/agents/` for user scope.

**6 — B.** A `deny` rule is enforced by the harness. `CLAUDE.md` is a prompt — it asks
the model to behave, which is not a security boundary. This distinction (deterministic
enforcement vs. instruction) is the single most testable idea in this domain.

**7 — B and D.** `model` and `outputStyle` are read once at session start. The docs name
exactly these two: `model` (switch mid-session with `/model` instead) and `outputStyle`
(part of the system prompt, rebuilt on `/clear` or restart). `permissions` and `hooks`
are documented as reloading live — Claude Code watches the settings files.

`env` is the honest gap here: it is not named in either list. Live reload is the
documented default for "most keys", so `env` is *probably* live, but process-environment
variables are exactly the kind of thing usually fixed at startup. Treat it as unverified
rather than assuming — and note that the question doesn't depend on it.

**8 — A, B, C** — `allow`, `deny`, `ask`. Straight from Claude Code's own hooks
reference:

> `permissionDecision` — `"allow"`, `"deny"`, or `"ask"` (PreToolUse only)

`ask` is the one people miss. It hands the decision back to the normal permission flow
and prompts the user — the middle setting between the hook deciding for you and the hook
staying out of it. `escalate` and `confirm` are invented.

> **On `defer`.** This question originally offered `defer` as option E and the key called
> it invented. That is no longer true: `claude-agent-sdk` 0.2.137 types
> `permissionDecision` as `Literal["allow", "deny", "ask", "defer"]`, with a
> `DeferredToolUse` dataclass behind it. With `defer` on the list, a "select three"
> question had four defensible answers — the same defect Q4 had. The option was replaced
> and the question scoped to **Claude Code** hooks.
>
> Keep the distinction: `defer` halts the run and hands the tool call back to *your code*
> to resume or abandon, which presupposes a programmatic caller. That is an Agent SDK
> capability, not something an interactive CLI session has anywhere to return to. The
> concept brief covers it.

> **This key was wrong until an audit caught it, and the way it was wrong is worth more
> than the fact.** It previously said `escalate` — a plausible-sounding word that appears
> nowhere in the API. It was never checked; it was recalled, written down confidently,
> and would have taught you a value that does not exist. Nothing would have errored: you
> would have found out by writing a hook that silently did nothing.
>
> The fix came from grepping the installed binary, which is as close to ground truth as
> this gets:
>
> ```bash
> grep -ao 'permissionDecision` - "allow[^`]*' ~/.local/share/claude/versions/<version>
> ```
>
> Same lesson as module 03's import: when a fact is cheap to check against the thing
> itself, check it against the thing itself.

**9 — B.** `.claude/settings.json` is the shared, committed project file.
`settings.local.json` is gitignored and personal.

**10 — B.** Path resolution before comparison. A is defeated by `./coach/../corpus/x.md`
and also false-positives on `corpus_notes.py`. This is the same class of bug as
path-traversal in a file-serving tool — worth internalizing now, because module 03 asks
you to write tool handlers that take model-supplied paths.

</details>

---

## Further reading

- [Settings reference](https://code.claude.com/docs/en/settings)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Subagents](https://code.claude.com/docs/en/sub-agents)
- [Permission modes](https://code.claude.com/docs/en/permission-modes)

---

**Next:** Module 02 — Prompt Engineering & Structured Output (20%)
