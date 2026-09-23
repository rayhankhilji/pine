# Pine

Private Markets Intelligence Engine: an autonomous investment-diligence system that ingests a company data room and produces an auditable, evidence-backed investment model.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned automatically)
- [Node.js](https://nodejs.org/) 22+ and [pnpm](https://pnpm.io/) 9+
- Optional: `tesseract` for OCR (`brew install tesseract`)

## Quickstart

```bash
make install   # install api (uv sync) and web (pnpm install) deps
make api       # FastAPI on http://localhost:8000 (worker runs in-process)
make web       # Next.js on http://localhost:3000
```

Then open http://localhost:3000 — the home page shows the API status and lets you create a deal.

Other commands:

```bash
make test       # api test suite
make lint       # ruff + mypy + eslint
make typecheck  # mypy only
make generate   # regenerate web/src/lib/api/types.ts from the OpenAPI schema
```

## Configuration

Copy `api/.env.example` to `api/.env` and `web/.env.example` to `web/.env.local`. All variables and defaults are documented in `api/.env.example` and ARCHITECTURE §12. Defaults are fully local: SQLite at `./pine.db`, `LLM_PROVIDER=fake`, `EMBEDDINGS_PROVIDER=hash` — no keys needed to run.

## Docs

- `PRD.md` — product requirements and acceptance criteria
- `ARCHITECTURE.md` — binding technical contract (data model, API, AI subsystem)
- `INSTRUCTIONS.md` — agent/human operating manual
- `DESIGN_SYSTEM.md` — UI tokens and screen specs
- `EVAL_GUARDRAILS.md` — budgets and blocking evals
- `TESTING_GUIDE.md` — test strategy and acceptance matrix
- `ROADMAP.md` / `TASK_LOG.md` — plan and progress

## License

MIT — see `LICENSE`.
