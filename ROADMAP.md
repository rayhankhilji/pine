# Pine — Roadmap

> Version 1.0 · Updated 2026-09-23. Every phase ends runnable. Each task is one commit or a handful of small commits; commit and push after every task.

## Overview

| Phase | Goal | Features | Effort |
|---|---|---|---|
| P0 Foundation | Monorepo, API skeleton, DB, jobs, CI, web shell | — | 1 day |
| P1 Ingestion | Upload a room, parse every file type, see documents | F-01, F-02, F-14 (fixtures) | 2 days |
| P2 Retrieval | Chunk, embed, hybrid search, rerank, search UI | F-03 | 1 day |
| P3 Facts & Graph | Fact extraction with evidence, entity graph, graph UI | F-04, F-05 | 2 days |
| P4 Contradictions | Rules engine, resolution, contradictions UI, overview tree | F-06, F-13 (overview) | 1.5 days |
| P5 Agents & Outputs | Agent runtime + gate, memo, model, risks, valuation, source map, viewer | F-07…F-12, F-15 | 3 days |
| P6 Polish & Hardening | Motion, a11y, perf, security checklist, docker, evals gate | all | 1 day |
| P7 Launch | Docker release, README, demo video assets | — | 0.5 day |

## Phase 0 — Foundation
**Goal:** `make install && make api && make web` gives a health-checked API with DB, migrations, job worker skeleton, error envelope, API-key auth, and a Next.js shell that shows API status; CI green.
**Tasks:**
- [ ] P0.T1 — Init `api/` with uv (Python 3.12 pinned), FastAPI app factory, `Settings`, `/api/v1/health` · refs: ARCHITECTURE §2, §12 · verify: `uv run --directory api pytest -q tests/test_health.py`
- [ ] P0.T2 — SQLAlchemy 2 `Base`, session dependency, Alembic wired to `DATABASE_URL`, empty initial migration · refs: ARCHITECTURE §4 Migrations · verify: `uv run --directory api alembic upgrade head`
- [ ] P0.T3 — Error envelope (`AppError`, validation, internal handlers) + request-id middleware + JSON logging · refs: ARCHITECTURE §5 conventions, §14 · verify: `tests/test_errors.py`
- [ ] P0.T4 — API-key middleware with `compare_digest`, open when unset · refs: ARCHITECTURE §11 · verify: `tests/test_auth.py`
- [ ] P0.T5 — `Job` model + worker loop (poll, lock, retry/backoff, stale-lock release) + `enqueue()` + `pine worker` CLI · refs: ARCHITECTURE §9 · verify: `tests/jobs/test_worker.py` (job runs, retries 3×, dead-letters)
- [ ] P0.T6 — `Deal` model, migration, `POST/GET/PATCH/DELETE /deals` with cursor pagination · refs: F-01, ARCHITECTURE §5 · verify: `tests/api/test_deals.py`
- [ ] P0.T7 — ruff + mypy strict config; `.github/workflows/ci.yml` api job · verify: CI green on push
- [ ] P0.T8 — Init `web/` (Next 16, TS strict, Tailwind 4, shadcn), `lib/api/client.ts` with `ApiError`, providers, home page with health status (loading/ok/error) · refs: ARCHITECTURE §7 · verify: `pnpm -C web lint && pnpm -C web build`
- [ ] P0.T9 — Design tokens in `globals.css` per DESIGN_SYSTEM §2–§6; app shell layout (`deals/[id]/layout.tsx` nav) with placeholder pages for every route in ARCHITECTURE §7, each with `loading.tsx` and `error.tsx` · verify: visual check, `pnpm -C web build`
- [ ] P0.T10 — `make generate`: OpenAPI → `web/src/lib/api/types.ts` via openapi-typescript; CI web job · verify: `make generate && git diff --exit-code web/src/lib/api/types.ts` in CI
- [ ] P0.T11 — Root `Makefile`, `.env.example`s, `.gitignore`, LICENSE (MIT), README quickstart · verify: fresh clone follows README to green
**Exit criteria:** `curl :8000/api/v1/health` → ok; `POST /deals` creates and lists; a queued test job executes via the worker; web home renders API status; CI green on `main`.
**Out of this phase:** any parsing, any LLM.

