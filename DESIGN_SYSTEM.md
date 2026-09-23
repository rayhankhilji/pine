# Pine — Design System

> Version 1.0 · Updated 2026-09-23 · Governs everything in `web/`. If a screen disagrees with this file, the screen is wrong.

## 1. Design Direction

**"Editorial terminal."** Pine looks like a Bloomberg terminal that went to finishing school: the density and seriousness of a market console, the typography and whitespace discipline of a well-set annual report, and the restraint of Linear. It is precise, dense, calm, and evidentiary — every pixel says "these numbers can be audited".

- **Is:** dense but ordered; typographically driven; generous information per viewport; quiet chrome so documents and numbers carry the visual weight.
- **Is not:** playful, rounded-and-friendly SaaS; purple-gradient "AI magic" marketing aesthetic; glassmorphism, blur panels, glow effects; illustration-first empty states.
- **Light-first:** light mode is the primary surface (analysts read documents all day); dark mode is a full first-class variant, not an inversion hack.
- **Evidence is the hero:** citation chips, quoted spans and highlighted page regions get the strongest accent treatment on screen. Decoration never competes with evidence.

References: Bloomberg terminal (density, mono numerals, status pills) · a well-set printed annual report (column discipline, tabular figures, rules) · Linear (restraint, keyboard feel, muted palette).

## 2. Color Tokens

All tokens are CSS custom properties consumed by Tailwind v4 `@theme` (see `web/src/app/globals.css`). Hex first, OKLCH in parentheses. Never hard-code a hex in a component — use the semantic token.

### Light mode (default)

| Token | Value | Usage |
|---|---|---|
| `--background` | `#F7F5F0` (oklch 0.965 0.008 90) | page background, "paper" |
| `--surface` / `--card` | `#FFFFFF` (oklch 1.0 0 0) | cards, panels, tables |
| `--foreground` / `--ink` | `#14201A` (oklch 0.25 0.03 160) | primary text |
| `--muted-foreground` | `#5C665F` (oklch 0.50 0.02 160) | secondary text — 7.0:1 on background |
| `--primary` | `#1F4D3A` (oklch 0.38 0.07 165) | pine green — actions, links, focus |
| `--primary-foreground` | `#F7F5F0` | text on primary — 8.6:1 |
| `--accent` (moss) | `#5B7F5A` (oklch 0.55 0.07 145) | secondary emphasis, tags |
| `--warning` (contested) | `#B7791F` (oklch 0.62 0.12 70) | contested badges, warnings — use `#8A5A14` for text-on-paper (5.3:1) |
| `--destructive` (oxblood) | `#8B2E2E` (oklch 0.42 0.13 25) | errors, failed status — 7.4:1 on surface |
| `--success` | `#2F7D4F` (oklch 0.50 0.10 155) | parsed/ready/ok — 5.1:1 on surface |
| `--info` (slate) | `#3D5A80` (oklch 0.45 0.09 250) | informational chips, links in docs |
| `--border` | `#E1DDD3` (oklch 0.89 0.01 90) | hairlines, card borders |
| `--input` | `#CFC9BB` | control borders |
| `--ring` | `#1F4D3A` | focus ring, 2 px |
| `--muted` | `#EFECE4` | subtle fills, hover on paper |
| `--highlight` | `#F3E3B8` | evidence highlight overlay (viewer, citation target) |

### Dark mode (`.dark`)

| Token | Value |
|---|---|
| `--background` | `#0F1311` (oklch 0.19 0.01 160) |
| `--surface` / `--card` | `#161B18` (oklch 0.23 0.01 160) |
| `--foreground` / `--ink` | `#E8EDE9` (oklch 0.93 0.01 150) |
| `--muted-foreground` | `#9AA69E` (oklch 0.70 0.02 160) — 5.9:1 |
| `--primary` | `#7FB69A` (oklch 0.72 0.09 160) |
| `--primary-foreground` | `#0F1311` |
| `--accent` | `#8FB08D` |
| `--warning` | `#D9A13F` — 5.4:1 on surface for text |
| `--destructive` | `#D06A6A` |
| `--success` | `#5FB385` |
| `--info` | `#8AA8CC` |
| `--border` | `#2A322D` |
| `--input` | `#3A443E` |
| `--ring` | `#7FB69A` |
| `--muted` | `#1E2621` |
| `--highlight` | `#4A3F1E` |

**Contrast requirements (WCAG AA, verified):** foreground/background 14.4:1 · muted-foreground/background ≥ 4.5:1 · primary-foreground/primary ≥ 4.5:1 both modes · warning/destructive/success/info **text** on surface ≥ 4.5:1 both modes. Status may use colour fills only when paired with a text label — never colour alone.

