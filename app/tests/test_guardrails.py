import pytest

from coach.guardrails import Budget, BudgetExceeded, is_in_corpus


def test_corpus_paths_detected():
    assert is_in_corpus("corpus/exam-blueprint.md")
    assert is_in_corpus("coach/../corpus/sneaky.md")


def test_non_corpus_paths_allowed():
    assert not is_in_corpus("coach/schema.py")
    assert not is_in_corpus("corpus_notes.py")   # substring, not the directory


def test_budget_raises_when_exhausted():
    budget = Budget(max_turns=2)
    budget.spend()
    budget.spend()
    with pytest.raises(BudgetExceeded):
        budget.spend()