## Phase 1 — Ingestion & document intelligence (F-01, F-02, F-14)
**Goal:** Upload a zip, every file parsed into pages/blocks/tables, documents page shows status live; synthetic demo room exists.
**Tasks:**
- [ ] P1.T1 — Models + migration: `Blob, Document, Page, Block, Table, Cell` · refs: ARCHITECTURE §4 · verify: `tests/models/test_schema.py`
- [ ] P1.T2 — `BlobStore` (sha256 content-addressed, `STORAGE_DIR`) · verify: `tests/storage/test_blobstore.py`
- [ ] P1.T3 — Upload service: multipart, size/quota checks, zip expansion with traversal/zip-bomb guards, dedupe by sha256, enqueue `parse_document` · refs: F-01.AC1–AC4, ARCHITECTURE §11 · verify: `tests/api/test_upload.py` (T-F01-AC1..AC4)
- [ ] P1.T4 — File type detection by signature bytes + extension allowlist (`ingest/detect.py`) · verify: `tests/ingest/test_detect.py`
- [ ] P1.T5 — Parser registry + `ParseResult` dataclasses + persistence (`ingest/persist.py`) · verify: unit test with a fake parser
- [ ] P1.T6 — PDF parser: PyMuPDF text blocks with bbox, pdfplumber tables → Table/Cell with bbox; scanned detection · refs: F-02.AC1 · verify: `tests/ingest/test_pdf.py` on `tests/fixtures/docs/table_5x4.pdf`
- [ ] P1.T7 — OCR path (`OCR_ENABLED`, pytesseract, graceful skip when binary missing) · refs: F-02.AC2 · verify: `tests/ingest/test_ocr.py` (skipped if no tesseract; CI installs it)
- [ ] P1.T8 — XLSX/CSV/TSV parser: sheets → Table with typed columns, cell refs · refs: F-02.AC3 · verify: `tests/ingest/test_spreadsheet.py`
- [ ] P1.T9 — DOCX and PPTX parsers (paragraph/heading/table; slide text + notes) · verify: `tests/ingest/test_office.py`
- [ ] P1.T10 — EML parser with attachments → child Documents; TXT/MD/image parsers · refs: F-02.AC5 · verify: `tests/ingest/test_email.py`
- [ ] P1.T11 — Failure handling: corrupt file → `failed` + error, retries, pipeline continues · refs: F-02.AC4 · verify: `tests/ingest/test_failures.py`
- [ ] P1.T12 — Document classifier (`doc_type` from filename + heuristics + header keywords; LLM optional later) · verify: `tests/ingest/test_classify.py` on demo files
- [ ] P1.T13 — Endpoints: documents list/detail/pages/render/file/reparse, tables detail, jobs, deal SSE events · refs: ARCHITECTURE §5 · verify: `tests/api/test_documents.py`
- [ ] P1.T14 — Demo room generator `pine demo build` → `fixtures/northwind/` + `ground_truth.json` + schema · refs: F-14.AC1 · verify: `tests/demo/test_build.py`
- [ ] P1.T15 — `POST /demo` service (build if missing, upload, enqueue) · verify: `tests/api/test_demo.py`
- [ ] P1.T16 — Web: deals home (create, list, load demo) with all states · verify: Playwright `e2e/deals.spec.ts`
- [ ] P1.T17 — Web: documents page (dropzone upload, table with status chips, unreadable group, live SSE updates, reparse) · verify: `e2e/documents.spec.ts`
- [ ] P1.T18 — Web: document viewer (pdf.js pages via `/render`, text layer, table view for spreadsheets), `?page=` deep link · verify: `e2e/viewer.spec.ts`
**Exit criteria:** demo room loads via UI; all 20+ files reach `parsed` (scanned page parsed if tesseract present, else flagged); T-F01-*, T-F02-* green.

