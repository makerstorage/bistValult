"""Dynamic ticker registry backed by raw_sources/company_meta/<TICKER>.json files.

Replaces the static bist30.py dict. Populate the JSON files by running:
    python -m cli.fetch_company_meta

The public interface is intentionally identical to the old bist30.py so that
any future code can swap the import without further changes.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_META_DIR = REPO_ROOT / "raw_sources" / "company_meta"


def _load() -> dict[str, dict]:
    if not _META_DIR.exists():
        return {}
    out: dict[str, dict] = {}
    for p in sorted(_META_DIR.glob("*.json")):
        ticker = p.stem.upper()
        try:
            out[ticker] = json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return out


TICKERS: dict[str, dict] = _load()


def all_tickers() -> list[str]:
    return list(TICKERS.keys())


def aliases_for(ticker: str) -> list[str]:
    return TICKERS[ticker]["aliases"]


def alias_to_ticker() -> dict[str, str]:
    """Reverse map: case-folded alias -> canonical ticker."""
    out: dict[str, str] = {}
    for ticker, data in TICKERS.items():
        for alias in data.get("aliases", []):
            out[alias.casefold()] = ticker
    return out


def get_company(ticker: str) -> dict:
    """Return the full metadata dict for a ticker. Raises KeyError if unknown."""
    return TICKERS[ticker]
