---
description: Synthesise bull and bear thesis pages for a single BIST ticker. Pre-filters context via a deterministic graph walk; runs the thesis-writer agent twice (once per side). User-triggered, never on cron.
allowed-tools: Bash, Read
argument-hint: <TICKER> [--dry-run] [--side bull|bear|both]
---

You are running the **thesis-writer pipeline** for a single ticker. Pass through to the Python entry point — there is no extra reasoning to do here.

## Step 1 — invoke

Run, from the project root:

```bash
python3 -m cli.run thesis --ticker $ARGUMENTS
```

(Pass any extra flags through verbatim — e.g. `--dry-run`, `--side bull`.)

Capture stdout. The Python orchestrator handles:

- Building the curated subgraph context in pure Python (no LLM).
- Refusing if the ticker has < 2 claims (logs a `REFUSED` line and exits 0).
- If `--dry-run`: prints the rendered prompt(s) and exits 0 without calling any model.
- Otherwise: runs the `thesis-writer` agent once per side (bull then bear by default), parses each `THESIS SUMMARY` block, and appends a single combined entry to `wiki/log.md`.

## Step 2 — surface the result to the user

If the orchestrator exited 0 with summary blocks on stdout, paste those blocks into your response so the user sees what was written.

If it exited non-zero, paste the stderr output so the user can diagnose.

## Hard rules for this command

- **Do not edit `wiki/` yourself.** Only the `thesis-writer` subagent (invoked by the Python runner) writes inside `wiki/theses/`, `wiki/risks/`, `wiki/catalysts/`, and `wiki/index.md`.
- **Do not edit `raw_sources/`.**
- **Do not call AskUserQuestion.** Any clarifying question belongs in this command's preamble, not as a runtime prompt.
- This command is **idempotent**: re-running it on the same ticker with no new claims produces zero diffs.
