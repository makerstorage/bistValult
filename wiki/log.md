# Wiki log

Chronological, append-only. Newest at the bottom. Every entry starts with `## [YYYY-MM-DD] <type> | <title>` so it is greppable.

Types: `ingest`, `query`, `lint`, `decision`, `update`.

```bash
grep "^## \[" wiki/log.md | tail -10
```

---

## [2026-04-29] update | Wiki skeleton initialized

- Created directory structure: `raw_sources/`, `wiki/` (with companies, sectors, themes, risks, catalysts, claims, theses, decisions, dashboards, sources), `templates/`.
- Seeded `wiki/index.md`, `wiki/log.md`, three dashboard stubs, nine page templates.
- No data ingested yet.
## [2026-04-29] ingest | news (no new sources)

## [2026-04-30] ingest | news (25 sources)

- Sources: [[sources/2026-04-30-quartr-tknsa-revenue-up-3-and-ebitda-improved-but-net-loss-persists-af673dee]], [[sources/2026-04-29-quartr-ykbnk-q1-2026-net-profit-more-than-doubled-year-over-year-dr-b04d1b17]], [[sources/2026-04-29-quartr-eregl-strong-q1-results-with-rising-ebitda-per-ton-and-robus-829c608f]], [[sources/2026-04-29-reuters-cw-enerji-says-unit-signs-sales-agreements-worth-2-1-million-42222c30]], [[sources/2026-04-29-reuters-anadolu-efes-says-it-signs-toll-filling-agreement-for-local-9786cd60]], [[sources/2026-04-29-reuters-isdemir-q1-net-profit-up-at-1-5-bln-lira-yoy-0a7c1d34]], [[sources/2026-04-28-reuters-tumosan-says-its-operations-continue-uninterrupted-denies-pr-fc9abdd6]], [[sources/2026-04-28-reuters-astor-enerji-says-it-signs-51-5-million-power-transformer-de-665949e1]], [[sources/2026-04-28-reuters-europower-enerji-says-unit-wins-teias-tender-worth-331-3-mln-f863e6cc]], [[sources/2026-04-28-reuters-ahlatci-dogal-gaz-fy-net-profit-rises-to-2-9-bln-lira-yoy-be757f16]], [[sources/2026-04-28-reuters-enerya-enerji-fy-net-profit-up-at-4-7-bln-lira-yoy-302a5d7d]], [[sources/2026-04-28-reuters-afyon-cimento-q1-net-result-turns-to-loss-of-73-4-mln-lira-y-52626a50]], [[sources/2026-04-24-reuters-orge-elektrik-says-it-signs-contract-worth-286-1-million-lir-c1dc907e]], [[sources/2026-04-24-reuters-orge-enerji-says-it-sells-1-98-mln-shares-acquired-from-buyb-0fa42213]], [[sources/2026-04-24-reuters-borusan-mannesmann-boru-says-us-unit-receives-new-sales-orde-845f41b1]], [[sources/2026-04-24-reuters-europower-enerji-says-it-wins-ayedas-tender-worth-1-7-mln-5f315877]], [[sources/2026-04-24-reuters-europower-enerji-says-it-wins-tender-from-baskent-elektrik-c-dc800509]], [[sources/2026-04-24-reuters-akcansa-cimento-says-it-proposes-to-pay-cash-dividend-at-gro-42308c20]], [[sources/2026-04-24-reuters-celebi-hava-servisi-says-it-will-exit-tanzania-operations-af-0c9c4874]], [[sources/2026-04-23-reuters-ulusoy-un-fy-loss-shrinks-to-130-9-mln-lira-yoy-438c3960]], [[sources/2026-04-23-reuters-cw-enerji-q1-net-profit-up-at-737-7-mln-lira-yoy-348e4cd0]], [[sources/2026-04-22-reuters-efor-yatirim-sanayi-ticaret-says-mapeg-approves-exploration-631d922d]], [[sources/2026-04-22-reuters-torunlar-reit-says-it-proposes-to-pay-cash-dividend-at-gross-799e5840]], [[sources/2026-04-22-reuters-stocks-fx-dip-on-us-iran-ceasefire-uncertainty-focus-on-cenb-63df0012]], [[sources/2026-04-22-reuters-aydem-yenilebilir-enerji-appoints-ayca-akgun-kulak-as-financ-8f9c3997]]
- Pages created: [[companies/AEFES]], [[companies/AFYON]], [[companies/AHGAZ]], [[companies/ASTOR]], [[companies/AYDEM]], [[companies/BRSAN]], [[companies/CLEBI]], [[companies/CWENE]], [[companies/EFOR]], [[companies/ENERY]], [[companies/EREGL]], [[companies/EUPWR]], [[companies/ISDMR]], [[companies/ORGE]], [[companies/TMSN]], [[companies/TRGYO]], [[companies/ULUUN]], [[companies/YKBNK]], [[sectors/aviation]], [[sectors/steel]]
- Pages updated: [[companies/AKCNS]], [[companies/TKNSA]], [[sectors/banking]], [[sectors/construction-materials]], [[sectors/energy]], [[sectors/food]], [[sectors/industrials]], [[sectors/real-estate]], [[themes/domestic-demand]], [[themes/exports]], [[themes/FX]], [[themes/inflation]], [[themes/interest-rates]], [[themes/regulation]], [[themes/renewable-energy]], [[wiki/index.md]]
- New claims: [[claims/aefes-uzbekistan-expansion-q2-2026]], [[claims/afyon-q1-2026-swings-to-loss-despite-revenue-growth]], [[claims/ahgaz-fy2025-profit-growth]], [[claims/astor-us-export-deal-51m-2026]], [[claims/brsan-us-unit-strong-order-inflow-2026]], [[claims/clebi-tanzania-exit-immaterial-to-consolidated-results]], [[claims/cwene-q1-2026-net-profit-doubled-yoy]], [[claims/efor-seven-mining-exploration-licenses-approved]], [[claims/enery-fy2025-profit-growth]], [[claims/eregl-2026-capex-600m-guidance]], [[claims/eregl-q1-2026-strong-domestic-demand-high-utilization]], [[claims/isdmr-q1-2026-net-profit-50pct-yoy]], [[claims/tknsa-net-loss-persists-high-finance-costs-2026]], [[claims/turkey-cbrt-rates-held-37pct-amid-iran-war-uncertainty-2026-04]], [[claims/uluun-fy2025-loss-narrowing-trend]], [[claims/ykbnk-q1-2026-net-profit-surged-78pct-yoy]]
- Contradictions: none
- Needs review: 2026-04-30-quartr-tknsa-revenue-up-3-and-ebitda-improved-but-net-loss-persists-af673dee (Quartr AI-generated), 2026-04-29-quartr-ykbnk-q1-2026-net-profit-more-than-doubled-year-over-year-dr-b04d1b17 (Quartr AI-generated; headline/body inconsistency on profit growth magnitude), 2026-04-29-quartr-eregl-strong-q1-results-with-rising-ebitda-per-ton-and-robus-829c608f (Quartr AI-generated)
- Skipped (already ingested): none
