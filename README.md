# bistValult

LLM-maintained investment research wiki for Borsa Istanbul companies. Raw data flows in via CLI fetchers and cron; an LLM agent maintains the wiki.

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
| Config | `docs/`, `templates/`, `.claude/agents/` | User + LLM | Co-evolved as conventions emerge. |

The LLM-driven steps run through one of two parallel back-ends:

- **OpenRouter (or any OpenAI-compatible API)** — used by the cron / scripted path. No Claude Code required.
- **Claude Code** — still available for interactive use (slash commands, ad-hoc queries, lint passes, the `tvscreener` MCP).

---

## Setup

**Requirements:**

- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv) (project package manager)
- An OpenRouter account, **or** an OpenAI API key — only needed for the LLM-driven commands (`news`, `kap`, `compact`)
- Claude Code CLI (optional — only for interactive use)

**Install dependencies:**

```bash
uv sync --extra dev
```

**Configure the LLM provider:**

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY (or OPENAI_API_KEY)
```

`.env` keys (defaults shown):

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required unless `OPENAI_API_KEY` is set |
| `BISTVALULT_MODEL` | `anthropic/claude-sonnet-4.5` | Any OpenRouter / OpenAI model id |
| `BISTVALULT_BASE_URL` | `https://openrouter.ai/api/v1` | Use `https://api.openai.com/v1` for OpenAI direct |
| `BISTVALULT_MAX_ITERATIONS` | `60` | Hard cap on agent loop turns per run |
| `BISTVALULT_MAX_INPUT_TOKENS` | `180000` | Token budget for the message history |

**Verify the install:**

```bash
uv run pytest -q                     # 18 unit tests, no API key required
uv run python -m cli.fetch_news --help
```

---

## Pipeline commands (cron / scripted, no Claude Code)

All five pipeline commands run through `cli.run`. Each mirrors what the matching `.claude/commands/*.md` slash command did under Claude Code, but talks to OpenRouter (or any OpenAI-compatible endpoint) instead.

Every command is **idempotent** — re-running back-to-back produces zero new wiki diffs.

### `uv run python -m cli.run news`

Fetches the latest BIST news articles and ingests them into the wiki.

1. `cli.fetch_news --since=last` — fetches new articles, deduplicates via `cli/state/news-seen.json`, writes raw files to `raw_sources/news/`. **Deterministic, no LLM.**
2. If new files exist, calls the `graph-ingestor` agent (loaded from `.claude/agents/graph-ingestor.md`) over the OpenRouter API. The agent creates source pages in `wiki/sources/`, updates company / sector / theme pages, and merges or mints claim pages.
3. Appends an entry to `wiki/log.md` and prints an `INGEST SUMMARY` block to stdout.

**Cost:** ~$0.05–$0.15 per article on `anthropic/claude-sonnet-4.5`. Free when there are no new articles.

### `uv run python -m cli.run kap`

Same as `news` but for **KAP filings** (Turkish public-disclosure platform). KAP filings are primary-source disclosures and override news on contradictions.

1. `cli.fetch_kap --since=last` — fetches new disclosures, dedup via `cli/state/kap-seen.json`, writes to `raw_sources/kap_filings/`.
2. If new files exist, dispatches the `graph-ingestor` agent (same agent as `news`; classification differs by `source_kind`).
3. Logs and prints `INGEST SUMMARY`.

### `uv run python -m cli.run prices`

Fetches the latest market-data snapshot (price + valuation fundamentals) for every **tracked** BIST ticker — i.e. tickers that already have a `wiki/companies/<TICKER>.md` page — and refreshes the wiki in place. **Deterministic fetch, no cost when data is unchanged.**

1. `cli.fetch_prices` — single POST to the TradingView screener. For each tracked ticker writes a single rolling file at `raw_sources/prices/<TICKER>.md` (no date prefix), overwritten each run. The file holds two tables: a `## Snapshot` block (price, change, volume, market cap, 52W range, weekly/monthly perf) and a `## Fundamentals` block (P/E, P/B, EV/EBITDA, EPS TTM, dividend yield, debt/equity, sector, industry). Files with byte-identical content to the previous run are skipped — stdout is empty and the agent is not invoked.
2. If any file changed, dispatches the `graph-ingestor` agent using the **market-data fast path**: refreshes the company page's `## Current snapshot` lines and overwrites the price/ratio rows of `## Financials` in place. **No `wiki/sources/<...>-price.md` page is ever created** — all market-data citations point at the single canonical page `wiki/sources/tradingview-screener.md` (lazily created on first ingest). No claims are minted; market values are brute facts.
3. Logs an aggregate entry to `wiki/log.md`.

**Cost:** Only incurred when data has actually changed. LLM cost is per-ticker batch, not per-file.

---

### `uv run python -m cli.run companies [--ticker TICKER] [--all] [--force]`

