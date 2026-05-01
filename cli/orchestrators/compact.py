"""Weekly wiki compaction. Python port of .claude/commands/compact.md."""

from __future__ import annotations

import sys
from pathlib import Path

from cli.agent import runner
from cli.orchestrators import _common

_REQUIRED = (
    "wiki/sources",
    "wiki/claims",
    "wiki/companies",
    "wiki/index.md",
    "wiki/log.md",
)


def _preflight_ok() -> bool:
    return all((_common.REPO_ROOT / Path(p)).exists() for p in _REQUIRED)


def main() -> int:
    if not _preflight_ok():
        _common.append_log(
            f"## [{_common.today()}] compact FAILED — wiki structure incomplete, aborting"
        )
        return 1

    user_prompt = (
        "Run all three compaction jobs in order:\n"
        "  Job 1 — source page pruning (delete source pages older than 30 days "
        "that are not sole citations)\n"
        "  Job 2 — claim consolidation (merge duplicate claim pages per ticker)\n"
        "  Job 3 — company page compaction (migrate old Events format, move events "
        "> 30 days to History)\n\n"
        f"Today's date: {_common.today()}"
    )
    try:
        result = runner.run("compactor", user_prompt)
    except runner.AgentError as exc:
        _common.append_log(f"## [{_common.today()}] compact FAILED — {exc}")
        print(f"agent failure: {exc}", file=sys.stderr)
        return 1

    if result.summary_block:
        print(result.summary_block)
    else:
        _common.append_log(
            f"## [{_common.today()}] compact FAILED — subagent did not complete normally"
        )
        print(result.final_text, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
