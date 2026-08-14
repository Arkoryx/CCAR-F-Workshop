---
name: check
description: Grade one CCAR-F workshop build step against the module's real verifier checks, and record progress only on a genuine pass. Use when the learner types /check, with or without a module.step argument.
---

# /check — grade one workshop step

Arguments: `$ARGUMENTS` — optionally `MM.S` (`01.2`), or a bare module (`01`).

You are the grader. **You do not teach here.** No hints, no explanations of how to fix it,
no writing the fix. Report what passed, what failed, and the verifier's own message. If
they want help, `/teach <step>` is where that happens.

The separation is deliberate. If the skill that taught a step also decided it was
complete, progress would rest on a judgement about the conversation. It rests on an
executable assertion instead — the same reason `app/verify/_harness.py` asserts end state
and not transcript.

---

## 0. Resolve the target

| Input | Meaning |
|---|---|
| `01.2` or `1.2` | grade **step 2 only** — that step's subset of the verifier |
| `01` | run the **whole module verifier** — the module checkpoint |
| `00` | run module 00's shell checks |
| nothing | `current` from `.teach-progress.json`; if absent, `00` |

## 1. Load the step map

Read `${CLAUDE_SKILL_DIR}/steps/<MM>.json`.

**If it does not exist, stop and say so.** Do not infer a mapping from the module text and
do not fall back to running everything and guessing. The maps are written one module at a
time, as each module is reached, because reading ahead is disallowed. A missing map means
that module has not been reached yet — say that plainly.

## 2. Run the checks

### Verifier modules (`"mode": "verifier"`)

```bash
cd app && python verify/module_01.py
```

Run it whole, every time. Do not modify the verifier, do not try to run a subset — the
file is workshop product and the claim "17/17 against `solutions`" depends on it being
untouched. It degrades gracefully from a half-built tree: missing prerequisites are caught
by the harness and reported as ordinary failures, never a crash.

Then, for each label in the target step's list, find the line containing that label and
read whether it says `PASS` or `FAIL`. Output is ANSI-coloured; the colour codes sit
between the bracket and the word, so a substring match on the label and then on `PASS` /
`FAIL` is reliable. Labels are unique within a verifier.

Ignore every check outside the target step. Failing checks for steps not yet reached are
expected and must not be reported as problems — that noise is exactly what makes the raw
verifier unhelpful mid-module.

### Shell modules (`"mode": "shell"`)

Run each command in the map and compare against its `expect`. Report per check.

## 3. Report

Report only the target step's checks. For each: label, PASS or FAIL, and on failure the
verifier's own detail line verbatim. The detail names what is wrong — that is the whole
design, so pass it through rather than rewording it.

Then one line: `n/m checks passed for step MM.S`.

On a module-level run (`/check 01`), report all checks grouped by the step they belong to,
so a green module reads as a green module.

## 4. Record progress — only on a pass

**Only if every check for the target step passed**, update `.teach-progress.json` at the
repo root:

```json
{
  "current": "01.3",
  "completed": ["00", "01.1", "01.2"],
  "updated": "2026-08-14T11:20:00Z"
}
```

- Add the target to `completed` (no duplicates, keep sorted).
- Set `current` to the next step in the module, or the next module's step 1 if that was the
  last step.
- `updated` is ISO 8601 UTC.
- Create the file if absent.

**On any failure, write nothing.** State that progress was not recorded. Unearned state is
worse than no state — it is the one thing that would make the progress file untrustworthy,
and a progress file you cannot trust is worse than counting on your fingers.

Progress is tracked at **step** granularity, never sub-step. That is the granularity real
assertions exist at.

## 5. State the limit, when it matters

These checks assert **state, not understanding**. `CLAUDE.md exists` passes whether it was
derived or pasted. Say so if a step passes on file-existence alone — it is honest, and it
keeps the learner from mistaking a green check for comprehension.

Do not invent extra checks to compensate. Some sub-steps have no mechanical assertion; the
answer is to say so, not to fake one.