Refreshes company metadata (name, sector, aliases) used for entity matching during news ingestion. **Deterministic, no LLM, no cost.**

```bash
uv run python -m cli.run companies --ticker GARAN     # one ticker
uv run python -m cli.run companies --all --force      # full refresh of universe.txt
```

Writes `raw_sources/company_meta/<TICKER>.json`. Does **not** create wiki pages — those are minted by the `graph-ingestor` when news references the ticker.

### `uv run python -m cli.run thesis --ticker TICKER [--side bull|bear|both] [--dry-run]`

Synthesises **bull and bear thesis pages** for a single ticker. User-triggered (not cron). The orchestrator first builds a curated subgraph in pure Python — `cli.lib.thesis_context` walks `company → claims → sources → sectors → themes → risks → catalysts` with hard caps (12 claims, 8 sources, 4 themes, 5 risks, 5 catalysts), so the agent only ever sees the most relevant ~25k input tokens for the ticker. Then it dispatches the `thesis-writer` agent **twice** (once per side, sharper than asking for both at once) and writes a single combined entry to `wiki/log.md`.

Mechanical confidence (Low / Medium / High) is computed deterministically from claim count, KAP-cited evidence, contradictions, and staleness — see `cli/lib/thesis_context.py:compute_confidence`. The agent uses it verbatim.

Behaviour:

- `<2` claims → refuses with a `REFUSED` log line and exits 0. Better no thesis than a thesis on thin evidence.
- `--dry-run` → prints the rendered prompt(s) and exits without an LLM call. Use this to inspect what the agent will see.
- Existing thesis pages are passed in as `## Existing thesis pages` and full-rewritten; git is the archive.
- The agent may mint stub `wiki/risks/<slug>.md` and `wiki/catalysts/<slug>.md` pages when surfacing a named risk/catalyst that does not yet have a dedicated page.

```bash
uv run python -m cli.run thesis --ticker EREGL --dry-run    # inspect prompt
uv run python -m cli.run thesis --ticker EREGL              # write both sides
uv run python -m cli.run thesis --ticker EREGL --side bull  # one side only
```

**Cost:** typically ~$0.05–$0.20 per ticker per side on `anthropic/claude-sonnet-4.5`.

### `uv run python -m cli.run compact`

Weekly maintenance — keeps the wiki bounded without losing information. Calls the `compactor` agent (`.claude/agents/compactor.md`).

Three jobs in order:

1. **Source pruning** — deletes `wiki/sources/*.md` older than 30 days. Skips any source page that is the sole citation for a claim.
2. **Claim consolidation** — merges duplicate claims (same ticker, same topic, same direction) into one canonical file with merged evidence.
3. **Company page compaction** — moves events older than 30 days from `## Events (last 30 days)` into a summarised `## History` paragraph.

Logs and prints `COMPACT SUMMARY`. Heavier than a single ingest — typically $0.30–$1 per weekly run.

---

## Manual / debugging commands

### `uv run python -m cli.orchestrators.dry_run <raw_path> [<raw_path> ...]`

Run the `graph-ingestor` agent against one or more hand-picked raw files, bypassing the fetcher. Useful for testing changes to the agent prompt, verifying a single article ingests correctly, or capping cost during the first end-to-end run.

```bash
uv run python -m cli.orchestrators.dry_run \
  raw_sources/news/2026-04-17-reuters-ulusoy-elektrik-says-it-is-to-pay-competition-board-fine-of-f47ec4b7.md
```

Prints `[runner] iter N — calling model …` lines on stderr so you can see how many turns it took.

### `uv run pytest`

Runs the unit-test suite. No API key required — tests cover tool-surface security (path allowlist, edit semantics, delete whitelist), prompt loading, and summary-block parsing.

### `uv run python -m cli.fetch_news --since=last`

Run any fetcher directly. Prints absolute paths of newly-written files to stdout. Same exit-code contract as the orchestrators (0 on success, 0 on no-new-data, non-zero on hard failure).

---

## Interactive commands (Claude Code, optional)

Slash commands continue to work inside an interactive `claude` session. They use Claude Code's own model and tools (Anthropic API), independent of the OpenRouter setup above.

| Slash command | Equivalent Python invocation |
|---|---|
| `/ingest-news` | `uv run python -m cli.run news` |
| `/ingest-kap` | `uv run python -m cli.run kap` |
| `/ingest-prices` | `uv run python -m cli.run prices` |
| `/ingest-companies` | `uv run python -m cli.run companies` |
| `/thesis EREGL` | `uv run python -m cli.run thesis --ticker EREGL` |
| `/compact` | `uv run python -m cli.run compact` |

Use slash commands for ad-hoc work, the `tvscreener` MCP, manual file ingestion, queries, and lint passes. Use the Python entry points for cron and CI.

