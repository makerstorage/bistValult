"""Tests for cli/lib/thesis_context.py.

We use a temp wiki tree built from minimal fixtures so the tests are
deterministic and decoupled from whatever's currently in the live wiki.
The shapes mirror real pages (verified against wiki/companies/EREGL.md and
wiki/claims/eregl-*.md).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cli.lib import thesis_context


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _wiki(tmp_path: Path) -> Path:
    """Make an empty wiki/ tree and return its root."""
    root = tmp_path / "wiki"
    for sub in ("companies", "claims", "sources", "sectors", "themes", "risks", "catalysts", "theses"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _company(wiki: Path, ticker: str, *, sector: str = "Steel", sectors: list[str] = ("steel",), themes: list[str] = ("domestic-demand", "exports"), inline_risks: str = "Global steel price volatility; high CapEx cycle.", inline_catalysts: str = "Strong domestic demand.") -> None:
    sect_links = ", ".join(f"[[sectors/{s}]]" for s in sectors)
    theme_links = ", ".join(f"[[themes/{t}]]" for t in themes)
    body = f"""---
type: company
ticker: {ticker}
sector: {sector}
last_updated: 2026-04-30
sources: []
tags: [company]
---

# {ticker} — Test Company

## Snapshot

- **Sector:** {sect_links}

## Exposure

- Macro factors: {theme_links}
- Risks: {inline_risks}
- Catalysts: {inline_catalysts}

## Theses

- Bull: Not available
- Bear: Not available
"""
    _write(wiki / "companies" / f"{ticker}.md", body)


def _claim(wiki: Path, slug: str, *, sources: list[str], statement: str, last_updated: str = "2026-04-30", contradicts: str = "None identified.") -> None:
    sources_inline = ", ".join(sources)
    body = f"""---
type: claim
last_updated: {last_updated}
sources: [{sources_inline}]
tags: [claim]
---

# Claim: {statement}

## Statement

{statement}

## Evidence

- [[sources/{sources[0]}]] — supporting evidence.

## Contradicts

- {contradicts}

## Confidence

Medium — test fixture.

## Status

Active — test.
"""
    _write(wiki / "claims" / f"{slug}.md", body)


def _source(wiki: Path, slug: str, *, kind: str = "news", subkind: str = "market-news", date_str: str = "2026-04-29", publisher: str = "Reuters") -> None:
    body = f"""---
type: source
last_updated: 2026-04-30
source_date: {date_str}
source_kind: {kind}
source_subkind: {subkind}
source_publisher: {publisher}
tags: [source]
---

# {slug}

## Provenance

- Publisher: {publisher}

## Key facts

- Some fact.

## Notes / caveats

- Caveat noise — should be trimmed out.
"""
    _write(wiki / "sources" / f"{slug}.md", body)


def _sector(wiki: Path, slug: str) -> None:
    body = f"""---
type: sector
last_updated: 2026-04-30
sources: []
tags: [sector]
---

# {slug.title()}

## Members in universe

- [[companies/EREGL]]

## Drivers

- Demand.

## Risks

- Volatility.

## Open questions

- Should be trimmed (not in keep list).
"""
    _write(wiki / "sectors" / f"{slug}.md", body)


def _theme(wiki: Path, slug: str) -> None:
    body = f"""---
type: theme
last_updated: 2026-04-30
sources: []
tags: [theme]
---

# {slug.title()}

## What it is

A macro driver.

## Current state

Trending.

## Companies benefiting

- [[companies/EREGL]]

## Companies hurt

- _None._

## Open questions

