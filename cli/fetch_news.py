"""News fetcher for the bistValult wiki.

Pulls BIST news from TradingView's public news-mediator endpoint
(see ``docs/tradingview-news-api.md``) and writes one markdown file per
article to ``raw_sources/news/``. Deduplication is keyed on the
TradingView article id and persisted in ``cli/state/news-seen.json``.

Cron contract:
  - Exit 0 even with zero new items.
  - Exit non-zero only on hard failure (no recoverable network errors —
    per-ticker request failures are logged and skipped).
  - Print absolute paths of newly-written files to stdout, one per line.
  - Idempotent: re-running back-to-back produces zero new files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from cli.lib import raw_writer, seen_state

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw_sources" / "news"
STATE_PATH = REPO_ROOT / "cli" / "state" / "news-seen.json"

SEEN_KEY = "tradingview-news"

LIST_URL = "https://news-mediator.tradingview.com/public/news-flow/v2/news"
STORY_URL = "https://news-mediator.tradingview.com/public/news/v1/story"
PUBLIC_TV_BASE = "https://www.tradingview.com"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------


def encode_query(params: list[tuple[str, str]]) -> str:
    """Percent-encode every reserved char inside values.

    TradingView requires the colon between filter key and value, and the
    comma between multi-values, to be percent-encoded. Using ``safe=''``
    handles both uniformly.
    """
    return "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params)


def http_get_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_url_tr_stocks(lang: str) -> str:
    """One list call for all Turkish-stock news. Filter keys must be alphabetical."""
    params = [
        ("filter", f"lang:{lang}"),
        ("filter", "market:stock"),
        ("filter", "market_country:TR"),
        ("client", "screener"),
        ("user_prostatus", "non_pro"),
    ]
    return f"{LIST_URL}?{encode_query(params)}"


def story_url_for(item_id: str, lang: str) -> str:
    params = [
        ("id", item_id),
        ("lang", lang),
        ("user_prostatus", "non_pro"),
    ]
    return f"{STORY_URL}?{encode_query(params)}"


def fetch_list(lang: str) -> list[dict[str, Any]]:
    url = list_url_tr_stocks(lang)
    try:
        data = http_get_json(url)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fetch_news] HTTP {e.code} list: {e.reason}\n")
        return []
    except urllib.error.URLError as e:
        sys.stderr.write(f"[fetch_news] network list: {e.reason}\n")
        return []
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[fetch_news] decode list: {e}\n")
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def fetch_story(item_id: str, lang: str) -> dict[str, Any] | None:
    url = story_url_for(item_id, lang)
    try:
        data = http_get_json(url)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fetch_news] HTTP {e.code} story {item_id}: {e.reason}\n")
        return None
    except urllib.error.URLError as e:
        sys.stderr.write(f"[fetch_news] network story {item_id}: {e.reason}\n")
        return None
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[fetch_news] decode story {item_id}: {e}\n")
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Article rendering
# ---------------------------------------------------------------------------


def ast_to_markdown(node: Any) -> str:
    """Flatten TradingView ``ast_description`` to markdown.

    Observed node types: ``root``, ``p``, ``b``, ``i``, ``a``, ``news-image``,
    ``br``. Unknown types fall back to emitting their children.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(ast_to_markdown(c) for c in node)
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    children = node.get("children")
    inner = ast_to_markdown(children) if children else ""
    if t in (None, "root"):
        return inner
    if t == "p":
        return inner.strip() + "\n\n"
    if t == "b":
        return f"**{inner}**"
    if t == "i":
        return f"*{inner}*"
    if t == "a":
        params = node.get("params") or {}
        href = params.get("url") or params.get("href") or ""
        return f"[{inner}]({href})" if href else inner
    if t == "br":
        return "\n"
    if t == "news-image":
        params = node.get("params") or {}
        img = params.get("image") or {}
        alt = img.get("alt") or ""
        url = img.get("url") or img.get("src") or ""
        if url:
            return f"\n![{alt}]({url})\n\n"
        return ""
    return inner


