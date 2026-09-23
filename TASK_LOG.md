# Pine — Task Log

> Updated 2026-09-23 · The running record of what is done, in progress, and decided. Agents update this file every session.

## Status

**Phase 0 — Foundation: complete.** All P0 tasks done. API has health, API-key auth (`compare_digest`), error envelope, request-id + JSON logging, Alembic migrations (deal, job), a polling job worker with retries/idempotency, and deals CRUD with cursor pagination. Web has the design-token theme (light+dark), deal shell nav, placeholder routes with loading/error states, and a working deals home (list + create). OpenAPI codegen (`make generate`) feeds `web/src/lib/api/types.ts`, drift-checked in CI.

**Next action: P1.T1** — models + migration for `Blob, Document, Page, Block, Table, Cell` (ARCHITECTURE §4).

## Current Phase Checklist

Phase 0 — Foundation:

- [x] P0.T1 — Init `api/` with uv (Python 3.12 pinned), FastAPI app factory, `Settings`, `/api/v1/health` · refs: ARCHITECTURE §2, §12 · verify: `uv run --directory api pytest -q tests/test_health.py`
- [x] P0.T2 — SQLAlchemy 2 `Base`, session dependency, Alembic wired to `DATABASE_URL`, migrations (initial, deal, job) · refs: ARCHITECTURE §4 Migrations · verify: `uv run --directory api alembic upgrade head`
- [x] P0.T3 — Error envelope (`AppError`, validation, internal handlers) + request-id middleware + JSON logging · refs: ARCHITECTURE §5 conventions, §14 · verify: `tests/test_errors.py`, `tests/test_request_id.py`
- [x] P0.T4 — API-key middleware with `compare_digest`, open when unset · refs: ARCHITECTURE §11 · verify: `tests/test_auth.py`
- [x] P0.T5 — `Job` model + worker loop (poll, lock, retry/backoff, stale-lock release) + `enqueue()` + `pine worker` CLI · refs: ARCHITECTURE §9 · verify: `tests/jobs/test_worker.py` (job runs, retries 3×, dead-letters)
- [x] P0.T6 — `Deal` model, migration, `POST/GET/PATCH/DELETE /deals` with cursor pagination · refs: F-01, ARCHITECTURE §5 · verify: `tests/api/test_deals.py`
- [x] P0.T7 — ruff + mypy strict config; `.github/workflows/ci.yml` api job · verify: CI green on push
- [x] P0.T8 — Init `web/` (Next 16, TS strict, Tailwind 4, shadcn), `lib/api/client.ts` with `ApiError`, providers, home page with health status (loading/ok/error) · refs: ARCHITECTURE §7 · verify: `pnpm -C web lint && pnpm -C web build`
- [x] P0.T9 — Design tokens in `globals.css` per DESIGN_SYSTEM §2–§6; app shell layout (`deals/[id]/layout.tsx` nav) with placeholder pages for every route in ARCHITECTURE §7, each with `loading.tsx` and `error.tsx` · verify: `pnpm -C web build`
- [x] P0.T10 — `make generate`: OpenAPI → `web/src/lib/api/types.ts` via openapi-typescript; CI web job drift check · verify: `make generate && git diff --exit-code web/src/lib/api/types.ts` in CI
- [x] P0.T11 — Root `Makefile`, `.env.example`s, `.gitignore`, LICENSE (MIT), README quickstart · verify: fresh clone follows README to green

## Up Next

Phase 1 — Ingestion & document intelligence:
- P1.T1 — Models + migration: `Blob, Document, Page, Block, Table, Cell`
- P1.T2 — `BlobStore` (sha256 content-addressed, `STORAGE_DIR`)
- P1.T3 — Upload service: multipart, size/quota, zip guards, dedupe, enqueue `parse_document`
- P1.T4 — File type detection (signature bytes + extension allowlist)

## Blockers

None.

## Decisions & Deviations

| Date | Decision | Context |
|---|---|---|
| 2026-09-23 | Next.js **16** (not 15) | `create-next-app@latest` scaffolds 16.3.6; ARCHITECTURE §2 stack table says 16 — table is authoritative |
| 2026-09-23 | shadcn init via `base-nova` preset (Base UI primitives, not Radix), `baseColor: neutral` | current shadcn CLI removed the `-b <color>` flag; consequence: components use `render=` prop, not `asChild` |
| 2026-09-23 | Package layout `api/pine/` via `tool.uv.build-backend` `module-root = ""` | spec requires `api/pine/`, not `uv init` default `src/` |
| 2026-09-23 | `web/.gitignore` gained `!.env.example` | Next template ignores `.env*`; example file must be tracked |
| 2026-09-23 | Deal cursor compares `datetime` objects, not ISO strings | SQLite stores `"YYYY-MM-DD HH:MM:SS"` — string-compare against `T`-separated ISO silently drops pages |
| 2026-09-23 | Worker: sync handlers run via `asyncio.to_thread` inside `wait_for(timeout)`; `run_once()` drives tests without sleeps | per ARCHITECTURE §9 timeouts table |
| 2026-09-23 | `web/openapi.json` committed alongside generated `types.ts` | drift check regenerates both deterministically |

## Session Log

### 2026-09-23 — Session 1
- Scaffolded `api/` (uv, py3.12, all deps incl. `ocr` extra) and `web/` (Next 16 + shadcn + react-query + zod).
- `create_app()`, CORS, API-key middleware, error envelope, `/api/v1/health`, typer CLI, Alembic init.
- Tests green: 9 passed; ruff + mypy strict clean; `pnpm lint && pnpm build` clean.

### 2026-09-23 — Session 2
- Wrote remaining build docs (INSTRUCTIONS, DESIGN_SYSTEM, EVAL_GUARDRAILS, TESTING_GUIDE, TASK_LOG, CLAUDE, AGENTS); `validate_docs.py` clean.
- `compare_digest` API key; request-id middleware + JSON logging + redaction; full §12 Settings.
- Job model + worker (poll/claim/backoff/stale-lock/idempotency, lifespan + `pine worker`); Deal model + CRUD with keyset cursor.
- Web: design tokens light+dark, Inter/JetBrains Mono, deal shell nav, 12 placeholder routes with loading/error, deals home (table + create dialog + health badge).
- `make generate` (export_openapi.py → openapi-typescript) + CI drift check; README quickstart.
- Final: 28 api tests green, ruff/mypy clean, web lint+build clean, openapi drift clean.

## Completed Phases

- **Phase 0 — Foundation** (2026-09-23): monorepo, API skeleton, DB + migrations, job worker, error envelope, API-key auth, web shell, CI. All exit criteria met.
