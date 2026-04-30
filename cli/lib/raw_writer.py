"""Atomic, deterministic writer for raw_sources/<kind>/ files."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


def slugify(text: str, max_len: int = 60) -> str:
    """Lowercase ASCII slug. Non-alphanumerics collapse to single hyphens."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", errors="ignore").decode("ascii")
    hyphenated = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return hyphenated[:max_len].rstrip("-")


def raw_filename(date: str, source: str, title: str) -> str:
    """Deterministic filename: <YYYY-MM-DD>-<source-slug>-<title-slug>.md"""
    return f"{date}-{slugify(source)}-{slugify(title)}.md"


def _format_frontmatter(fm: dict[str, Any]) -> str:
    """JSON-encode every value. JSON is a strict subset of YAML for these
    types, so the result is always valid YAML and never needs ad-hoc quoting."""
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def write_raw(
    raw_dir: Path,
    filename: str,
    frontmatter: dict[str, Any],
    body: str,
    *,
    overwrite: bool = False,
) -> Path | None:
    """Write a raw markdown file atomically.

    Returns the target path if written, or None if it already existed and
    overwrite=False.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / filename
    if target.exists() and not overwrite:
        return None

    content = _format_frontmatter(frontmatter) + "\n\n" + body.strip() + "\n"

    fd, tmp = tempfile.mkstemp(prefix=filename + ".", suffix=".tmp", dir=str(raw_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        return target
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