**Semantic → status mapping:** `parsed/ready/completed` → success · `queued/parsing/indexing/running` → info · `contested/open contradiction/warning` → warning · `failed/error/critical` → destructive · `unsupported/unknown` → muted-foreground.

## 3. Typography

Two families only, both via `next/font`:

| Role | Family | Notes |
|---|---|---|
| Text & display | **Inter** (variable) | UI, headings, body. Display sizes use `tracking-tight` (`-0.02em`). No separate serif — hierarchy via weight/size/tracking. |
| Data & code | **JetBrains Mono** (variable) | **All numerals**, tables, metrics, citation chips, code, tokens, latency figures. Always with `font-variant-numeric: tabular-nums`. |

Scale (Inter, px / line-height):

| Token | Size | Weight | Use |
|---|---|---|---|
| `--text-xs` | 11/16 | 400–500 | chips, table secondary, timestamps |
| `--text-sm` | 13/20 | 400–500 | body dense, tables, nav |
| `--text-base` | 15/24 | 400 | default body, memo prose is 16/26 |
| `--text-lg` | 18/28 | 500 | card headlines, section titles |
| `--text-xl` | 22/30 | 600 | page titles |
| `--text-2xl` | 28/36 | 600 | deal name, big metrics |
| `--text-3xl` | 36/44 | 650 | hero metric only |

Rules: body copy sentence case; numerals always mono+tabular; metric values ≥ `--text-lg` mono; citation chips `[D12 p4]` are `text-xs` mono in a bordered pill; quotes in evidence use Inter with a 2 px `--accent` left rule — not italics.

## 4. Spacing, Layout & Grid

- **Base unit 4 px.** Scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 (`space-1`…`space-16`). Dense tables may use 6 px row padding; nothing else off-scale.
- **Page shell:** sidebar-less; top deal header + left-aligned section nav (see §9). Content max-width 1280 px, padding 24 px, gap 24 px.
- **Overview grid:** two-column card grid (`grid-cols-1 lg:grid-cols-2`, gap 16) of the 10 sections; each card = section title, headline metric, source count, contested badge.
- **Tables:** dense rows (36 px), hairline row borders `--border`, header `text-xs` uppercase tracking-wide muted, sticky header on scroll, mono numerals right-aligned.
- **Reader column:** memo and document text at 65 ch max.
- **Drawers:** right-side, 480 px, slide per §6; overlay `bg-foreground/20`, no blur.

## 5. Shape, Elevation & Effects

- **Radius:** 4 px chips/inputs/buttons · 6 px cards/panels · 10 px drawers/dialogs. Nothing larger.
- **Borders over shadows:** elevation is expressed with a 1 px `--border` hairline on a `--surface` fill. Shadows reserved for floating layers only: `shadow-sm` for dropdowns/popovers, `shadow-md` for dialogs/drawers — never on static cards.
- **Dividers:** 1 px `--border`; double-rule (`border-t` + 4 px gap + `border-t`) under deal header for the "annual report" cue.
- **No** gradients, glows, glass, or decorative illustration. One accent texture allowed: none.

## 6. Motion

Library: `motion` (framer-motion). Durations and easings are tokens — never literals in components.

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 80 ms | hover/active feedback |
| `--dur-fast` | 150 ms | chips, menus, small fades |
| `--dur-med` | 220 ms | drawers, dialogs, accordions |
| `--dur-slow` | 320 ms | page transitions, large panels |
| `--ease-standard` | cubic-bezier(0.2, 0, 0, 1) | default |
| `--ease-enter` | cubic-bezier(0, 0, 0, 1) | entering elements |
| `--ease-exit` | cubic-bezier(0.3, 0, 1, 1) | leaving elements |
| spring snappy | stiffness 500, damping 35 | chips, popovers, toggles |
| spring gentle | stiffness 220, damping 28 | drawers, panels, layout |

**Choreography:**
- List/cards stagger: 30 ms per item, **max 8 items**, then instant.
- Deal section nav underline: layoutId slide, `--dur-fast`.
- Drawer: x 480→0, spring gentle; content fades 100 ms delayed.
- Citation chip → viewer: click scrolls to page, then highlight pulses `--highlight` → transparent ×1 over 600 ms.
- Agent log rows: enter opacity+y 4 px, `--dur-fast`, ease-enter; newest row pinned.
- Contested badge: single 1→1.04→1 scale pulse on mount (spring snappy). Never loops.
- Page transitions: opacity only, `--dur-med`.
- **`prefers-reduced-motion`:** all animation → opacity-only ≤ 150 ms; springs disabled; no stagger, no pulse.

