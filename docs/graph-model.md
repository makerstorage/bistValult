# Graph model

Wiki pages = graph nodes. Obsidian `[[wikilinks]]` = edges. Treat every edit as an addition or change to a graph.

## Node types

- **Company** — one per BIST 30 ticker
- **Sector** — banking, aviation, retail, defense, ...
- **Theme / MacroFactor** — inflation, interest rates, FX, oil prices, exports
- **Source** — summary of one raw input
- **Event** — discrete thing that happened (dividend, contract, regulatory action)
- **Metric** — financial line item (usually inside company page, not standalone)
- **Risk** — named downside driver
- **Catalyst** — named upside or thesis-changing driver
- **Claim** — discrete citable assertion
- **Thesis** — coherent bull or bear narrative for a company
- **Decision** — dated investment assessment, snapshot in time

## Core edges

```
Company   → belongs_to        → Sector
Company   → exposed_to        → Risk
Company   → benefits_from     → MacroFactor
Company   → hurt_by           → MacroFactor
Company   → reports           → Metric
Source    → supports          → Claim
Source    → contradicts       → Claim
Source    → updates           → Metric
Source    → describes         → Event
Event     → strengthens       → Thesis
Event     → weakens           → Thesis
Claim     → supports          → Thesis
Risk      → threatens         → Thesis
Catalyst  → may_change        → Thesis
Decision  → about             → Company
Decision  → based_on          → Thesis / Claim / Metric / Risk
Decision  → valid_until       → Date
```

## The reasoning chain

```
evidence  →  claim  →  thesis  →  decision
```

Don't shortcut it. A `decisions/` page should trace back through theses, supported by claims, sourced to raw files. Every link in the chain is a citable wiki page.

## Practical effect on edits

When ingesting a source, ask:

- Which existing claim(s) does this support or contradict?
- Which thesis is affected?
- Does it create a new Risk or Catalyst node?
- Does the company's decision page need updating, or expiring?

A single source typically touches 5–15 wiki pages.