- Trimmed.
"""
    _write(wiki / "themes" / f"{slug}.md", body)


# ---------------------------------------------------------------------------
# Build()
# ---------------------------------------------------------------------------


def test_build_refuses_when_no_company_page(tmp_path):
    wiki = _wiki(tmp_path)
    ctx = thesis_context.build("NOPE", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.refused is True
    assert "No company page" in ctx.refusal_reason
    assert ctx.claims == []


def test_build_refuses_when_thin_evidence(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "2026-04-29-reuters-eregl-q1")
    _claim(
        wiki,
        "eregl-q1-2026-domestic-demand",
        sources=["2026-04-29-reuters-eregl-q1"],
        statement="EREGL hit 96% capacity utilization in Q1 2026.",
    )
    # 1 claim < MIN_CLAIMS_FOR_THESIS (2)
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.refused is True
    assert "below minimum" in ctx.refusal_reason
    assert ctx.claim_count == 1


def test_build_collects_claims_and_sources(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    for n in range(3):
        _source(wiki, f"2026-04-{29 - n:02d}-reuters-eregl-{n}")
        _claim(
            wiki,
            f"eregl-claim-{n}",
            sources=[f"2026-04-{29 - n:02d}-reuters-eregl-{n}"],
            statement=f"Statement {n}.",
            last_updated=f"2026-04-{30 - n:02d}",
        )
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.refused is False
    assert ctx.claim_count == 3
    # Sorted newest first
    assert [c.slug for c in ctx.claims] == ["eregl-claim-0", "eregl-claim-1", "eregl-claim-2"]
    # Sources resolved & deduped
    assert len(ctx.sources) == 3
    # Source body trimmed: "Notes / caveats" stripped, "Key facts" kept
    s0 = ctx.sources[0]
    assert "## Key facts" in s0.body_trimmed
    assert "Notes / caveats" not in s0.body_trimmed


def test_build_filters_other_tickers_claims(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    _source(wiki, "src-2")
    _claim(wiki, "eregl-claim-a", sources=["src-1"], statement="EREGL fact.")
    _claim(wiki, "eregl-claim-b", sources=["src-2"], statement="EREGL fact 2.")
    # Foreign claims should not slip in even though they share the sources/ folder.
    _claim(wiki, "thyao-foreign", sources=["src-1"], statement="THYAO fact.")
    _claim(wiki, "turkey-cbrt-rate", sources=["src-1"], statement="Turkey macro.")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.claim_count == 2
    assert {c.slug for c in ctx.claims} == {"eregl-claim-a", "eregl-claim-b"}


def test_build_caps_at_max(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    for n in range(20):
        _claim(
            wiki,
            f"eregl-claim-{n:02d}",
            sources=["src-1"],
            statement=f"Statement {n}.",
            last_updated=f"2026-04-{(n % 28) + 1:02d}",
        )
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.claim_count == thesis_context.CAP_CLAIMS  # 12


def test_build_loads_sectors_and_themes(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL", sectors=["steel"], themes=["domestic-demand", "exports"])
    _source(wiki, "src-1")
    for n in range(2):
        _claim(wiki, f"eregl-c-{n}", sources=["src-1"], statement=f"S{n}.")
    _sector(wiki, "steel")
    _theme(wiki, "domestic-demand")
    _theme(wiki, "exports")

    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert [s.slug for s in ctx.sectors] == ["steel"]
    assert [t.slug for t in ctx.themes] == ["domestic-demand", "exports"]
    # Body trimmed: Open questions stripped from sector
    assert "## Open questions" not in ctx.sectors[0].body_trimmed
    assert "## Members in universe" in ctx.sectors[0].body_trimmed


def test_build_extracts_inline_risks_and_catalysts(tmp_path):
    wiki = _wiki(tmp_path)
    _company(
        wiki,
        "EREGL",
        inline_risks="FX exposure; energy cost surge.",
        inline_catalysts="Q2 EBITDA/ton uplift; export pricing.",
    )
    _source(wiki, "src-1")
    for n in range(2):
        _claim(wiki, f"eregl-c-{n}", sources=["src-1"], statement=f"S{n}.")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.inline_risks == "FX exposure; energy cost surge."
    assert ctx.inline_catalysts == "Q2 EBITDA/ton uplift; export pricing."


def test_build_existing_theses_are_loaded(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    for n in range(2):
        _claim(wiki, f"eregl-c-{n}", sources=["src-1"], statement=f"S{n}.")
    _write(wiki / "theses" / "EREGL-bull.md", "# bull placeholder\nold version body")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.bull_existing is not None
    assert "old version body" in ctx.bull_existing
    assert ctx.bear_existing is None


# ---------------------------------------------------------------------------
# Source ranking — KAP > news; recency tie-break
# ---------------------------------------------------------------------------


def test_sources_kap_priority_outranks_recent_news(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "2026-04-29-reuters-eregl", kind="news")
    _source(
        wiki,
        "2026-04-15-kap-eregl-fr",
        kind="kap_filing",
        subkind="kap-financial-report",
        date_str="2026-04-15",
        publisher="KAP",
    )
    _claim(wiki, "eregl-c-1", sources=["2026-04-29-reuters-eregl"], statement="A.")
    _claim(wiki, "eregl-c-2", sources=["2026-04-15-kap-eregl-fr"], statement="B.")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert ctx.sources[0].slug == "2026-04-15-kap-eregl-fr"


def test_sources_capped(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    for n in range(15):
        _source(wiki, f"src-{n:02d}", date_str=f"2026-04-{(n % 28) + 1:02d}")
        _claim(wiki, f"eregl-c-{n}", sources=[f"src-{n:02d}"], statement=f"S{n}.")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    assert len(ctx.sources) == thesis_context.CAP_SOURCES  # 8


# ---------------------------------------------------------------------------
# Confidence — KAP-weighted, 4-factor
# ---------------------------------------------------------------------------


def _make_claim(*, sources=("src",), kap=False, contradictions=False, last_updated="2026-04-30"):
    return thesis_context.ClaimRef(
        slug="x",
        path=Path("/tmp/x"),
        statement="x",
        sources=list(sources),
        last_updated=date.fromisoformat(last_updated),
        has_kap_source=kap,
        has_contradictions=contradictions,
        body="",
    )


def test_confidence_low_when_few_claims():
    today = date(2026, 5, 2)
    claims = [_make_claim(), _make_claim()]  # score = 2
    c = thesis_context.compute_confidence(claims, today)
    assert c.rating == "Low"
    assert c.score == 2


def test_confidence_medium_three_news_claims():
    today = date(2026, 5, 2)
    claims = [_make_claim() for _ in range(3)]  # score = 3
    c = thesis_context.compute_confidence(claims, today)
    assert c.rating == "Medium"
    assert c.score == 3


def test_confidence_high_kap_boost():
    today = date(2026, 5, 2)
    # 2 KAP-cited claims: score = 2 + 2*2 = 6 → High
    claims = [_make_claim(kap=True), _make_claim(kap=True)]
    c = thesis_context.compute_confidence(claims, today)
    assert c.rating == "High"
    assert c.score == 6
    assert c.breakdown["kap_cited"] == 2


def test_claim_contradiction_detection_ignores_placeholder(tmp_path):
    """Claim files whose `## Contradicts` is just `- None identified.` should
    not flip the contradiction flag — only a wikilink to a claim/source counts."""
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    _claim(
        wiki,
        "eregl-claim-placeholder",
        sources=["src-1"],
        statement="Placeholder claim.",
        contradicts="None identified.",  # the live convention
    )
    _claim(
        wiki,
        "eregl-claim-real-contradiction",
        sources=["src-1"],
        statement="Contradicted claim.",
        contradicts="[[claims/eregl-claim-placeholder]] — disagrees on capacity utilization.",
    )
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    by_slug = {c.slug: c for c in ctx.claims}
    assert by_slug["eregl-claim-placeholder"].has_contradictions is False
    assert by_slug["eregl-claim-real-contradiction"].has_contradictions is True


def test_confidence_penalised_by_contradictions():
    today = date(2026, 5, 2)
    # 4 claims, 2 contradicted: score = 4 - 2*2 = 0 → Low
    claims = [
        _make_claim(),
        _make_claim(),
        _make_claim(contradictions=True),
        _make_claim(contradictions=True),
    ]
    c = thesis_context.compute_confidence(claims, today)
    assert c.rating == "Low"
    assert c.score == 0


def test_confidence_penalised_by_stale():
    today = date(2026, 5, 2)
    # 5 claims; 3 of them > 60 days old. Score = 5 - 3 = 2 → Low
    claims = [
        _make_claim(last_updated="2026-04-30"),
        _make_claim(last_updated="2026-04-20"),
        _make_claim(last_updated="2026-01-01"),  # 121 d
        _make_claim(last_updated="2026-01-15"),  # 107 d
        _make_claim(last_updated="2026-02-01"),  # 90 d
    ]
    c = thesis_context.compute_confidence(claims, today)
    assert c.breakdown["stale_60d"] == 3
    assert c.score == 2
    assert c.rating == "Low"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_user_prompt_includes_all_sections(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    _claim(wiki, "eregl-c-1", sources=["src-1"], statement="A.")
    _claim(wiki, "eregl-c-2", sources=["src-1"], statement="B.")
    _sector(wiki, "steel")
    _theme(wiki, "domestic-demand")
    _theme(wiki, "exports")

    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    bull_prompt = thesis_context.render_user_prompt(ctx, "bull")
    bear_prompt = thesis_context.render_user_prompt(ctx, "bear")

    assert "BULL case" in bull_prompt
    assert "BEAR case" in bear_prompt
    assert "wiki/theses/EREGL-bull.md" in bull_prompt
    assert "wiki/theses/EREGL-bear.md" in bear_prompt
    assert "## Claims (2 selected" in bull_prompt
    assert "## Cited sources (1)" in bull_prompt
    assert "[[claims/eregl-c-1]]" in bull_prompt
    assert "## Sector context" in bull_prompt
    assert "## Theme / macro context" in bull_prompt
    # Mechanical confidence is rendered, not LLM-judged
    assert "Mechanical confidence (do not override): Low" in bull_prompt


def test_render_user_prompt_invalid_side(tmp_path):
    wiki = _wiki(tmp_path)
    _company(wiki, "EREGL")
    _source(wiki, "src-1")
    _claim(wiki, "eregl-c-1", sources=["src-1"], statement="A.")
    _claim(wiki, "eregl-c-2", sources=["src-1"], statement="B.")
    ctx = thesis_context.build("EREGL", wiki_root=wiki, today=date(2026, 5, 2))
    with pytest.raises(ValueError, match="bull|bear"):
        thesis_context.render_user_prompt(ctx, "neutral")
