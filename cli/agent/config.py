"""Runtime configuration for the LLM-driven subagent runner.

Loads from .env (via python-dotenv) and process environment.
Supports any OpenAI-compatible chat-completions endpoint — defaults
to OpenRouter, but the same code paths work against api.openai.com/v1
or a self-hosted gateway by swapping ``BISTVALULT_BASE_URL`` and the key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env once at import time. ``override=False`` means real env vars win
# over the file — handy for cron, where launchd may inject the key directly.
load_dotenv(REPO_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    max_iterations: int
    max_input_tokens: int


def _require_key() -> str:
    """Prefer OPENROUTER_API_KEY; fall back to OPENAI_API_KEY for direct OpenAI use."""
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        val = os.environ.get(name)
        if val:
            return val
    raise RuntimeError(
        "No API key found. Set OPENROUTER_API_KEY (or OPENAI_API_KEY) "
        "in .env or the environment."
    )


def load() -> Config:
    return Config(
        api_key=_require_key(),
        base_url=os.environ.get(
            "BISTVALULT_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        model=os.environ.get("BISTVALULT_MODEL", "anthropic/claude-sonnet-4.5"),
        max_iterations=int(os.environ.get("BISTVALULT_MAX_ITERATIONS", "60")),
        max_input_tokens=int(
            os.environ.get("BISTVALULT_MAX_INPUT_TOKENS", "180000")
        ),
    )
