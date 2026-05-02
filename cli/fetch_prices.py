"""Price + fundamentals snapshot fetcher for the bistValult wiki.

Pulls the latest TradingView screener row for each *tracked* BIST ticker —
i.e. tickers that already have a ``wiki/companies/<TICKER>.md`` page — and
writes one rolling markdown file per ticker to ``raw_sources/prices/<TICKER>.md``.
The file is overwritten on every run; `price_date` (in frontmatter) is the
authoritative timestamp.

Cron contract:
  - Exit 0 even with zero new files written.
  - Exit non-zero only on hard failure (network unavailable, auth failure).
  - Print absolute paths of newly-written files to stdout, one per line.
  - Idempotent: re-running on the same calendar day with unchanged data
    produces zero stdout lines (no agent re-invocation).
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from cli.lib import raw_writer

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw_sources" / "prices"
WIKI_COMPANIES_DIR = REPO_ROOT / "wiki" / "companies"

SCANNER_URL = "https://scanner.tradingview.com/global/scan"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# Columns to request from TradingView screener (internal field names).
# Split into two semantic blocks the ingestor will route to two different
# sections of the company page:
#   - SNAPSHOT_COLUMNS  → ## Current snapshot  (fast-changing, daily)
#   - FUNDAMENTALS_COLS → ## Financials table  (ratios, quarterly-stable)
SNAPSHOT_COLUMNS = [
    "name",                # ticker symbol, e.g. "THYAO"
    "close",               # last close price (TRY)
    "change",              # % change vs prior close
    "change_abs",          # absolute change (TRY)
    "volume",              # session volume (shares)
    "market_cap_basic",    # market cap (TRY)
    "price_52_week_high",  # 52-week high (TRY)
    "price_52_week_low",   # 52-week low (TRY)
    "Perf.W",              # 1-week performance (%)
    "Perf.1M",             # 1-month performance (%)
]

FUNDAMENTALS_COLUMNS = [
    "price_earnings_ttm",            # P/E TTM
    "price_book_ratio",              # P/B (FY)
    "enterprise_value_to_ebitda_ttm",# EV / EBITDA (TTM)
    "earnings_per_share_basic_ttm",  # EPS basic (TTM)
    "dividend_yield_recent",         # most recent dividend yield (%)
    "debt_to_equity",                # Debt / Equity
    "sector",                        # TradingView sector classification
    "industry",                      # TradingView industry classification
]

COLUMNS = SNAPSHOT_COLUMNS + FUNDAMENTALS_COLUMNS

# Maximum number of rows per API response (BIST has ~774 listed stocks).
SCAN_LIMIT = 1000


def tracked_tickers() -> set[str]:
    """Return the set of tickers we maintain wiki pages for.

    A wiki page is the strongest signal that a ticker is tracked — deleting
    the page auto-untracks it. company_meta is the enrichment universe
    (~774); tracked is a subset (~44 today).
    """
    if not WIKI_COMPANIES_DIR.exists():
        return set()
    return {p.stem.upper() for p in WIKI_COMPANIES_DIR.glob("*.md")}


def fetch_all_turkey_stocks() -> list[dict[str, Any]]:
    """Single scan call for all Turkey-market stocks. Returns list of {ticker, fields}."""
    payload = {
        "columns": COLUMNS,
        "markets": ["turkey"],
        "filter": [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, SCAN_LIMIT],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SCANNER_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fetch_prices] HTTP {e.code}: {e.reason}\n")
        raise
    except urllib.error.URLError as e:
        sys.stderr.write(f"[fetch_prices] network error: {e.reason}\n")
        raise

    rows = []
    for item in data.get("data", []):
        raw_symbol = item.get("s", "")
        ticker = raw_symbol.split(":", 1)[-1] if ":" in raw_symbol else raw_symbol
        values = dict(zip(COLUMNS, item.get("d", [])))
        rows.append({"ticker": ticker, **values})
    return rows


def fmt_num(v: Any, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v:,.{decimals}f}"


def fmt_pct(v: Any) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def fmt_mcap(v: Any) -> str:
    """Format market cap (TRY) as human-readable string."""
    if v is None:
        return "N/A"
    if v >= 1e12:
        return f"{v/1e12:.2f}T TRY"
    if v >= 1e9:
        return f"{v/1e9:.2f}B TRY"
    if v >= 1e6:
        return f"{v/1e6:.2f}M TRY"
    return f"{v:,.0f} TRY"


def fmt_str(v: Any) -> str:
    if v is None or v == "":
        return "N/A"
    return str(v)


def render_price_file(ticker: str, row: dict[str, Any], date: str) -> tuple[dict, str]:
    price = row.get("close")
    change_pct = row.get("change")
    change_abs = row.get("change_abs")
    volume = row.get("volume")
    mcap = row.get("market_cap_basic")
    high52 = row.get("price_52_week_high")
    low52 = row.get("price_52_week_low")
    perf_w = row.get("Perf.W")
    perf_1m = row.get("Perf.1M")

    pe = row.get("price_earnings_ttm")
    pb = row.get("price_book_ratio")
    ev_ebitda = row.get("enterprise_value_to_ebitda_ttm")
    eps_ttm = row.get("earnings_per_share_basic_ttm")
    div_yield = row.get("dividend_yield_recent")
    debt_eq = row.get("debt_to_equity")
    sector = row.get("sector")
    industry = row.get("industry")

    fm: dict[str, Any] = {
        "type": "raw",
        "source_kind": "prices",
        "source_publisher": "TradingView screener",
        "ticker": ticker,
        "currency": "TRY",
        "price_date": date,
        "related_tickers": [ticker],
    }

    sign = "+" if (change_pct or 0) > 0 else ""
    body = f"# {ticker} — market data {date}\n\n"

    body += "## Snapshot\n\n"
    body += "| Metric | Value |\n|---|---|\n"
    body += f"| Price (TRY) | {fmt_num(price)} |\n"
    body += f"| Change % | {fmt_pct(change_pct)} |\n"
    body += f"| Change (abs, TRY) | {sign}{fmt_num(change_abs)} |\n"
    body += f"| Volume | {int(volume):,} |\n" if volume is not None else "| Volume | N/A |\n"
    body += f"| Market Cap | {fmt_mcap(mcap)} |\n"
    body += f"| 52W High (TRY) | {fmt_num(high52)} |\n"
    body += f"| 52W Low (TRY) | {fmt_num(low52)} |\n"
    body += f"| Weekly Perf % | {fmt_pct(perf_w)} |\n"
    body += f"| Monthly Perf % | {fmt_pct(perf_1m)} |\n"

    body += "\n## Fundamentals\n\n"
    body += "| Metric | Value |\n|---|---|\n"
    body += f"| P/E (TTM) | {fmt_num(pe)} |\n"
    body += f"| P/B (FY) | {fmt_num(pb)} |\n"
    body += f"| EV/EBITDA (TTM) | {fmt_num(ev_ebitda)} |\n"
    body += f"| EPS basic (TTM, TRY) | {fmt_num(eps_ttm)} |\n"
    body += f"| Dividend yield | {fmt_pct(div_yield)} |\n"
    body += f"| Debt / Equity | {fmt_num(debt_eq)} |\n"
    body += f"| Sector (TV) | {fmt_str(sector)} |\n"
    body += f"| Industry (TV) | {fmt_str(industry)} |\n"

    return fm, body


def main(argv: list[str] | None = None) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    known_tickers = tracked_tickers()
    if not known_tickers:
        sys.stderr.write(
            "[fetch_prices] no tracked company pages found in wiki/companies/\n"
        )
        return 1

    try:
        rows = fetch_all_turkey_stocks()
    except (urllib.error.HTTPError, urllib.error.URLError):
        return 1

    if not rows:
        sys.stderr.write("[fetch_prices] no data returned from screener\n")
        return 1

    written: list[Path] = []
    unchanged = 0
    seen_tickers: set[str] = set()

    for row in rows:
        ticker = row["ticker"]
        if ticker not in known_tickers:
            continue
        seen_tickers.add(ticker)

        filename = f"{ticker}.md"
        fm, body = render_price_file(ticker, row, today)
        target = raw_writer.write_raw(
            RAW_DIR, filename, fm, body, overwrite=True, skip_if_unchanged=True
        )
        if target is not None:
            written.append(target)
        else:
            unchanged += 1

    missing = sorted(known_tickers - seen_tickers)
    if missing:
        sys.stderr.write(
            f"[fetch_prices] {len(missing)} tracked ticker(s) had no screener row: "
            + ", ".join(missing)
            + "\n"
        )

    if unchanged:
        sys.stderr.write(
            f"[fetch_prices] {unchanged} ticker(s) had unchanged data — skipped\n"
        )

    for p in written:
        print(str(p.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
