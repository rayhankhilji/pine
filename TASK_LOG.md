# Pine — Task Log

> Updated 2026-09-23 · The running record of what is done, in progress, and decided. Agents update this file every session.

## Status

**Phase 0 — Foundation: complete.** All P0 tasks done. API has health, API-key auth (`compare_digest`), error envelope, request-id + JSON logging, Alembic migrations (deal, job), a polling job worker with retries/idempotency, and deals CRUD with cursor pagination. Web has the design-token theme (light+dark), deal shell nav, placeholder routes with loading/error states, and a working deals home (list + create). OpenAPI codegen (`make generate`) feeds `web/src/lib/api/types.ts`, drift-checked in CI.

**Phase 1 — Ingestion: complete.** All P1 tasks done: full upload/document/table/job/SSE API surface (ARCHITECTURE §5), deterministic Northwind demo room + `POST /demo` (202, 409 on concurrent ingest), web home "Load demo" → documents page (dropzone, zip expansion, status pills, unreadable group, live SSE) and document viewer (rendered pages, thumbnails, text panel, spreadsheet tables, `?page=` deep links). Live check: `POST /api/v1/demo` ingested 19 documents → all `parsed` in ~5 s; 19 parse + 19 classify + 1 index job succeeded. 99 api tests green; ruff + mypy strict clean; web lint + build clean; Playwright e2e specs + CI `e2e` job added.

**Phase 2 — Retrieval: complete.** All P2 tasks done: `Chunk` model + structure-aware chunker (400/800/60 prose overlap, ≤25-row table groups with header repeat, slide/email kinds), HashEmbedder (256-d deterministic sha256) + OpenAIEmbedder (batch-100/retry/fallback), real `index_deal` job, index status (empty/indexing/stale/ready), hybrid BM25 + dense cosine with RRF(k=60) and hard filters, rerankers (none/llm/cross-encoder lazy), `POST /deals/{id}/search` + `POST|GET /deals/{id}/index`, web search page (query/k/doc-type chips, highlighted hits → document viewer deep links), index pill + Reindex on documents page, e2e spec. Live check: `POST /demo` → 39 chunks indexed (`ready`); `"annual recurring revenue"` returns `email_02.eml`, `MSA_Delta_Freight.pdf`, `02_Financials_FY2024_FY2025.xlsx` top-3. 145 api tests green; ruff + mypy strict clean; web lint + build clean; Playwright search spec green.

**Phase 3 — Facts & knowledge graph: in progress.** P3.T1 (Evidence/Entity/EntityAlias/Relation/Fact/FactLink models + migration `21768d57a624`, MetricId/Unit/PeriodType vocabularies), P3.T2 (`EvidenceStore` — sole writer of Fact/Entity/Relation rows; quote substring validation `EvidenceInvalid`, `EvidenceRequired` invariants, evidence stubs + `link_evidence` copy-on-retarget, entity/alias and relation dedupe), P3.T3 (`pine/facts/periods.py` — PeriodSpec parsing for FY/quarter/month/TTM/as-of labels, fiscal-calendar-aware bounds via `deal.fiscal_year_end_month`, `comparable()` overlap rules, hypothesis round-trips), P3.T4 (deterministic table extractors: P&L/balance sheet, bank statement monthly+FY `bank_inflows` and closing `cash_balance` + `bank_account` entity, customer list → Customer entities + `has_customer` edges + aggregates, cap table → Shareholder/SecurityClass + `owns_shares` + `shares_outstanding`; ordered registry `run_extractors`; cell-level evidence on every fact), P3.T5 (`LLMCall` model + migration, recorded/hash-cached call wrapper, FakeLLM scripted YAML + deterministic extract fallback, OpenAILLM structured outputs, LLM extraction tests + shared `tests/facts/conftest.py` fixtures), P3.T6 (`pine/facts/llm_extract.py` — prose-chunk LLM extraction with verbatim `evidence_quote` substring check, `EVIDENCE_MISMATCH` rejection, dedupe), P3.T7 (`pine/facts/derive.py` — runway, gross margin, concentration, NRR as `derived` facts with `FactLink` lineage) and P3.T8 (`pine/graph/` — `resolve.py` alias-hit + fuzzy token_set ≥ 92 merges repointing facts/relations/evidence/aliases, `extract.py` contract counterparty + email person entities, `build.py` orchestrator, `export.py` JSON/GraphML) done. 7 graph tests green incl. F-04.AC1/AC2 demo-room checks.

