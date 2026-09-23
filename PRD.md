# Pine — Product Requirements

> Profile: AI agent product (+ B2B fintech / data pipeline) · Scope tier: MVP · Version: 1.0 · Updated: 2026-09-23

## 1. Summary

Pine is a Private Markets Intelligence Engine: an autonomous investment-diligence system that ingests an entire company data room (pitch decks, financial statements, bank statements, contracts, customer lists, cap tables, spreadsheets, board decks, emails, legal documents) and produces an auditable investment model. Every number and every conclusion in Pine's output is traceable to a specific document, page, and text span. Pine is for growth-equity and venture investors who currently spend weeks reconciling inconsistent numbers by hand, and it exists because LLMs are now good enough to read the documents but not trustworthy enough to be believed without evidence.

## 2. Problem & Opportunity

A typical Series B data room contains 50–500 files in a dozen formats. The same quantity — revenue, ARR, customer count, burn — appears in the deck, the P&L, the customer CSV, the board deck and the bank statements, and they rarely agree. Analysts reconcile these by hand in Excel, lose the trail of which number came from where, and the investment memo ends up citing "management figures" that nobody can re-derive. Existing tooling is either generic RAG chat (which hallucinates and cannot say "these three sources disagree") or manual. The opportunity is a system that is structurally incapable of making an unsupported claim: it extracts facts with provenance, builds a graph, detects contradictions deterministically, and only then lets agents reason — with their outputs validated against the evidence store.

## 3. Target Users

| Persona | Context | Goals | Frustrations | Technical level | Device |
|---|---|---|---|---|---|
| **Deal Analyst (primary)** | Associate/VP at a growth or VC fund, runs 3–6 diligences per quarter | Get to a defensible model and memo fast; know where every number came from | Reconciling numbers across files; losing provenance; re-reading 400-page data rooms | Excel expert, comfortable with web apps, not a programmer | Laptop, large screen |
| Investment Committee member | Partner reviewing the memo | Trust the numbers; see risks and disagreements up front | Memos that hide uncertainty; "per management" figures | Non-technical | Laptop / tablet |
| Diligence engineer | Technical person at a fund or a fintech building on Pine | Run Pine headless, extend extractors and agents | Black-box AI tools with no API | Developer | Terminal |

## 4. Core User Journeys

**J1 — First run: from zip to memo (time-to-value target: first overview in < 5 min for a 50-file room)**
1. Analyst creates a deal ("Northwind SaaS, Series B") — F-01
2. Drags a folder/zip of the data room onto the deal — F-01
3. Pine parses every file, showing per-file progress and any files it could not read — F-02
4. Pine chunks, embeds and indexes the corpus — F-03
5. Pine extracts facts and builds the knowledge graph — F-04, F-05
6. Contradiction engine flags disagreements (e.g. three ARR figures) — F-06
7. Agents run; every claim is evidence-checked — F-07
8. Analyst opens the deal overview tree (Revenue, Customers, Margins, Cap table, …) — F-13
9. Analyst exports the memo, model, risk matrix, contradiction report and source map — F-08…F-12

**J2 — Trace a number**
1. Analyst sees "ARR: $12.0M (contested)" in the overview — F-13
2. Clicks it → sees three facts from three documents with values, periods and confidence — F-06, F-11
3. Clicks a fact → document viewer opens at the page with the span highlighted — F-11, F-13
4. Analyst marks one fact as authoritative; downstream outputs recompute — F-06

**J3 — Headless / API run**
1. Engineer `POST /api/v1/deals`, uploads files, `POST /api/v1/deals/{id}/runs` — F-01, F-07
2. Polls `GET /api/v1/runs/{id}` until `completed` — F-15
3. Downloads outputs from `GET /api/v1/deals/{id}/outputs/{kind}` — F-08…F-12

**J4 — Demo without a real data room**
1. New user clicks "Load demo data room" — F-14
2. Pine seeds the synthetic Northwind room (deck, P&L, bank CSV, contracts, customer list, cap table, board deck, emails) with planted contradictions — F-14
3. J1 steps 3–9 run automatically

