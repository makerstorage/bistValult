"""Verify the SUMMARY_RE regex parses the exact block formats both subagent
prompts emit. Belt-and-braces — if either format ever drifts, this fails."""

from __future__ import annotations

from cli.agent.runner import SUMMARY_RE

INGEST_FIXTURE = """\
Some natural-language reasoning the model emitted before the block.

INGEST SUMMARY
  files processed:    3
  sources created:    3
  pages created:      2
  pages updated:      5
  claims minted:      1
  claims merged:      2
  contradictions:     0
  needs_review:       0
  skipped (existing): 0
"""

COMPACT_FIXTURE = """\
Wrap-up reasoning.

COMPACT SUMMARY
  sources pruned:         12
  sources protected:      3
  claims consolidated:    2
  redundant claims deleted: 2
  pages migrated:         0
  pages compacted:        4
  review flags:           0
"""

THESIS_FIXTURE = """\
Some narrative reasoning.

THESIS SUMMARY
  ticker:                EREGL
  side:                  bull
  thesis path:           wiki/theses/EREGL-bull.md
  thesis status:         created
  claims cited:          3
  sources cited:         2
  risks linked:          1
  risks minted:          1
  catalysts linked:      1
  catalysts minted:      0
  mechanical confidence: Low
  contradictions noted:  0
"""


def test_ingest_summary_extracts():
    m = SUMMARY_RE.search(INGEST_FIXTURE)
    assert m is not None
    block = m.group(0)
    assert block.startswith("INGEST SUMMARY")
    assert "files processed:    3" in block
    assert "skipped (existing): 0" in block


def test_compact_summary_extracts():
    m = SUMMARY_RE.search(COMPACT_FIXTURE)
    assert m is not None
    block = m.group(0)
    assert block.startswith("COMPACT SUMMARY")
    assert "sources pruned:         12" in block
    assert "review flags:           0" in block


def test_thesis_summary_extracts():
    m = SUMMARY_RE.search(THESIS_FIXTURE)
    assert m is not None
    block = m.group(0)
    assert block.startswith("THESIS SUMMARY")
    assert "ticker:                EREGL" in block
    assert "side:                  bull" in block
    assert "mechanical confidence: Low" in block


def test_no_summary_returns_none():
    assert SUMMARY_RE.search("model returned no summary block at all") is None
