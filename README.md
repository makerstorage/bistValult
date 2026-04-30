# bistValult

LLM-maintained investment research wiki for Borsa Istanbul companies. Raw data flows in via CLI fetchers and cron; Claude maintains the wiki.

---

## How it works

```
raw_sources/   →   graph-ingestor agent   →   wiki/
(immutable)         (LLM-owned)               (markdown knowledge graph)
```

Three strict layers:

| Layer | Path | Owner | Rule |
|---|---|---|---|
| Raw inputs | `raw_sources/` | CLI / user | Immutable. Never edited after write. |
| Wiki | `wiki/` | LLM agents | Derived from raw inputs only. |
| Config | `docs/`, `templates/` | User + LLM | Co-evolved as conventions emerge. |

---

## Setup

**Requirements:** Python ≥ 3.11, [uv](https://github.com/astral-sh/uv), Claude Code CLI.

```bash
# Install Python dependencies
uv sync

# Verify CLI works
python -m cli.fetch_news --help
python -m cli.fetch_company_meta --help
```

---

## Pipeline commands

All pipeline commands run as Claude Code slash commands — either manually in a Claude session or unattended via cron.

### `/ingest-news`

Fetches the latest news articles for tracked BIST companies and ingests them into the wiki.

**What it does:**
1. Runs `python -m cli.fetch_news --since=last` — fetches new articles, deduplicates via `cli/state/news-seen.json`, writes raw files to `raw_sources/news/`.
2. Passes new file paths to the `graph-ingestor` subagent.
3. The ingestor creates source pages in `wiki/sources/`, updates company/sector/theme pages, and merges or mints claim pages.

**Run manually:**
```
/ingest-news
```

**Cron (every 6 hours):**
```cron
0 */6 * * * cd /path/to/bistValult && claude -p "/ingest-news" >> logs/ingest-news.log 2>&1
```

**Output:** Appends a structured entry to `wiki/log.md`. Prints an `INGEST SUMMARY` block to stdout (captured by cron log).

---

### `/ingest-companies`

Refreshes company metadata (name, sector, aliases, market cap) for tickers in the tracked universe. Used for entity matching during news ingestion.

**What it does:**
1. Runs `python -m cli.fetch_company_meta --ticker <TICKER>` (single ticker) or `--all --force` (full refresh).
2. Writes `raw_sources/company_meta/<TICKER>.json` files.
3. Does **not** update `wiki/companies/` pages — that happens during news ingestion when a source references the ticker.

**Run for one ticker:**
```
/ingest-companies --ticker GARAN
```

**Run for all tickers:**
```
/ingest-companies --all --force
```

**Cron (weekly, Sunday midnight):**
```cron
0 0 * * 0 cd /path/to/bistValult && claude -p "/ingest-companies" >> logs/ingest-companies.log 2>&1
```

---

### `/compact`

Weekly maintenance — keeps the wiki bounded and clean without losing information.

**What it does (three jobs in order):**

1. **Source pruning** — deletes `wiki/sources/` pages older than 30 days. Safety check: never deletes a source page that is the sole citation for any claim.
2. **Claim consolidation** — merges duplicate claim pages (same ticker, same topic) into a single canonical claim with all evidence combined. Rewires backlinks in company pages before deleting redundant files.
3. **Company page compaction** — moves events older than 30 days from `## Events (last 30 days)` into a summarised `## History` paragraph. Migrates old-format `## Events` sections to the new rolling-window format.

**Run manually:**
```
/compact
```

**Cron (weekly, Sunday 02:00 — after `/ingest-companies`):**
```cron
0 2 * * 0 cd /path/to/bistValult && claude -p "/compact" >> logs/compact.log 2>&1
```

**Output:** Appends a `compact` entry to `wiki/log.md`. Prints a `COMPACT SUMMARY` block to stdout.

---

## Manual workflows

### Ingest a file you dropped in

Drop a file into the appropriate `raw_sources/<kind>/` folder, then start a Claude session and describe what you dropped. Claude will:

1. Read the raw file.
2. Discuss the key takeaways with you.
3. Write a `wiki/sources/` page, update affected company/sector/theme/claim pages, detect contradictions, update `wiki/index.md`, and append to `wiki/log.md`.

### Query the wiki

Ask Claude a question in a session — e.g. _"Which BIST names benefit from rate cuts?"_ or _"What's the current picture on EREGL?"_

Claude reads `wiki/index.md` first, drills into relevant pages, and synthesises an answer with citations. If the answer is substantial (a comparison, thesis update, or investability assessment) it files it back as a `decisions/` or `claims/` page so the analysis is not lost.

### Lint (health check)

Ask Claude to run a lint pass:

```
Run a lint pass on the wiki.
```

Claude checks for: stale data past freshness thresholds, orphan pages, claims with no thesis, contradictions without resolution, decisions past `valid_until`, and concepts mentioned in multiple pages but lacking their own page. It reports findings and waits for your confirmation before fixing anything.

---

## Agent inventory

| Agent | File | Invoked by | Purpose |
|---|---|---|---|
| `graph-ingestor` | `.claude/agents/graph-ingestor.md` | `/ingest-news` (auto), manual ingest | Writes all wiki updates from raw sources |
| `compactor` | `.claude/agents/compactor.md` | `/compact` | Prunes, merges, and compacts the wiki weekly |

**Agents not yet built** (see `docs/gapanalises.md`):

| Agent | Purpose |
|---|---|
| `thesis-writer` | Synthesises accumulated claims into bull/bear thesis pages per company |
| `lint` | Automated health check; writes `wiki/dashboards/lint-report.md` |
| `decision-drafter` | Drafts A–E/U rated decision pages on user request |

---

## Recommended cron schedule

```cron
# bistValult — full pipeline
# News: every 6 hours
0 */6 * * *  cd /path/to/bistValult && claude -p "/ingest-news"       >> logs/ingest-news.log 2>&1

# Company metadata: weekly, Sunday midnight
0 0   * * 0  cd /path/to/bistValult && claude -p "/ingest-companies"  >> logs/ingest-companies.log 2>&1

# Compaction: weekly, Sunday 02:00
0 2   * * 0  cd /path/to/bistValult && claude -p "/compact"           >> logs/compact.log 2>&1
```

Create the log directory first:

```bash
mkdir -p logs
```

---

## Wiki structure

```
wiki/
  index.md          # navigational catalog — one line per page
  log.md            # chronological, append-only run history
  companies/        # TICKER.md — one page per tracked company
  sectors/          # banking.md, steel.md, energy.md, …
  themes/           # inflation.md, interest-rates.md, FX.md, …
  risks/            # named downside drivers
  catalysts/        # named upside drivers
  claims/           # discrete citable assertions — one per file
  theses/           # bull/bear narratives per company
  decisions/        # dated investment assessments (A–E/U rating scale)
  sources/          # one summary page per ingested raw source (pruned after 30 days)
  dashboards/       # bist30-overview, valuation-watchlist, risk-register
```

## Raw sources structure

```
raw_sources/
  news/             # fetched news articles (fetch_news.py)
  company_meta/     # TICKER.json registry (fetch_company_meta.py)
  prices/           # price snapshots (fetch_prices.py — not yet built)
  financials/       # structured financials (fetch_financials.py — not yet built)
  kap_filings/      # KAP primary disclosures (fetch_kap.py — not yet built)
  analyst_notes/    # broker research (fetch_analyst_notes.py — not yet built)
  macro/            # CBRT rates, CPI, FX (fetch_macro.py — not yet built)
  sector_reports/   # sector research (fetch_sector_reports.py — not yet built)
```

---

## Key rules (always apply)

1. **No hallucinated numbers.** Prices, ratios, financials must come from `raw_sources/` or the `tvscreener` MCP. If unavailable, say so.
2. **No binary buy/sell calls.** Use the A/B/C/D/E/U rating scale; final decisions belong to the user.
3. **Cite every claim** with `[[sources/...]]`. **Date every datum** (`YYYY-MM-DD`).
4. **Conservative language** — "appears", "suggests", "warrants research"; never "will" / "is a buy".
