# TradingView News API — Unofficial Reference

Reverse‑engineered from the public `news-mediator.tradingview.com` host that powers
`https://www.tradingview.com/news-flow/`. No authentication is required for the
non‑pro feed; everything is plain HTTPS GET.

> Probed on 2026‑04‑28 against the live endpoint. Schemas come from the
> `public/news-flow/v1/meta` endpoint (the same the web client calls).
> Field set may evolve.

---

## Endpoints

| Purpose                    | Method | URL |
|----------------------------|--------|-----|
| **Filter catalog (meta)**  | GET    | `https://news-mediator.tradingview.com/public/news-flow/v1/meta` |
| **News list**              | GET    | `https://news-mediator.tradingview.com/news-flow/v2/news` |
| **News list (public)**     | GET    | `https://news-mediator.tradingview.com/public/news-flow/v2/news` |
| **Story detail**           | GET    | `https://news-mediator.tradingview.com/public/news/v1/story` |

The `/news-flow/v2/news` and `/public/news-flow/v2/news` variants take identical
parameters; the `public/` one omits the cookie‑auth path used by signed‑in users.

---

## Common query parameters (list endpoint)

| Param            | Required | Notes |
|------------------|----------|-------|
| `filter`         | repeated | One `filter=key:value` per facet. **Filters MUST be sorted alphabetically by key.** Unknown keys are silently ignored. |
| `client`         | yes      | Always seen as `screener` from the web UI. |
| `streaming`      | no       | `true` to hint long‑poll mode. The HTTP response is still a single JSON document. |
| `user_prostatus` | yes      | `non_pro` for guests, `pro` (or `pro_premium`) when authenticated. Some filters are gated on this. |
| `pub_usage`      | no       | Comma‑joined list — internal usage telemetry, optional. |

### Filter syntax

A single filter is `filter=<id>:<value>`. To pass multiple values for one facet,
join with a comma: `filter=<id>:<v1>,<v2>,<v3>`. **Both the filter list and the
values within a multi‑value filter must be sorted alphabetically** — otherwise
the server returns `HTTP 400`:

```
{"status":"error","message":"Bad Request: incorrect order of filters: filters must be sorted"}
{"status":"error","message":"... filter values must be sorted"}
```

URL‑encode the colon (`%3A`) and the comma (`%2C`).

### Worked example

Request: English‑language news, related to either Reuters or Dow Jones, from
the Turkish market only:

```
GET https://news-mediator.tradingview.com/news-flow/v2/news
    ?filter=lang%3Aen
    &filter=market_country%3ATR
    &filter=provider%3Adow-jones%2Creuters
    &client=screener
    &streaming=true
    &user_prostatus=non_pro
```

Filter keys appear in alphabetical order: `lang` → `market_country` → `provider`.
Within `provider`, values are alphabetically sorted: `dow-jones,reuters`.

---

## Filter catalog

10 filters, taken verbatim from the meta endpoint.

### `lang` — Language *(required, single‑select)*

Defaults to `en`. Returned titles are localized in this language.

| ID | Title |
|----|-------|
| `en` | English |
| `en_IN` | English (India) |
| `ru` | Русский |
| `zh-Hant` | 繁體中文 |
| `zh-Hans` | 简体中文 |
| `ar` | العربية |
| `he` | עברית |
| `ko` | 한국어 |
| `ja` | 日本語 |
| `vi` | Tiếng Việt |
| `th` | ภาษาไทย |
| `ms` | Bahasa Melayu |
| `id` | Bahasa Indonesia |
| `pt` | Português |
| `tr` | Türkçe |
| `pl` | Polski |
| `it` | Italiano |
| `es` | Español |
| `fr` | Français |
| `de` | Deutsch |

### `market` — Market *(multi‑select)*

| ID | Title |
|----|-------|
| `stock` | Stocks |
| `etf` | ETFs |
| `crypto` | Crypto |
| `forex` | Forex |
| `index` | Indices |
| `futures` | Futures |
| `bond` | Government bonds |
| `corp_bond` | Corporate bonds |
| `economic` | Economy |

### `market_country` — Country *(multi‑select, dynamic)*

Server‑side type is `country`; values are not enumerated by the meta endpoint.
Use **ISO 3166‑1 alpha‑2** codes (`US`, `TR`, `JP`, `DE`, `GB`, `IN`, `CN`,
`BR`, …). Verified examples: `TR` and `JP` both return news items.

### `symbol` — Instrument *(multi‑select, dynamic)*

Free‑form symbols in `EXCHANGE:TICKER` form, e.g. `BIST:THYAO`,
`NASDAQ:AAPL`, `BINANCE:BTCUSDT`, `TVC:GOLD`, `FX:EURUSD`. The same encoding
TradingView uses everywhere else.

