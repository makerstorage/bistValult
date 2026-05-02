"""Per-ticker thesis writer. Python entry point invoked as ``cli.run thesis``.

Usage:
    python -m cli.run thesis --ticker EREGL                  # write bull + bear
    python -m cli.run thesis --ticker EREGL --dry-run        # render prompts only
    python -m cli.run thesis --ticker EREGL --side bull      # one side only
    python -m cli.run thesis --ticker EREGL --side bear

Pipeline (per design lock-in):
    1. Build a curated subgraph context via cli.lib.thesis_context.build().
    2. If <2 claims, refuse with a log line and exit 0.
    3. If --dry-run, print the rendered user prompt(s) to stdout and exit.
    4. Otherwise run the thesis-writer agent once per side, sequentially.
       Each call emits a THESIS SUMMARY block; both are echoed to stdout
       and combined into a single wiki/log.md entry.

The agent is the same prompt source as the file at .claude/agents/thesis-writer.md
(loaded by cli.agent.runner via cli.agent.prompts).
"""

from __future__ import annotations

import argparse
import re
import sys

from cli.agent import runner
from cli.lib import thesis_context
from cli.orchestrators import _common

SIDES = ("bull", "bear")


def _parse_summary_field(block: str, field: str) -> str:
    """Pull a single line out of a THESIS SUMMARY block.

    The block is fixed-format (see thesis-writer.md §Termination), so a
    line-based regex is enough. Returns the empty string on miss.
    """
    pattern = re.compile(rf"^\s*{re.escape(field)}:\s*(.+?)\s*$", re.MULTILINE)
    m = pattern.search(block)
    return m.group(1).strip() if m else ""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cli.run thesis",
        description="Synthesise bull/bear thesis pages for a single BIST ticker.",
    )
    p.add_argument("--ticker", required=True, help="Ticker symbol (e.g. EREGL).")
    p.add_argument(
        "--side",
        choices=("bull", "bear", "both"),
        default="both",
        help="Which thesis to write. Default: both (two LLM calls).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the curated context block(s) to stdout and exit; no LLM call.",
    )
    return p.parse_args(argv)


def _refuse(ctx: thesis_context.ThesisContext) -> int:
    line = (
        f"## [{_common.today()}] thesis | {ctx.ticker} REFUSED — {ctx.refusal_reason}"
    )
    _common.append_log(line)
    print(f"refused: {ctx.refusal_reason}", file=sys.stderr)
    # Refusal is not a hard failure — exit 0 so cron / batch callers don't alarm.
    return 0


def _dry_run(ctx: thesis_context.ThesisContext, sides: list[str]) -> int:
    for side in sides:
        prompt = thesis_context.render_user_prompt(ctx, side)
        print(f"\n========== USER PROMPT ({ctx.ticker} {side}) ==========\n")
        print(prompt)
        # Cheap size signal — character count is a usable proxy for tokens
        # (~4 chars/token average for English+code).
        print(
            f"\n[dry-run] {side} prompt: {len(prompt)} chars "
            f"(~{len(prompt) // 4} tokens estimated)\n",
            file=sys.stderr,
        )
    return 0


def _run_one_side(ctx: thesis_context.ThesisContext, side: str) -> tuple[bool, str]:
    """Run the thesis-writer agent once. Returns (ok, summary_block_or_error)."""
    user_prompt = thesis_context.render_user_prompt(ctx, side)
    try:
        result = runner.run("thesis-writer", user_prompt)
    except runner.AgentError as exc:
        return False, f"agent error: {exc}"
    if not result.summary_block:
        return False, "agent did not emit THESIS SUMMARY block:\n" + result.final_text
    return True, result.summary_block


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else [])
    ticker = args.ticker.strip().upper()

    ctx = thesis_context.build(ticker)

    if ctx.refused and "below minimum" in ctx.refusal_reason:
        return _refuse(ctx)
    if ctx.refused:
        # No company page — surface to stderr and exit non-zero so cron sees it.
        _common.append_log(
            f"## [{_common.today()}] thesis | {ticker} FAILED — {ctx.refusal_reason}"
        )
        print(ctx.refusal_reason, file=sys.stderr)
        return 1

    sides: list[str] = list(SIDES) if args.side == "both" else [args.side]

    if args.dry_run:
        return _dry_run(ctx, sides)

    summaries: dict[str, str] = {}
    for side in sides:
        ok, payload = _run_one_side(ctx, side)
        if not ok:
            _common.append_log(
                f"## [{_common.today()}] thesis | {ticker} {side} FAILED — {payload.splitlines()[0]}"
            )
            print(payload, file=sys.stderr)
            return 1
        summaries[side] = payload
        # Echo each summary to stdout so the cron log captures both.
        print(payload)

    log_lines = [f"## [{_common.today()}] thesis | {ticker} ({', '.join(sides)})"]
    for side in sides:
        block = summaries[side]
        status = _parse_summary_field(block, "thesis status") or "unknown"
        path = _parse_summary_field(block, "thesis path") or f"wiki/theses/{ticker}-{side}.md"
        claims_cited = _parse_summary_field(block, "claims cited")
        risks_minted = _parse_summary_field(block, "risks minted")
        catalysts_minted = _parse_summary_field(block, "catalysts minted")
        log_lines.append(
            f"- {side}: [[{path.replace('wiki/', '').removesuffix('.md')}]] "
            f"({status}; {claims_cited} claims, "
            f"+{risks_minted} risks, +{catalysts_minted} catalysts)"
        )
    log_lines.append(f"- mechanical confidence: {ctx.confidence.render()}")
    _common.append_log("\n".join(log_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