P3.T9 (facts + graph/entity endpoints per ARCHITECTURE §5: `GET /deals/{id}/facts` with metric/period/source filters + cursor pagination + embedded evidence, `GET/PATCH /facts/{id}` with `derived_from` lineage, `GET /deals/{id}/graph` with `?types`/`?limit`/`?format=graphml`, `GET /entities/{id}` detail, `POST /entities/{id}/merge` 409-on-self + `/split` 201; `split_entity` service in `graph/resolve.py`) and P3.T10 (job chain: `index_deal` enqueues `extract_facts` keyed `facts:{deal}:{chunks}`; `extract_facts` runs extractors→LLM→derive and enqueues `build_graph`; `build_graph` enqueues a `detect_contradictions` stub; classify-pending deferral guard; all wired into worker/main imports) done. `demo_deal` fixture now drains the entire chain — facts/entities/graph exist after ingest; 18 api tests + 1 chain test green.

**Next action: P3.T11** — see ROADMAP Phase 3.

## Current Phase Checklist

Phase 3 — Facts & knowledge graph (F-04, F-05):

- [x] P3.T1 — Models + migration `21768d57a624`; `pine/schemas/` vocabularies · tests/models/test_schema.py
- [x] P3.T2 — `EvidenceStore` + invariants · tests/facts/test_invariants.py (17 tests)
- [x] P3.T3 — `pine/facts/periods.py` PeriodSpec parsing + comparability · tests/facts/test_periods.py
- [x] P3.T4 — Table extractors (pnl, bank_statement, customer_list, cap_table) + registry · tests/facts/test_table_extractors.py (7 tests)
- [x] P3.T5 — `pine/llm/` tools/StructuredResult/LLMCall + FakeLLM YAML scripts
- [x] P3.T6 — LLM prose extraction
- [x] P3.T7 — Derived facts
- [x] P3.T8 — `pine/graph/` resolve/extract/build/export · tests/graph (7 tests)
- [x] P3.T9 — Facts + graph endpoints · tests/api/test_facts.py (11), test_graph.py (7)
- [x] P3.T10 — Job chain extract_facts → build_graph → detect_contradictions · tests/jobs/test_chain.py
- [ ] P3.T11 — Web facts page
- [ ] P3.T12 — Web graph page
- [ ] P3.T13 — `pine eval demo` / `pine eval evidence`


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

Phase 2 — Retrieval (F-03):
- [x] P2.T1 — `Chunk` model + migration `d4d47b54c38d`; `pine/index/chunker.py` (o200k_base, 400/800/60 prose, ≤25-row table groups with header repeat, slide/email kinds) · tests/index/test_chunker.py (8 tests)
- [x] P2.T2 — `pine/index/embeddings.py` (Embedder protocol, HashEmbedder 256-d sha256, OpenAIEmbedder batch-100/retry/≤4-concurrent, EMBEDDINGS_FALLBACK), `pine/index/vectors.py` pack/unpack · tests/index/test_embedders.py (10 tests)
- [x] P2.T3 — real `index_deal` handler in `pine/index/jobs.py` (stub removed), `pine/index/status.py` (empty/indexing/stale/ready via `meta["indexed"]` stamp); reparse clears stamp · tests/index/test_index_job.py (3 tests)
- [x] P2.T4 — `pine/index/retrieval.py` (BM25Okapi + float32 cosine matrix, per-deal caches keyed `(deal_id, chunk_count)`, RRF k=60 top-50×2, hard filters) · tests/index/test_retrieval.py (9 tests incl. AC1/AC2)
- [x] P2.T5 — `pine/index/rerank.py` (NoReranker, LLMReranker listwise ≤25 candidates `{ranking:[int]}`, CrossEncoderReranker lazy-import w/ fallback), minimal `pine/llm/` (base protocol, FakeLLM rerank script, OpenAILLM structured outputs, `get_llm`/`model_for`) · tests/index/test_rerank.py (9 tests)
- [x] P2.T6 — `pine/api/search.py` + `pine/api/schemas/search.py` (SearchRequest/SearchHit/IndexStatus), POST index → 202 {job_id}, OpenAPI types regenerated · tests/api/test_search.py (8 tests)
- [x] P2.T7 — Web: `/deals/[id]/search` (query box, k control, doc_type chips, term-highlighted hits linking to `?page=` viewer), documents-page index pill for all states + Reindex button, `useSearch`/`useIndexStatus`/`useReindex` hooks on generated types · e2e/search.spec.ts green

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
| 2026-09-23 | mypy `follow_imports = "skip"` for `pymupdf` | package ships `py.typed` but wraps the compiled `_mupdf` module — partial typing produced false-positive strict errors on every call; module is now `Any` |
| 2026-09-28 | SQLite: WAL + `busy_timeout=30s` + `check_same_thread=False`; no `BEGIN IMMEDIATE` | deferred-write upgrades (`SQLITE_BUSY_SNAPSHOT`) are rare and jobs self-retry; `BEGIN IMMEDIATE` serialized *all* txns (including reads) and starved the `to_thread` pool — tested and reverted |
| 2026-09-28 | Worker DB calls run via `asyncio.to_thread`; `parse_document` parses outside the DB txn | sync sqlite busy-waits on the event loop wedged the whole server; long parses must not hold write locks |
| 2026-09-28 | Demo fixtures are content-stable, not byte-identical | office/PDF/EML writers embed random MIME boundaries and binary metadata; seeded RNG fixes all extracted text/tables |
| 2026-09-28 | Playwright e2e runs `workers: 1` | all tests share one SQLite file; parallel writers contend |

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

