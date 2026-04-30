# Workflows

Four operations: **ingest** (manual, new raw source), **automated ingest** (cron-driven), **query** (user question), **lint** (health check).

---

## Ingest

User drops a file into `raw_sources/`. Steps:

1. Read the raw file.
2. Classify: news / financial statement / price-volume / KAP filing / analyst note / macro / sector report.
3. **Discuss key takeaways with the user before writing.** Don't ingest silently.
4. Write `wiki/sources/<YYYY-MM-DD>-<slug>.md` — a structured summary (key facts, dates, entities mentioned, link to raw file).
5. Update affected pages — typically one company page plus relevant sectors, themes, risks, catalysts, claims, and possibly the company's thesis/decision pages. A single source can touch 5–15 wiki pages.
6. Flag contradictions with existing claims (see `conventions.md` §"Track contradictions").
7. Update `wiki/index.md` if new pages were created.
8. Append to `wiki/log.md` (see `conventions.md` §"Log format").

---

## Automated ingest (cron-driven)

Separate path from the manual `ingest` above. Cron fires repeatedly throughout the day; there is no user in the loop.

1. macOS cron / launchd invokes `claude -p "/ingest-<kind>"` headlessly. (One command per kind: `ingest-news`, `ingest-prices`, `ingest-financials`, `ingest-kap`, `ingest-analyst-notes`, `ingest-macro`, `ingest-sector-reports`.)
2. The slash command (`.claude/commands/ingest-<kind>.md`) runs the matching fetcher: `python -m cli.fetch_<kind> --since=last`.
3. The CLI:
   - Reads `cli/state/<kind>-seen.json` for dedup.
   - Fetches new items from configured sources.
   - Writes new raw files to `raw_sources/<kind>/`.
   - Updates the seen-state file.
   - Prints absolute paths of newly-written files to stdout, one per line. Exits 0 even with zero new items.
4. If stdout is empty, the slash command appends `## [<date>] ingest | <kind> (no new sources)` to `wiki/log.md` and stops.
5. Otherwise, the slash command spawns the `graph-ingestor` subagent (`.claude/agents/graph-ingestor.md`) and passes it the list of new file paths.
6. The subagent ingests each file per its system prompt — classify, create source page, touch entity pages, mint claims, detect contradictions, update `wiki/index.md`, append a single combined entry to `wiki/log.md`.

**Boundaries.**
- Only the CLI writes to `raw_sources/`.
- Only the `graph-ingestor` subagent writes to `wiki/` during this path.
- The subagent has no internet access, no MCP, no `Task`, no `AskUserQuestion`.

**Failure modes.**
- CLI fails → slash command writes a `FAILED` line to `wiki/log.md` and exits non-zero (cron log surfaces it).
- Subagent hits material uncertainty on a file → sets `needs_review: true` in that source page's frontmatter and continues. The user picks these up later via `lint`.

---

## Query

User asks a question (e.g., "Should I look at ASELS?", "Which BIST 30 names benefit from rate cuts?"):

1. Read `wiki/index.md` first to find relevant pages.
2. Drill into the company page, sector, themes, risks, catalysts, recent sources.
3. Synthesize an answer with citations to `[[wiki pages]]`.
4. **If the answer is substantial** (a comparison, an analysis, a thesis update, an investability assessment), file it back as a new `decisions/` page or new `claims/` page. Don't let analysis disappear into chat.
5. Append a `query` entry to `wiki/log.md`.

---

## Lint

User asks for a health check. Scan and report:

- **Contradictions** between pages
- **Stale data** past freshness thresholds (30d for prices/ratios, 90d for financials)
- **Orphan pages** with no inbound links
- **Concepts mentioned but lacking their own page** (e.g., a risk named in three companies but no `risks/<name>.md` exists)
- **Missing cross-references** (claim cites no thesis; thesis lists no risks)
- **Data gaps** that suggest a useful next source to request from the user
- **Expired decisions** (past `valid_until`)

**Report findings; do not fix without confirming** with the user.
