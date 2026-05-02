"""Thesis-writing context selector.

The thesis-writer agent is the first one in the pipeline that needs *judgment*,
not just classification. Its single biggest failure mode is being drowned in
noise: every claim, every event, every source for a ticker, plus theme/sector
context, plus existing thesis pages. Even a well-covered ticker has > 100kb of
prose if you naively concatenate everything reachable from its node.

This module does the graph walk *deterministically* in pure Python and emits a
single ``ThesisContext`` block. The agent then sees only a curated subgraph
plus instructions — no rummaging via Grep/Read for context, only for verification.

Layered selection (caps configurable, defaults match docs/gapanalises §3.2):

  L0  Company page                          (always, full)
  L1  Claims about ticker                   (cap 12, newest first)
  L2  Sources cited by L1 claims            (cap 8, KAP > news, then recency)
  L3  Sectors the company belongs to        (cap 2)
  L4  Themes the company is exposed to      (cap 4)
  L5  Risks the company is exposed to       (cap 5; usually inline today)
  L6  Catalysts that may benefit it         (cap 5; usually inline today)
  L7  Existing thesis pages                 (always; bull + bear if present)

Mechanical confidence (audited, deterministic) — see compute_confidence().
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI = REPO_ROOT / "wiki"

# ---------------------------------------------------------------------------
# Caps — tight enough to keep ~25k input tokens at the agent's prompt
# ---------------------------------------------------------------------------

CAP_CLAIMS = 12
CAP_SOURCES = 8
CAP_SECTORS = 2
CAP_THEMES = 4
CAP_RISKS = 5
CAP_CATALYSTS = 5

# Per-source body trimming — drop everything after Notes/caveats; we only need
# Provenance + Key facts to verify a quote.
SOURCE_KEEP_SECTIONS = ("## Provenance", "## Key facts", "## Entities mentioned")

# Per-sector / per-theme body trimming — keep the discriminating sections only.
SECTOR_KEEP_SECTIONS = ("## Members in universe", "## Drivers", "## Risks")
THEME_KEEP_SECTIONS = ("## What it is", "## Current state", "## Companies benefiting", "## Companies hurt")

CONFIDENCE_HIGH = 6
CONFIDENCE_MEDIUM = 3

# Refuse threshold — fewer than this many claims and we don't write a thesis.
MIN_CLAIMS_FOR_THESIS = 2

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]\|]+?)\]\]")
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")


# ---------------------------------------------------------------------------
# Frontmatter parser — small enough that pulling in PyYAML is overkill
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_without_frontmatter).

    Supports the subset our pages actually use: scalar strings/ints, ``[a, b, c]``
    inline lists, and quoted strings. Anything more exotic falls back to raw
    string. We never round-trip — read-only.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    out: dict = {}
    for raw_line in fm_text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
            out[key] = items
        elif value.startswith('"') and value.endswith('"'):
            out[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            out[key] = value[1:-1]
        else:
            out[key] = value
    return out, body


def _parse_iso_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _extract_section(body: str, header: str) -> str:
    """Return the body of a `## Section` block (header excluded), or '' if absent.

    A section runs from its header line up to the next `## ` header or EOF.
    """
    pattern = re.compile(
        rf"^{re.escape(header)}\s*\n(.*?)(?=^## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(body)
    return m.group(1).strip() if m else ""


def _keep_only_sections(body: str, headers: tuple[str, ...]) -> str:
    """Return a re-assembled body containing only the listed `## Section` blocks
    in their original order. Used to strip noisy boilerplate from sources/sectors/themes.
    """
    kept = []
    for h in headers:
        sect = _extract_section(body, h)
        if sect:
            kept.append(f"{h}\n\n{sect}")
    return "\n\n".join(kept).strip()


def _ticker_from_claim_filename(path: Path) -> str | None:
    """Claim filenames are kebab-case `<ticker-or-topic>-<rest>.md`.

    The first hyphen-separated token is the ticker for company-scoped claims
    (e.g. `eregl-q1-2026-...md` → EREGL). Topic-scoped claims (e.g.
    `turkey-cbrt-rates-...md`) won't match a real ticker — the caller filters
    using ``known_tickers`` so they're harmless.
    """
    head = path.stem.split("-", 1)[0]
    return head.upper() if head else None


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ClaimRef:
    slug: str
    path: Path
    statement: str
    sources: list[str]
    last_updated: date | None
    has_kap_source: bool
    has_contradictions: bool
    body: str

    def render(self) -> str:
        sources_inline = ", ".join(f"[[sources/{s}]]" for s in self.sources) or "(no sources)"
        date_str = self.last_updated.isoformat() if self.last_updated else "unknown"
        return (
            f"### [[claims/{self.slug}]] (updated {date_str})\n"
            f"Statement: {self.statement}\n"
            f"Sources: {sources_inline}\n"
            f"KAP-grade: {'yes' if self.has_kap_source else 'no'} · "
            f"Contradicted: {'yes' if self.has_contradictions else 'no'}\n"
        )


@dataclass
class SourceRef:
    slug: str
    path: Path
    source_kind: str
    source_subkind: str
    publisher: str
    published: date | None
    body_trimmed: str

    @property
    def kap_priority(self) -> int:
        """Higher = preferred when the cap forces us to drop sources."""
        if self.source_kind == "kap_filing":
            return 2
        if self.source_subkind in ("kap-financial-report", "kap-special-situation"):
            return 2
        return 1

    def render(self) -> str:
        date_str = self.published.isoformat() if self.published else "unknown"
        head = (
            f"### [[sources/{self.slug}]] — {self.publisher} ({self.source_kind}/{self.source_subkind}, {date_str})"
        )
        return f"{head}\n\n{self.body_trimmed}\n"


@dataclass
class EntityRef:
    """Generic page reference — used for sectors, themes, risks, catalysts."""
    kind: str  # "sectors" | "themes" | "risks" | "catalysts"
    slug: str
    path: Path
    body_trimmed: str

    def render(self) -> str:
        return f"### [[{self.kind}/{self.slug}]]\n\n{self.body_trimmed}\n"


@dataclass
class Confidence:
    rating: str  # "Low" | "Medium" | "High"
    score: int
    breakdown: dict[str, int]

    def render(self) -> str:
        parts = ", ".join(f"{k}={v}" for k, v in self.breakdown.items())
        return f"{self.rating} (score={self.score}; {parts})"


@dataclass
class ThesisContext:
    ticker: str
    company_name: str
    company_body: str
    claims: list[ClaimRef]
    sources: list[SourceRef]
    sectors: list[EntityRef]
    themes: list[EntityRef]
    risks: list[EntityRef]
    catalysts: list[EntityRef]
    inline_risks: str  # Raw text from company `## Exposure` `Risks:` line
    inline_catalysts: str  # Same for `Catalysts:` line
    bull_existing: str | None
    bear_existing: str | None
    confidence: Confidence
    refused: bool = False
    refusal_reason: str = ""
    today: date = field(default_factory=date.today)

    @property
    def claim_count(self) -> int:
        return len(self.claims)


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _select_claims(ticker: str, claims_dir: Path, today: date) -> list[ClaimRef]:
    out: list[ClaimRef] = []
    for path in sorted(claims_dir.glob("*.md")):
        # Cheap filter — the filename starts with the ticker, lowercased.
        head_ticker = _ticker_from_claim_filename(path)
        if head_ticker != ticker:
            continue
        text = _read_text(path)
        fm, body = _parse_frontmatter(text)
        statement = _extract_section(body, "## Statement").strip() or _first_h1(body)
        evidence = _extract_section(body, "## Evidence")
        contradicts = _extract_section(body, "## Contradicts")
        sources_list = fm.get("sources") or []
        if isinstance(sources_list, str):
            sources_list = [sources_list]
        # KAP detection — any cited source whose slug carries the marker.
        has_kap = any("kap" in s.lower() for s in sources_list)
        # "Has contradictions" — true only when the Contradicts section actually
        # links a contradicting claim or source. Placeholder bullets like
        # "- None identified." carry no wikilink; ignore them.
        has_contradictions = bool(_WIKILINK_RE.search(contradicts))
        last_updated = _parse_iso_date(fm.get("last_updated", ""))
        out.append(
            ClaimRef(
                slug=path.stem,
                path=path,
                statement=statement,
                sources=list(sources_list),
                last_updated=last_updated,
                has_kap_source=has_kap,
                has_contradictions=has_contradictions,
                body=body.strip(),
            )
        )
    # Newest first; unknown dates sink to the bottom.
    out.sort(
        key=lambda c: c.last_updated or date.min,
        reverse=True,
    )
    return out[:CAP_CLAIMS]


def _select_sources(claims: list[ClaimRef], sources_dir: Path) -> list[SourceRef]:
    seen: dict[str, SourceRef] = {}
    for c in claims:
        for slug in c.sources:
            if slug in seen:
                continue
            p = sources_dir / f"{slug}.md"
            if not p.exists():
                continue
            text = _read_text(p)
            fm, body = _parse_frontmatter(text)
            trimmed = _keep_only_sections(body, SOURCE_KEEP_SECTIONS) or body.strip()
            seen[slug] = SourceRef(
                slug=slug,
                path=p,
                source_kind=str(fm.get("source_kind", "")).strip() or "unknown",
                source_subkind=str(fm.get("source_subkind", "")).strip() or "",
                publisher=str(fm.get("source_publisher", "")).strip() or "unknown",
                published=_parse_iso_date(fm.get("source_date") or fm.get("published") or ""),
                body_trimmed=trimmed,
            )
    refs = list(seen.values())
    # KAP first; then newest; then alpha.
    refs.sort(
        key=lambda s: (s.kap_priority, s.published or date.min, s.slug),
        reverse=True,
    )
    return refs[:CAP_SOURCES]


def _wikilink_targets(body: str, prefix: str) -> list[str]:
    """Return slugs from `[[<prefix>/<slug>]]` references, in order, deduped."""
    seen: list[str] = []
    for m in _WIKILINK_RE.finditer(body):
        target = m.group(1)
        if target.startswith(f"{prefix}/"):
            slug = target[len(prefix) + 1 :].strip()
            if slug and slug not in seen:
                seen.append(slug)
    return seen


def _load_entity(kind: str, slug: str, base_dir: Path, keep_sections: tuple[str, ...]) -> EntityRef | None:
    p = base_dir / f"{slug}.md"
    if not p.exists():
        return None
    text = _read_text(p)
    _, body = _parse_frontmatter(text)
    trimmed = _keep_only_sections(body, keep_sections) or body.strip()
    return EntityRef(kind=kind, slug=slug, path=p, body_trimmed=trimmed)


def _extract_inline_exposure_line(body: str, label: str) -> str:
    """Pull the bullet `Risks: ...` or `Catalysts: ...` from the `## Exposure` section.

    Returns the text after the colon, or '' if absent. Used because most companies
    today list risks/catalysts as inline prose, not [[risks/<slug>]] wikilinks.
    """
    exposure = _extract_section(body, "## Exposure")
    if not exposure:
        return ""
    pattern = re.compile(rf"^[-*]\s*{re.escape(label)}\s*:\s*(.+)$", re.MULTILINE)
    m = pattern.search(exposure)
    return m.group(1).strip() if m else ""


def _first_h1(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""


# ---------------------------------------------------------------------------
# Confidence — mechanical, KAP-weighted, 4-factor (per design lock-in)
# ---------------------------------------------------------------------------


def compute_confidence(claims: list[ClaimRef], today: date) -> Confidence:
    n_claims = len(claims)
    n_kap = sum(1 for c in claims if c.has_kap_source)
    n_contradictions = sum(1 for c in claims if c.has_contradictions)
    n_stale = sum(
        1 for c in claims
        if c.last_updated is not None and (today - c.last_updated).days > 60
    )
    score = n_claims + 2 * n_kap - 2 * n_contradictions - n_stale
    if score >= CONFIDENCE_HIGH:
        rating = "High"
    elif score >= CONFIDENCE_MEDIUM:
        rating = "Medium"
    else:
        rating = "Low"
    return Confidence(
        rating=rating,
        score=score,
        breakdown={
            "claims": n_claims,
            "kap_cited": n_kap,
            "contradictions": n_contradictions,
            "stale_60d": n_stale,
        },
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(ticker: str, *, today: date | None = None, wiki_root: Path | None = None) -> ThesisContext:
    """Build a ThesisContext for a ticker.

    ``today`` is injectable for deterministic tests. ``wiki_root`` lets tests
    point at a fixture tree.
    """
    today = today or date.today()
    wiki = wiki_root or WIKI
    ticker = ticker.upper()
    company_path = wiki / "companies" / f"{ticker}.md"
    if not company_path.exists():
        return ThesisContext(
            ticker=ticker,
            company_name="",
            company_body="",
            claims=[],
            sources=[],
            sectors=[],
            themes=[],
            risks=[],
            catalysts=[],
            inline_risks="",
            inline_catalysts="",
            bull_existing=None,
            bear_existing=None,
            confidence=Confidence(rating="Low", score=0, breakdown={}),
            refused=True,
            refusal_reason=f"No company page at wiki/companies/{ticker}.md",
            today=today,
        )

    company_text = _read_text(company_path)
    company_fm, company_body = _parse_frontmatter(company_text)
    company_name = _first_h1(company_body) or ticker

    claims = _select_claims(ticker, wiki / "claims", today)
    sources = _select_sources(claims, wiki / "sources")

    # Sectors — frontmatter sector + body wikilinks.
    sector_slugs: list[str] = []
    fm_sector = str(company_fm.get("sector") or "").strip()
    if fm_sector:
        sector_slugs.append(fm_sector.lower())
    for slug in _wikilink_targets(company_body, "sectors"):
        if slug not in sector_slugs:
            sector_slugs.append(slug)
    sectors_dir = wiki / "sectors"
    sectors = [
        e
        for slug in sector_slugs[:CAP_SECTORS]
        if (e := _load_entity("sectors", slug, sectors_dir, SECTOR_KEEP_SECTIONS)) is not None
    ]

    theme_slugs = _wikilink_targets(company_body, "themes")[:CAP_THEMES]
    themes_dir = wiki / "themes"
    themes = [
        e
        for slug in theme_slugs
        if (e := _load_entity("themes", slug, themes_dir, THEME_KEEP_SECTIONS)) is not None
    ]

    risk_slugs = _wikilink_targets(company_body, "risks")[:CAP_RISKS]
    risks_dir = wiki / "risks"
    risks = [
        e
        for slug in risk_slugs
        if (e := _load_entity("risks", slug, risks_dir, ())) is not None
    ]

    catalyst_slugs = _wikilink_targets(company_body, "catalysts")[:CAP_CATALYSTS]
    catalysts_dir = wiki / "catalysts"
    catalysts = [
        e
        for slug in catalyst_slugs
        if (e := _load_entity("catalysts", slug, catalysts_dir, ())) is not None
    ]

    inline_risks = _extract_inline_exposure_line(company_body, "Risks")
    inline_catalysts = _extract_inline_exposure_line(company_body, "Catalysts")

    bull_path = wiki / "theses" / f"{ticker}-bull.md"
    bear_path = wiki / "theses" / f"{ticker}-bear.md"
    bull_existing = _read_text(bull_path) if bull_path.exists() else None
    bear_existing = _read_text(bear_path) if bear_path.exists() else None

    confidence = compute_confidence(claims, today)

    refused = len(claims) < MIN_CLAIMS_FOR_THESIS
    refusal_reason = (
        f"Only {len(claims)} claim(s) for {ticker}; below minimum {MIN_CLAIMS_FOR_THESIS}. "
        "More evidence needed before drafting a thesis."
        if refused else ""
    )

    return ThesisContext(
        ticker=ticker,
        company_name=company_name,
        company_body=company_body.strip(),
        claims=claims,
        sources=sources,
        sectors=sectors,
        themes=themes,
        risks=risks,
        catalysts=catalysts,
        inline_risks=inline_risks,
        inline_catalysts=inline_catalysts,
        bull_existing=bull_existing,
        bear_existing=bear_existing,
        confidence=confidence,
        refused=refused,
        refusal_reason=refusal_reason,
        today=today,
    )


# ---------------------------------------------------------------------------
# Rendering — produce the prompt block the agent actually receives
# ---------------------------------------------------------------------------


_SIDE_FRAMING = {
    "bull": (
        "You are arguing the strongest plausible BULL case for this company "
        "given the evidence below. Cite every assertion via [[claims/...]] or "
        "[[sources/...]]. Be specific. Avoid generic optimism."
    ),
    "bear": (
        "You are arguing the strongest plausible BEAR case for this company "
        "given the evidence below. Cite every assertion via [[claims/...]] or "
        "[[sources/...]]. Be specific. Avoid generic pessimism."
    ),
}


def render_user_prompt(ctx: ThesisContext, side: str) -> str:
    """Render the per-side user prompt that the orchestrator sends to the agent.

    `side` is `"bull"` or `"bear"`. The system prompt comes from
    `.claude/agents/thesis-writer.md` — this is *only* the user message.
    """
    if side not in _SIDE_FRAMING:
        raise ValueError(f"side must be 'bull' or 'bear', got {side!r}")

    framing = _SIDE_FRAMING[side]
    out_path = f"wiki/theses/{ctx.ticker}-{side}.md"

    parts: list[str] = []
    parts.append(framing)
    parts.append("")
    parts.append(f"Ticker: {ctx.ticker} ({ctx.company_name})")
    parts.append(f"Today: {ctx.today.isoformat()}")
    parts.append(f"Output file: {out_path}")
    parts.append(f"Mechanical confidence (do not override): {ctx.confidence.render()}")
    parts.append("")
    parts.append("---")
    parts.append("## Company page (current state)")
    parts.append("")
    parts.append(ctx.company_body)
    parts.append("")

    parts.append("---")
    parts.append(f"## Claims ({len(ctx.claims)} selected, newest first)")
    parts.append("")
    if ctx.claims:
        for c in ctx.claims:
            parts.append(c.render())
    else:
        parts.append("_No claims found._")
    parts.append("")

    parts.append("---")
    parts.append(f"## Cited sources ({len(ctx.sources)})")
    parts.append("")
    if ctx.sources:
        for s in ctx.sources:
            parts.append(s.render())
    else:
        parts.append("_No sources resolved._")
    parts.append("")

    if ctx.sectors:
        parts.append("---")
        parts.append(f"## Sector context ({len(ctx.sectors)})")
        parts.append("")
        for e in ctx.sectors:
            parts.append(e.render())
        parts.append("")

    if ctx.themes:
        parts.append("---")
        parts.append(f"## Theme / macro context ({len(ctx.themes)})")
        parts.append("")
        for e in ctx.themes:
            parts.append(e.render())
        parts.append("")

    if ctx.risks or ctx.inline_risks:
        parts.append("---")
        parts.append("## Risks")
        parts.append("")
        if ctx.risks:
            for e in ctx.risks:
                parts.append(e.render())
        if ctx.inline_risks:
            parts.append(f"_Inline (no dedicated page yet):_ {ctx.inline_risks}")
        parts.append("")

    if ctx.catalysts or ctx.inline_catalysts:
        parts.append("---")
        parts.append("## Catalysts")
        parts.append("")
        if ctx.catalysts:
            for e in ctx.catalysts:
                parts.append(e.render())
        if ctx.inline_catalysts:
            parts.append(f"_Inline (no dedicated page yet):_ {ctx.inline_catalysts}")
        parts.append("")

    parts.append("---")
    parts.append("## Existing thesis pages")
    parts.append("")
    other_side = "bear" if side == "bull" else "bull"
    same_existing = ctx.bull_existing if side == "bull" else ctx.bear_existing
    other_existing = ctx.bear_existing if side == "bull" else ctx.bull_existing
    if same_existing:
        parts.append(f"### Prior {side} thesis (you are revising this)")
        parts.append("")
        parts.append(same_existing.strip())
        parts.append("")
    else:
        parts.append(f"_No prior {side} thesis exists. You are writing the first version._")
        parts.append("")
    if other_existing:
        parts.append(f"### Current {other_side} thesis (for tension awareness — do NOT edit)")
        parts.append("")
        parts.append(other_existing.strip())
        parts.append("")

    parts.append("---")
    parts.append("## Your task")
    parts.append("")
    parts.append(
        f"Write `{out_path}` from `templates/thesis.md`. The thesis must:\n"
        f"  - Cite supporting [[claims/...]] for every assertion in the Narrative.\n"
        f"  - Use the mechanical confidence rating exactly as given above.\n"
        f"  - Set `last_updated: {ctx.today.isoformat()}` in frontmatter.\n"
        f"  - Populate `sources:` frontmatter with the slugs of the claims' sources actually used.\n"
        f"  - List concrete observable evidence in `## What would invalidate it`.\n"
        f"  - If a named risk or catalyst belongs in this thesis but no `wiki/risks/<slug>.md` "
        f"or `wiki/catalysts/<slug>.md` page exists yet, mint a stub from the matching template "
        f"before linking to it. Stubs may be sparse but must cite at least one source.\n"
        f"  - Emit a `THESIS SUMMARY` block at the end of your response (see system prompt)."
    )
    parts.append("")

    return "\n".join(parts)