### `watchlist` — Watchlist *(single‑select, auth required)*

Server‑side type is `watchlist`. Used to scope news to a saved watchlist; only
meaningful when the request is authenticated.

### `sector` — Sector *(multi‑select)*

GICS‑style 21 sectors. Values are the human‑readable strings — keep the spaces
and the case.

| ID |
|----|
| `Commercial Services` |
| `Communications` |
| `Consumer Durables` |
| `Consumer Non-Durables` |
| `Consumer Services` |
| `Distribution Services` |
| `Electronic Technology` |
| `Energy Minerals` |
| `Finance` |
| `Government` |
| `Health Services` |
| `Health Technology` |
| `Industrial Services` |
| `Miscellaneous` |
| `Non-Energy Minerals` |
| `Process Industries` |
| `Producer Manufacturing` |
| `Retail Trade` |
| `Technology Services` |
| `Transportation` |
| `Utilities` |

### `corp_activity` — Corporate activity *(multi‑select)*

| ID | Title |
|----|-------|
| `ipo` | IPOs |
| `earnings` | Earnings |
| `earnings_calls` | Earnings calls |
| `dividends` | Dividends |
| `share_buybacks` | Share buybacks |
| `strategy_business_products` | Strategy, business, and products |
| `mergers_and_acquisitions` | Mergers and acquisitions |
| `management` | Management |
| `insider_trading` | Insider trading |
| `ownership_changes` | Ownership changes |
| `esg` | ESG and regulation |
| `recommendation` | Analysts |
| `credit_ratings` | Credit ratings |

### `economic_category` — Economics *(multi‑select)*

| ID | Title |
|----|-------|
| `gdp` | GDP |
| `labor` | Labor |
| `prices` | Prices |
| `health` | Health |
| `money` | Money |
| `trade` | Trade |
| `government` | Government |
| `business` | Business |
| `consumer` | Consumer |
| `housing` | Housing |
| `taxes` | Taxes |

### `priority` — Format *(multi‑select)*

Tags applied to specific newswire formats, useful to surface only fast‑moving
items.

| ID | Title |
|----|-------|
| `flash` | Flash |
| `important` | Important |
| `top_stories` | Top stories |
| `key_facts` | Key facts |

### `provider` — Provider *(multi‑select, 52 sources)*

| ID | Title |
|----|-------|
| `reuters` | Reuters |
| `dow-jones` | Dow Jones Newswires |
| `market-watch` | MarketWatch |
| `trading-economics` | Trading Economics |
| `sharecast` | ShareCast |
| `dpa_afx` | dpa-AFX |
| `macenews` | Mace News |
| `tradingview` | TradingView |
| `marketbeat` | MarketBeat |
| `barchart` | Barchart |
| `cointelegraph` | Cointelegraph |
| `cme_group` | CME Group |
| `quartr` | Quartr |
| `quartr_insights` | Quartr Insights |
| `beincrypto` | Beincrypto |
| `newsbtc` | NewsBTC |
| `zacks` | Zacks |
| `stockstory` | Stock Story |
| `marketindex` | Market Index |
| `99Bitcoins` | 99Bitcoins |
| `acceswire` | Access Newswire |
| `acn` | Asian Corporate Newswire |
| `bravenewcoin` | Brave New Coin |
| `chainwire` | Chainwire |
| `coindar` | Coindar |
| `coinmarketcal` | CoinMarketCal |
| `coinpedia` | Coinpedia |
| `cryptobriefing` | Crypto Briefing |
| `cryptonews` | CryptoNews |
| `eqs` | EQS |
| `etfcom` | etf.com |
| `financemagnates` | Finance Magnates |
| `financewire` | FinanceWire |
| `forexlive` | InvestingLive |
| `globenewswire` | GlobeNewswire |
| `gurufocus` | GuruFocus |
| `investorplace` | InvestorPlace |
| `invezz` | Invezz |
| `jcn` | Japan Corporate News |
| `leverage_shares` | Leverage Shares |
| `miranda_partners` | Miranda Partners |
| `modular_finance` | MFN by Modular Finance |
| `moneycontrol` | Moneycontrol |
| `nbd` | National Bank Of Denmark |
| `tmx_newsfile` | TMX Newsfile |
| `pressetext` | pressetext |
| `smallcaps` | Small Caps |
| `stocktwits` | Stocktwits |
| `the_block` | The Block |
| `thenewswire` | The newswire.ca |
| `u_today` | U.Today |
| `zawya` | Zawya |

---

## List response schema

