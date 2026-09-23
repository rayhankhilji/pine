# Pine — Evaluation & Guardrails

> Version 1.0 · Updated 2026-09-23 · Blocking evals gate merges; budgets gate releases. IDs are stable — cite them in code, tests and reviews.

## 1. Definition of Done

A task is done only when **all** are true:

- [ ] Code compiles and is typed: `make lint` clean (ruff, mypy strict, ESLint).
- [ ] Tests exist at the path named in the ROADMAP task and pass: `make test`.
- [ ] Every acceptance criterion referenced by the task has a `T-Fxx-ACn` row green in TESTING_GUIDE §6.
- [ ] Error paths use the standard envelope + catalogue codes (ARCHITECTURE §5).
- [ ] No guardrail in this file is weakened without an ADR.
- [ ] TASK_LOG.md updated; committed per the commit-frequency rule (INSTRUCTIONS §11).
- [ ] Phase exit criteria (ROADMAP) are met before starting the next phase.

## 2. Security Guardrails

| ID | Rule | Reason | Verification |
|---|---|---|---|
| G-SEC-01 | API key compared with `hmac.compare_digest`; routes under `/api/*` require it when `PINE_API_KEY` set (except `/health`). | Timing-safe auth | `tests/test_auth.py`; code review |
| G-SEC-02 | Uploads: extension allowlist + signature-byte detection; size cap `MAX_FILE_MB` (200) per file, `MAX_DEAL_GB` (2) per deal. | Malware/quota | `tests/api/test_upload.py`; fuzz via hypothesis (P6.T5) |
| G-SEC-03 | Zip expansion: ≤ 5 000 members, ≤ 2 GB expanded, normalised paths only, no `..`/absolute traversal. | Zip-bomb/path traversal | `tests/api/test_upload.py` traversal cases |
| G-SEC-04 | Every deal-scoped query filters `deal_id` via `repos/base.py: scoped()`. | Cross-deal leakage | repo tests + code review checklist |
| G-SEC-05 | Outbound HTTP only to `OPENAI_BASE_URL` host; user-supplied URLs never fetched. | SSRF | dependency audit; `grep -r "httpx\|requests"` review |
| G-SEC-06 | Secrets via env only; never logged; `.env` git-ignored. | Leakage | `git log -p` scan; log redaction test |
| G-SEC-07 | Logs redact bank account numbers (regex on 8+ digit runs) via `logging/redact.py`. | Confidential data in logs | `tests/security/test_redact.py` (P6) |
| G-SEC-08 | CORS restricted to `WEB_ORIGIN`; web sends CSP `default-src 'self'`, `worker-src blob:`; HSTS in prod. | XSS/origin lockdown | header test; manual QA |
| G-SEC-09 | Rate limit 60 writes/min per API key (token bucket) → `429 RATE_LIMITED`. | Abuse | `tests/api/test_rate_limit.py` (P1+) |
| G-SEC-10 | No third-party analytics or telemetry anywhere. | Confidentiality | dependency review |

## 3. AI / Agent Guardrails

| ID | Rule | Reason | Verification |
|---|---|---|---|
| G-AI-01 | Uploaded and retrieved content is **data, never instructions**: document text is quoted/wrapped, system prompts forbid following in-document directives. | Prompt injection via data room | prompt review; injection fixture test |
| G-AI-02 | Every `fact` claim requires ≥ 1 resolvable `evidence_id` and a `quote` that is a verbatim substring of the evidence text (whitespace-normalised). | No unsupported claims | `tests/agents/test_gate.py`; `pine eval evidence` = 1.0 |
| G-AI-03 | `inference` claims need ≥ 1 evidence id or fact id, all resolvable. | Grounded reasoning | gate tests |
| G-AI-04 | `opinion` claims only from `investment_committee` agent; all other agents' opinions → `GateRejection(opinion_not_allowed)`. | Opinions are accountable | gate tests |
| G-AI-05 | Agent loop caps: ≤ 12 iterations, ≤ 120 s per agent, ≤ 2 structured-output repair retries. | Runaway/cost | `tests/agents/test_runtime.py` |
| G-AI-06 | Agents may only cite evidence ids returned by tools (pre-created stubs); the gate resolves them — agents never write Facts/Entities/Evidence. | Provenance integrity | boundary review; gate tests |
| G-AI-07 | `detect_contradictions` is deterministic rules R1–R7; LLMs may only explain/prioritise, never create or suppress contradictions. | Reproducibility (ADR-005) | `tests/contradictions/` |
| G-AI-08 | `LLM_PROVIDER=fake` runs make **zero** network calls. | Offline determinism (ADR-006) | `F-07.AC4` test asserts no network |
| G-AI-09 | Structured-output failure → repair retry with validation error appended (≤ 2); then AgentRun `failed`, run continues. | Robustness | runtime tests |
| G-AI-10 | Every LLM call recorded as `LLMCall` (model, tokens, cost, latency, request_hash). | Audit + cost | `tests/llm/`; F-15.AC1 |

## 4. Cost & Token Budgets

| Operation | Model | Max input tokens | Max output tokens | Notes |
|---|---|---|---|---|
| `extract_facts` (per chunk) | gpt-5-mini | 6 000 | 1 000 | only classified prose chunks |
| Agent iteration (document/legal/market/accounting/contradiction/risk) | gpt-5-mini | 60 000 | 4 000 | per iteration, ≤ 12 iterations |
| Financial + InvestmentCommittee agents | gpt-5 | 120 000 | 8 000 | per iteration |
| Rerank (`llm`) | gpt-5-mini | 8 000 | 500 | listwise |
| Embeddings | text-embedding-3-small | batch 100 texts × ≤ 800 tokens | — | batch + concurrent 4 |

