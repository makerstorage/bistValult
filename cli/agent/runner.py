"""Subagent runner — chat-completions loop with tool calling.

Provider-agnostic; talks to any OpenAI-compatible endpoint. Default config
points at OpenRouter, but the same code works against api.openai.com/v1 by
swapping ``BISTVALULT_BASE_URL`` and the API key.

The flow mirrors what Claude Code's Task tool used to do for us:
  1. Strip frontmatter from ``.claude/agents/<name>.md``; that body is the
     subagent's system prompt.
  2. Append a small ``boot_context()`` block (today's date + ticker registry
     summary) so the model doesn't waste turns rediscovering the obvious.
  3. Loop: ask the model, run any requested tool calls, feed results back,
     repeat until the model returns a final assistant message — which must
     contain the ``INGEST SUMMARY`` or ``COMPACT SUMMARY`` block.
  4. Extract that block; the orchestrator prints it to stdout for the cron log.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import date

from openai import OpenAI

from cli.agent import config as agent_config
from cli.agent import prompts, tools
from cli.lib import registry

# A summary block runs from the literal header line to the end of the message.
SUMMARY_RE = re.compile(
    r"^(INGEST SUMMARY|COMPACT SUMMARY|THESIS SUMMARY)\b.*?(?=\Z)",
    re.MULTILINE | re.DOTALL,
)


class AgentError(RuntimeError):
    pass


@dataclass
class RunResult:
    final_text: str
    summary_block: str | None
    iterations: int


def _boot_context() -> str:
    """Information cheap to compute deterministically and expensive to discover via tool calls."""
    today = date.today().isoformat()
    tickers = registry.all_tickers()
    return (
        "\n\n---\n"
        f"Today's date: {today}\n"
        f"Known tickers in raw_sources/company_meta/: {len(tickers)} "
        f"({', '.join(tickers[:10])}{'…' if len(tickers) > 10 else ''})\n"
        "---\n"
    )


def _extract_summary(text: str) -> str | None:
    m = SUMMARY_RE.search(text)
    return m.group(0).strip() if m else None


def run(subagent_name: str, user_prompt: str, *, verbose: bool = False) -> RunResult:
    """Run one subagent turn end-to-end.

    Raises AgentError on iteration cap, missing summary, or auth/transport
    failures from the OpenAI client.
    """
    cfg = agent_config.load()
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)

    system_prompt = prompts.load_subagent_prompt(subagent_name) + _boot_context()
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tool_schemas = tools.schemas()

    for iteration in range(1, cfg.max_iterations + 1):
        if verbose:
            print(f"[runner] iter {iteration} — calling model {cfg.model}", file=sys.stderr)
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto",
            temperature=0.0,
        )
        choice = resp.choices[0]
        msg = choice.message

        # Persist the assistant turn verbatim.
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            final_text = msg.content or ""
            return RunResult(
                final_text=final_text,
                summary_block=_extract_summary(final_text),
                iterations=iteration,
            )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                tool_result = json.dumps(
                    {"ok": False, "error": f"Invalid JSON arguments: {exc}"}
                )
            else:
                tool_result = tools.dispatch(tc.function.name, args)
            if verbose:
                preview = tool_result[:120].replace("\n", " ")
                print(f"[runner]   tool {tc.function.name} → {preview}", file=sys.stderr)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                }
            )

    raise AgentError(
        f"Iteration cap ({cfg.max_iterations}) hit for subagent {subagent_name!r} "
        "before final response. Increase BISTVALULT_MAX_ITERATIONS or chunk the input."
    )
