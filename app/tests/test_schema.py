import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from coach.schema import Question

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_question_parses():
    payload = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    q = Question.model_validate(payload)
    assert q.correct_labels == ["C"]


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda p: p.update(correct_labels=[]), "no correct answer"),
        (lambda p: p.update(correct_labels=["Z"]), "answer references a missing choice"),
        (lambda p: p.update(correct_labels=["A", "B", "C", "D"]), "every choice correct"),
        (lambda p: p["choices"].pop(), "only three choices"),
        (lambda p: p["choices"].append({"label": "A", "text": "dupe"}), "duplicate label"),
    ],
)
def test_invalid_questions_rejected(mutate, reason):
    payload = json.loads((FIXTURES / "valid_question.json").read_text(encoding="utf-8"))
    mutate(payload)
    with pytest.raises(ValidationError):
        Question.model_validate(payload)