## 5. Features

### F-01 · Deals & data room upload — Priority: P0
- **User story:** As a Deal Analyst, I want to create a deal and upload a whole data room so that Pine can analyse every file in one place.
- **Details:** Deal has name, company name, stage, currency (default USD), fiscal year end (default Dec). Upload accepts multiple files and `.zip` archives (expanded server-side, nested folders preserved as `path`). Accepted types: pdf, docx, pptx, xlsx, xls, csv, tsv, txt, md, eml, msg (msg is P2), png, jpg. Max 200 MB per file, 2 GB per deal. Duplicate files (same sha256) are deduplicated and linked. Unsupported files are stored and marked `unsupported`, never silently dropped.
- **States:** empty (no deals → "Create a deal" + "Load demo"), uploading (per-file progress), success (file list with status chips), error (per-file: too large / unsupported / corrupt; deal-level: quota exceeded), partial (some files failed — banner with count and retry).
- **Acceptance criteria:**
  - F-01.AC1 — Given a new deal, When I upload a zip containing 10 files in nested folders, Then 10 `Document` rows exist with `path` preserved and `status = queued`.
  - F-01.AC2 — Given a file over 200 MB, When I upload it, Then the API returns `413 FILE_TOO_LARGE` and no Document row is created.
  - F-01.AC3 — Given two byte-identical files under different names, When both are uploaded, Then one `Blob` and two `Document` rows exist.
  - F-01.AC4 — Given a `.xyz` file, When uploaded, Then a Document row exists with `status = unsupported` and the UI shows it in an "Unreadable files" group.
- **Dependencies:** none

### F-02 · Document intelligence (parsing, OCR, layout, tables) — Priority: P0
- **User story:** As a Deal Analyst, I want every file turned into structured text, pages and tables so that nothing in the room is invisible to analysis.
- **Details:** Per type: PDF → text per page with bounding boxes, tables extracted with cell coordinates, scanned pages detected (< 50 chars/page) and OCR'd; DOCX → paragraphs + tables; PPTX → per-slide text + notes + tables; XLSX/CSV → each sheet becomes a `Table` with typed columns (number/date/text/currency inferred); EML → headers, body, attachments (attachments become child Documents); images → OCR. Every extracted unit is a `Page` (or sheet) with `Block`s (paragraph/heading/table/cell/figure) carrying `bbox` and `order`. Parsing runs as a background job with retries; a failed parser does not fail the deal.
- **States:** queued, parsing, parsed, failed (with parser error and "retry" action), unsupported.
- **Acceptance criteria:**
  - F-02.AC1 — Given a text PDF with a 5×4 table, When parsed, Then a `Table` with 5 rows and 4 columns exists linked to the page, and cell text matches the fixture.
  - F-02.AC2 — Given an image-only PDF page, When parsed with OCR enabled, Then the page has `is_scanned = true` and ≥ 90 % of the fixture's words are present in block text.
  - F-02.AC3 — Given an XLSX with two sheets, When parsed, Then two `Table` rows exist with `sheet_name` set and numeric columns typed `number`.
  - F-02.AC4 — Given a corrupt PDF, When parsed, Then Document `status = failed`, `error` is populated, and the pipeline continues with other files.
  - F-02.AC5 — Given an EML with a PDF attachment, When parsed, Then a child Document exists with `parent_document_id` set.
- **Dependencies:** F-01

