"""KAP disclosure fetcher for the bistValult wiki.

Pulls Türkiye Kamuyu Aydınlatma Platformu disclosures from the public list
endpoint at ``https://kap.org.tr/tr/api/disclosure/list/main``, filters to
exchange-traded companies (memberType ``PYS``) and the high-signal disclosure
types (``ODA``, ``FR``, ``CA``), fetches each disclosure's HTML detail page,
parses to plain text + attachment links, and writes one markdown file per
disclosure to ``raw_sources/kap_filings/``.

Deduplication is keyed on the KAP ``disclosureIndex`` and persisted in
``cli/state/kap-seen.json``.

Cron contract:
  - Exit 0 even with zero new items.
  - Exit non-zero only on hard failure (per-detail HTTP failures are logged
    to stderr and skipped — the disclosure is left in the seen-state for
    a future retry).
  - Print absolute paths of newly-written files to stdout, one per line.
  - Idempotent: re-running back-to-back produces zero new files.
"""

from __future__ import annotations

import argparse
import html
import http.client
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from cli.lib import raw_writer, registry, seen_state

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw_sources" / "kap_filings"
STATE_PATH = REPO_ROOT / "cli" / "state" / "kap-seen.json"

SEEN_KEY = "kap-disclosures"

LIST_URL = "https://kap.org.tr/tr/api/disclosure/list/main"
DETAIL_URL = "https://kap.org.tr/tr/Bildirim/{idx}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30  # seconds
DETAIL_RETRIES = 2  # extra attempts on transient network errors (3 total tries)

# Transient network errors worth retrying on detail-page fetches. KAP serves
# multi-MB HTML for big financial reports and the connection occasionally drops
# mid-read (IncompleteRead). HTTPError is intentionally excluded — 4xx/5xx are
# usually deterministic, retrying just spams the server.
_TRANSIENT_NET_ERRORS: tuple[type[BaseException], ...] = (
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    ConnectionError,
    TimeoutError,
    urllib.error.URLError,
)

# API filter — settled with user. PYS-only, high-signal disclosure types.
DEFAULT_DISCLOSURE_TYPES = ["ODA", "FR", "CA"]
DEFAULT_MEMBER_TYPES = ["PYS"]


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------


def http_post_json(url: str, body: dict[str, Any]) -> Any:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, *, retries: int = DETAIL_RETRIES) -> str:
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
                raw = resp.read()
            # KAP serves UTF-8; fall back to replace if a stray byte sneaks through.
            return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            raise
        except _TRANSIENT_NET_ERRORS as e:
            if attempt >= retries:
                raise
            sys.stderr.write(
                f"[fetch_kap] transient {type(e).__name__} on {url} "
                f"(attempt {attempt + 1}/{retries + 1}); retrying\n"
            )
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# List fetch
# ---------------------------------------------------------------------------


def kap_date(d: datetime) -> str:
    """KAP requires GG.AA.YYYY (Turkish day-month-year)."""
    return d.strftime("%d.%m.%Y")


def fetch_list(
    *,
    days: int,
    disclosure_types: list[str],
    member_types: list[str],
) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc)
    body = {
        "fromDate": kap_date(today - timedelta(days=days)),
        "toDate": kap_date(today),
        "disclosureTypes": disclosure_types,
        "memberTypes": member_types,
        "mkkMemberOid": None,
    }
    try:
        data = http_post_json(LIST_URL, body)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fetch_kap] HTTP {e.code} list: {e.reason}\n")
        return []
    except urllib.error.URLError as e:
        sys.stderr.write(f"[fetch_kap] network list: {e.reason}\n")
        return []
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[fetch_kap] decode list: {e}\n")
        return []
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Detail-page parsing
# ---------------------------------------------------------------------------

_CHROME_END_SENTINELS = (
    "Veri Depolama Kuruluşu",
    "Kapat Gönderim Tarihi",
)
_CONTENT_END_SENTINELS = (
    "Bildirimler Finansal Tablolar Hak Kullanımları",
    "PDF WORD EXCEl YAZDIR",
    "PDF WORD EXCEL YAZDIR",
)

# Detail-body cap. Most ODA/CA filings are <5KB; financial reports (FR) inline
# the full XBRL line-item tree and routinely exceed 100KB. Capping at 20KB keeps
# the raw file ingestor-friendly without losing the narrative explanation —
# the canonical full disclosure remains accessible via source_url + attachments.
_DETAIL_BODY_CAP = 20_000
_TRUNCATION_NOTE = (
    "\n\n_(detay metni uzunluk sınırı nedeniyle kısaltıldı — "
    "tam içerik için kaynak URL'sine ve eklere bakın)_"
)

_ATT_RE = re.compile(
    r'<a[^>]*href="(https://kap\.org\.tr/tr/api/file/download/[^"]+)"[^>]*>([^<]+)</a>',
    re.S,
)
_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)
_STYLE_RE = re.compile(r"<style\b.*?</style>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\n]+")


