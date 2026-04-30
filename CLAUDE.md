# bistValult

LLM-maintained investment research wiki for Borsa Istanbul companies, built on the llm-wiki pattern. The user curates raw inputs; you maintain the wiki.

## Repo layout

- `raw_sources/` — immutable inputs (manual or CLI-written). Read-only.
- `wiki/` — your output. Markdown pages with `[[wikilinks]]`, organized by entity type.
- `cli/` — Python data fetchers. Cron-driven; write to `raw_sources/<kind>/`.
- `.claude/commands/` — orchestrator slash commands invoked by cron (`ingest-news`, …).
- `.claude/agents/graph-ingestor.md` — specialist subagent that owns all `wiki/` writes during automated ingestion.
- `docs/` — your operating manual. Load on demand per the table below.
- `templates/` — page skeletons; copy when creating a new page.

## Operating manual — read on demand

| File | When to read |
|------|--------------|
| `docs/architecture.md` | First time, or when creating new directories |
| `docs/conventions.md` | Before writing or editing any wiki page |
| `docs/graph-model.md` | When deciding which pages a fact touches, or planning cross-links |
| `docs/rating-scale.md` | Before producing or updating a `decisions/` page |
| `docs/workflows.md` | When ingesting a source, answering a query, or doing a lint pass |

## Two ingestion paths

- **Manual** — user drops a file into `raw_sources/`, you discuss takeaways, then update the wiki. See `docs/workflows.md` §"Ingest".
- **Automated (cron-driven)** — macOS cron fires `claude -p "/ingest-<kind>"`. The slash command runs the matching `cli/fetch_<kind>.py`, then delegates to the `graph-ingestor` subagent which writes the wiki updates. See `docs/workflows.md` §"Automated ingest". You (the main agent) never run the automated path interactively — it is invoked by external schedulers.

## Hard rules — always apply

1. **No hallucinated numbers.** Prices, ratios, financials must come from `raw_sources/` or the `tvscreener` MCP. If unavailable, say so.
2. **No binary buy/sell calls.** Use the A/B/C/D/E/U rating scale; final investment decisions belong to the user.
3. **Cite every claim** with `[[sources/...]]`. **Date every datum** (`YYYY-MM-DD`).
4. **Conservative language** — "appears", "suggests", "warrants research"; never "will" / "is a buy".