## 7. Iconography

`lucide-react` only, 16 px default / 14 px in dense tables / 20 px in empty states; stroke 1.5. Icons supplement text labels — never replace them on destructive or ambiguous actions. Recurring glyphs: `FileText` documents · `AlertTriangle` contested/contradiction · `CheckCircle2` parsed/resolved · `CircleDashed` queued · `XCircle` failed · `Quote` evidence · `GitBranch` graph · `ShieldAlert` risk · `Play`/`Square` run/cancel.

## 8. Components

Built on shadcn/ui primitives (Radix) re-themed with §2 tokens. Component inventory and rules:

- **Button:** primary `--primary` fill; secondary surface + border; ghost for toolbar; destructive oxblood. Height 32 px default (dense), radius 4.
- **Badge / Status pill:** `text-xs` mono, radius 4, 1 px border tinted at 30 % of the status colour + status-coloured text — never solid fills except `primary`. Includes text label always (see Risk grid rule).
- **Citation chip:** `[D12 p4]` — mono `text-xs`, bordered, `bg-muted`; hover → `--primary` border + tooltip with quote; click → viewer deep link + highlight pulse.
- **Card:** surface, `--border` 1 px, radius 6, padding 16, no shadow.
- **Table:** §4; numeric columns right-aligned mono; row hover `bg-muted`; selected row left 2 px `--primary` rule.
- **Dialog:** radius 10, max-width 480, `--dur-med` enter; destructive confirmations require typing? No — single confirm, but button labelled with the action ("Delete deal").
- **Drawer (Sheet):** right, 480 px, spring gentle; used for contradiction detail, entity panel.
- **Tabs:** underline style, `--primary` 2 px indicator.
- **Tooltip:** `text-xs`, surface+border, 150 ms.
- **Skeleton:** `bg-muted` bars, 1200 ms shimmer (opacity pulse under reduced-motion); match final layout geometry — no spinners for content areas; spinners only inside buttons.
- **Toast (sonner):** bottom-right, `text-sm`, auto 4 s; errors persist until dismissed.
- **Empty state:** 20 px icon muted, one-line description, one primary action. No illustrations.
- **Progress:** determinate bar `--primary` for uploads/runs when count known; otherwise status text, not spinners.
- **Contested badge:** amber `warning` pill + `AlertTriangle` + count (e.g. "3 sources disagree").

## 9. Patterns & Screen Specs

Every route below ships all five states: **empty** (action prompt), **loading** (skeleton of final layout), **error** (message + retry), **partial** (some data failed — banner with count), **success**. API down → route-level `error.tsx` with retry (F-13.AC3).

### `/` — Deals
Table of deals (name, company, stage pill, document count, last run status, open contradictions, created). Header actions: **New deal** (Dialog: name, company, stage select, currency, FY-end month — react-hook-form + zod) and **Load demo**. Empty: "Create a deal or load the demo data room." Loading: 5 skeleton rows. Error: card with message + Retry.

### `/deals/[id]` — Overview tree
Deal header: name, company, stage pill, run-status pill, "Run analysis" button. Body: two-column grid of the **10 sections** — `revenue, customers, margins, cap_table, contracts, liabilities, hiring, cash, forecast, risks`. Each card: section title, headline metric (mono, `text-xl`; "—" + `missing` chip when absent), source count (`12 sources`), contested badge when any headline fact is contested, click → section detail (facts/contradictions filtered). Run panel docks under the header when a run is active (agent statuses streaming).

### `/deals/[id]/documents`
Upload dropzone (drag + browse, per-file progress bars), document table (filename, path, type chip, status pill, pages, size, error on hover), "Unreadable files" collapsible group at bottom (`unsupported`/`failed` with retry). Index status chip + Reindex button in toolbar. Empty → dropzone fills content area. Live updates via SSE.

### `/deals/[id]/documents/[docId]` — Viewer
Three regions: thumbnail rail (96 px, left, page list or sheet tabs), page canvas centre (pdf.js render + highlight overlay rects from `bbox`; spreadsheet docs render as table view), evidence list right (quotes citing this document, click → page + pulse). `?page=&evidence=` deep links. Scanned pages show an "OCR" chip; `ocr_skipped` shows a warning banner.

### `/deals/[id]/search`
Single-line query input (`/`), filter row (doc type multi-select, document, date range, rerank toggle), results list: filename + `p{n}` link, snippet with `<mark>` matches, score mono `text-xs`. Empty-query state shows recent documents. Zero results: "No matches — try fewer filters."