def parse_detail_html(html_text: str) -> tuple[str, list[dict[str, str]]]:
    """Return (body_markdown, attachments) extracted from a KAP detail page.

    Body is plain text with paragraph breaks; attachments are
    ``[{"title": "<filename>", "url": "<download-url>"}]`` deduped by URL,
    in the order they appear in the HTML.
    """
    # Attachments first — must match the original markup, not the stripped text.
    seen_urls: set[str] = set()
    attachments: list[dict[str, str]] = []
    for url, title in _ATT_RE.findall(html_text):
        if url in seen_urls:
            continue
        seen_urls.add(url)
        attachments.append({"title": title.strip(), "url": url})

    # Body — strip script/style, drop tags, collapse whitespace, clip nav chrome.
    no_script = _SCRIPT_RE.sub("", html_text)
    no_style = _STYLE_RE.sub("", no_script)
    text = _TAG_RE.sub(" ", no_style)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()

    # Clip leading nav chrome — content begins after the footer-copyright sentinel.
    start = -1
    for sent in _CHROME_END_SENTINELS:
        idx = text.find(sent)
        if idx >= 0:
            start = idx + len(sent)
            break
    if start >= 0:
        text = text[start:].strip()

    # Clip trailing post-content nav chrome.
    for sent in _CONTENT_END_SENTINELS:
        idx = text.find(sent)
        if idx >= 0:
            text = text[:idx].strip()
            break

    if len(text) > _DETAIL_BODY_CAP:
        text = text[:_DETAIL_BODY_CAP].rstrip() + _TRUNCATION_NOTE

    return text, attachments


# ---------------------------------------------------------------------------
# Item shaping
# ---------------------------------------------------------------------------


