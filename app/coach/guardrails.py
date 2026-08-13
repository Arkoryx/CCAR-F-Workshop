"""Permission callback and budget tracking for the Coach agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = (ROOT / "corpus").resolve()

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}


class BudgetExceeded(RuntimeError):
    """Raised when the agent exhausts its allotted turns."""


@dataclass
class Budget:
    """Turn accounting. The loop's third termination condition."""

    max_turns: int = 12
    turns_used: int = 0
    denials: list[str] = field(default_factory=list)

    def spend(self) -> None:
        self.turns_used += 1
        if self.turns_used > self.max_turns:
            raise BudgetExceeded(f"exceeded {self.max_turns} turns")

    @property
    def remaining(self) -> int:
        return max(0, self.max_turns - self.turns_used)


def is_in_corpus(raw_path: str) -> bool:
    """Resolve before comparing. Same rule as the module 01 hook."""
    if not raw_path:
        return False
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    return resolved == CORPUS or CORPUS in resolved.parents


def make_permission_callback(budget: Budget):
    """Build a can_use_tool callback bound to a budget.

    Returns PermissionResultAllow / PermissionResultDeny. Imported lazily so this
    module can be unit-tested without the SDK installed.
    """
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any):
        if tool_name in WRITE_TOOLS and is_in_corpus(input_data.get("file_path", "")):
            reason = f"{tool_name} blocked: the corpus is read-only"
            budget.denials.append(reason)
            return PermissionResultDeny(message=reason, interrupt=False)

        if budget.remaining == 0:
            reason = "turn budget exhausted"
            budget.denials.append(reason)
            return PermissionResultDeny(message=reason, interrupt=True)

        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool
