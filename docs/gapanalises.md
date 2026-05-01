# Gap Analysis & Agents Needed

_Last updated: 2026-04-30_

---

## 1. Current state

### What exists

| Component | Status |
|---|---|
| `cli/fetch_news.py` + `ingest-news` command | Working |
| `cli/fetch_company_meta.py` + `ingest-companies` command | Working |
| `graph-ingestor` subagent | Working |
| `raw_sources/` folder structure (all 8 kinds) | Exists, mostly empty |
| `wiki/` structure (all directories) | Exists |
| `templates/` (all page types) | Complete |
| `docs/` operating manual | Complete |

### What is missing — CLI fetchers

The docs define 7 ingest kinds. Only 2 have fetchers and slash commands:

| Kind | CLI fetcher | Slash command | Raw data present |
|---|---|---|---|
| `news` | `fetch_news.py` ✓ | `ingest-news.md` ✓ | Yes (380+ items) |
| `company_meta` | `fetch_company_meta.py` ✓ | `ingest-companies.md` ✓ | Yes |
| `prices` | — | — | **Empty** |
| `financials` | — | — | **Empty** |
| `kap_filings` | `fetch_kap.py` ✓ | `ingest-kap.md` ✓ | Yes (live; daily cron) |
| `analyst_notes` | — | — | **Empty** |
| `macro` | — | — | **Empty** |
| `sector_reports` | — | — | **Empty** |

### What is missing — wiki content

Every company page currently has:
- `Last price: Not available` — no price data pipeline
- `Bull: Not available / Bear: Not available` — no thesis pages written
- Financials sourced from AI-generated news summaries, flagged `needs_review`
- Zero `decisions/` pages (rating scale defined but never used)
- Zero `risks/` or `catalysts/` standalone pages (referenced but not created)
- Zero `theses/` pages

---

## 2. The growth problem

The graph-ingestor has a **1:many expansion rate**: 1 raw file → 5–15 wiki page writes. With 380+ news items already in `raw_sources/news/`, full ingestion would produce 2,000–5,700 wiki page touches — most of it redundant. The fifth article confirming "strong domestic demand" mints a new claim page that duplicates the fourth.

Without controls, the wiki hits noise faster than insight.

---

## 3. Agents needed

### 3.1 ~~Triage agent~~ — rejected design

A pre-ingest filter that discards "noise" before graph-ingestor runs was considered and rejected.

**Risk:** If the filter miscategorises a material item as noise, the wiki silently loses that connection. The raw file still exists in `raw_sources/` but no wiki node reflects it, and there is no easy way to discover what was dropped. An LLM classifier making autonomous discard decisions is too risky for an investment research system where a single missed claim can invalidate a thesis.

**Alternative:** Control expansion rate inside graph-ingestor and compact after the fact. See §4.

---

### 3.1 Compactor agent ✓ built

**Role:** Weekly housekeeping. Keeps the vault at a stable size rather than unbounded growth.

**When invoked:** Weekly cron.

**Three jobs:**

1. **Claim consolidation** — finds claim pages about the same assertion (e.g., multiple `eregl-domestic-demand-*.md` pages), merges them into one page with all sources listed, deletes the redundant files.
2. **Source page pruning** — deletes source pages older than 30 days. Claims they supported keep their `[[sources/...]]` link as a dead reference, which is acceptable — the claim is the durable node, not the source summary.
3. **Company page compaction** — replaces the ever-growing `## Events` append list with a "Current snapshot" block (latest known state) plus a rolling 30-day events window. Older events are summarised into a single paragraph and the individual bullets dropped.

**File:** `.claude/agents/compactor.md` ✓

**Slash command:** `.claude/commands/compact.md` ✓

---

### 3.2 Thesis-writer agent (medium priority, new)

**Role:** Synthesis layer between claims and decisions. Reads all claims for a company and writes or updates `wiki/theses/<TICKER>-bull.md` and `wiki/theses/<TICKER>-bear.md`.

**When invoked:** Triggered by the slash command when a company's claim count crosses a threshold (e.g., 3+ new claims since last thesis update), or manually by the user.

**Output:** Populated thesis pages that complete the `evidence → claim → thesis → decision` chain defined in `docs/graph-model.md`. Without this agent, decisions pages cannot be properly authored.

**File:** `.claude/agents/thesis-writer.md`

**Slash command:** `.claude/commands/write-thesis.md`

---

### 3.3 Lint agent (medium priority, new)

**Role:** Implements the `lint` workflow defined in `docs/workflows.md` which currently has no agent backing it.

**When invoked:** Weekly cron, or manually by the user.

**Checks:**
- Stale data past freshness thresholds (30d for prices/ratios, 90d for financials)
- Orphan pages with no inbound links
- Claims with no thesis connection
- Theses with no decisions page
- Decisions past `valid_until`
- Contradictions recorded but unresolved
- Concepts mentioned in multiple pages but lacking their own page (e.g., a risk named in five companies but no `risks/<name>.md` exists)