### F-03 · Semantic chunking, embeddings, hybrid search, reranking — Priority: P0
- **User story:** As an agent (and as an analyst searching), I want to retrieve the most relevant passages and table rows across the whole room so that reasoning is grounded in the right evidence.
- **Details:** Chunking is structure-aware: headings start new chunks; tables are chunked per row-group with header row repeated; target 400 tokens, max 800, 60-token overlap for prose. Each `Chunk` stores `document_id, page_no, block_ids, char_start/end, text, token_count, embedding`. Retrieval = BM25 (keyword) ∪ dense cosine (embeddings) fused with reciprocal rank fusion (k = 60), top 50 → reranked to top 10 by a cross-encoder or LLM reranker (`RERANKER=cross-encoder|llm|none`). Filters: document type, document id, date range, entity. Embeddings provider: OpenAI `text-embedding-3-small` (1536-d) with deterministic `hash` provider for tests/offline.
- **States:** indexing (progress per deal), ready, stale (documents added since last index → "Reindex" action), error.
- **Acceptance criteria:**
  - F-03.AC1 — Given the demo room is indexed, When I search "annual recurring revenue", Then the top-3 results include the deck ARR slide chunk and the customer-list recurring revenue table chunk.
  - F-03.AC2 — Given a query containing an exact contract clause id ("Section 7.2"), When searched, Then the chunk containing that literal string ranks in the top 3 (BM25 path works).
  - F-03.AC3 — Given `EMBEDDINGS_PROVIDER=hash`, When indexing runs twice, Then chunk embeddings are byte-identical (determinism).
  - F-03.AC4 — Given a table with 200 rows, When chunked, Then every row chunk contains the header row text.
- **Dependencies:** F-02

### F-04 · Knowledge graph with evidence — Priority: P0
- **User story:** As a Deal Analyst, I want the company represented as a graph (Company → Customer → Contract → Revenue → Invoice, plus people, cap table, liabilities) so that relationships are explicit and navigable.
- **Details:** Entity types: `Company, Customer, Contract, RevenueStream, Invoice, Person, Shareholder, SecurityClass, Liability, BankAccount, Employee, Market`. Relation types: `HAS_CUSTOMER, HAS_CONTRACT, GENERATES_REVENUE, BILLED_BY, OWNS_SHARES, EMPLOYS, OWES, BANKS_WITH, COMPETES_IN`. Every entity and relation has ≥ 1 `Evidence` (document, page, chunk, char span, optional table cell). Entity resolution merges duplicates by normalised name + fuzzy match (token-set ratio ≥ 92) with a manual merge/split action. Graph is exportable as JSON and GraphML.
- **States:** building, ready, empty (no entities extracted → guidance), error.
- **Acceptance criteria:**
  - F-04.AC1 — Given the demo room, When the graph is built, Then a `Company` node "Northwind" exists with ≥ 20 `HAS_CUSTOMER` edges, and each edge has ≥ 1 Evidence row.
  - F-04.AC2 — Given "Acme Corp." in a contract and "ACME Corporation" in the customer CSV, When resolved, Then one Customer entity exists with two `EntityAlias` rows.
  - F-04.AC3 — Given any entity, When `GET /api/v1/entities/{id}` is called, Then the response includes `evidence[]` and no entity exists with zero evidence (DB constraint enforced in tests).
- **Dependencies:** F-03, F-05

### F-05 · Fact extraction (metrics with provenance) — Priority: P0
- **User story:** As a Deal Analyst, I want every quantitative claim (ARR, revenue, gross margin, cash, burn, headcount, churn, contract value) captured as a normalised fact with period, unit, source and confidence so that facts can be compared.
- **Details:** A `Fact` = `(subject_entity, metric, value, unit, currency, period_start, period_end, period_type, as_of, source_kind, confidence, extraction_method, evidence[])`. Metrics are a controlled vocabulary in `packages/schemas/metrics.py` (≈ 40 metrics: `arr, mrr, revenue, recurring_revenue, gross_margin, net_revenue_retention, logo_churn, cash_balance, net_burn, runway_months, headcount, cac, ltv, contract_value, …`). Extraction paths: (a) deterministic table extractors (P&L, bank statement, customer list, cap table templates); (b) LLM structured extraction from prose chunks with mandatory `evidence_quote` that must be a substring of the chunk (rejected otherwise); (c) derived facts computed from other facts (e.g. `runway_months = cash / net_burn`) with `extraction_method = derived` and evidence inherited. `source_kind ∈ {deck, financial_statement, bank_statement, customer_list, contract, cap_table, board_deck, email, legal, other}` inferred from document classification.
- **States:** extracting (progress), ready, error; per-fact `confidence` badge.
- **Acceptance criteria:**
  - F-05.AC1 — Given the demo P&L XLSX, When extracted, Then facts `revenue` for FY2024 and FY2025 exist with `extraction_method = table` and values equal to the fixture.
  - F-05.AC2 — Given a prose chunk "ARR reached $12M in Q4 2025", When LLM-extracted, Then a fact `arr = 12000000 USD, period 2025-Q4` exists whose `evidence_quote` is a substring of the chunk text.
  - F-05.AC3 — Given an LLM extraction whose `evidence_quote` is not in the chunk, When validated, Then the fact is rejected and logged as `EVIDENCE_MISMATCH` (no Fact row).
  - F-05.AC4 — Given `cash_balance` and `net_burn` facts for the same period, When derivation runs, Then a `runway_months` fact exists with `extraction_method = derived` and both parents listed in `derived_from`.
