# Workshop kickoff prompt

Paste everything below the line into a fresh Claude Code session started in
`C:\Users\Eleko\Claude Training\CCAR-F Workshop`.

---

I'm working through a hands-on workshop to prepare for the **Claude Certified Architect –
Foundations (CCAR-F)** exam. The workshop is in this repo. I build a study app called the
Certification Coach, and building it is how I learn the five exam domains.

**Read `README.md` first, then `workshop/00-setup.md`.** Don't read ahead past the module
I'm on.

## Setup that already exists

- `.venv/` at the repo root, with `anthropic`, `claude-agent-sdk`, `mcp`, `pydantic`,
  `pytest`, and `ruff` installed. Activate with `.venv\Scripts\Activate.ps1`.
- `app/` is my workspace. It currently holds only `verify/` and `pyproject.toml` — the
  rest is what I'm about to build.
- `app/verify/module_01.py` … `module_06.py` are checkpoint verifiers. Run them **from
  `app/`**: `python verify/module_01.py`. They're offline and free; `--live` adds real
  API calls.
- A complete reference implementation exists on the **`solutions` git branch** at
  `app/coach/`. All six verifiers pass against it.

## How I want you to work with me

**I type the code. You don't build it for me.** The whole point is that I write it and
understand it. When a module says to create a file:

- Explain what it does and why it's shaped that way **before** any code appears.
- Then let me write it. Answer questions, review what I wrote, help me debug.
- If I explicitly ask you to write a file, write it — then walk me through it.

**Never open the `solutions` branch unless I ask.** Not to check my work, not to
"confirm the approach." If I'm stuck, help me reason from the error first. I'll ask for
the reference when I want it, with `git show solutions:app/coach/<file>.py`.

**Stop at every checkpoint.** When a module says to run a verifier, stop and have me run
it. Don't continue to the next section until it passes. If it fails, the failure message
names what's wrong — start there, not by rewriting from scratch.

**Answer my questions properly.** I'm learning this for an exam, so when I ask why
something works, I want the mechanism, not reassurance. If I'm about to do something that
would pass the checkpoint but teach me the wrong model, say so.

**If you're unsure of a fact, check it.** Not from memory. This workshop has already had
five defects fixed and every one was a plausible-sounding recalled fact — a class name, an
enum value, a package name, a threshold. Verify against the installed package, the running
binary, or the current docs:

```bash
python -c "from mcp.server import FastMCP; print(FastMCP)"   # the shape of the check
```

## Things that are already known to be true

- Modules 00 and 01 are fully verified. Start there.
- **Before module 02, `corpus/` needs real source material.** It currently holds one
  64-line blueprint file. Module 02 generates questions *from the corpus*, so with only
  that file the output will be thin and I'll wrongly blame my prompt.
- The drill answer keys at the end of each module have been audited against primary
  sources. Trust them more than you'd normally trust a quiz key — but the **exam blueprint
  weightings are third-party and unconfirmed**, so treat the 27/20/20/18/15 domain split
  as approximate.
- These paths have **never been executed by anyone**: the MCP server has never been
  started, the agent has never run a batch, and no live API call has ever been made. If
  something breaks there, it's genuinely new — don't assume I did it wrong.

## Start here

Confirm the environment (`python --version`, imports, `claude --version`), then walk me
into `workshop/00-setup.md`. Tell me roughly how long module 00 and module 01 should
take before we begin.
