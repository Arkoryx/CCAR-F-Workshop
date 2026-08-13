"""Data contract for generated practice questions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Domain(str, Enum):
    """The five CCAR-F exam domains, with their blueprint weights."""

    AGENTIC = "agentic_architecture"
    CLAUDE_CODE = "claude_code_config"
    PROMPTING = "prompt_engineering"
    TOOLS_MCP = "tool_design_mcp"
    CONTEXT = "context_reliability"


WEIGHTS: dict[Domain, float] = {
    Domain.AGENTIC: 0.27,
    Domain.CLAUDE_CODE: 0.20,
    Domain.PROMPTING: 0.20,
    Domain.TOOLS_MCP: 0.18,
    Domain.CONTEXT: 0.15,
}


class Choice(BaseModel):
    label: str = Field(description="Single uppercase letter, A through E.")
    text: str = Field(description="The answer option.")


class Question(BaseModel):
    domain: Domain
    stem: str = Field(description="The question. States how many answers to select.")
    choices: list[Choice]
    correct_labels: list[str] = Field(description="Labels of every correct choice.")
    explanation: str = Field(description="Why the answer is right AND why each distractor is wrong.")
    source: str = Field(description="Doc URL or blueprint domain backing this question.")

    # These validators run client-side, after the response arrives. The API does not
    # enforce them: length and count constraints are not part of the supported
    # JSON Schema subset. This is the gap you close in code.

    @field_validator("choices")
    @classmethod
    def four_or_five_choices(cls, v: list[Choice]) -> list[Choice]:
        if not 4 <= len(v) <= 5:
            raise ValueError(f"expected 4-5 choices, got {len(v)}")
        labels = [c.label for c in v]
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate choice labels: {labels}")
        return v

    @model_validator(mode="after")
    def answers_exist_and_are_not_all(self) -> Question:
        labels = {c.label for c in self.choices}
        unknown = set(self.correct_labels) - labels
        if unknown:
            raise ValueError(f"correct_labels reference missing choices: {sorted(unknown)}")
        if not self.correct_labels:
            raise ValueError("a question with no correct answer is not a question")
        if len(self.correct_labels) == len(self.choices):
            raise ValueError("every choice marked correct")
        return self


class QuestionBatch(BaseModel):
    questions: list[Question]
