# Coding agent instructions

- Work one milestone at a time from `AGENTIC_SDLC_PLAN.md`.
- Do not begin the next milestone until every acceptance criterion for the current one passes.
- Use Python 3.11+, `uv`, pytest, Ruff, type hints, and Pydantic v2.
- Verify third-party APIs before use and pin dependency versions.
- Never place credentials in code, prompts, logs, traces, command arguments, or committed files.
- Put ambiguous decisions in `docs/DECISIONS.md` and continue.
- Keep GitHub, sandbox, and LLM integrations behind interfaces so tests can use fakes.

## Commands

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

