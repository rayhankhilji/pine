# Pine — Agent Instructions

> Operating manual for AI agents (and humans) building Pine. ARCHITECTURE.md is the contract — where docs disagree, ARCHITECTURE wins, then PRD, then ROADMAP.

## 0. Read Order

Read these in order before writing code:

1. `INSTRUCTIONS.md` (this file) — how to work.
2. `ARCHITECTURE.md` — the binding contract: data model (§4), API table (§5), component boundaries (§3), jobs (§9), AI subsystem (§10), security (§11), env vars (§12).
3. `PRD.md` — product intent and acceptance criteria (`F-xx.ACn`).
4. `DESIGN_SYSTEM.md` — before touching anything in `web/`.
5. `EVAL_GUARDRAILS.md` — definition of done, budgets, blocking evals.
6. `ROADMAP.md` — the current phase and task list.
7. `TASK_LOG.md` — what is done, in progress, blocked; update it as you work.
8. `TESTING_GUIDE.md` — how to verify.

## 1. Mission

Build Pine: a Private Markets Intelligence Engine that ingests a whole data room and produces an auditable investment model where **every claim is backed by evidence**. The product's core promise is that it is structurally incapable of an unsupported claim — Facts, Entities, Relations and Claims exist only with Evidence rows (ARCHITECTURE §4, ADR-003). When in doubt, prefer provenance over cleverness.

## 2. Operating Loop

1. Read `TASK_LOG.md` → find the current phase and next unchecked task in `ROADMAP.md`.
2. Re-read the ARCHITECTURE sections listed in the task's `refs:` and the PRD feature's acceptance criteria.
3. Implement the smallest change that satisfies the task; follow §6–§8 of this file.
4. Run the task's `verify:` command plus `make lint`; add/adjust tests at the paths named in the task.
5. Commit per §11, update `TASK_LOG.md`, move to the next task.
6. If the task's verify fails and you cannot fix it in two attempts, follow §10.

## 3. Tech Stack (locked)

Do not substitute libraries. Full table with versions and rationale: ARCHITECTURE §2.