- **Dependencies:** F-02, F-03

### F-06 · Contradiction engine — Priority: P0
- **User story:** As a Deal Analyst, I want Pine to tell me when different documents disagree about the same thing so that I investigate the right issues first.
- **Details:** Deterministic rules run over `Fact`s grouped by `(subject, metric, comparable period)`: (R1) numeric disagreement beyond tolerance (default 5 % relative or metric-specific, e.g. `headcount` 0); (R2) unit/currency mismatch; (R3) temporal impossibility (ARR declining while deck says "growing 3× YoY"); (R4) sum mismatch (customer-list recurring revenue sum ≠ reported ARR); (R5) cap table does not sum to 100 %; (R6) contract term vs. revenue recognition period conflict; (R7) bank inflows vs. reported revenue divergence > 15 %. Each `Contradiction` has `severity (info|low|medium|high|critical)`, `rule_id`, `facts[]`, `explanation` (templated, not LLM), and `status (open|resolved|dismissed)`. Resolution = mark one fact authoritative or dismiss with note; downstream outputs recompute. A `ComparablePeriod` helper maps FY/quarter/month/TTM/"as of" into overlapping windows.
- **States:** none found (positive empty state), list with severity filter, detail with evidence trail, resolved.
- **Acceptance criteria:**
  - F-06.AC1 — Given deck ARR 12.0M, statement SaaS revenue 9.7M, customer-list recurring revenue 10.2M for FY2025, When the engine runs, Then one `Contradiction` with `rule_id = R1`, 3 facts, severity ≥ high exists and its explanation names all three sources.
  - F-06.AC2 — Given two facts differing by 2 % on `revenue`, When the engine runs, Then no contradiction is created.
  - F-06.AC3 — Given a cap table summing to 103 %, When R5 runs, Then a contradiction with severity high is created citing the cap-table document.
  - F-06.AC4 — Given an open contradiction, When I mark fact B authoritative, Then status = resolved, `authoritative_fact_id = B`, and the deal overview shows B's value.
- **Dependencies:** F-05

### F-07 · Evidence-gated agent pipeline — Priority: P0
- **User story:** As an IC member, I want specialised agents to analyse the room and produce conclusions I can trust because every claim is validated against evidence.
- **Details:** Agents (in order, DAG): `DocumentAgent` (classify documents, detect gaps: "no bank statements after March"), `FinancialAgent` (revenue quality, margins, cash, burn, forecast inputs), `AccountingAgent` (recognition policies, one-offs, deferred revenue, related-party items), `LegalAgent` (contract terms, change-of-control, exclusivity, liabilities, litigation, IP), `MarketAgent` (TAM claims vs. evidence, competitors — from room documents only, no web in MVP), `ContradictionAgent` (explains and prioritises engine output, proposes resolution questions for management), `RiskAgent` (builds risk matrix), `InvestmentCommitteeAgent` (synthesises memo, recommendation, valuation scenarios). Each agent: receives tools `search(query, filters)`, `get_facts(metric, period)`, `get_entity(id)`, `get_contradictions()`, `open_document(id, page)`; emits `Claim`s `{text, kind (fact|inference|opinion), evidence_ids[], fact_ids[], confidence}`. The `EvidenceGate` rejects any `fact` claim without ≥ 1 evidence id resolving to a real chunk/cell whose text contains the claim's `quote`; `inference` claims must reference ≥ 1 fact or evidence; `opinion` claims are allowed only from `InvestmentCommitteeAgent` and are labelled as such in outputs. Max 12 tool iterations per agent, 120 s timeout, structured output with 2 repair retries. All prompts live in `api/pine/agents/prompts/*.md`. Provider: OpenAI (`gpt-5` for IC/Financial, `gpt-5-mini` for others — see ARCHITECTURE §10) via a provider interface with a `FakeLLM` for tests.
- **States:** run queued, running (per-agent status + live log), completed, failed (agent name + error, partial outputs kept), cancelled.
- **Acceptance criteria:**
  - F-07.AC1 — Given a FakeLLM returning a claim with a non-existent evidence id, When the gate runs, Then the claim is dropped, a `GateRejection` row is logged, and the run still completes.
  - F-07.AC2 — Given the demo room, When a run completes, Then every `Claim` of kind `fact` in the memo has ≥ 1 resolvable evidence id (integration test walks all claims).
  - F-07.AC3 — Given an agent exceeding 12 iterations, When running, Then it is stopped, its partial claims are kept, and the run reports `agent_status = iteration_limit`.
  - F-07.AC4 — Given `LLM_PROVIDER=fake`, When a full run executes, Then it completes in < 60 s with zero network calls.
- **Dependencies:** F-03, F-04, F-05, F-06

### F-08 · Investment memo — Priority: P0
- **User story:** As an IC member, I want a structured memo (Markdown + DOCX) with inline citations so that I can read the conclusions and check any of them.
- **Details:** Sections: Summary & recommendation, Company, Revenue & customers, Margins & unit economics, Cash & runway, Cap table, Contracts & legal, Liabilities, Team & hiring, Forecast, Valuation, Risks, Open questions for management, Contradictions, Appendix: source map. Each claim renders as text followed by citation chips `[D12 p4]` linking to evidence. Opinion claims are visually marked. Memo is regenerated on each run and versioned.
- **States:** not generated (before first run), generating, ready, stale (facts changed after generation), error.
- **Acceptance criteria:**
  - F-08.AC1 — Given a completed run, When I open the memo, Then every section exists and every sentence with a number has ≥ 1 citation chip.
  - F-08.AC2 — Given the memo, When I download DOCX, Then a valid .docx with the same headings and footnoted citations is produced.
- **Dependencies:** F-07

### F-09 · Financial model & forecast (XLSX) — Priority: P0
- **User story:** As a Deal Analyst, I want a spreadsheet model built from extracted facts with live formulas so that I can adjust assumptions myself.
- **Details:** Workbook sheets: `Inputs` (all facts used, with source cell comments), `Historicals` (revenue, COGS, gross margin, opex, EBITDA, cash, burn by period), `Customers` (cohort/top-customer concentration), `Forecast` (36 months driven by `Assumptions` sheet: growth, churn, gross margin, hiring plan), `CapTable` (fully diluted, pro forma for the proposed round), `Valuation` (see F-12), `Sources` (fact id → document/page). Formulas are real Excel formulas (openpyxl), not pasted values, except historical inputs. Each input cell carries a comment with the fact id and citation.
- **States:** not generated, generating, ready, stale, error.
- **Acceptance criteria:**
  - F-09.AC1 — Given a completed run, When I download the model, Then the workbook opens (openpyxl load) with all 7 sheets and `Forecast!B10` contains a formula referencing `Assumptions`.
  - F-09.AC2 — Given `revenue` facts for 3 periods, When generated, Then `Historicals` has those 3 columns with the exact fact values and a cell comment containing the fact id.
- **Dependencies:** F-05, F-07

### F-10 · Risk matrix — Priority: P0
- **User story:** As an IC member, I want a risk matrix (likelihood × impact) with evidence so that I can weigh risks consistently across deals.
- **Details:** `Risk` = `{title, category (financial|legal|market|operational|team|accounting|data_quality), likelihood 1–5, impact 1–5, score, description, mitigations, claims[]}`. Produced by `RiskAgent`; every risk cites ≥ 1 claim (hence evidence). Exportable as JSON and Markdown table; rendered as a 5×5 heat grid.
- **States:** empty ("no risks identified" is itself flagged as suspicious), grid, detail.
- **Acceptance criteria:**
  - F-10.AC1 — Given a completed demo run, When I open risks, Then ≥ 5 risks exist across ≥ 3 categories and each has ≥ 1 evidence id.
  - F-10.AC2 — Given an open critical contradiction, When RiskAgent runs, Then a `data_quality` risk referencing that contradiction exists.
- **Dependencies:** F-06, F-07

### F-11 · Contradiction report & source map — Priority: P0
- **User story:** As a Deal Analyst, I want a report of every disagreement and a map from every output number back to its source so that the work is auditable.
- **Details:** Contradiction report (Markdown/JSON): each contradiction with rule, severity, facts table (value, unit, period, document, page, quote), status, proposed management question. Source map (JSON + interactive UI): `output location → claim → evidence → document/page/span`. Document viewer renders PDF pages (PDF.js) with highlighted spans; spreadsheets render as tables with highlighted cells.
- **States:** report empty (no contradictions), list, detail; viewer loading, ready, page-not-found error.
- **Acceptance criteria:**
  - F-11.AC1 — Given evidence with a bbox on a PDF page, When I open it from a citation chip, Then the viewer opens at that page with the span highlighted within 1 s (local).
  - F-11.AC2 — Given the source map JSON, When validated, Then every `evidence_id` resolves and every `document_id` exists (integration test).
- **Dependencies:** F-06, F-07

### F-12 · Valuation scenarios — Priority: P0
- **User story:** As an IC member, I want base/bull/bear valuation scenarios with explicit assumptions so that the recommendation is quantified.
- **Details:** Methods: revenue multiple (ARR × multiple range), DCF on the forecast (WACC, terminal growth), and precedent-style sensitivity table. Scenario assumptions are `Fact`-backed where possible (ARR, growth, margin) and explicitly labelled `assumption` otherwise. Output: table of scenario → assumptions → enterprise value → implied ownership at proposed round; also written into the XLSX `Valuation` sheet.
- **States:** not generated, ready, missing-inputs (lists which facts are absent, e.g. "no ARR fact").
- **Acceptance criteria:**
  - F-12.AC1 — Given ARR and growth facts, When scenarios generate, Then three scenarios exist with `enterprise_value` and every assumption either cites a fact id or is flagged `assumption`.
  - F-12.AC2 — Given no ARR fact and no revenue fact, When generation runs, Then status = `missing_inputs` listing `arr|revenue` and no scenario is fabricated.
- **Dependencies:** F-05, F-09

### F-13 · Web dashboard — Priority: P0
- **User story:** As a Deal Analyst, I want a dashboard that shows the company tree (Revenue, Customers, Margins, Cap table, Contracts, Liabilities, Hiring, Cash, Forecast, Risks) with contested values marked so that I can navigate the analysis.
- **Details:** Routes in ARCHITECTURE §7. Overview tree nodes show headline facts with confidence and "contested" badge (open contradiction). Documents page with status, type, page count, parse errors. Graph page (force layout, filter by type). Contradictions page. Memo page. Model page (sheet preview + download). Sources page (source map explorer). Run panel with per-agent status streamed via SSE.
- **States:** every screen implements empty / loading (skeleton) / error (retry) / partial (run in progress) / success.
- **Acceptance criteria:**
  - F-13.AC1 — Given a deal with a completed run, When I open `/deals/{id}`, Then the 10 tree sections render with headline facts and contested badges matching open contradictions.
  - F-13.AC2 — Given a run in progress, When I view the deal, Then agent statuses update live without page reload (SSE).
  - F-13.AC3 — Given the API is down, When I open any deal page, Then an error state with a retry button renders (no blank screen, no uncaught exception).
- **Dependencies:** F-01…F-12

### F-14 · Synthetic demo data room — Priority: P0
- **User story:** As a new user or test suite, I want a realistic synthetic data room with planted contradictions so that Pine can be demonstrated and tested deterministically.
- **Details:** Generator script `pine demo build` produces `fixtures/northwind/` with: pitch deck PPTX (ARR $12M), P&L XLSX (SaaS revenue $9.7M), customer list CSV (recurring revenue sums to $10.2M, 40 customers, top customer 22 %), bank statements CSV (12 months), 5 contract PDFs (one with change-of-control clause, one auto-renew), cap table XLSX (sums to 103 % — planted), board deck PDF, 6 EML emails (one mentions a churned customer still in the list), a scanned-PDF page (rendered image) for OCR. A `ground_truth.json` lists planted facts and contradictions used by tests.
- **States:** not loaded, loading, loaded.
- **Acceptance criteria:**
  - F-14.AC1 — Given a clean checkout, When `pine demo build` runs, Then all files above exist and `ground_truth.json` validates against its schema.
  - F-14.AC2 — Given the demo room, When the full pipeline runs with `LLM_PROVIDER=fake`, Then ≥ 90 % of `ground_truth.facts` are recovered (value within tolerance) and 100 % of `ground_truth.contradictions` are flagged.
- **Dependencies:** F-02…F-06

### F-15 · Runs, audit log & cost tracking — Priority: P1
- **User story:** As a Diligence engineer, I want each pipeline run recorded with per-agent timings, token usage and cost so that runs are reproducible and affordable.
- **Details:** `Run` and `AgentRun` rows with status, started/finished, tokens in/out, cost USD, model, prompt version hash. `GET /api/v1/runs/{id}` returns the tree. Cost caps per ARCHITECTURE/EVAL_GUARDRAILS G-COST.
- **States:** list, detail, cap-exceeded.
- **Acceptance criteria:**
  - F-15.AC1 — Given a completed run, When fetched, Then each AgentRun has `tokens_in, tokens_out, cost_usd, duration_ms` populated (0 for fake provider).
- **Dependencies:** F-07

## 6. Out of Scope

- Multi-tenant auth, SSO, roles — single-workspace local/self-hosted MVP; a static API key protects the API. (Keeps Phase 0 small; add later behind the policy layer.)
- Live web research by MarketAgent — evidence must come from the room in MVP to keep the evidence guarantee simple.
- Real-time collaboration / comments — not needed for time-to-first-memo.
- Fine-tuning models — prompt + structured outputs suffice.
- `.msg` Outlook files — P2; `.eml` covers the test corpus.
- Native mobile apps — desktop web only.
- Data room connectors (Datasite, Intralinks, Google Drive) — upload/zip only.
- Excel formula parsing of uploaded models — we read values, not formulas.
- Automated valuation "recommendation" without human review — Pine outputs scenarios, the IC decides.

## 7. Success Metrics

| Metric | Definition | Target | Tool |
|---|---|---|---|
| **Evidence coverage (north star)** | `fact` claims with ≥ 1 resolvable evidence ÷ all `fact` claims in memo | 100 % (hard gate) | `pine eval evidence` in CI |
| Fact recall on demo room | recovered `ground_truth.facts` ÷ total | ≥ 90 % | `pine eval demo` |
| Contradiction recall on demo room | flagged planted contradictions ÷ planted | 100 % | `pine eval demo` |
| Contradiction precision | contradictions not dismissed as noise ÷ raised (manual review set of 30) | ≥ 80 % | review sheet `evals/contradictions.csv` |
| Time to first overview | upload complete → overview renders, 50-file demo room, fake LLM | < 5 min (p95) | `run.duration_ms` in Run table |
| Cost per run | Σ `AgentRun.cost_usd` on demo room, real provider | < $3.00 | Run table |
| Activation | deals with ≥ 1 completed run ÷ deals created | ≥ 70 % | SQL on `deal`, `run` |
| Retention proxy | users returning to open a memo ≥ 24 h after run | ≥ 50 % | app log event `memo_opened` |

## 8. Non-Functional Requirements

