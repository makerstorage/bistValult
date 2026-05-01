"""Shared helpers for orchestrator scripts.

Each orchestrator is a Python port of one ``.claude/commands/*.md`` file.
The original markdown commands shared the same shape: run a Python fetcher,
branch on stdout, append a single line to ``wiki/log.md``, optionally
delegate to a subagent. This module captures the bits common to all of them.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_PATH = REPO_ROOT / "wiki" / "log.md"


def today() -> str:
    return date.today().isoformat()


def append_log(line: str) -> None:
    """Append a single Markdown line to wiki/log.md.

    Always trailing-newline-terminated. Creates the file (and parent dir)
    on first call. Format matches the existing slash-command output.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    needs_leading_nl = LOG_PATH.exists() and not LOG_PATH.read_text(
        encoding="utf-8"
    ).endswith("\n")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        if needs_leading_nl:
            f.write("\n")
        f.write(line.rstrip("\n") + "\n")


def run_fetcher(module: str, args: list[str]) -> tuple[int, list[str], str]:
    """Run a ``python3 -m cli.<module>`` fetcher and split its stdout into paths.

    Returns (returncode, paths, stderr). Paths are non-empty stripped lines.
    """
    proc = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    paths = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return proc.returncode, paths, proc.stderr


def first_stderr_line(stderr: str) -> str:
    for ln in stderr.splitlines():
        s = ln.strip()
        if s:
            return s
    return "(no stderr)"
