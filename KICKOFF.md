# Workshop kickoff prompt

Paste everything below the line into a fresh Claude Code session started in the workshop
root.

The teaching protocol is **not** in here — it lives in `.claude/skills/teach/SKILL.md` and
loads when you run `/teach`. This file carries only what a cold session cannot discover
for itself: what the repo is, what is already true, and what never to do. One rule, one
home; a rule written in two places is a rule that will drift.

---

I'm working through a hands-on workshop to prepare for the **Claude Certified Architect –
Foundations (CCAR-F)** exam. The workshop is in this repo. I build a study app called the
Certification Coach, and building it is how I learn the five exam domains.

**Read `README.md` first.** Don't read ahead past the module I'm on.

## How this workshop is run

Two project skills drive it. Use them rather than walking the module markdown yourself:

- **`/teach`** — teaches the current build step. Sub-steps, each with the reasoning, and
  I attempt before you show me anything. `/teach 01.4` opens a specific step; bare
  `/teach` resumes where I left off. Invoke it **once per step** — the sub-steps happen in
  conversation after that.
- **`/check`** — grades a step against the module's real verifier checks and is the only
  thing that records progress. `/check 01.2` grades one step, `/check 01` runs the whole
  module checkpoint. Call it as often as I like.

If I ask you to just walk me through a module without the skills, that's fine — but the
skills are the intended path, and `/teach` is where the teaching rules live.

## Setup that already exists

- `.venv/` at the repo root, with `anthropic`, `claude-agent-sdk`, `mcp`, `pydantic`,
  `pytest`, and `ruff` installed. **Activation is per-shell.** PowerShell:
  `.venv\Scripts\Activate.ps1`. Git Bash: `source .venv/Scripts/activate` — `Scripts`, not
  the `bin` every Unix tutorial shows, and the extensionless `activate`, not
  `Activate.ps1`. If an import fails while `python --version` looks right, this is why;
  `which python` confirms it.
- `app/` is my workspace — what I build. Workshop content (`workshop/`, `references/`,
  `app/verify/`, `README.md`) lives on `main`; my build lives on my own branch. See
  `workshop/00-setup.md` §5.
- `app/verify/module_01.py` … `module_06.py` are checkpoint verifiers. Run them **from
  `app/`**. They're offline and free; `--live` adds real API calls.
- A complete reference implementation exists on the **`solutions` git branch** at
  `app/coach/`. All six verifiers pass against it.

## Standing rules

**Never open the `solutions` branch unless I ask.** Not to check my work, not to "confirm
the approach." If I'm stuck, help me reason from the error first. I'll ask for the
reference when I want it, with `git show solutions:app/coach/<file>.py`.

**Stop at every checkpoint.** Don't continue to the next step because the last one went
well. If a check fails, the failure message names what's wrong — start there, not by
rewriting from scratch.

**If you're unsure of a fact, check it.** Not from memory. This workshop has shipped
defects that were every one of them a plausible-sounding recalled fact — a class name, an
enum value, a package name, a threshold. Verify against the installed package, the running
binary, or the current docs:

```bash
python -c "from mcp.server import FastMCP; print(FastMCP)"   # the shape of the check
```

**Answer my questions properly.** I'm learning this for an exam, so when I ask why
something works, I want the mechanism, not reassurance. If I'm about to do something that
would pass the checkpoint but teach me the wrong model, say so.

## Things that are already known to be true

- **Before module 02, `corpus/` needs real source material.** It holds one 64-line
  blueprint file. Module 02 generates questions *from the corpus*, so with only that file
  the output will be thin and I'll wrongly blame my prompt.
- The drill answer keys have been audited against primary sources. Trust them more than
  you'd normally trust a quiz key — but the **blueprint weightings are third-party and
  unconfirmed**, so treat the 27/20/20/18/15 domain split as approximate, and never quote
  me a question count for a topic.
- Keys pinned to a moving SDK can rot. One drill answer was correct when written and
  false a version later. If a key and the installed package disagree, the package wins.
- These paths have **never been executed by anyone**: the MCP server has never been
  started, the agent has never run a batch, and no live API call has ever been made. If
  something breaks there, it's genuinely new — don't assume I did it wrong.

## Start here

Confirm the environment, then run `/teach` and pick up where I left off. If there's no
progress file yet, that means module 00.