## Phase 2 — Retrieval (F-03)
**Goal:** Hybrid search over the room from API and UI.
**Tasks:**
- [ ] P2.T1 — `Chunk` model + migration; structure-aware chunker (headings, table row-groups with header repeat, 400/800/60 tokens) · refs: F-03.AC4 · verify: `tests/index/test_chunker.py`
- [ ] P2.T2 — `Embedder` protocol, `HashEmbedder`, `OpenAIEmbedder` (batch, retry), embedding storage as float32 · refs: F-03.AC3 · verify: `tests/index/test_embedders.py`
- [ ] P2.T3 — `index_deal` job: chunk + embed all parsed docs, index status (`empty|indexing|ready|stale`) · verify: `tests/index/test_index_job.py`
- [ ] P2.T4 — BM25 index (per deal, cached) and dense search (numpy), RRF fusion, filters · refs: F-03.AC1, AC2 · verify: `tests/index/test_retrieval.py` on demo room
- [ ] P2.T5 — Rerankers: `none`, `llm` (FakeLLM in tests), `cross-encoder` optional extra · verify: `tests/index/test_rerank.py`
- [ ] P2.T6 — Endpoints `POST /deals/{id}/search`, `POST/GET /deals/{id}/index` · verify: `tests/api/test_search.py`
- [ ] P2.T7 — Web: search page (query, filters, results with document/page links, empty/loading/error) + index status/reindex on documents page · verify: `e2e/search.spec.ts`
**Exit criteria:** T-F03-AC1..AC4 green; search p95 < 300 ms on demo room.

## Phase 3 — Facts & knowledge graph (F-04, F-05)
**Goal:** Every number in the room becomes a Fact with Evidence; entities and relations form a navigable graph.
**Tasks:**
- [ ] P3.T1 — Models + migration: `Evidence, Entity, EntityAlias, Relation, Fact, FactLink`; `MetricId` vocabulary + `Unit/PeriodType` enums in `pine/schemas/` · refs: ARCHITECTURE §4 · verify: `tests/models/test_schema.py`
- [ ] P3.T2 — `EvidenceStore`: create evidence (quote substring validation), `add_fact` invariant (`EvidenceRequired`), `add_entity`, `add_relation` · verify: `tests/facts/test_invariants.py`
- [ ] P3.T3 — Period parsing/normalisation (`FY2025`, `Q4'25`, `Dec-25`, `TTM Mar 2026`, "as of") → `PeriodSpec` · verify: `tests/facts/test_periods.py` (hypothesis)
- [ ] P3.T4 — Deterministic table extractors: P&L, bank statement, customer list, cap table (header synonym matching, cell-level evidence) · refs: F-05.AC1 · verify: `tests/facts/test_table_extractors.py` on demo files
- [ ] P3.T5 — `LLM` protocol, `FakeLLM` (YAML fixtures), `OpenAILLM` structured outputs, `LLMCall` accounting + cache · refs: ARCHITECTURE §10 · verify: `tests/llm/test_providers.py`
- [ ] P3.T6 — LLM prose extraction (`ExtractedFact` schema, quote substring check, `EVIDENCE_MISMATCH` rejection, dedupe) · refs: F-05.AC2, AC3 · verify: `tests/facts/test_llm_extraction.py`
- [ ] P3.T7 — Derived facts (runway, gross margin, concentration, NRR) with `FactLink` · refs: F-05.AC4 · verify: `tests/facts/test_derive.py`
- [ ] P3.T8 — Entity extraction from tables/contracts/emails; entity resolution (rapidfuzz ≥ 92, aliases); relations · refs: F-04.AC1, AC2 · verify: `tests/graph/test_resolution.py`, `tests/graph/test_build.py`
- [ ] P3.T9 — Graph export JSON/GraphML; endpoints facts/entities/graph/merge/split · refs: F-04.AC3 · verify: `tests/api/test_facts.py`, `tests/api/test_graph.py`
- [ ] P3.T10 — Jobs `extract_facts`, `build_graph` chained after index · verify: `tests/jobs/test_chain.py`
- [ ] P3.T11 — Web: facts page (filters, evidence popover → viewer deep link with highlight) · verify: `e2e/facts.spec.ts`
- [ ] P3.T12 — Web: graph page (force graph, type filter, entity side panel with evidence, merge/split) · verify: `e2e/graph.spec.ts`
- [ ] P3.T13 — `pine eval demo` fact-recall against `ground_truth.json` · refs: F-14.AC2 · verify: recall ≥ 0.9 with fake provider
**Exit criteria:** demo run yields facts for all planted metrics; graph has Company→Customer→Contract→Revenue chains; T-F04-*, T-F05-* green; eval recall ≥ 90 %.

