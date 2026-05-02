# Wiki conventions

## YAML frontmatter

Every wiki page starts with frontmatter (Dataview-compatible):

```yaml
---
type: company | sector | theme | risk | catalyst | claim | thesis | decision | source
ticker: THYAO              # companies & decisions only
sector: Aviation           # companies only
last_updated: 2026-04-29
sources: [2026-04-29-thyao-q1-results, 2026-03-15-aviation-fuel-outlook]
tags: []
---
```

## Discipline rules — non-negotiable

1. **Cite every claim.** No assertion without a `[[sources/...]]` link. If you cannot cite it, mark `[unsourced]` and add to the page's "Open questions" section.
2. **Date every datum.** Prices, ratios, market cap, financial line items — all carry `YYYY-MM-DD`.
3. **Separate facts from interpretation.** Use distinct sections or `Fact:` / `Interpretation:` prefixes.
4. **Flag stale data.** Prepend `⚠️ Stale (as of YYYY-MM-DD):` if older than 30 days for prices/ratios or 90 days for financials.
5. **Track contradictions.** When a new source disagrees with an existing claim, do not silently overwrite. Add a `## Contradictions` section listing both with dates and source links.
6. **No hallucinated numbers.** Use `raw_sources/` or the `tvscreener` MCP. If unavailable, write "Not available" and add to "Open questions".
7. **Conservative language.** Prefer "appears", "suggests", "warrants further research" over "is" / "will".
8. **Market-data placement.** Live market data — price, volume, market cap, valuation ratios, performance % — lives **only on the company page** (`## Current snapshot` for fast-changing fields; `## Financials` for ratios). Never create a per-ticker per-day source page for market data. The canonical citation for all such data is `[[sources/tradingview-screener]]`.

## Log format

`wiki/log.md` entries start with `## [YYYY-MM-DD] <type> | <title>` so they're greppable:

```bash
grep "^## \[" wiki/log.md | tail -10
```

Types: `ingest`, `query`, `lint`, `decision`, `update`.

Example:

```markdown
## [2026-04-29] ingest | THYAO Q1 2026 results
- Source: [[sources/2026-04-29-thyao-q1-results]]
- Updated: [[companies/THYAO]], [[sectors/aviation]], [[themes/oil-prices]]
- New claims: [[claims/thyao-revenue-momentum-q1-2026]]
- Contradictions: none
```
