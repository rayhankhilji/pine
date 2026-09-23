# Pine — Task Log

> Updated 2026-09-23 · The running record of what is done, in progress, and decided. Agents update this file every session.

## Status

**Phase 0 — Foundation: in progress.** Monorepo scaffolded, API skeleton live (health, auth, error envelope), Alembic wired, web shell rendering API status, CI in place. Remaining: request-id + JSON logging, full Settings env vars, job worker, deals CRUD, design tokens + app shell, OpenAPI codegen, README quickstart.

## Current Phase Checklist

Phase 0 — Foundation (copied from ROADMAP.md):

- [x] P0.T1 — Init `api/` with uv (Python 3.12 pinned), FastAPI app factory, `Settings`, `/api/v1/health` · refs: ARCHITECTURE §2, §12 · verify: `uv run --directory api pytest -q tests/test_health.py`
- [ ] P0.T2 — SQLAlchemy 2 `Base`, session dependency, Alembic wired to `DATABASE_URL`, empty initial migration · refs: ARCHITECTURE §4 Migrations · verify: `uv run --directory api alembic upgrade head`
- [~] P0.T3 — Error envelope (`AppError`, validation, internal handlers) done; request-id middleware + JSON logging still pending · refs: ARCHITECTURE §5 conventions, §14 · verify: `tests/test_errors.py`
- [x] P0.T4 — API-key middleware with `compare_digest`, open when unset · refs: ARCHITECTURE §11 · verify: `tests/test_auth.py`
- [ ] P0.T5 — `Job` model + worker loop (poll, lock, retry/backoff, stale-lock release) + `enqueue()` + `pine worker` CLI · refs: ARCHITECTURE §9 · verify: `tests/jobs/test_worker.py` (job runs, retries 3×, dead-letters)
- [ ] P0.T6 — `Deal` model, migration, `POST/GET/PATCH/DELETE /deals` with cursor pagination · refs: F-01, ARCHITECTURE §5 · verify: `tests/api/test_deals.py`
- [x] P0.T7 — ruff + mypy strict config; `.github/workflows/ci.yml` api job · verify: CI green on push
- [x] P0.T8 — Init `web/` (Next 16, TS strict, Tailwind 4, shadcn), `lib/api/client.ts` with `ApiError`, providers, home page with health status (loading/ok/error) · refs: ARCHITECTURE §7 · verify: `pnpm -C web lint && pnpm -C web build`
- [ ] P0.T9 — Design tokens in `globals.css` per DESIGN_SYSTEM §2–§6; app shell layout (`deals/[id]/layout.tsx` nav) with placeholder pages for every route in ARCHITECTURE §7, each with `loading.tsx` and `error.tsx` · verify: visual check, `pnpm -C web build`
- [ ] P0.T10 — `make generate`: OpenAPI → `web/src/lib/api/types.ts` via openapi-typescript; CI web job · verify: `make generate && git diff --exit-code web/src/lib/api/types.ts` in CI
- [ ] P0.T11 — Root `Makefile`, `.env.example`s, `.gitignore`, LICENSE (MIT), README quickstart · verify: fresh clone follows README to green

## Up Next

Phase 1 — Ingestion & document intelligence (first tasks):
- P1.T1 — Models + migration: `Blob, Document, Page, Block, Table, Cell`
- P1.T2 — `BlobStore` (sha256 content-addressed)
- P1.T3 — Upload service with zip expansion + guards

## Blockers

None.

## Decisions & Deviations

| Date | Decision | Context |
|---|---|---|
| 2026-09-23 | Next.js **16** (not 15) | `create-next-app@latest` scaffolds 16.3.6; ARCHITECTURE §2 diagram label says 15, stack table says 16 — table is authoritative |
| 2026-09-23 | shadcn init via `base-nova` preset, `baseColor: neutral` | current shadcn CLI removed the `-b <color>` flag (`-b` now selects component library); tokens will be overridden in P0.T9 anyway |
| 2026-09-23 | Package layout `api/pine/` via `tool.uv.build-backend` `module-root = ""` | brief specifies `api/pine/`, not the `src/` layout `uv init --package` defaults to |
| 2026-09-23 | `web/.gitignore` gained `!.env.example` | Next template ignores `.env*`; example file must be tracked |

## Session Log

### 2026-09-23 — Session 1
- Scaffolded `api/` (uv, py3.12, all deps incl. `ocr` extra) and `web/` (Next 16 + shadcn + react-query + zod).
- Implemented `create_app()`, CORS, API-key middleware (`compare_digest`), error envelope, `/api/v1/health`, typer CLI, Alembic initial migration.
- Tests green: 9 passed; ruff + mypy strict clean; `pnpm lint && pnpm build` clean.
- Wrote DESIGN_SYSTEM.md, INSTRUCTIONS.md, EVAL_GUARDRAILS.md, TESTING_GUIDE.md, TASK_LOG.md, CLAUDE.md, AGENTS.md.

## Completed Phases

None yet.