## Phase 4 — Contradiction engine & overview (F-06, F-13 overview)
**Goal:** Disagreements are detected deterministically, resolvable, and visible on the overview tree.
**Tasks:**
- [ ] P4.T1 — Models + migration: `Contradiction, ContradictionFact` · verify: schema test
- [ ] P4.T2 — `ComparablePeriod` (overlap rules FY/Q/M/TTM/point) · verify: `tests/contradictions/test_periods.py`
- [ ] P4.T3 — Rules R1 (numeric spread, metric tolerances), R2 (unit/currency) · refs: F-06.AC1, AC2 · verify: `tests/contradictions/test_r1_r2.py`
- [ ] P4.T4 — Rules R4 (component sum), R5 (cap table 100 %), R7 (bank inflows vs revenue) · refs: F-06.AC3 · verify: `tests/contradictions/test_sums.py`
- [ ] P4.T5 — Rules R3 (temporal/growth claims) and R6 (contract term vs recognition) · verify: `tests/contradictions/test_r3_r6.py`
- [ ] P4.T6 — Engine runner: fingerprint idempotency, severity scoring, templated explanations, `detect_contradictions` job · verify: `tests/contradictions/test_engine.py`
- [ ] P4.T7 — Resolution service + endpoint (`authoritative`, dismiss, recompute stale outputs) · refs: F-06.AC4 · verify: `tests/api/test_contradictions.py`
- [ ] P4.T8 — Overview service (10 sections, headline metrics, contested/missing flags) + `GET /deals/{id}/overview` · refs: F-13.AC1 · verify: `tests/api/test_overview.py`
- [ ] P4.T9 — Web: contradictions page (list, severity filter, detail drawer with facts/evidence, resolve/dismiss with optimistic update) · verify: `e2e/contradictions.spec.ts`
- [ ] P4.T10 — Web: overview tree page (10 sections, headline cards, contested badges, click-through to facts/contradictions) · verify: `e2e/overview.spec.ts`
- [ ] P4.T11 — `pine eval demo` contradiction recall (100 % planted) · verify: eval output
**Exit criteria:** demo room shows the ARR three-way contradiction and the 103 % cap table; resolving updates the overview; T-F06-*, T-F13-AC1 green.

## Phase 5 — Agents & outputs (F-07…F-12, F-15)
**Goal:** Full pipeline run produces memo, model, risks, valuation, contradiction report and source map — every claim evidence-gated.
**Tasks:**
- [ ] P5.T1 — Models + migration: `Run, AgentRun, Claim, GateRejection, Risk, RiskClaim, ValuationScenario, Output` · verify: schema test
- [ ] P5.T2 — Agent tools (search/get_facts/get_entity/list_entities/get_contradictions/open_document/get_table) returning `evidence_id` stubs · refs: ARCHITECTURE §10 · verify: `tests/agents/test_tools.py`
- [ ] P5.T3 — `EvidenceGate` (all reject reasons) · refs: F-07.AC1 · verify: `tests/agents/test_gate.py`
- [ ] P5.T4 — Agent runtime loop (structured output, tool dispatch, iteration/timeout limits, repair retries, token/cost accounting) · refs: F-07.AC3 · verify: `tests/agents/test_runtime.py` with FakeLLM scripts
- [ ] P5.T5 — Prompts + `DocumentAgent`, `FinancialAgent`, `AccountingAgent` · verify: `tests/agents/test_agents_financial.py` (fixtures)
- [ ] P5.T6 — `LegalAgent`, `MarketAgent`, `ContradictionAgent` · verify: `tests/agents/test_agents_legal.py`
- [ ] P5.T7 — `RiskAgent` (→ Risk rows, data_quality from contradictions) and `InvestmentCommitteeAgent` (opinions allowed, recommendation) · refs: F-10.AC1, AC2 · verify: `tests/agents/test_risk_ic.py`
- [ ] P5.T8 — Orchestrator DAG, `run_pipeline` job, cancel, cost pre-check, SSE run events, run endpoints · refs: F-07.AC4, F-15.AC1 · verify: `tests/agents/test_orchestrator.py`, `tests/api/test_runs.py`
- [ ] P5.T9 — Memo generator (Markdown with citation chips; DOCX via python-docx with footnotes) · refs: F-08.AC1, AC2 · verify: `tests/outputs/test_memo.py`
- [ ] P5.T10 — Valuation engine (revenue multiple, DCF, sensitivity; `missing_inputs`) · refs: F-12.AC1, AC2 · verify: `tests/outputs/test_valuation.py`
- [ ] P5.T11 — XLSX model generator (7 sheets, formulas, fact-id cell comments) · refs: F-09.AC1, AC2 · verify: `tests/outputs/test_model_xlsx.py`
- [ ] P5.T12 — Risk matrix, contradiction report, source map, graph outputs; `Output` versioning, stale + regenerate; outputs endpoints · refs: F-11.AC2 · verify: `tests/outputs/test_reports.py`, `tests/api/test_outputs.py`
- [ ] P5.T13 — `pine run <deal>` CLI + `pine eval evidence` (100 % coverage gate) · refs: F-07.AC2 · verify: CI step
- [ ] P5.T14 — Web: run panel (start, live agent statuses via SSE, rejections count) on overview; runs page · refs: F-13.AC2 · verify: `e2e/run.spec.ts`
- [ ] P5.T15 — Web: memo page (sections, citation chips → viewer highlight, opinion markers, download MD/DOCX) · refs: F-11.AC1 · verify: `e2e/memo.spec.ts`
- [ ] P5.T16 — Web: risks page (5×5 grid + list + detail), model page (sheet preview + download), sources page (source map explorer) · verify: `e2e/outputs.spec.ts`
**Exit criteria:** `pine run` on demo room with fake provider completes < 60 s with evidence coverage 100 %; with OpenAI provider completes < $3; all F-07…F-12 tests green.

