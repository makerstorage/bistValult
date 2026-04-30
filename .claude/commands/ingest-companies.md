---
description: Enrich a company's metadata from TradingView. Pass --ticker TICKER to update one entry in company_meta/.
allowed-tools: Bash, Read, Edit, Write
argument-hint: (no arguments — runs unattended)
---

You are running the automated **company metadata fetch**. There is no user attached. Run to completion and exit. **Do not call AskUserQuestion under any circumstances.**

## Step 1 — fetch

Run the metadata fetcher via Bash, from the project root.
Pass `--ticker <TICKER>` for a specific company, or `--all --force` to refresh all 774 entries:

```
python3 -m cli.fetch_company_meta --ticker <TICKER>
```

Capture stdout (absolute paths of written JSON files) and stderr (errors).

## Step 2 — empty result

If stdout is empty **and** the CLI exited 0:

1. Append a single line to `wiki/log.md`:
   ```
   ## [<today's date in YYYY-MM-DD>] ingest | company-meta (no new files)
   ```
2. Stop.

## Step 3 — CLI failure

If the CLI exited non-zero:

1. Append to `wiki/log.md`:
   ```
   ## [<today's date>] ingest | company-meta FAILED — <one-line reason from stderr>
   ```
2. Exit non-zero so the cron log surfaces the failure.

## Step 4 — log success

If stdout has one or more paths:

1. Count the written files (N).
2. Append to `wiki/log.md`:
   ```
   ## [<today's date>] ingest | company-meta (N tickers written)
   ```
3. Stop.

Company wiki pages are **not** created here — they are created by the graph-ingestor during news ingestion when a source's `related_tickers` references a ticker. This command only refreshes the metadata registry used for entity matching.

## Hard rules

- Do not edit `raw_sources/` yourself. Only the CLI writes there.
- Do not edit `wiki/` beyond appending to `wiki/log.md`.
- Do not call AskUserQuestion. Cron is unattended.
- Idempotent: re-running the same ticker without `--force` writes nothing if the JSON already exists.