### `/deals/[id]/graph`
Canvas force graph (react-force-graph-2d, lazy-loaded). Nodes coloured by entity type (legend chips top-left, each with label — never colour-only); selected entity opens right drawer: canonical name, aliases, evidence list, relations, facts, merge/split actions.

### `/deals/[id]/facts`
Filter bar (metric select, period range, source kind, contested-only toggle) + table: metric, value (mono, formatted), unit, period, source doc chip, confidence bar, contested badge. Row click → drawer with evidence quotes → viewer links. `is_authoritative` star.

### `/deals/[id]/contradictions`
List rows: severity pill, metric, spread %, rule id mono, status. Click → **detail drawer**: templated explanation, facts table (value · unit · period · source doc · verbatim quote with `Quote` icon), management question, actions **Mark authoritative** per row + **Dismiss** with note. Optimistic update with rollback.

### `/deals/[id]/memo`
Reader: 65 ch centred column, Inter 16/26. Citation chips inline `[D12 p4]` → viewer. Opinion sentences get a 2 px `--info` left rule + `opinion` label chip. Header: run selector, download MD / DOCX buttons, section TOC (sticky left, `text-xs`). Sections skeleton while generating.

### `/deals/[id]/model`
Sheet preview (Historicals, Forecast, Valuation tabs; read-only grid, mono numerals) + download XLSX. `missing_inputs` state lists needed metrics.

### `/deals/[id]/risks`
**5×5 grid**: likelihood (y) × impact (x); each occupied cell shows count + a risk chip; **severity conveyed by fill + text label together** ("Critical", "High"…) — never colour alone. Below: risk list (category pill, score mono, title); click → drawer with description, mitigations, linked claims/evidence, contradiction link.

### `/deals/[id]/sources`
Source map explorer: memo sections left → claims centre (each with kind chip) → evidence right (document, page, quote → viewer). Search box filters claims.

### `/deals/[id]/runs`
Run table (status pill, started, duration, tokens in/out mono, cost USD mono, agents expanded row: per-agent status/iterations/tokens, rejections count). Live run streams statuses. Failed runs show `error` inline.

## 10. Content & Voice

- **Sentence case** everywhere (buttons "Create deal", not "Create Deal"). No exclamation marks. No marketing adjectives.
- **Error formula:** *what happened* + *what to do*. "Upload failed — 2 files exceeded 200 MB. Remove them or split the archive." Never bare codes to users; codes live in `details`.
- **Numbers:** currency in deal currency, compact notation `$12.0M` / `$340K`; percents 1 decimal (`12.4 %`); counts plain (`1,247`); dates `23 Sep 2026`; periods `FY2025`, `Q4 2025`, `TTM Mar 2026`. All mono/tabular.
- **Uncertainty is content:** "contested", "3 sources disagree", "not in data room" are first-class labels — never hide missing data.
- Status labels: queued, parsing, parsed, failed, unsupported, indexing, ready, stale, running, completed, cancelled.

## 11. Accessibility

- WCAG 2.2 AA: contrast pairs per §2; focus ring `--ring` 2 px, offset 2, always visible; never remove outlines.
- All status conveyed by icon + text, never colour alone (Risk grid includes labels).
- Keyboard: nav sections via arrow keys; viewer `←/→` pages, `E` next evidence; `/` focuses search; `Cmd/Ctrl+Enter` submits dialogs; drawer/menu Esc closes. Focus returns to trigger on close.
- Live regions: run status pill `aria-live="polite"`; upload progress `aria-valuenow`.
- Reduced motion per §6. Minimum hit target 24 px (dense tables exempt → 20 px rows still keyboard-navigable).
- axe: zero serious/critical violations per page (checked in P6).

## 12. Implementation

- Tokens live in `web/src/app/globals.css` as CSS variables under `:root` (light) and `.dark` (dark), mapped into Tailwind via `@theme inline`. Dark mode toggled by `.dark` class on `<html>` (default follows `prefers-color-scheme`).
- Fonts: Inter + JetBrains Mono via `next/font/google`, exposed as `--font-sans` / `--font-mono`.
- Components consume only semantic utilities (`bg-surface`, `text-muted-foreground`, `border-border`, `text-warning`…). Raw hex/px/rgba in `src/` is a lint-level failure (enforced in P6 review; grep `#[0-9a-fA-F]{6}` should return only `globals.css`).
- Numerals: wrap metrics in `font-mono tabular-nums` (`.tnum` utility allowed).
- pdf.js and react-force-graph are `next/dynamic` lazy imports (JS budget, EVAL_GUARDRAILS §6).
- New components: compose shadcn primitives; if a pattern repeats twice it becomes a component in `src/components/`.
