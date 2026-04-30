"""Fetch/refresh company metadata from TradingView for tickers in raw_sources/company_meta/.

The company registry is driven entirely by what JSON files exist in company_meta/.
That directory is seeded from the BIST company list (sirketler.xlsx). Any ticker
that appears in raw data but lacks a JSON file gets a stub wiki page with
needs_review: true; run this script with --ticker to enrich it.

Cron contract:
  - Exit 0 even with zero new files written.
  - Exit non-zero only on hard failure.
  - Print absolute paths of written files to stdout, one per line.
  - Idempotent: skips tickers that already have a JSON file unless --force.

Usage:
    python -m cli.fetch_company_meta --ticker THYAO   # enrich/create one ticker
    python -m cli.fetch_company_meta --ticker THYAO --force  # re-fetch even if exists
    python -m cli.fetch_company_meta --all --force    # refresh all 774 tickers from TV
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

REPO_ROOT = Path(__file__).resolve().parent.parent
META_DIR = REPO_ROOT / "raw_sources" / "company_meta"

SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
THROTTLE = 0.5  # seconds between requests


def search_ticker(ticker: str) -> dict | None:
    """Query TradingView symbol search and return the first BIST match."""
    params = urllib.parse.urlencode({"text": ticker, "exchange": "BIST", "lang": "en"})
    url = f"{SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fetch_company_meta] HTTP {e.code} for {ticker}: {e.reason}\n")
        return None
    except urllib.error.URLError as e:
        sys.stderr.write(f"[fetch_company_meta] network error for {ticker}: {e.reason}\n")
        return None
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[fetch_company_meta] decode error for {ticker}: {e}\n")
        return None

    symbols = data if isinstance(data, list) else data.get("symbols") if isinstance(data, dict) else None
    if not isinstance(symbols, list):
        return None
    for sym in symbols:
        if isinstance(sym, dict) and sym.get("exchange") == "BIST" and sym.get("symbol") == ticker:
            return sym
    for sym in symbols:
        if isinstance(sym, dict) and sym.get("exchange") == "BIST":
            return sym
    return None


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(text)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def process_ticker(ticker: str, force: bool) -> Path | None:
    """Fetch metadata for one ticker and write/merge the JSON. Returns path if written."""
    dest = META_DIR / f"{ticker}.json"

    if dest.exists() and not force:
        return None

    existing: dict = {}
    if dest.exists():
        try:
            existing = json.loads(dest.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    tv = search_ticker(ticker)
    if tv is None:
        if not dest.exists():
            # Create a minimal stub so the ticker is at least recognized
            write_atomic(dest, {
                "name": ticker,
                "sector": "",
                "exchange": "BIST",
                "description": "",
                "aliases": [ticker],
            })
            return dest
        sys.stderr.write(f"[fetch_company_meta] no TradingView data for {ticker}, keeping existing\n")
        return None

    tv_name = tv.get("description") or tv.get("full_name") or ticker
    tv_exchange = tv.get("exchange") or "BIST"

    aliases: list[str] = existing.get("aliases", [])
    if ticker not in aliases:
        aliases.insert(0, ticker)
    if tv_name and tv_name not in aliases:
        aliases.append(tv_name)

    payload = {
        "name": tv_name,
        "sector": existing.get("sector") or "",
        "exchange": tv_exchange,
        "description": existing.get("description") or "",
        "aliases": aliases,
    }

    write_atomic(dest, payload)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_company_meta")
    ap.add_argument("--force", action="store_true", help="Re-fetch even if JSON already exists")
    ap.add_argument("--ticker", metavar="TICKER", help="Process a single ticker")
    ap.add_argument("--all", dest="all_tickers", action="store_true",
                    help="Process all existing tickers in company_meta/ (use with --force to refresh)")
    ap.add_argument("--throttle", type=float, default=THROTTLE,
                    help=f"Seconds between requests (default: {THROTTLE})")
    args = ap.parse_args(argv)

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.all_tickers:
        tickers = sorted(p.stem.upper() for p in META_DIR.glob("*.json"))
    else:
        ap.print_help()
        return 0

    written: list[Path] = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(args.throttle)
        result = process_ticker(ticker, force=args.force)
        if result is not None:
            written.append(result)

    for p in written:
        print(str(p.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
