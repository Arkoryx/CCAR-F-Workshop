"""Minimal check harness for workshop module verification.

Every module ships a `verify/module_NN.py` that asserts the module's end state.
The point: it does not matter how you or Claude got there. The destination is
checked, so a checkpoint that quietly stopped being true says so out loud.

Usage inside a module verifier:

    from _harness import Checks, PROJECT

    c = Checks("01")
    c.check("CLAUDE.md exists", lambda: (PROJECT / "CLAUDE.md").exists())
    raise SystemExit(c.report())

A check function returns either a bool, or a (bool, detail) tuple when you want
a failure message. Exceptions are caught and reported as failures — a verifier
should never crash, it should report.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

# app/ — the project root. verify/ lives directly inside it.
PROJECT = Path(__file__).resolve().parents[1]

CheckResult = bool | tuple[bool, str]

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


class Checks:
    """Collects check results and reports them with a process exit code."""

    def __init__(self, module: str) -> None:
        self.module = module
        self.results: list[tuple[bool, str, str]] = []

    def check(self, label: str, fn: Callable[[], CheckResult]) -> None:
        try:
            outcome = fn()
        except Exception as exc:  # a broken check is a failed check, not a crash
            self.results.append((False, label, f"{type(exc).__name__}: {exc}"))
            return

        if isinstance(outcome, tuple):
            ok, detail = outcome
        else:
            ok, detail = bool(outcome), ""
        self.results.append((bool(ok), label, detail))

    def report(self) -> int:
        """Print results. Returns an exit code: 0 all passed, 1 otherwise."""
        failed = [r for r in self.results if not r[0]]

        print(f"\n  Module {self.module} verification\n")
        for ok, label, detail in self.results:
            mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
            print(f"  [{mark}] {label}")
            if detail and not ok:
                print(f"         {DIM}{detail}{RESET}")

        total = len(self.results)
        passed = total - len(failed)
        print(f"\n  {passed}/{total} passed\n")
        return 1 if failed else 0


def file_exists(relative: str) -> Callable[[], CheckResult]:
    """Convenience: check a path exists relative to the project root."""

    def _check() -> CheckResult:
        path = PROJECT / relative
        return path.exists(), f"missing: {path}"

    return _check
