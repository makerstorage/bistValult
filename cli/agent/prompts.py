"""Load subagent system prompts from .claude/agents/*.md.

The .md files are kept *exactly* as authored — they are still the
source of truth for prompt content even after the port off Claude Code.
This module strips the YAML frontmatter and returns the markdown body.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def load_subagent_prompt(name: str) -> str:
    """Return the markdown body of ``.claude/agents/<name>.md``.

    Raises FileNotFoundError if the file does not exist.
    """
    path = AGENTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1).lstrip()
