---
name: drill
description: Run a CCAR-F module's end-of-module exam drill — ten questions under near-exam conditions, scored, then walked one at a time, with results recorded so misses can be re-drilled. Use when the learner types /drill, with or without a module number.
---

# /drill — run one module's exam drill

Arguments: `$ARGUMENTS` — optionally a module (`01`), and optionally `--missed`.

The learner has finished a module's build and is now testing whether they can retrieve it.
Your job is to run a fair test and then explain the mechanism behind each answer. Not to
be encouraging, and not to defend the answer key.

---

## 0. Resolve the target

| Input | Target |
|---|---|
| `01` or `1` | module 01's drill |
| nothing | the highest module whose build is complete, from `.teach-progress.json` |
| `01 --missed` | only the questions missed on the last recorded run |
| `00`, `06` | **refuse** — neither has a drill |

Module 00 is setup and module 06 *is* an exam. If asked for either, say so and stop; do
not improvise questions.

For `--missed`, read `last.missed` from `.drill-results.json`. If there is no prior run, or
nothing was missed, say so rather than silently running the full drill.

## 1. Read the drill, and nothing else

Read `workshop/<MM>-*.md` and take the `## Exam drill` section. **Read no other module** —
reading ahead spoils material the learner has not reached. Never open the `solutions`
branch.

The drill is ten questions numbered `**N.**`, followed by one `<details>` block holding the
answer key as entries `**N — ...**`.

## 2. Pre-flight — validate the drill before running it

Check the section against itself:

- ten questions, ten key entries, each question with a matching entry
- for every question marked `*(Select two.)*` or `*(Select three.)*`, the key gives that
  many letters
- **for every key with more than one letter, the question says so** — a multi-answer key on
  a question with no `(Select N)` marker is a defect
- every letter in a key appears among that question's options

Report anything you find, then **run the drill anyway**. A defective question is still
worth attempting; the learner needs to know before they blame themselves for missing it.

> **This is not hypothetical.** Module 04's Q7 has a four-letter key and no multi-select
> marker. Module 01's Q4 once had two correct answers among its options. Both are the same
> defect, and both were found by comparing a drill against itself rather than by a reader.

## 3. Ask all ten — no verdicts

Present one question at a time, verbatim, with its options. Wait for an answer. Then the
next. **Say nothing about correctness until all ten are answered.**

This is the whole design. A verdict on Q2 changes how they approach Q3 — they recalibrate
against you instead of against the material, and the test stops measuring recall. It is the
same reason drills sit at the end of a module rather than after each build step.

If they ask mid-run whether they got one right, tell them you will cover it at the end and
move on. If they want to change an earlier answer before the tenth, let them.

### The hard rule

**Do not display the `<details>` block, any key entry, or any hint about an answer until
all ten answers are in.** Not a nudge, not "are you sure", not a raised eyebrow. Restating
the question is fine. Confirming you recorded their answer is fine.

## 4. Walk them, one at a time

Now go through the questions in order, **pausing between each** so every explanation gets
its own beat rather than arriving as one wall of text.

For each:

1. **Verdict** — correct or not, and what the key says.
2. **The mechanism**, not a restatement of the key. Why is the right answer right, and what
   would have to be true for the distractor they picked to be right? A wrong answer is
   usually a coherent model applied to the wrong thing; name the model.
3. **Where they met it**, if they did. Much of a module's drill is testable *because* the
   build exercised it. Module 01's Q2, Q3, Q4, Q6 and Q10 all have live counterparts in
   that module's build. Connecting the question to the moment it happened is worth more
   than the explanation alone.
4. **The exam framing** — one line on the testable idea, tied to the module's own task
   statements from its header.

## 5. Score

Compare their letters to the key's.

**Multi-select is all-or-nothing** — three of four correct scores zero. Say that this is
how *you* are scoring, and that whether the real exam awards partial credit on
multiple-response items is **unverified**: `references/exam-blueprint.md` comes from
third-party sources and does not say. Do not invent a rule and attribute it to the exam.

Report the score, the missed question numbers, and the module's domain from its header.
Note that the **module number is not the domain number** — module 01 is Domain 2, module 04
is Domain 1 — so read it from the file rather than inferring it.

**No manufactured precision.** Never convert a score into a predicted exam result, and
never quote a question count for a topic. The weightings are approximate and third-party.

## 6. Record the result

Write `.drill-results.json` at the repo root (gitignored, per-learner):

```json
{
  "01": {
    "domain": "Claude Code Configuration & Workflows",
    "runs": 2,
    "last": { "score": 8, "of": 10, "missed": [4, 8], "at": "2026-08-21T04:24:20Z" },
    "history": [ { "score": 6, "missed": [2, 4, 6, 8], "at": "2026-08-20T18:02:11Z" } ]
  }
}
```

Push the previous `last` onto `history` before overwriting it, increment `runs`, and use
ISO 8601 UTC. Create the file if absent; never disturb other modules' entries.

A `--missed` run records normally, with `missed` holding whatever they got wrong *this*
time — so repeated `--missed` runs converge rather than looping on the original set.

---

## When the learner disputes an answer

**Do not defend the key.** This workshop's keys have been wrong twice in ways that mattered:
once naming a `permissionDecision` value that never existed, once calling `defer` invented
when the installed SDK types it as valid. The second was *correct when written* and became
false as the SDK moved.

So when they push back with an actual argument:

1. **Check a primary source.** The installed package, the running binary, current docs —
   never memory. The shape of the check:
   ```bash
   python -c "import inspect, claude_agent_sdk.types as t; print(inspect.getsource(t.PreToolUseHookSpecificOutput))"
   ```
2. **If the key is wrong**, say so plainly, score in their favour, and offer the fix flow
   from `workshop/00-setup.md` §5 — correct it on `main` so the next person doesn't learn
   it wrong. Record the version you verified against; a key pinned to a moving SDK needs a
   version, not just a source.
3. **If the key is right**, explain the mechanism that makes it right. "The key says so" is
   not an answer, and this workshop has earned the right to be doubted.

If they are simply guessing rather than arguing, say what the mechanism is and move on.

## Standing rules

- Never read past the module being drilled. Never open `solutions`.
- Never reveal an answer before all ten are in.
- Verify facts against the installed package or current docs rather than recalling them.
- Answer *why* questions with the mechanism. They are studying for an exam; reassurance is
  worthless to them.
