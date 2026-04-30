"""Persistent dedup state for CLI fetchers.

State file is a JSON document keyed by source name, then by article id:

    {
      "<source-name>": {
        "<article-id-or-canonical-url>": {
          "hash": "sha256:...",
          "fetched": "2026-04-29T12:34:56Z"
        }
      }
    }

Save is atomic: write to a sibling tempfile, fsync, rename.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def hash_body(body: str) -> str:
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_seen(state: dict, source: str, article_id: str) -> bool:
    return article_id in state.get(source, {})


def mark_seen(state: dict, source: str, article_id: str, body: str) -> None:
    state.setdefault(source, {})[article_id] = {
        "hash": hash_body(body),
        "fetched": now_iso(),
    }