### Manual file ingestion

Drop a file into the matching `raw_sources/<kind>/` folder, then describe it in a Claude session. The agent reads the file, discusses takeaways with you, then updates `wiki/`.

### Query the wiki

Ask a question in a Claude session — e.g. _"Which BIST names benefit from rate cuts?"_ or _"What's the current picture on EREGL?"_ The agent reads `wiki/index.md` first, drills in, and synthesises an answer with citations. Substantial answers are filed back as `decisions/` or `claims/` pages.

### Lint (health check)

Ask Claude to run a lint pass. It checks for stale data, orphan pages, contradictions, expired decisions, and concepts mentioned but lacking pages. Reports findings; never fixes without your confirmation.

---

## Agent inventory

| Agent | Prompt file | Invoked by | Purpose |
|---|---|---|---|
| `graph-ingestor` | `.claude/agents/graph-ingestor.md` | `cli.run news`, `cli.run kap`, manual ingest | Writes all wiki updates from raw sources |
| `compactor` | `.claude/agents/compactor.md` | `cli.run compact` | Prunes, merges, and compacts the wiki weekly |
| `thesis-writer` | `.claude/agents/thesis-writer.md` | `cli.run thesis --ticker T` | Writes one side of a company's thesis (bull or bear) given a curated subgraph |

The Python runner loads each agent's `.md` body verbatim as the LLM system prompt, so the same prompt source is authoritative for both back-ends.

**Agents not yet built** (see `docs/gapanalises.md`):

| Agent | Purpose |
|---|---|
| `lint` | Automated health check; writes `wiki/dashboards/lint-report.md` |
| `decision-drafter` | Drafts A–E/U rated decision pages on user request |

---

## Recommended cron schedule (macOS launchd)

Each plist points at the absolute `uv` binary and the project root. Replace the paths with your own.

**News — every 6 hours:**

```xml
<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/uv</string>
  <string>run</string>
  <string>--project</string><string>/Users/nuri/Code/bistValult</string>
  <string>python</string><string>-m</string><string>cli.run</string><string>news</string>
</array>
<key>StartCalendarInterval</key>
<array>
  <dict><key>Hour</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>6</integer></dict>
  <dict><key>Hour</key><integer>12</integer></dict>
  <dict><key>Hour</key><integer>18</integer></dict>
</array>
<key>StandardOutPath</key><string>/Users/nuri/Code/bistValult/logs/ingest-news.log</string>
<key>StandardErrorPath</key><string>/Users/nuri/Code/bistValult/logs/ingest-news.log</string>
```

**KAP — every 30 minutes during trading hours:** same shape, swap `news` → `kap`.

**Companies — Sunday midnight:** swap to `companies` with optional `--all --force`.

**Compact — Sunday 02:00:** swap to `compact`.

If you prefer plain cron over launchd:

```cron
# bistValult — full pipeline
0 */6 * * *        cd /Users/nuri/Code/bistValult && /opt/homebrew/bin/uv run python -m cli.run news      >> logs/ingest-news.log 2>&1
*/30 9-18 * * 1-5  cd /Users/nuri/Code/bistValult && /opt/homebrew/bin/uv run python -m cli.run kap       >> logs/ingest-kap.log  2>&1
30 18 * * 1-5      cd /Users/nuri/Code/bistValult && /opt/homebrew/bin/uv run python -m cli.run prices    >> logs/ingest-prices.log 2>&1
0    0 * * 0       cd /Users/nuri/Code/bistValult && /opt/homebrew/bin/uv run python -m cli.run companies >> logs/ingest-companies.log 2>&1
0    2 * * 0       cd /Users/nuri/Code/bistValult && /opt/homebrew/bin/uv run python -m cli.run compact   >> logs/compact.log 2>&1
```

Create the log directory once:

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
  kap_filings/      # KAP primary disclosures (fetch_kap.py)
  company_meta/     # TICKER.json registry (fetch_company_meta.py)
  universe.txt      # tracked tickers, one per line
  prices/           # rolling per-ticker market-data files (fetch_prices.py — daily cron; tracked tickers only)
  financials/       # structured financials (fetcher not yet built)
  analyst_notes/    # broker research (fetcher not yet built)
  macro/            # CBRT rates, CPI, FX (fetcher not yet built)
  sector_reports/   # sector research (fetcher not yet built)
```

---

## Key rules (always apply)

1. **No hallucinated numbers.** Prices, ratios, financials must come from `raw_sources/` or the `tvscreener` MCP. If unavailable, say so.
2. **No binary buy/sell calls.** Use the A/B/C/D/E/U rating scale; final decisions belong to the user.
3. **Cite every claim** with `[[sources/...]]`. **Date every datum** (`YYYY-MM-DD`).
4. **Conservative language** — "appears", "suggests", "warrants research"; never "will" / "is a buy".
