"""File-system tools exposed to the subagent LLM.

Five tools — read_file, write_file, edit_file, grep, delete_file. Designed to
mirror Claude Code's Read/Write/Edit/Grep semantics so the existing subagent
prompts (.claude/agents/*.md) work without modification.

Security model — every path argument is normalised and checked against a
per-tool allow-list rooted at the repo root. The model cannot escape via
``..`` or absolute paths outside the allowed roots; it gets a structured
error string back, which it can reason about and retry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Read access — anywhere under these roots is OK.
READ_ROOTS = (
    REPO_ROOT / "wiki",
    REPO_ROOT / "raw_sources",
    REPO_ROOT / "docs",
    REPO_ROOT / "templates",
    REPO_ROOT / ".claude",
    REPO_ROOT / "CLAUDE.md",
)

# Write / edit — strictly under wiki/.
WRITE_ROOTS = (REPO_ROOT / "wiki",)

# Delete — even tighter: only ephemeral source pages and claim pages.
# Compactor needs both. Ingestor never deletes (its prompt forbids it).
DELETE_GLOBS = (
    "wiki/sources/*.md",
    "wiki/claims/*.md",
)


class ToolError(Exception):
    """Raised by tool implementations on user-facing failures.

    The agent loop catches this, formats the message as the tool's
    response, and lets the model adapt.
    """


def _resolve(path_str: str) -> Path:
    """Resolve a path relative to the repo root. Absolute paths are accepted
    as long as they lie inside the repo (the allow-list does the rest)."""
    p = Path(path_str)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


def _under_any(p: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            p.relative_to(root)
            return True
        except ValueError:
            if p == root:
                return True
    return False


def _check_read(p: Path) -> None:
    if not _under_any(p, READ_ROOTS):
        raise ToolError(
            f"Path not readable: {p} is outside the allowed read roots "
            f"({', '.join(str(r.relative_to(REPO_ROOT)) for r in READ_ROOTS)})."
        )


def _check_write(p: Path) -> None:
    if not _under_any(p, WRITE_ROOTS):
        raise ToolError(
            f"Path not writable: {p} is outside wiki/. "
            "Subagents can only write inside wiki/."
        )


def _check_delete(p: Path) -> None:
    rel = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else None
    if rel is None:
        raise ToolError(f"Refusing to delete outside repo: {p}")
    for pattern in DELETE_GLOBS:
        if Path(rel).match(pattern):
            return
    raise ToolError(
        f"Refusing to delete {rel} — only {', '.join(DELETE_GLOBS)} are deletable."
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def read_file(path: str, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """Read a UTF-8 text file. Returns {content, truncated, total_lines}.

    ``content`` is line-numbered (``"   1\\t<line>"``) so the model can quote
    line numbers for the user, matching Claude Code's Read tool format.
    """
    p = _resolve(path)
    _check_read(p)
    if not p.exists():
        raise ToolError(f"File does not exist: {path}")
    if not p.is_file():
        raise ToolError(f"Not a regular file: {path}")
    raw = p.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    total = len(lines)

    start = (offset or 0)
    end = total if limit is None else min(total, start + limit)
    selected = lines[start:end]

    numbered = "\n".join(f"{i + 1:6d}\t{line}" for i, line in enumerate(selected, start=start))
    return {
        "content": numbered,
        "total_lines": total,
        "returned_range": [start, end],
        "truncated": end < total,
    }


def write_file(path: str, content: str) -> dict[str, Any]:
    """Create or overwrite a file. Path must be under wiki/."""
    p = _resolve(path)
    _check_write(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p.relative_to(REPO_ROOT)), "bytes_written": len(content.encode("utf-8"))}


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict[str, Any]:
    """Exact-match find/replace, mirroring Claude Code's Edit tool.

    - Fails if ``old_string`` is not found.
    - Fails if ``old_string`` matches multiple times and ``replace_all`` is False
      — forces the model to widen its quote until the match is unique.
    """
    p = _resolve(path)
    _check_write(p)
    if not p.exists():
        raise ToolError(f"File does not exist: {path}")
    text = p.read_text(encoding="utf-8")
    occurrences = text.count(old_string)
    if occurrences == 0:
        raise ToolError(
            f"old_string not found in {path}. "
            "Quote a unique substring exactly as it appears in the file."
        )
    if occurrences > 1 and not replace_all:
        raise ToolError(
            f"old_string matches {occurrences} times in {path}. "
            "Either widen the quote to make it unique, or pass replace_all=true."
        )
    new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
    p.write_text(new_text, encoding="utf-8")
    replaced = occurrences if replace_all else 1
    return {"path": str(p.relative_to(REPO_ROOT)), "replacements": replaced}


def grep(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    max_results: int = 200,
) -> dict[str, Any]:
    """Pure-Python file search. Two modes:

    - ``files_with_matches`` (default): list paths containing a match.
      ``pattern`` may be empty — together with ``glob`` this acts as a
      glob/list operation (replaces the dropped Glob tool).
    - ``content``: ``filename:lineno:line`` for each match.
    """
    search_root = _resolve(path)
    _check_read(search_root)

    if output_mode not in ("files_with_matches", "content"):
        raise ToolError(f"Unknown output_mode: {output_mode}")

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags) if pattern else None
    except re.error as exc:
        raise ToolError(f"Invalid regex pattern: {exc}")

    if search_root.is_file():
        candidates: list[Path] = [search_root]
    else:
        pattern_glob = glob or "*"
        candidates = sorted(p for p in search_root.rglob(pattern_glob) if p.is_file())

    matches: list[str] = []
    truncated = False

    for f in candidates:
        try:
            f.relative_to(REPO_ROOT)
        except ValueError:
            continue
        rel = str(f.relative_to(REPO_ROOT))

        # Pattern-less listing — emit the file path itself.
        if regex is None:
            matches.append(rel)
            if len(matches) >= max_results:
                truncated = True
                break
            continue

        # Pattern search — read and scan.
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if output_mode == "files_with_matches":
            if regex.search(text):
                matches.append(rel)
                if len(matches) >= max_results:
                    truncated = True
                    break
        else:  # content
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{rel}:{lineno}:{line}")
                    if len(matches) >= max_results:
                        truncated = True
                        break
            if truncated:
                break

    return {
        "matches": matches,
        "match_count": len(matches),
        "truncated": truncated,
    }


def delete_file(path: str) -> dict[str, Any]:
    """Delete a file. Whitelisted to wiki/sources/*.md and wiki/claims/*.md."""
    p = _resolve(path)
    _check_delete(p)
    if not p.exists():
        # Idempotency: deleting a non-existent file is a no-op, not an error.
        return {"path": str(p.relative_to(REPO_ROOT)), "deleted": False, "reason": "not_found"}
    p.unlink()
    return {"path": str(p.relative_to(REPO_ROOT)), "deleted": True}


# ---------------------------------------------------------------------------
# OpenAI tool-calling JSON schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    impl: Any  # Callable
    schema: dict[str, Any]


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="read_file",
        impl=read_file,
        schema={
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a UTF-8 text file. Returns line-numbered content (matches Claude Code's Read tool format).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or repo-relative file path."},
                        "offset": {"type": "integer", "description": "Zero-based line to start at.", "minimum": 0},
                        "limit": {"type": "integer", "description": "Max lines to return.", "minimum": 1},
                    },
                    "required": ["path"],
                },
            },
        },
    ),
    ToolSpec(
        name="write_file",
        impl=write_file,
        schema={
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file under wiki/. Path must be inside wiki/.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string", "description": "Full file contents (UTF-8)."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
    ),
    ToolSpec(
        name="edit_file",
        impl=edit_file,
        schema={
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": (
                    "Exact-match find/replace on a file under wiki/. Fails if old_string "
                    "is not found, or matches multiple times unless replace_all=true. "
                    "Mirrors Claude Code's Edit semantics."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "replace_all": {"type": "boolean", "default": False},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
        },
    ),
    ToolSpec(
        name="grep",
        impl=grep,
        schema={
            "type": "function",
            "function": {
                "name": "grep",
                "description": (
                    "Search files via ripgrep. output_mode=files_with_matches lists "
                    "paths containing the pattern; output_mode=content returns "
                    "filename:lineno:line. With pattern='' and a glob you get a plain "
                    "file listing — use this in place of glob."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern, or empty string to list files."},
                        "path": {"type": "string", "description": "Search root (file or directory).", "default": "."},
                        "glob": {"type": "string", "description": "Filename glob, e.g. '*.md'."},
                        "output_mode": {
                            "type": "string",
                            "enum": ["files_with_matches", "content"],
                            "default": "files_with_matches",
                        },
                        "case_insensitive": {"type": "boolean", "default": False},
                        "max_results": {"type": "integer", "default": 200, "minimum": 1},
                    },
                    "required": ["pattern"],
                },
            },
        },
    ),
    ToolSpec(
        name="delete_file",
        impl=delete_file,
        schema={
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": (
                    "Delete a file. Whitelisted to wiki/sources/*.md and wiki/claims/*.md "
                    "(used by the compactor). Idempotent — deleting a missing file is a no-op."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
    ),
]


def schemas() -> list[dict[str, Any]]:
    return [t.schema for t in TOOLS]


def dispatch(name: str, arguments: dict[str, Any]) -> str:
    """Run one tool call and return its JSON-serialised result string."""
    for t in TOOLS:
        if t.name == name:
            try:
                result = t.impl(**arguments)
                return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
            except ToolError as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
            except TypeError as exc:
                return json.dumps(
                    {"ok": False, "error": f"Bad arguments to {name}: {exc}"},
                    ensure_ascii=False,
                )
    return json.dumps({"ok": False, "error": f"Unknown tool: {name}"}, ensure_ascii=False)