- **Performance:** parse throughput ≥ 2 pages/s text PDFs on a laptop; OCR ≥ 0.3 pages/s; search p95 < 300 ms for 50k chunks; overview page LCP < 2.5 s; INP < 200 ms.
- **Availability:** self-hosted MVP; API restarts must resume queued jobs (job state in DB, not memory).
- **Accessibility:** WCAG 2.2 AA; keyboard parity for viewer and tree; no colour-only meaning for severity.
- **Privacy:** data rooms are confidential — no third-party analytics; documents never leave the host except chunk text sent to the configured LLM/embedding provider; provider data-retention flags set to no-training. Redact bank account numbers in logs.
- **Localization:** English UI; number/currency formatting by deal currency; multi-currency facts stored with currency code.
- **Browsers:** last 2 versions of Chrome, Edge, Safari, Firefox; min width 1024 px.
- **Data retention:** deals persist until deleted; delete cascades to blobs; export before delete.

## 9. Assumptions

| # | Assumption | Reasoning | To change |
|---|---|---|---|
| A1 | Python for the engine, Next.js for the UI | Best OCR/table/PDF ecosystem is Python; user confirmed | ARCHITECTURE §2 + ADR |
| A2 | SQLite (dev/default) via SQLAlchemy 2, Postgres 16 optional via `DATABASE_URL` | Zero-setup local run; same ORM for both | Set `DATABASE_URL`; migrations are Alembic and DB-agnostic |
| A3 | Vector search in-process (numpy cosine over stored embeddings) + BM25 via `rank_bm25` | Data rooms are ≤ 100k chunks; avoids a vector DB dependency | ADR to swap in pgvector when > 250k chunks |
| A4 | OpenAI is the only live LLM/embedding provider in MVP; `fake` and `hash` providers for tests | User chose OpenAI; deterministic tests need no network | Add provider class in `api/pine/llm/providers/` |
| A5 | Background jobs run in-process (FastAPI lifespan worker polling a `job` table) | No Redis/Celery ops burden for MVP | ADR to move to arq/Redis |
| A6 | OCR via Tesseract (`pytesseract`), optional at install | Free, local, good enough for scanned statements | `OCR_PROVIDER` setting |
| A7 | Single API key auth (`PINE_API_KEY`), no users table | Out of scope §6 | Add auth phase later |
| A8 | Currency conversion is not performed; mismatched currencies raise contradiction R2 | Avoid silent FX assumptions | Add FX table + `fx_rate` facts |

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM extraction hallucinates numbers | Mandatory `evidence_quote` substring check; table extractors preferred; recall evals |
| Table extraction quality on messy PDFs | pdfplumber + camelot-style heuristics; fall back to LLM table repair with cell-level evidence; fixtures for regression |
| Entity resolution merges wrong customers | Conservative threshold, manual split, aliases preserved |
| Contradiction noise | Metric-specific tolerances, period comparability rules, precision eval set |
| Cost blow-up on big rooms | Token caps per agent, cheaper model for extraction, caching by chunk hash |
| Python 3.14 wheel availability for PDF/OCR libs | Pin Python 3.12 via `uv python pin 3.12` |

## 11. Open Questions

| Question | Owner | Default if unanswered | Decide by |
|---|---|---|---|
| Should the memo DOCX use a fund-specific template? | User | Built-in neutral template | P5 |
| Allow MarketAgent web search later? | User | No (room-only evidence) | Post-MVP |
| Postgres as default for team deployments? | User | SQLite default, Postgres via env | P6 |

## 12. Glossary

- **Data room** — the set of files a company shares for diligence.
- **Fact** — a normalised quantitative or categorical statement with provenance.
- **Evidence** — a pointer to a document, page, chunk and character/cell span.
- **Claim** — an agent statement (`fact`, `inference`, `opinion`) with evidence/fact references.
- **Evidence gate** — validator that rejects claims lacking resolvable evidence.
- **Contradiction** — a rule-detected disagreement between facts.
- **Run** — one execution of the pipeline for a deal.
- **ARR / MRR / NRR** — annual/monthly recurring revenue, net revenue retention.
