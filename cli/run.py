"""Single entry point that replaces ``claude -p "/<command>"`` in cron.

Usage:
    python -m cli.run news
    python -m cli.run kap
    python -m cli.run prices
    python -m cli.run companies [--ticker TICKER] [--all] [--force]
    python -m cli.run compact
    python -m cli.run thesis --ticker TICKER [--side bull|bear|both] [--dry-run]

Each subcommand mirrors what the matching .claude/commands/<name>.md file
used to do under Claude Code, but runs against any OpenAI-compatible API
(default: OpenRouter — see .env.example).
"""

from __future__ import annotations

import sys

from cli.orchestrators import (
    compact,
    ingest_companies,
    ingest_kap,
    ingest_news,
    ingest_prices,
    write_thesis,
)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "news":
        return ingest_news.main()
    if cmd == "kap":
        return ingest_kap.main()
    if cmd == "prices":
        return ingest_prices.main()
    if cmd == "companies":
        return ingest_companies.main(rest)
    if cmd == "compact":
        return compact.main()
    if cmd == "thesis":
        return write_thesis.main(rest)

    print(f"Unknown subcommand: {cmd!r}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
