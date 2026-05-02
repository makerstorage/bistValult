---
description: Fetch latest price snapshots for all tracked BIST tickers and ingest into the wiki graph. Cron-safe (idempotent).
allowed-tools: Bash, Read, Edit, Write, Task
argument-hint: (no arguments — runs unattended)
---

You are running the automated **price snapshot ingestion pipeline**. There is no user attached. Run to completion and exit. **Do not call AskUserQuestion under any circumstances.**

## Step 1 — fetch

Run the price fetcher via Bash, from the project root:

```
python3 -m cli.fetch_prices
```

Capture stdout. Each non-empty line is the absolute path of a newly-written raw price snapshot file.

## Step 2 — empty result

If stdout is empty (no new snapshots) **and** the CLI exited 0:

1. Append a single line to `wiki/log.md`:
   ```
   ## [<today's date in YYYY-MM-DD>] ingest | prices (no new snapshots — already up to date)
   ```
2. Stop. Do not invoke the subagent.

## Step 3 — CLI failure

If the CLI exited non-zero:

1. Append to `wiki/log.md`:
   ```
   ## [<today's date>] ingest | prices FAILED — <one-line reason from stderr>
   ```
2. Exit non-zero so the cron log surfaces the failure.

## Step 4 — delegate to graph-ingestor

If stdout has one or more paths, spawn the `graph-ingestor` subagent via the Task tool. Pass it exactly:

```
Ingest these new price snapshot files. Process each in order, following your system prompt:

<paste the captured paths here, one per line>
```

Wait for the subagent to finish. Print its `INGEST SUMMARY` block to stdout so the cron log captures it.

## Hard rules for this command

- **Do not edit `wiki/` yourself.** Only the `graph-ingestor` subagent writes to `wiki/`.
- **Do not edit `raw_sources/`.** Only the CLI writes there.
- **Do not call AskUserQuestion.** Cron is unattended.
- This command is fully idempotent — re-running it back-to-back on the same day must be a no-op.
