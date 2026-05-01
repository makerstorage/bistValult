"""Manual single-file ingestion — handy for verifying the LLM loop without
running the full fetch pipeline.

Usage:
    python -m cli.orchestrators.dry_run path/to/raw_sources/news/<file>.md [...more]

Behaves like ingest_news/ingest_kap but takes the file list directly from
argv instead of subprocessing a fetcher. The graph-ingestor's idempotency
contract still applies — re-running on the same file is a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cli.agent import runner
from cli.orchestrators import _common


def main(argv: list[str] | None = None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    if not paths:
        print("usage: python -m cli.orchestrators.dry_run <raw_path> [<raw_path> ...]", file=sys.stderr)
        return 2

    abs_paths: list[str] = []
    for p in paths:
        ap = Path(p).resolve()
        if not ap.exists():
            print(f"error: {p} does not exist", file=sys.stderr)
            return 2
        abs_paths.append(str(ap))

    user_prompt = (
        "Ingest these new files. Process each in order, following your system prompt:\n\n"
        + "\n".join(abs_paths)
    )
    try:
        result = runner.run("graph-ingestor", user_prompt, verbose=True)
    except runner.AgentError as exc:
        print(f"agent failure: {exc}", file=sys.stderr)
        return 1

    print(f"\n[dry_run] iterations: {result.iterations}", file=sys.stderr)
    if result.summary_block:
        print(result.summary_block)
        return 0
    print("agent did not emit INGEST SUMMARY block; final text follows:", file=sys.stderr)
    print(result.final_text, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