def published_date(ts: Any) -> str:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def related_tickers_from_item(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for rel in item.get("relatedSymbols") or []:
        if not isinstance(rel, dict):
            continue
        sym = rel.get("symbol")
        if not isinstance(sym, str) or ":" not in sym:
            continue
        exchange, ticker = sym.split(":", 1)
        if exchange != "BIST":
            continue
        if ticker not in out:
            out.append(ticker)
    return out


def story_link(item: dict[str, Any], story: dict[str, Any] | None) -> str:
    direct = item.get("link")
    if isinstance(direct, str) and direct:
        return direct
    if story:
        s_link = story.get("link")
        if isinstance(s_link, str) and s_link:
            return s_link
    path = item.get("storyPath")
    if not (isinstance(path, str) and path) and story:
        path = story.get("story_path")
    if isinstance(path, str) and path:
        return PUBLIC_TV_BASE + path
    return ""


def article_filename(date: str, provider_id: str, title: str, item_id: str) -> str:
    """Deterministic, collision-free filename per article."""
    title_slug = raw_writer.slugify(title) or "untitled"
    provider_slug = raw_writer.slugify(provider_id) or "tradingview"
    id_suffix = hashlib.sha1(item_id.encode("utf-8")).hexdigest()[:8]
    return f"{date}-{provider_slug}-{title_slug}-{id_suffix}.md"


def render_article(
    item: dict[str, Any],
    story: dict[str, Any] | None,
    tickers: list[str],
    published: str,
) -> tuple[dict[str, Any], str]:
    title = ((story or {}).get("title")) or item.get("title") or "(untitled)"
    published_ts = item.get("published")
    provider = item.get("provider") or (story or {}).get("provider") or {}
    provider_id = provider.get("id") or "tradingview"
    provider_name = provider.get("name") or provider_id
    permission = (story or {}).get("permission") or item.get("permission") or "headline"
    short_desc = ((story or {}).get("short_description") or "").strip()
    body_md = ""
    if story:
        ast = story.get("ast_description")
        if isinstance(ast, dict):
            body_md = ast_to_markdown(ast).strip()

    fm: dict[str, Any] = {
        "type": "raw",
        "source_kind": "news",
        "source_publisher": provider_name,
        "source_url": story_link(item, story),
        "published": published,
        "fetched": seen_state.now_iso(),
        "tradingview_id": item.get("id", ""),
        "tradingview_provider_id": provider_id,
        "permission": permission,
        "related_tickers": tickers,
        "language": (story or {}).get("language") or "en",
    }
    if isinstance(published_ts, (int, float)):
        fm["published_unix"] = int(published_ts)

    parts: list[str] = [f"# {title}", ""]
    if short_desc and short_desc not in body_md:
        parts.extend([short_desc, ""])
    if body_md:
        parts.append(body_md)
    elif permission == "headline":
        parts.append("_(headline only — body gated to authenticated TradingView users)_")
    else:
        parts.append("_(no body returned by source)_")
    return fm, "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_news")
    ap.add_argument(
        "--since",
        default="last",
        help="Cron-contract compatibility flag; dedup is driven by the seen-state file",
    )
    ap.add_argument("--lang", default="en", help="TradingView language filter (default: en)")
    ap.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="Seconds to sleep between story fetches (default: 1.0)",
    )
    ap.add_argument(
        "--max-stories",
        type=int,
        default=25,
        help="Cap on story-detail fetches per run; remainder picked up on next tick (default: 25)",
    )
    args = ap.parse_args(argv)

    state = seen_state.load(STATE_PATH)
    written: list[Path] = []

    # Step 1 — single list call: latest TR-market stock news.
    items = fetch_list(args.lang)

    # Step 2 — keep only items mentioning a BIST ticker and aren't seen yet.
    new_items: list[tuple[str, dict[str, Any], list[str]]] = []
    for item in items:
        iid = item.get("id")
        if not isinstance(iid, str) or not iid:
            continue
        tickers = related_tickers_from_item(item)
        if not tickers:
            continue
        if seen_state.is_seen(state, SEEN_KEY, iid):
            continue
        new_items.append((iid, item, tickers))

    # Step 3 — fetch story body and write a raw file for each, capped & throttled.
    fetched_count = 0
    try:
        for iid, item, tickers in new_items:
            title = item.get("title") or "untitled"
            provider_id = (item.get("provider") or {}).get("id") or "tradingview"
            published = published_date(item.get("published"))
            filename = article_filename(published, provider_id, title, iid)

            # Cheap recovery: file already exists from a prior run whose state
            # didn't persist. Mark seen and move on without hitting the network.
            if (RAW_DIR / filename).exists():
                seen_state.mark_seen(state, SEEN_KEY, iid, "")
                continue

            if fetched_count >= args.max_stories:
                continue  # leave for the next cron tick

            story = fetch_story(iid, args.lang)
            fetched_count += 1
            fm, body = render_article(item, story, tickers, published)

            target = raw_writer.write_raw(RAW_DIR, filename, fm, body, overwrite=False)
            seen_state.mark_seen(state, SEEN_KEY, iid, body)
            if target is not None:
                written.append(target)
            time.sleep(args.throttle)
    finally:
        seen_state.save(STATE_PATH, state)

    deferred = sum(
        1
        for iid, item, _ in new_items
        if iid not in state.get(SEEN_KEY, {})
    )
    if deferred:
        sys.stderr.write(
            f"[fetch_news] {deferred} new item(s) deferred to next run (max-stories cap)\n"
        )

    for p in written:
        print(str(p.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