## Phase 6 — Polish & Hardening
**Tasks:**
- [ ] P6.T1 — Motion pass per DESIGN_SYSTEM §6 (page transitions, list stagger, drawer, streaming agent log) + reduced-motion · verify: manual QA checklist
- [ ] P6.T2 — Accessibility audit (axe in Playwright, keyboard nav for viewer/tree/grid, live regions for run status) · verify: zero serious/critical axe violations
- [ ] P6.T3 — Performance: search/overview p95 budgets, web vitals on overview, embedding batch tuning · verify: `pine bench` output within EVAL_GUARDRAILS §6
- [ ] P6.T4 — Empty/error/partial state review across every route · verify: screenshot checklist
- [ ] P6.T5 — Security checklist G-SEC-* (upload guards fuzz test with hypothesis, header checks, log redaction test) · verify: `tests/security/`
- [ ] P6.T6 — Docker Compose (api, worker, web, postgres) + Postgres CI matrix job · verify: `docker compose up` → demo run completes
- [ ] P6.T7 — Eval gates in CI: `pine eval demo` (recall thresholds) + `pine eval evidence` blocking · verify: CI
- [ ] P6.T8 — Copy review, README with screenshots/GIF, CONTRIBUTING · verify: review
**Exit criteria:** all EVAL_GUARDRAILS budgets met; CI includes evals; compose deployment works.

## Phase 7 — Launch
- [ ] P7.T1 — Release workflow (GHCR images on tag), `v0.1.0` tag · verify: images pull and run
- [ ] P7.T2 — Backup/restore rehearsal (`pine backup`/`pine restore`) · verify: restored demo deal opens
- [ ] P7.T3 — Launch checklist: env docs, cost caps set, Sentry optional, demo deal recorded · verify: checklist complete

## Later / Backlog
- F-15 extras: per-deal cost dashboards, prompt version diffing
- MarketAgent web research with URL evidence (needs evidence model for web pages)
- Multi-user auth + roles; Postgres default; pgvector; arq/Redis worker
- `.msg` support; Datasite/Drive connectors; FX conversion facts
- LLM-assisted table repair for messy PDFs

## Feature → Phase Map

| Feature | Phase | Tasks |
|---|---|---|
| F-01 | P0, P1 | P0.T6, P1.T3, P1.T16, P1.T17 |
| F-02 | P1 | P1.T4–T13 |
| F-03 | P2 | P2.T1–T7 |
| F-04 | P3 | P3.T1, T2, T8, T9, T12 |
| F-05 | P3 | P3.T1–T7, T10, T11, T13 |
| F-06 | P4 | P4.T1–T7, T9, T11 |
| F-07 | P5 | P5.T2–T8, T13, T14 |
| F-08 | P5 | P5.T9, T15 |
| F-09 | P5 | P5.T11, T16 |
| F-10 | P5 | P5.T7, T12, T16 |
| F-11 | P1, P5 | P1.T18, P5.T12, T15, T16 |
| F-12 | P5 | P5.T10, T11, T16 |
| F-13 | P0, P4, P5 | P0.T9, P4.T8, T10, P5.T14 |
| F-14 | P1, P3, P4 | P1.T14, T15, P3.T13, P4.T11 |
| F-15 | P5 | P5.T1, T8, T14 |
