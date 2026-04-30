---
description: Weekly wiki compaction — prune stale source pages, consolidate duplicate claims, compact company event histories. Cron-safe (idempotent).
allowed-tools: Bash, Read, Edit, Write, Task
argument-hint: (no arguments — runs unattended)
---

You are running the automated **wiki compaction pipeline**. There is no user attached. Run to completion and exit. **Do not call AskUserQuestion under any circumstances.**

## Step 1 — pre-flight check

Verify the wiki is in a consistent state before compacting:

```bash
# Confirm wiki/ and its key subdirectories exist
ls wiki/sources wiki/claims wiki/companies wiki/index.md wiki/log.md
```

If any path is missing, append to `wiki/log.md`:

```
## [<today's date>] compact FAILED — wiki structure incomplete, aborting
```

Then exit non-zero.

## Step 2 — delegate to compactor agent

Spawn the `compactor` subagent via the Task tool. Pass it exactly:

```
Run all three compaction jobs in order:
  Job 1 — source page pruning (delete source pages older than 30 days that are not sole citations)
  Job 2 — claim consolidation (merge duplicate claim pages per ticker)
  Job 3 — company page compaction (migrate old Events format, move events > 30 days to History)

Today's date: <insert today's date as YYYY-MM-DD>
```

Wait for the subagent to finish. Capture its `COMPACT SUMMARY` block.

## Step 3 — handle failure

If the subagent exits with an error or does not emit a `COMPACT SUMMARY` block:

1. Append to `wiki/log.md`:
   ```
   ## [<today's date>] compact FAILED — subagent did not complete normally
   ```
2. Exit non-zero so the cron log surfaces the failure.

## Step 4 — log and finish

Print the captured `COMPACT SUMMARY` to stdout so the cron log captures it.

## Hard rules for this command

- **Do not edit `wiki/` yourself.** Only the `compactor` subagent writes to `wiki/`.
- **Do not touch `raw_sources/`.** Compaction never touches raw inputs.
- **Do not call AskUserQuestion.** Cron is unattended.
- This command is fully idempotent — re-running it back-to-back must be a no-op.