- **api/**: Python 3.12 (pinned, never bump — OCR/PDF wheels), uv, FastAPI, SQLAlchemy 2 + Alembic, SQLite default / Postgres 16 optional, pydantic v2, typer + rich, PyMuPDF + pdfplumber, pytesseract (optional `ocr` extra), openpyxl/python-docx/python-pptx/pandas, tiktoken, rank-bm25, numpy, openai (gpt-5 / gpt-5-mini), rapidfuzz, networkx, sse-starlette. Tests: pytest, pytest-asyncio, pytest-cov, hypothesis, httpx TestClient.
- **web/**: Next.js **16** (App Router), TypeScript 5 strict, Tailwind CSS 4, shadcn/ui (Radix), TanStack Query 5, `motion` (framer-motion), pdfjs-dist 4, react-force-graph-2d, lucide-react, react-hook-form + zod, Vitest + Testing Library, Playwright.
- **Contract**: web never hand-writes API response types — `make generate` produces `web/src/lib/api/types.ts` from the FastAPI OpenAPI schema.

## 4. Repository Structure

```
api/            FastAPI engine (uv project, package `pine`)
  pine/
    api/        routers + schemas (no business logic)
    services/   use-cases, transactions
    models/     SQLAlchemy entities (ARCHITECTURE §4)
    repos/      query helpers; deal-scoped access via scoped(deal_id)
    ingest/     detection + parsers (no LLM calls)
    index/      chunking, embed, BM25/dense/RRF, rerank
    facts/      extractors, EvidenceStore (only writer of Fact/Entity/Claim)
    graph/      entities, relations, resolution, export
    contradictions/  rules R1–R7 (no LLM)
    agents/     runtime, tools, prompts, EvidenceGate
    outputs/    memo/model/risk/source-map generators (no LLM)
    llm/        provider interface, openai/fake/hash impls, accounting
    jobs/       Job table, worker loop, queue
    storage/    blob store (sha256, STORAGE_DIR)
  alembic/      migrations (autogenerate → hand-review; never edit applied)
  tests/        mirrors pine/; fixtures in tests/fixtures/
web/            Next.js app
  src/app/      routes per ARCHITECTURE §7
  src/components/  UI + domain components
  src/lib/api/  client.ts, hooks.ts, types.ts (generated), schemas.ts
Makefile        install / api / web / test / lint / typecheck / generate
fixtures/northwind/  demo data room + ground_truth.json
```

Component boundaries and "must NOT" rules are enforced — see ARCHITECTURE §3.

## 5. Commands

```bash
make install     # uv sync (api) + pnpm install (web)
make api         # uv run --directory api pine serve   → :8000
make web         # pnpm -C web dev                     → :3000
make test        # uv run --directory api pytest -q
make lint        # ruff check + mypy + pnpm -C web lint
make typecheck   # mypy pine tests
make generate    # regenerate web/src/lib/api/types.ts from OpenAPI

uv run --directory api pytest -q tests/path/test_x.py   # one file
uv run --directory api alembic upgrade head             # migrate
uv run --directory api alembic revision --autogenerate -m "…"
uv run --directory api pine worker                      # standalone worker
pnpm -C web add <pkg>                                   # web deps
```

## 6. Coding Standards

**Python (`api/`):**
- Fully typed; `mypy --strict` must pass. ruff clean (E,F,I,UP,B,SIM, line-length 100).
- SQLAlchemy 2.0 style: `Mapped[...]`/`mapped_column`, `select()`, no `Query` API. UUIDv7 string ids via `uuid_utils`; `created_at`/`updated_at` via `TimestampMixin`.
- Pydantic v2 models at every boundary (HTTP schemas, LLM structured outputs, job payloads).
- Money: `Numeric(20,4)` + `currency`, **never floats**. Quantities `Numeric(24,6)`.
- **Every Fact/Entity/Relation/Claim is written only via `EvidenceStore`** with ≥ 1 Evidence (or FactLink for derived facts). `add_fact` raises `EvidenceRequired` otherwise.
- Routers contain no business logic; services own transactions; repos own queries; `ingest/` and `contradictions/` never call LLMs; `agents/` never write Facts.
- Enums are `StrEnum`s stored as strings. Migrations additive-only; `batch_alter_table` for SQLite ALTERs.

**TypeScript (`web/`):**
- `strict`; **no `any`**, no non-null `!` without a comment justifying it.
- All HTTP via `web/src/lib/api/client.ts` + `hooks.ts`; response types from generated `types.ts` only; form validation via `zod` schemas in `lib/api/schemas.ts` + react-hook-form.
- Components use DESIGN_SYSTEM tokens — no raw hex/px/rgba in `src/`; numerals use mono + `tabular-nums`.
- Heavy deps (pdf.js, react-force-graph) are lazy `next/dynamic` imports.

## 7. Frontend Rules

DESIGN_SYSTEM.md is binding. Non-negotiables:

- Editorial-terminal direction: light-first + full dark; hairline borders over shadows; radius ≤ 10; no gradients/glassmorphism/glow.
- Every route implements all five states: empty, loading (skeleton matching final layout), error (message + retry), partial, success. `error.tsx` + `loading.tsx` per route.
- Status is icon + text, never colour alone. Contested data gets the amber `warning` badge — uncertainty is content.
- Motion per §6 tokens; `prefers-reduced-motion` → opacity ≤ 150 ms.
- Query keys per ARCHITECTURE §7; SSE handlers only invalidate query keys. Optimistic updates only for contradiction resolve and `PATCH /facts`.
- No `fetch` outside `src/lib/api/`; no endpoints not in ARCHITECTURE §5.

## 8. Backend Rules

- Error envelope `{"error": {code, message, details}}` everywhere; codes only from the ARCHITECTURE §5 catalogue; raise `AppError`, never hand-build error JSON.
- Auth: `X-API-Key` vs `PINE_API_KEY` via `hmac.compare_digest`; open when unset. Deal-scoped queries always filter `deal_id`.
- Pagination: cursor `?cursor&limit` (default 50, max 200) → `{items, next_cursor}`, keyset on `created_at|id`, base64.
- `Idempotency-Key` header on POSTs that create work → `Job.idempotency_key`.
- Workers: jobs enqueue with idempotency keys (`parse:{doc}`, `index:{deal}:{n}`, `run:{run}`, `output:{run}:{kind}:{v}`); retries 5 s·2^attempts, max 3 → `failed`; per-kind timeouts per ARCHITECTURE §9.
- LLM calls only through `pine/llm/` provider interface with `LLMCall` accounting; FakeLLM/HashEmbedder keep tests and evals offline and deterministic.
- Logging: JSON logs with `request_id`; secrets and bank account numbers are redacted; never log file contents or API keys.

## 9. Prohibited

- No web fetch of user-supplied URLs; outbound HTTP only to `OPENAI_BASE_URL`.
- No third-party analytics/telemetry in web or api.
- No floats for money or metric values; no string concatenation into SQL; no `eval`/`exec`.
- No writing docs files unprompted (PRD/ARCHITECTURE/ROADMAP are human-owned).
- No editing applied migrations; no destructive DDL before P7.
- No `any` in TS; no untyped public functions in Python; no `# type: ignore` without justification comment.
- No bypassing `EvidenceStore`; no agents writing Facts; no LLM calls in `ingest/`, `contradictions/`, `outputs/`.
- No committing secrets; `.env` stays git-ignored.

## 10. When Stuck

1. Re-read the ARCHITECTURE section for the task — the answer is usually there.
2. Check `TASK_LOG.md` decisions/deviations for prior art.
3. Search the codebase for the nearest analogous implementation and follow it.
4. Reduce scope: implement the smallest correct slice, mark the rest pending in TASK_LOG.
5. Two failed verification attempts on the same failure → stop and escalate (§12) with the exact command, error, and your diagnosis. Do not keep retrying blind.

## 11. Git & Commits

- **Conventional Commits**: `feat(api): …`, `fix(web): …`, `test:`, `chore:`, `docs:`, `ci:`, `refactor:`.
- **Commit frequency rule (user requirement — do not skip):** one small commit per unit of work — each module, each test file, each config change, each fix — and **`git push` after every commit**. Never batch unrelated files into one commit; never squash, amend, or rewrite history; no `Co-Authored-By` trailers.
- Stage files explicitly (`git add path`), never `git add .`; never commit `.env` or secrets.
- `main` is the working branch for this project; keep it green — run the task's verify command before pushing.

## 12. Human Escalation

Stop and ask the human when:

- ARCHITECTURE and PRD conflict, or a task requires changing either.
- A required secret/credential is missing (`OPENAI_API_KEY`, etc.).
- Verification is blocked by the environment after two workaround attempts.
- A change would break an existing public API shape, applied migration, or committed fixture.
- Cost or security guardrails (EVAL_GUARDRAILS) would be exceeded by the requested change.

Escalate with: what you tried, exact command + error output, your best diagnosis, and the specific decision or input needed.
