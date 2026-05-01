"""Company-meta refresh. Python port of .claude/commands/ingest-companies.md.

No LLM here — the original slash command was already pure deterministic logic.
"""

from __future__ import annotations

import argparse
import sys

from cli.orchestrators import _common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh company metadata from TradingView.")
    parser.add_argument("--ticker", help="Single ticker to refresh.")
    parser.add_argument("--all", action="store_true", help="Refresh every ticker in universe.txt.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing JSON files.")
    args = parser.parse_args(argv)

    fetcher_args: list[str] = []
    if args.ticker:
        fetcher_args += ["--ticker", args.ticker]
    if args.all:
        fetcher_args.append("--all")
    if args.force:
        fetcher_args.append("--force")

    rc, paths, stderr = _common.run_fetcher("cli.fetch_company_meta", fetcher_args)

    if rc != 0:
        reason = _common.first_stderr_line(stderr)
        _common.append_log(f"## [{_common.today()}] ingest | company-meta FAILED — {reason}")
        print(stderr, file=sys.stderr, end="")
        return rc

    if not paths:
        _common.append_log(f"## [{_common.today()}] ingest | company-meta (no new files)")
        return 0

    _common.append_log(
        f"## [{_common.today()}] ingest | company-meta ({len(paths)} tickers written)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
