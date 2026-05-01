"""Verify the subagent prompt loader strips frontmatter cleanly and finds both agents."""

from __future__ import annotations

from cli.agent import prompts


def test_graph_ingestor_loads():
    body = prompts.load_subagent_prompt("graph-ingestor")
    assert not body.startswith("---")
    assert "bistValult graph ingestor" in body
    assert "INGEST SUMMARY" in body


def test_compactor_loads():
    body = prompts.load_subagent_prompt("compactor")
    assert not body.startswith("---")
    assert "bistValult compactor" in body
    assert "COMPACT SUMMARY" in body