**Output:** Writes `wiki/dashboards/lint-report.md`. Reports, never fixes without user confirmation.

**File:** `.claude/agents/lint.md`

**Slash command:** `.claude/commands/lint.md`

---

### 3.4 Decision-drafter agent (lower priority, user-triggered)

**Role:** Drafts a `decisions/` page for a company on user request. Reads the company page, its thesis pages, and recent claims; applies the A/B/C/D/E/U rating scale from `docs/rating-scale.md`; writes a draft decision page for the user to review and approve.

**When invoked:** User runs `/decide <TICKER>`. Not automated — decisions require human approval.

**File:** `.claude/agents/decision-drafter.md`

**Slash command:** `.claude/commands/decide.md`

---

## 4. Algorithm changes to graph-ingestor

**Design principle: append-only at ingestion, tidy at compaction.**

Nothing is discarded at ingest time. Every raw file gets a source page — a faithful, lightweight record. Growth is controlled by reducing how many new pages are minted per source, not by filtering sources out. Pruning happens later, in the compactor, where decisions are reversible (the raw file and source page still exist).

### 4.1 Merge-not-Mint (claim deduplication) — primary growth control

Current behaviour: always mints a new claim file per assertion.

Proposed change: before writing a new claim, grep `wiki/claims/` for existing claims on the same topic and ticker. If a match exists, add the new source as a second citation on the existing claim page — no new file. Only mint a new claim file when no existing claim covers the same assertion.

**Effect:** The fifth article confirming "EREGL strong domestic demand" adds one source citation to `claims/eregl-q1-2026-strong-domestic-demand-high-utilization.md` instead of creating a sixth file. Claim pages become richer; the directory stays bounded.

This is the single highest-leverage change to the existing agent.

### 4.2 Source page always created — the safe floor

Every raw item that reaches graph-ingestor gets a `wiki/sources/` page regardless of whether it mints new claims or not. This is the minimal faithful record. It is what the compactor prunes later (after 30 days), not the ingestor.

### 4.3 Snapshot-not-Append (company page events)

Current behaviour: the `## Events` section grows indefinitely with appended dated bullets.

Proposed change:
- Keep a `## Current snapshot` section that is **overwritten** with the latest known state of each metric.
- Keep a rolling `## Events (last 30 days)` section with individual bullets.
- Events older than 30 days are summarised into one paragraph in a `## History` section; individual bullets are dropped.

The compactor agent runs this transformation weekly — the ingestor just appends as now.

---

## 5. Missing data sources (to unlock the reasoning chain)

The graph model requires `evidence → claim → thesis → decision`. Current evidence is news only. The following data kinds are needed to complete the chain:

| Data kind | Why needed | Source |
|---|---|---|
| **Prices** | Without current price, no valuation assessment is possible | tvscreener MCP (available now) |
| **Financials** | Q-results currently come from news summaries (AI-generated, `needs_review`). Need structured balance sheet / P&L data | KAP filings or a financial data API |
| **KAP filings** | Primary disclosure source for BIST companies. Currently proxied by Reuters summaries | KAP (Kamuyu Aydınlatma Platformu) |
| **Macro** | CBRT rates, CPI, FX rates — needed for macro theme pages and thesis context | CBRT, TurkStat, or a macro data API |
| **Analyst notes** | External price targets and ratings for calibration | Broker research, Quartr, etc. |

**Priority order:**
1. `fetch_prices.py` — tvscreener MCP is already wired in; this is the fastest unblock.
2. `fetch_financials.py` — unblocks thesis writing.
3. `fetch_kap.py` — replaces news-summary proxies with primary source data.
4. `fetch_macro.py` — completes macro theme pages.

---

## 6. Target pipeline (after all changes)

```
CLI fetcher
    ↓ (all items pass through — nothing discarded here)
Graph-ingestor        ← existing; add merge-not-mint + snapshot-not-append
    ↓                    every item gets a source page; claims are merged not minted
Compactor agent       ← new; weekly; prunes old source pages, merges claims, compacts events
    ↓
Thesis-writer agent   ← new; synthesis layer; triggered per company
    ↓
Decision-drafter      ← new; user-triggered; drafts A–E/U rating page
    ↓
decisions/            ← user reviews and approves
```

**No triage step.** Data loss at ingestion time is not acceptable in an investment research system. Growth is controlled by merge-not-mint (fewer new files per source) and by the compactor (pruning after the fact, always with the raw file as ground truth).

**Vault size ceiling (stable, not unbounded):**

```
(tracked companies × 1 page)
+ (active claims — deduplicated)
+ (30 days of source pages — pruned weekly)
+ (1 thesis page per company)
+ (1 decision page per company — dated snapshots)
+ (sector / theme / risk / catalyst pages — slow-growing)
```