### 2026-09-23 — Session 3
- Committed all outstanding P1.T1–T12 work in small commits; fixed ruff/mypy strict issues (pymupdf module skip, bytes prefix sniffing, typed test fixtures).
- 66 api tests green, ruff + mypy strict clean.

### 2026-09-28 — Session 4
- P1.T13: upload endpoint (zip expansion, traversal/bomb guards, sha256 dedupe, `__MACOSX`/dotfile skip), document list/detail/page/render/file/reparse, table detail, job detail, deal SSE (real-Uvicorn test — TestClient buffers infinite streams).
- P1.T14: `pine demo build` — Northwind room (19 files, ~152 KB) + `ground_truth.json`; PyMuPDF-only PDFs; committed fixtures.
- P1.T15: `POST /demo` — builds fixtures under `STORAGE_DIR/demo`, creates Northwind Series B deal, ingests with preserved paths; 409 while another demo ingest runs.
- P1.T16–T18: web demo button, documents page (react-dropzone, upload progress, status pills, unreadable group, SSE invalidation + toasts, index pill placeholder), document viewer (render rail/canvas/text panel, spreadsheet table view, `?page=` links, download).
- Playwright e2e: config boots migrated API + dev server; specs for deals/documents/viewer; CI `e2e` job.
- Concurrency fixes found via e2e: WAL + busy_timeout + `check_same_thread=False`; worker polls moved off the event loop; parse jobs hold no write lock while parsing; periodic stale-lock requeue.
- Final: 99 api tests green, ruff/mypy clean, web lint+build clean; live `POST /demo` → 19 docs all `parsed`, all jobs succeeded.

### 2026-09-28 — Session 5
- P2.T1–T7: `Chunk` model + migration `d4d47b54c38d`, structure-aware chunker, HashEmbedder/OpenAIEmbedder + vectors, `index_deal` job + status service, BM25+dense RRF retrieval, rerankers + `pine/llm` layer, search/index endpoints, web search page + index/reindex UI, e2e spec.
- Live check on fresh DB: `POST /demo` → 19 docs parsed → 39 chunks embedded (`ready`); `"annual recurring revenue"` → email_02.eml, MSA_Delta_Freight.pdf, 02_Financials_FY2024_FY2025.xlsx.
- Final: 145 api tests green (1 skipped), ruff/mypy strict clean, web lint+build clean, `make generate` drift-free.

## Completed Phases

- **Phase 0 — Foundation** (2026-09-23): monorepo, API skeleton, DB + migrations, job worker, error envelope, API-key auth, web shell, CI. All exit criteria met.
- **Phase 1 — Ingestion & document intelligence** (2026-09-28): full upload→parse→classify pipeline, document APIs + SSE, demo room + `POST /demo`, documents UI + viewer, e2e harness. Exit criteria met: demo room loads via UI, all files reach `parsed`.
- **Phase 2 — Retrieval** (2026-09-28): structure-aware chunking, deterministic hash + OpenAI embeddings, index job + status, hybrid BM25/dense RRF search with filters, optional reranking, search/index APIs, search UI + reindex, e2e. Exit criteria met: hybrid search returns traceable hits over the demo room.
