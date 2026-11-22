# Agentic SDLC

Agentic SDLC turns a natural-language product brief into a reviewed release pull request. A PM
agent coordinates specialist agents while a deterministic controller enforces lifecycle gates,
budgets, and repository safety. Agents may merge reviewed task pull requests into `integration`;
only a human can merge the final release into `main`.

The implementation follows [AGENTIC_SDLC_PLAN.md](AGENTIC_SDLC_PLAN.md) one milestone at a time.

## AI engineering team

The agent runtime is PM-led and built with Deep Agents. `build_team()` creates six isolated
specialists:

- architect: architecture, contracts, data models, and ADRs;
- coder: backend and general implementation tasks;
- UI developer: accessible front-end implementation and UI tests;
- DevOps: scaffolding, CI, containers, and build configuration;
- QA tester: independent acceptance verification with structured `TestReport` output;
- reviewer: read-only review with a head-SHA-bound structured `ReviewVerdict`.

Every specialist has an explicit custom-tool list, its own model selection, a focused prompt, and a
role-specific skill set. PM, architect, QA, and reviewer writes are constrained by Deep Agents
filesystem permissions. GitHub tools are optional and supplied through the `RoleToolProvider`
interface, so the complete team can be composed and tested without GitHub credentials.

Required model configuration uses LangChain's `provider:model` form:

```bash
export PM_MODEL=openai:gpt-6-astra
export ARCHITECT_MODEL=openai:gpt-6-astra
export CODER_MODEL=openai:gpt-6.2-sol
export REVIEWER_MODEL=openai:gpt-6-astra
export OPENAI_API_KEY=...
```

Build the graph with an appropriate Deep Agents backend and durable checkpointer:

```python
from agentic_sdlc.config import Settings
from agentic_sdlc.team import build_team

settings = Settings.from_env()
team = build_team(
    backend=sandbox_backend,
    checkpointer=checkpointer,
    settings=settings,
)
```

The backend determines whether shell execution is available. Production execution must use an
isolated sandbox backend; filesystem permissions alone do not constrain shell commands.

## FastAPI

The API runs projects in the background and exposes status, server-sent events, clarification
answers, cancellation, and generated artifacts. Start it with:

```bash
uv sync --locked
uv run agentic-sdlc-api
```

Check readiness before spending a model call:

```bash
curl http://127.0.0.1:8000/ready
```

Submit a small product:

```bash
curl -X POST http://127.0.0.1:8000/projects \
  -H 'Content-Type: application/json' \
  -d '{"brief":"Create a small Python CLI that stores and lists notes in a JSON file"}'
```

Use the returned ID with `GET /projects/{id}` and `GET /projects/{id}/events`. Download a generated
file with `GET /projects/{id}/artifacts/{path}`. Interactive answers and cancellation use
`POST /projects/{id}/answers` and `POST /projects/{id}/cancel`.

The current runner is deliberately file-only. It can generate a small product through the real
Deep Agents team when model settings and the provider API credential are present, but it cannot yet
execute or test generated code. Docker-sandbox execution is the next runtime capability.

## Web console

The React console in `frontend/` accepts a natural-language product brief and follows the project
worker in real time. It shows runtime readiness, delivery phases, streamed activity, clarification
input, cancellation controls, and downloadable artifacts. Recent project IDs stay in browser
storage; generated source stays on the API host under `.agentic-sdlc/projects/<project-id>/`.

With the API running, start the UI in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies API and documentation requests to port 8000.

Frontend verification is lockfile-backed:

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

## Development setup

Prerequisites: Python 3.11 or newer and `uv`.

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Runtime and development dependencies are exactly pinned in `pyproject.toml` and transitively
locked in `uv.lock`.

## M0: target repository bootstrap

`scripts/bootstrap_product_repo.py` is an administrator-operated, one-time setup utility. It
creates a repository with `main` and `integration`, installs a minimal CI workflow and CODEOWNERS,
then protects both branches. It is deliberately not part of the agent runtime.

Set an administrator credential only in the process environment:

```bash
export GITHUB_ADMIN_TOKEN=github_pat_...
uv run python scripts/bootstrap_product_repo.py \
  --owner example-org \
  --name generated-product \
  --codeowner '@example-org/platform-reviewers'
```

Use `--personal` when creating the repository for the authenticated user rather than an
organization. Run with `--dry-run` to print the intended operations without using a credential or
changing GitHub.

The bootstrap credential needs repository administration and workflow-content access. It must not
be shared with agents. The separate runtime GitHub App is expected to have Contents, Pull requests,
Issues, and Workflows permissions described in the plan, but no Administration permission.

After setup, manually verify with the runtime GitHub App installation token:

1. A checked and approved task PR can be merged into `integration`.
2. A direct push or merge to `main` is rejected.

This live permission check cannot be performed by the local test suite because it requires a real
GitHub organization, App installation, and human reviewer.