```jsonc
{
  "items": [
    {
      "id": "tag:reuters.com,2026:newsml_L8N40T0V8:0",
      "title": "Turkish Airlines replaces CEO and chairman ...",
      "published": 1775826314,            // unix seconds
      "urgency": 2,                        // 1 = flash, 2 = standard, 3 = lower
      "permission": "headline",            // "headline" | "provider" | absent
      "link": "https://...",               // when provider supplies external URL
      "relatedSymbols": [
        { "symbol": "BIST:THYAO", "logoid": "turk-hava-yollari" }
      ],
      "storyPath": "/news/<id>-slug/",
      "provider": {
        "id": "reuters",
        "name": "Reuters",
        "logo_id": "reuters"
      }
    }
  ]
}
```

`permission` values:
- `headline` — title only via the list endpoint; the body is gated to
  authenticated users via the story endpoint.
- `provider` — full content available; some providers (Dow Jones, ShareCast,
  …) license headline‑plus‑body to non‑pro readers.
- *(absent)* — same as `provider` for free items (Quartr summaries, etc.).

A list response usually contains up to 200 items per call. There is no `next`
cursor in the public response; the web UI re‑queries with narrower filters or
opens the SSE channel implied by `streaming=true`.

---

## Story detail endpoint

```
GET https://news-mediator.tradingview.com/public/news/v1/story
    ?id=<URL-encoded item.id>
    &lang=en
    &user_prostatus=non_pro
```

The `id` value carries colons and commas, so it **must** be percent‑encoded.

Response (selected fields):

```jsonc
{
  "id": "tag:reuters.com,2026:newsml_L6N419030:0",
  "title": "...",
  "short_description": "...",              // text excerpt
  "ast_description": {                      // structured body
    "type": "root",
    "children": [
      { "type": "p", "children": ["..."] },
      { "type": "news-image", "params": { "image": { "id": "...", "alt": "...", ... } } },
      ...
    ]
  },
  "language": "en",
  "tags": [
    { "title": "GDP", "args": [ { "id": "economic_category", "value": "gdp" } ] },
    { "title": "Reuters", "args": [ { "id": "provider", "value": "reuters" } ] }
  ],
  "copyright": "...",
  "published": 1777381275,
  "urgency": 2,
  "permission": "headline",
  "story_path": "/news/...slug/",
  "read_time": 162,                         // seconds
  "provider": { "id": "reuters", "name": "Reuters", "logo_id": "reuters" },
  "distributor": { "id": "refinitiv", "name": "Refinitiv", "logo_id": "refinitiv" }
}
```

The `ast_description` tree is what TradingView renders in its story view. Node
`type`s observed: `root`, `p`, `news-image`, plus inline mark types (`b`, `i`,
`a`) inside `children`.

---

## Meta endpoint

```
GET https://news-mediator.tradingview.com/public/news-flow/v1/meta
    ?lang=en
    &user_prostatus=non_pro
```

Returns the canonical filter catalog used in this document, plus:

| Field | Meaning |
|-------|---------|
| `multiplication_factor` | Used by the UI for rate scaling; observed value `5000000`. |
| `alerts_limits` | News‑alerts caps: `{ default: 1, pro: 10 }`. |

Each filter object contains:

```jsonc
{
  "id": "provider",
  "type": "list",            // list | symbol | country | watchlist
  "title": "Provider",
  "description": "Provider",
  "allow_multiselect": true,
  "constraints": {
    "default": null,
    "required": false,
    "values": [ { "id": "reuters", "title": "Reuters" }, ... ],
    "available": { "with_any": [ { "filter_id": "...", "value_id": "..." } ] },
    "blocked_by": [ { "filter_id": "...", "reason": "..." } ]
  }
}
```

`available.with_any` and `blocked_by` describe inter‑filter dependencies (a
filter that only unlocks when another is set, or that blocks another when set).
Both are empty for guest sessions in the current catalog.

---

## Common errors

| HTTP | Body | Cause |
|------|------|-------|
| 400  | `incorrect order of filters: filters must be sorted` | `filter=` keys not in alphabetical order |
| 400  | `filter values must be sorted`                       | comma‑joined values not alphabetical |
| 400  | `incorrect filter structure: filter '<id>' has invalid values` | unknown value for an enumerated filter |

Unknown filter keys are silently dropped (no error).

---

## Quick recipes

**Latest English headlines, all providers**
```
filter=lang:en
```

**Crypto news from a specific country**
```
filter=lang:en & filter=market:crypto & filter=market_country:US
```

**Reuters + Dow Jones flashes only**
```
filter=lang:en & filter=priority:flash & filter=provider:dow-jones,reuters
```

**Earnings news for one symbol**
```
filter=corp_activity:earnings & filter=lang:en & filter=symbol:NASDAQ:AAPL
```

**US economic prints**
```
filter=economic_category:gdp,labor,prices & filter=lang:en & filter=market:economic & filter=market_country:US
```
