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
- Every generated question must map to a domain in `references/exam-blueprint.md`.
- Format with `ruff` before committing.
