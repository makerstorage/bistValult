# cli

Python data fetchers for the bistValult wiki. Each module fetches one kind of source from the internet and writes new raw files to `raw_sources/<kind>/`.

## Layout

- `fetch_news.py` — news fetcher entry point. Implementation pending the user's source/protocol spec.
- `lib/seen_state.py` — JSON-backed dedup state (atomic save).
- `lib/raw_writer.py` — deterministic filename + atomic write for `raw_sources/<kind>/`.
- `lib/registry.py` — dynamic ticker registry; reads `raw_sources/company_meta/*.json`.
- `fetch_company_meta.py` — fetches company metadata from TradingView for tickers in `raw_sources/universe.txt`.
- `state/` — persistent CLI state (e.g. `news-seen.json`). Created on first run.

## Run

From the project root:

```
python -m cli.fetch_news --since=last
```

Each fetcher prints absolute paths of newly-written raw files to stdout, one per line. Empty stdout means "nothing new."

## Cron contract — every fetcher must obey

- Exit 0 on success even when zero new items.
- Exit non-zero only on hard failure (network, auth, write).
- Be idempotent: dedup via `state/<kind>-seen.json`.
- Never overwrite or modify existing files in `raw_sources/`.
- Never block on stdin; never prompt.