def parse_publish_date(s: str | None) -> str:
    """KAP publishDate is 'DD.MM.YYYY HH:MM:SS' → ISO date 'YYYY-MM-DD'."""
    if not isinstance(s, str) or not s:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    head = s.split(" ", 1)[0]
    try:
        return datetime.strptime(head, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def split_related_stocks(s: Any) -> list[str]:
    if not isinstance(s, str) or not s.strip():
        return []
    return [p.strip().upper() for p in s.split(",") if p.strip()]


def disclosure_filename(
    *,
    published: str,
    stock_code: str,
    disclosure_type: str,
    title: str,
    idx: int,
) -> str:
    """Deterministic, collision-free filename per disclosure.

    Schema: <YYYY-MM-DD>-kap-<stockcode-lower>-<type-lower>-<title-slug>-<idx>.md
    The integer disclosureIndex is globally unique on KAP, so two re-runs
    cannot collide.
    """
    title_slug = raw_writer.slugify(title) or "untitled"
    stock_slug = raw_writer.slugify(stock_code) or "x"
    type_slug = raw_writer.slugify(disclosure_type) or "x"
    return f"{published}-kap-{stock_slug}-{type_slug}-{title_slug}-{idx}.md"


def render_disclosure(
    *,
    item: dict[str, Any],
    detail_body: str,
    attachments: list[dict[str, str]],
) -> tuple[dict[str, Any], str]:
    basic = item.get("disclosureBasic") or {}
    detail = item.get("disclosureDetail") or {}

    idx_raw = basic.get("disclosureIndex")
    try:
        idx = int(idx_raw)
    except (TypeError, ValueError):
        idx = 0

    title = (basic.get("title") or "").strip() or "(başlıksız)"
    summary = (basic.get("summary") or "").strip()
    stock_code = (basic.get("stockCode") or "").strip()
    disclosure_type = (basic.get("disclosureType") or "").strip()
    published = parse_publish_date(basic.get("publishDate"))

    related = [stock_code] if stock_code else []
    for t in split_related_stocks(basic.get("relatedStocks")):
        if t not in related:
            related.append(t)

    period = basic.get("period")
    year = basic.get("year")

    fm: dict[str, Any] = {
        "type": "raw",
        "source_kind": "kap_filing",
        "source_publisher": "KAP",
        "source_url": DETAIL_URL.format(idx=idx),
        "published": published,
        "fetched": seen_state.now_iso(),
        "kap_disclosure_index": idx,
        "kap_disclosure_type": disclosure_type,
        "kap_member_oid": basic.get("mkkMemberOid") or "",
        "kap_company_title": (basic.get("companyTitle") or "").strip(),
        "kap_is_late": bool(basic.get("isLate")),
        "kap_is_blocked": bool(basic.get("isBlocked")),
        "kap_period": period if isinstance(period, str) and period else None,
        "kap_year": int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None,
        "kap_attachment_count": int(basic.get("attachmentCount") or 0),
        "kap_attachments": attachments,
        "kap_member_type": (detail.get("memberType") or "PYS"),
        "related_tickers": related,
        "language": "tr",
    }

    parts: list[str] = [f"# {title}", ""]
    if summary and summary not in detail_body:
        parts.append(summary)
        parts.append("")
    if detail_body:
        parts.append(detail_body)
    else:
        parts.append("_(bildirim detay sayfasından metin çıkarılamadı)_")
    return fm, "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_kap")
    ap.add_argument(
        "--since",
        default="last",
        help="Cron-contract compatibility flag; dedup is driven by the seen-state file",
    )
    ap.add_argument(
        "--days",
        type=int,
        default=2,
        help="List window in days back from today (default: 2 — absorbs cron-tick jitter)",
    )
    ap.add_argument(
        "--max-stories",
        type=int,
        default=30,
        help="Cap on detail-page fetches per run; remainder picked up next tick (default: 30)",
    )
    ap.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="Seconds to sleep between detail fetches (default: 1.0)",
    )
    args = ap.parse_args(argv)

    state = seen_state.load(STATE_PATH)
    written: list[Path] = []

    rows = fetch_list(
        days=args.days,
        disclosure_types=DEFAULT_DISCLOSURE_TYPES,
        member_types=DEFAULT_MEMBER_TYPES,
    )

    # KAP's memberType=PYS is broader than the BIST equity universe we track —
    # it includes portfolio managers, REIT funds, etc. Filter primary stockCode
    # against the canonical ticker registry (see cli/lib/registry.py, sourced
    # from raw_sources/company_meta/). Same approach as fetch_news.py.
    bist_universe = set(registry.all_tickers())
    skipped_off_universe = 0

    # Filter — must have stockCode and a disclosureIndex; not seen yet.
    new_items: list[tuple[int, dict[str, Any]]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        basic = item.get("disclosureBasic") or {}
        idx_raw = basic.get("disclosureIndex")
        try:
            idx = int(idx_raw)
        except (TypeError, ValueError):
            continue
        stock_code = (basic.get("stockCode") or "").strip().upper()
        if not stock_code:
            continue  # PYS members without a tradable stockCode (rare; skip defensively)
        if stock_code not in bist_universe:
            skipped_off_universe += 1
            continue
        if seen_state.is_seen(state, SEEN_KEY, str(idx)):
            continue
        new_items.append((idx, item))

    if skipped_off_universe:
        sys.stderr.write(
            f"[fetch_kap] skipped {skipped_off_universe} non-BIST disclosure(s) "
            f"(stockCode not in registry)\n"
        )

    fetched_count = 0
    try:
        for idx, item in new_items:
            basic = item.get("disclosureBasic") or {}
            title = (basic.get("title") or "").strip() or "untitled"
            stock_code = (basic.get("stockCode") or "").strip()
            disclosure_type = (basic.get("disclosureType") or "").strip()
            published = parse_publish_date(basic.get("publishDate"))
            filename = disclosure_filename(
                published=published,
                stock_code=stock_code,
                disclosure_type=disclosure_type,
                title=title,
                idx=idx,
            )

            # Cheap recovery: file already exists from a prior run whose state
            # didn't persist. Mark seen and move on without hitting the network.
            if (RAW_DIR / filename).exists():
                seen_state.mark_seen(state, SEEN_KEY, str(idx), "")
                continue

            if fetched_count >= args.max_stories:
                continue  # leave for the next cron tick

            try:
                html_text = http_get_text(DETAIL_URL.format(idx=idx))
                detail_body, attachments = parse_detail_html(html_text)
            except urllib.error.HTTPError as e:
                sys.stderr.write(f"[fetch_kap] HTTP {e.code} detail {idx}: {e.reason}\n")
                fetched_count += 1
                time.sleep(args.throttle)
                continue
            except _TRANSIENT_NET_ERRORS as e:
                sys.stderr.write(
                    f"[fetch_kap] network detail {idx}: {type(e).__name__}: {e}\n"
                )
                fetched_count += 1
                time.sleep(args.throttle)
                continue

            fetched_count += 1

            fm, body = render_disclosure(
                item=item,
                detail_body=detail_body,
                attachments=attachments,
            )

            target = raw_writer.write_raw(RAW_DIR, filename, fm, body, overwrite=False)
            seen_state.mark_seen(state, SEEN_KEY, str(idx), body)
            if target is not None:
                written.append(target)
            time.sleep(args.throttle)
    finally:
        seen_state.save(STATE_PATH, state)

    deferred = sum(
        1
        for idx, _ in new_items
        if str(idx) not in state.get(SEEN_KEY, {})
    )
    if deferred:
        sys.stderr.write(
            f"[fetch_kap] {deferred} new disclosure(s) deferred to next run "
            f"(max-stories cap)\n"
        )

    for p in written:
        print(str(p.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
