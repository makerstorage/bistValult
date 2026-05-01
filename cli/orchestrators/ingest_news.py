"""Automated news ingestion pipeline. Python port of .claude/commands/ingest-news.md.

Run: ``python -m cli.orchestrators.ingest_news`` (or via ``cli.run news``).

Cron-safe — exits 0 on success even when no new articles, non-zero on hard
failure so launchd surfaces it. Idempotent: re-running back-to-back is a no-op.
"""

from __future__ import annotations

import sys

from cli.agent import runner
from cli.orchestrators import _common


def main() -> int:
    rc, paths, stderr = _common.run_fetcher("cli.fetch_news", ["--since=last"])

    if rc != 0:
        reason = _common.first_stderr_line(stderr)
        _common.append_log(f"## [{_common.today()}] ingest | news FAILED — {reason}")
        print(stderr, file=sys.stderr, end="")
        return rc

    if not paths:
        _common.append_log(f"## [{_common.today()}] ingest | news (no new sources)")
        return 0

    user_prompt = (
        "Ingest these new news files. Process each in order, following your system prompt:\n\n"
        + "\n".join(paths)
    )
    try:
        result = runner.run("graph-ingestor", user_prompt)
    except runner.AgentError as exc:
        _common.append_log(f"## [{_common.today()}] ingest | news FAILED — {exc}")
        print(f"agent failure: {exc}", file=sys.stderr)
        return 1

    if result.summary_block:
        print(result.summary_block)
    else:
        _common.append_log(
            f"## [{_common.today()}] ingest | news FAILED — subagent did not emit INGEST SUMMARY"
        )
        print(
            "agent did not emit INGEST SUMMARY block; final text follows on stderr",
            file=sys.stderr,
        )
        print(result.final_text, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
