# Architecture

Three layers — keep strictly separated.

## Layer 1: `raw_sources/` (immutable)

User-curated inputs. Read-only — never modify.

```
raw_sources/
  news/
  prices/
  financials/
  kap_filings/      # KAP = Kamuyu Aydınlatma Platformu (Turkish disclosure platform)
  analyst_notes/
  macro/
  sector_reports/
  company_meta/     # one <TICKER>.json per known company; seeded from sirketler.xlsx
```

If a raw file is wrong, the user replaces it.

## Layer 2: `wiki/` (LLM-owned, derived)

```
wiki/
  index.md          # navigational catalog of every page (one line per page)
  log.md            # chronological append-only record
  companies/        # one page per tracked ticker (THYAO.md, AKBNK.md, ...)
  sectors/          # banking, aviation, retail, defense, ...
  themes/           # macro factors: inflation, interest-rates, fx-risk, exports
  risks/            # named downside drivers: fuel-cost-risk, fx-debt-risk
  catalysts/        # named upside drivers: rate-cycle, tourism-season, earnings
  claims/           # discrete citable assertions (one per file)
  theses/           # bull/bear thesis pages per company
  decisions/        # dated investment assessments (snapshots in time)
  dashboards/       # bist30-overview, valuation-watchlist, risk-register
  sources/          # one summary page per ingested raw source
```

## Layer 3: `docs/` + `templates/` (configuration)

Operating manual and page skeletons. Co-evolved with the user as conventions emerge.

## File naming

- Companies: uppercase ticker — `THYAO.md`, `AKBNK.md`, `BIMAS.md`
- Everything else: kebab-case — `fuel-cost-risk.md`, `interest-rates.md`
- Source summaries: `<YYYY-MM-DD>-<slug>.md` — `2026-04-29-thyao-q1-results.md`
- Decision snapshots: `<TICKER>-<YYYY-MM-DD>.md` — `THYAO-2026-04-29.md`
