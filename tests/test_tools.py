"""Unit tests for the agent tool surface — path allow-list enforcement,
edit_file uniqueness semantics, grep pattern-less listing.

These tests do NOT require an API key — they exercise tool implementations
directly against a temp wiki/ tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.agent import tools


@pytest.fixture
def wiki_file(monkeypatch, tmp_path):
    """Repoint REPO_ROOT and the allow-lists at a tmp dir, then create a sample wiki file."""
    wiki = tmp_path / "wiki"
    (wiki / "sources").mkdir(parents=True)
    (wiki / "claims").mkdir()
    (wiki / "companies").mkdir()
    (tmp_path / "raw_sources").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "templates").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# placeholder\n", encoding="utf-8")

    monkeypatch.setattr(tools, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        tools,
        "READ_ROOTS",
        (
            tmp_path / "wiki",
            tmp_path / "raw_sources",
            tmp_path / "docs",
            tmp_path / "templates",
            tmp_path / ".claude",
            tmp_path / "CLAUDE.md",
        ),
    )
    monkeypatch.setattr(tools, "WRITE_ROOTS", (tmp_path / "wiki",))

    sample = wiki / "companies" / "TEST.md"
    sample.write_text("# TEST\n\nfoo bar baz\n", encoding="utf-8")
    return tmp_path, sample


def test_write_file_under_wiki(wiki_file):
    tmp_path, _ = wiki_file
    out = tools.write_file("wiki/sources/2026-05-01-x.md", "hello\n")
    assert out["bytes_written"] == 6
    assert (tmp_path / "wiki/sources/2026-05-01-x.md").read_text() == "hello\n"


def test_write_file_outside_wiki_rejected(wiki_file):
    with pytest.raises(tools.ToolError, match="outside wiki/"):
        tools.write_file("raw_sources/news/evil.md", "x")


def test_write_file_traversal_rejected(wiki_file):
    with pytest.raises(tools.ToolError, match="outside wiki/"):
        tools.write_file("wiki/../raw_sources/news/evil.md", "x")


def test_edit_file_unique_match(wiki_file):
    out = tools.edit_file("wiki/companies/TEST.md", "foo bar", "FOO BAR")
    assert out["replacements"] == 1


def test_edit_file_missing_old_string(wiki_file):
    with pytest.raises(tools.ToolError, match="not found"):
        tools.edit_file("wiki/companies/TEST.md", "nonexistent", "x")


def test_edit_file_ambiguous_match(wiki_file):
    _, sample = wiki_file
    sample.write_text("a\na\n", encoding="utf-8")
    with pytest.raises(tools.ToolError, match="matches 2 times"):
        tools.edit_file(str(sample), "a", "b")


def test_edit_file_replace_all(wiki_file):
    _, sample = wiki_file
    sample.write_text("a\na\n", encoding="utf-8")
    out = tools.edit_file(str(sample), "a", "b", replace_all=True)
    assert out["replacements"] == 2
    assert sample.read_text() == "b\nb\n"


def test_delete_only_whitelisted_paths(wiki_file):
    tmp_path, _ = wiki_file
    src = tmp_path / "wiki/sources/2026-05-01-x.md"
    src.write_text("x", encoding="utf-8")
    out = tools.delete_file("wiki/sources/2026-05-01-x.md")
    assert out["deleted"] is True
    assert not src.exists()


def test_delete_company_page_rejected(wiki_file):
    with pytest.raises(tools.ToolError, match="Refusing to delete"):
        tools.delete_file("wiki/companies/TEST.md")


def test_delete_missing_is_idempotent(wiki_file):
    out = tools.delete_file("wiki/sources/never-existed.md")
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


def test_grep_files_with_matches(wiki_file):
    tmp_path, _ = wiki_file
    (tmp_path / "wiki/sources/a.md").write_text("hello world\n", encoding="utf-8")
    (tmp_path / "wiki/sources/b.md").write_text("nothing here\n", encoding="utf-8")
    out = tools.grep("hello", "wiki/sources")
    assert any("a.md" in m for m in out["matches"])
    assert not any("b.md" in m for m in out["matches"])


def test_grep_pattern_less_listing(wiki_file):
    tmp_path, _ = wiki_file
    (tmp_path / "wiki/sources/a.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "wiki/sources/b.txt").write_text("x\n", encoding="utf-8")
    out = tools.grep("", "wiki/sources", glob="*.md")
    matches = "\n".join(out["matches"])
    assert "a.md" in matches
    assert "b.txt" not in matches


def test_dispatch_unknown_tool():
    raw = tools.dispatch("nope", {})
    parsed = json.loads(raw)
    assert parsed["ok"] is False
    assert "Unknown tool" in parsed["error"]