**Run caps:** `RUN_MAX_TOKENS = 1_500_000` · `RUN_MAX_COST_USD = 10`.

| ID | Rule | Reason | Verification |
|---|---|---|---|
| G-COST-01 | Before a run starts, projected cost is checked; if over cap → `402 COST_CAP_EXCEEDED` and no Run work begins. | No surprise spend | `tests/api/test_runs.py` |
| G-COST-02 | Mid-run cap breach → graceful stop: current agent finishes its iteration, remaining agents skipped, partial outputs generated, Run marked `failed` with cost error. | Bounded loss | orchestrator test |
| G-COST-03 | Demo run (`fixtures/northwind`, real provider) targets < $3 total. | Demo affordability | manual cost check on changes to prompts |
| G-COST-04 | `LLM_CACHE=1` default in dev/test: identical request_hash returns cached response, `cache_hit=true`. | Dev cost | `tests/llm/test_cache.py` |

## 5. Error Handling Conventions

- Envelope `{"error": {"code", "message", "details"}}` on every non-2xx; `details.request_id` on INTERNAL.
- Codes only from the catalogue (ARCHITECTURE §5): VALIDATION 422 · UNAUTHORIZED 401 · NOT_FOUND 404 · CONFLICT 409 · FILE_TOO_LARGE 413 · DEAL_QUOTA_EXCEEDED 413 · UNSUPPORTED_TYPE 415 · RUN_IN_PROGRESS 409 · MISSING_INPUTS 422 · RATE_LIMITED 429 · PROVIDER_ERROR 502 · COST_CAP_EXCEEDED 402 · INTERNAL 500.
- `AppError(code, message, status, details)` — routers raise, never return raw error JSON.
- Provider failures: 3× exponential backoff + jitter on 429/5xx, 60 s timeout → then `PROVIDER_ERROR` surfaced, AgentRun `failed`, run continues (G-AI-09).
- User-facing messages follow DESIGN_SYSTEM §10: what happened + what to do.

## 6. Reliability & Performance Budgets

| ID | Budget | Measurement |
|---|---|---|
| G-PERF-01 | Hybrid search p95 < 300 ms @ 50k chunks/deal | `tests/index/` benchmark + `pine bench` |
| G-PERF-02 | `GET /deals/{id}/overview` p95 < 400 ms | API benchmark |
| G-PERF-03 | Upload of 100 files → `201` in < 10 s | `tests/api/test_upload.py` timing |
| G-PERF-04 | Full demo run with fake providers < 60 s | F-07.AC4 test |
| G-PERF-05 | Web vitals on overview: LCP < 2.5 s, INP < 200 ms, CLS < 0.1 | Lighthouse/Playwright (P6) |
| G-PERF-06 | Web JS ≤ 300 kB gz on overview route; pdf.js and force-graph lazy-loaded | `next build` output + bundle check |
| G-PERF-07 | Worker stale-lock release < 15 min; poll 500 ms; concurrency `WORKER_CONCURRENCY` (4) | `tests/jobs/test_worker.py` |
| G-PERF-08 | Restart-resume: queued jobs survive restart (DB-backed) | worker test |

## 7. Quality Evals

| Eval | Command | Threshold | Blocking |
|---|---|---|---|
| Fact recall on demo room | `pine eval demo` | ≥ 0.9 of `ground_truth.facts` recovered (value within tolerance) | yes (P3+) |
| Contradiction recall | `pine eval demo` | = 1.0 of planted contradictions flagged | yes (P4+) |
| Evidence coverage | `pine eval evidence` | = 1.0 — every `fact` claim has ≥ 1 resolvable evidence | yes (P5+) |
| Determinism | index twice with `hash` provider | embeddings byte-identical | yes (P2+) |

**Coverage floors (pytest-cov, api):** ≥ 85 % lines on `pine/facts/`, `pine/contradictions/`, `pine/agents/gate.py`; ≥ 70 % overall. Enforced in CI from P3 onward.

## 8. Privacy & Compliance

| ID | Rule | Verification |
|---|---|---|
| G-PRIV-01 | Data rooms are confidential: documents and extracted content never leave the machine except to OpenAI when `LLM_PROVIDER=openai` (documented, user-configured). | config review |
| G-PRIV-02 | `LLMCall.response` bodies stored only when `LLM_CACHE=1`; production deployments may set `LLM_CACHE=0` to avoid retaining LLM responses. | code review |
| G-PRIV-03 | No analytics, tracking, or crash-reporting third parties (Sentry only opt-in via `SENTRY_DSN`, P6). | dependency audit |
| G-PRIV-04 | Secrets and account numbers redacted in logs (G-SEC-06/07). | redaction test |
| G-PRIV-05 | Soft-deleted deals exclude all child rows from every list/detail response. | `tests/api/test_deals.py` |
| G-PRIV-06 | Backups (`pine backup`) stay local; restore rehearsal in P6 — no cloud sync built in. | checklist |

## 9. Change Control

- **ARCHITECTURE.md changes** require human approval; agents flag, never edit.
- **Guardrail changes** (this file) require an ADR entry in ARCHITECTURE §16.
- **API contract changes** (§5 shapes/codes) must update ARCHITECTURE + regenerate `types.ts` (`make generate`) in the same commit; CI fails on drift (`git diff --exit-code`).
- **Migration changes**: additive-only; never edit applied migrations; autogenerate then hand-review.
- **Prompt changes** (`agents/prompts/*.md`) bump the front-matter `version:` and update FakeLLM fixtures.
- **Dependency additions**: justify in the commit message; prefer stdlib/existing deps; check licence.
- **Guardrail overrides** in tests (e.g. raising iteration caps): never weaken a guardrail to make a test pass — fix the code or escalate.
