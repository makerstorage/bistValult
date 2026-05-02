# Gap Analysis & Agents Needed

_Last updated: 2026-05-02 (thesis-writer agent shipped — see §3.2)_

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
| `prices` | `fetch_prices.py` ✓ | `ingest-prices.md` ✓ | Yes (daily cron) |
| `financials` | — | — | **Empty** |
| `kap_filings` | `fetch_kap.py` ✓ | `ingest-kap.md` ✓ | Yes (live; daily cron) | ✓ done |
| `analyst_notes` | — | — | **Empty** |
| `macro` | — | — | **Empty** |
| `sector_reports` | — | — | **Empty** |

### What is missing — wiki content

Every company page currently has:
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

### 3.2 Thesis-writer agent ✓ built (2026-05-02)

**Role:** Synthesis layer between claims and decisions. Writes or updates `wiki/theses/<TICKER>-bull.md` and `wiki/theses/<TICKER>-bear.md` for a single ticker.

**Trigger:** User-triggered per ticker — `uv run python -m cli.run thesis --ticker EREGL` or `/thesis EREGL`. Cron-driven change-detection mode is deliberately not built yet; we want one-ticker-at-a-time judgment-checking before we automate.

**Architecture (the heart of the design — keep coherent if changing).**

The thesis-writer is the first agent that needs *judgment*, not classification. Its biggest failure mode is being drowned in noise. The defence is a **deterministic Python-side context selector** at `cli/lib/thesis_context.py`:

- Walks `company → claims → sources → sectors → themes → risks → catalysts → existing thesis` with hard caps (12 claims, 8 sources, 2 sectors, 4 themes, 5 risks, 5 catalysts).
- Sources are KAP-prioritised, then by recency.
- Source bodies are trimmed to `Provenance + Key facts + Entities mentioned` only — Notes/caveats stripped.
- Sector / theme bodies trimmed to their discriminating sections only.
- The agent never does broad graph traversal — the curated block is canonical for the run.

**Mechanical confidence (not LLM-judged):** `compute_confidence()` in the same module computes a `score = #claims + 2*#KAP_cited - 2*#contradictions - #stale_60d`. High ≥ 6, Medium 3–5, Low ≤ 2. The agent receives this verbatim and is forbidden from overriding it.

**Two-pass execution:** the orchestrator (`cli/orchestrators/write_thesis.py`) runs the agent twice — once with bull framing, once with bear — to avoid the "balanced bull / balanced bear that hedge each other into mush" failure mode. Same context block, different framing.

**Refusal contract:** if the ticker has < 2 claims, the orchestrator refuses without an LLM call and logs `REFUSED — Only N claim(s) for TICKER; below minimum 2.`. Conservative-tone rule applied at the design level: better no thesis than a bad one.

**Risk / catalyst minting:** the agent may write **stub** `wiki/risks/<slug>.md` and `wiki/catalysts/<slug>.md` pages when a thesis surfaces a named risk/catalyst with no dedicated page yet. Stubs are bare — name, one-line description, one source, one company link, one open question. Both folders started empty; theses are the natural moment to populate them.

**Files:**
- `.claude/agents/thesis-writer.md`
- `.claude/commands/thesis.md` (slash command name is `/thesis`, not `/write-thesis`)
- `cli/orchestrators/write_thesis.py`
- `cli/lib/thesis_context.py`
- `tests/test_thesis_context.py` (17 unit tests, no LLM)

**Open follow-ups:**
- Cron-driven change-detection (3+ new claims since last thesis run) — gated on confidence the user-triggered version produces good output across enough tickers first.
- `--all` mode to walk every tracked ticker — premature until single-ticker output is trusted.
- Confidence formula tuning once we have ground truth from a few decisions cycles.

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

## 4. Algorithm changes to graph-ingestor ✓ done

**Design principle: append-only at ingestion, tidy at compaction.**

Nothing is discarded at ingest time. Every raw file gets a source page — a faithful, lightweight record. Growth is controlled by reducing how many new pages are minted per source, not by filtering sources out. Pruning happens later, in the compactor, where decisions are reversible (the raw file and source page still exist).

### 4.1 Merge-not-Mint (claim deduplication) ✓ implemented

Step 7 of `graph-ingestor.md` implements the full merge-before-mint procedure: grep `wiki/claims/` for the ticker, read matching files, compare semantically, merge if matching (add source citation + update `last_updated`) or mint only if no match exists. Run summary tracks `claims minted` vs `claims merged` counts.

### 4.2 Source page always created — the safe floor ✓ implemented

Step 5 of `graph-ingestor.md` always writes a source page. Step 2's skip-if-exists check ensures idempotency.

### 4.3 Snapshot-not-Append (company page events) ✓ implemented

Step 6 of `graph-ingestor.md` enforces snapshot-not-append discipline:
- `## Financials` table — overwrite existing metric rows in place; only add new rows for new metrics.
- `## Events (last 30 days)` — append bullets; rename legacy `## Events` headers.
- `## Current snapshot` — overwrite if present; compactor creates it on first compaction run.
- `## History` — never touched by ingestor; compactor-managed.

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
1. ~~`fetch_prices.py`~~ ✓ done — `fetch_prices.py` + `ingest-prices` shipped. **Corrected 2026-05-01:** scope reduced to tracked tickers only (wiki/companies/*.md, ~44 vs the prior 774); raw files are now rolling per-ticker (`raw_sources/prices/<TICKER>.md`, no date prefix, overwritten each run) instead of one file per ticker per day; the graph-ingestor's market-data fast path no longer creates `wiki/sources/<...>-price.md` per ingest — all market-data citations point at the single canonical page `wiki/sources/tradingview-screener.md` (lazily created on first run). Fundamentals (P/E, P/B, EV/EBITDA, EPS TTM, dividend yield, debt/equity) overwrite-in-place into the company page's `## Financials` table. New convention rule documented at `docs/conventions.md` §8 ("Market-data placement").
2. `fetch_financials.py` — unblocks thesis writing.
3. ~~`fetch_kap.py`~~ ✓ done — `fetch_kap.py` + `ingest-kap` shipped; KAP filings are live.
4. `fetch_macro.py` — completes macro theme pages.

---

## 6. Target pipeline (after all changes)

```
CLI fetcher
    ↓ (all items pass through — nothing discarded here)
Graph-ingestor        ← merge-not-mint + snapshot-not-append already implemented ✓
    ↓                    every item gets a source page; claims are merged not minted
Compactor agent       ← built ✓; weekly cron; prunes old source pages, merges claims, compacts events
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
