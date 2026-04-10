"""Unit tests for memex/cli.py — embedding text, excerpt extraction, index, and query."""
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from memex.cli import (
    _extract_md_section,
    build_embed_text,
    extract_excerpt,
    extract_title,
    cli,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_MD = """\
---
title: "Use Redis for caching"
date: 2026-04-01
author: "alice"
source: "https://github.com/acme/repo/pull/42"
confidence: 0.85
tags: []
---

# Use Redis for caching

## Context

The team needed a fast in-memory store for session data. PostgreSQL was being hit on
every request, causing latency spikes during peak traffic.

## Decision

Use Redis as an in-memory cache layer between the application and PostgreSQL.

## Alternatives considered

- Memcached — ruled out because team has no experience with it
- In-process LRU cache — doesn't work across multiple app instances

## Constraints

- Redis must be deployed as a separate service
- Cache invalidation must be handled explicitly

## Revisit signals

_None_

---

_Extracted by Memex from [PR #42](https://github.com/acme/repo/pull/42) · 2026-04-01_
"""

LOW_CONF_MD = """\
---
title: "Low confidence record"
date: 2026-04-01
author: "memex-init"
source: "pyproject.toml"
confidence: 0.50
tags: ["init"]
---

# Low confidence record

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Some brief context here about the decision.

## Decision

A decision was made about the system.

## Alternatives considered

_None recorded_

## Constraints

_None recorded_

## Revisit signals

_None_

---

_Extracted by Memex from repo scan · 2026-04-01_
"""

NO_SECTIONS_MD = """\
---
title: "Hand-written note"
date: 2026-04-01
author: "bob"
source: "https://github.com/acme/repo/pull/99"
confidence: 0.70
tags: []
---

This is a hand-written note with no standard sections.
It has some content but no ## headers.
"""


# ---------------------------------------------------------------------------
# _extract_md_section
# ---------------------------------------------------------------------------

class TestExtractMdSection:
    def test_extracts_section_body(self):
        result = _extract_md_section(FULL_MD, "Context")
        assert "PostgreSQL was being hit" in result
        assert "##" not in result

    def test_missing_section_returns_empty(self):
        result = _extract_md_section(FULL_MD, "Nonexistent")
        assert result == ""

    def test_case_insensitive(self):
        md = "## CONTEXT\nSome context here.\n## Decision\nA decision.\n"
        assert "Some context here." in _extract_md_section(md, "Context")

    def test_does_not_bleed_into_next_section(self):
        result = _extract_md_section(FULL_MD, "Context")
        assert "Use Redis as an in-memory" not in result  # that's in Decision

    def test_stops_at_horizontal_rule(self):
        result = _extract_md_section(FULL_MD, "Revisit signals")
        assert "_Extracted by Memex" not in result


# ---------------------------------------------------------------------------
# build_embed_text
# ---------------------------------------------------------------------------

class TestBuildEmbedText:
    def test_includes_title(self):
        result = build_embed_text(FULL_MD)
        assert "Use Redis for caching" in result

    def test_includes_context(self):
        result = build_embed_text(FULL_MD)
        assert "PostgreSQL was being hit" in result

    def test_includes_decision(self):
        result = build_embed_text(FULL_MD)
        assert "in-memory cache layer" in result

    def test_includes_alternatives(self):
        result = build_embed_text(FULL_MD)
        assert "Memcached" in result
        assert "In-process LRU cache" in result

    def test_includes_constraints(self):
        result = build_embed_text(FULL_MD)
        assert "Redis must be deployed" in result

    def test_strips_yaml_frontmatter(self):
        result = build_embed_text(FULL_MD)
        assert "confidence:" not in result
        assert "tags:" not in result
        assert "author:" not in result

    def test_strips_warning_block(self):
        result = build_embed_text(LOW_CONF_MD)
        assert "⚠️" not in result
        assert "limited rationale present" not in result

    def test_strips_footer(self):
        result = build_embed_text(FULL_MD)
        assert "_Extracted by Memex" not in result

    def test_no_markdown_headers(self):
        result = build_embed_text(FULL_MD)
        assert "## " not in result

    def test_skips_none_recorded_alternatives(self):
        result = build_embed_text(LOW_CONF_MD)
        assert "Alternatives:" not in result

    def test_skips_none_recorded_constraints(self):
        result = build_embed_text(LOW_CONF_MD)
        assert "Constraints:" not in result

    def test_fallback_on_no_sections(self):
        result = build_embed_text(NO_SECTIONS_MD)
        # Falls back to raw content — should at least contain the note text (case-preserved)
        assert "hand-written note" in result.lower()

    def test_alternatives_formatted_with_semicolons(self):
        result = build_embed_text(FULL_MD)
        assert "Alternatives: " in result
        # Both alternatives joined
        assert "Memcached" in result and "In-process" in result


# ---------------------------------------------------------------------------
# extract_excerpt
# ---------------------------------------------------------------------------

class TestExtractExcerpt:
    def test_returns_context_and_decision(self):
        result = extract_excerpt(FULL_MD)
        assert "PostgreSQL was being hit" in result  # from Context
        assert "in-memory cache layer" in result      # from Decision

    def test_skips_warning_block(self):
        result = extract_excerpt(LOW_CONF_MD)
        assert "⚠️" not in result
        assert "Low confidence" not in result

    def test_shows_actual_context_for_low_confidence(self):
        result = extract_excerpt(LOW_CONF_MD)
        assert "Some brief context here" in result

    def test_context_truncated_at_300_chars(self):
        long_context = "word " * 100  # 500 chars
        md = f"---\ntitle: t\n---\n## Context\n{long_context}\n## Decision\nFoo.\n"
        result = extract_excerpt(md)
        # Context portion is capped at 300 chars and ends with ellipsis
        assert "…" in result
        assert result.endswith("Foo.")  # decision shown in full
        # No mid-word cuts — the part before " — " ends cleanly
        context_part = result.split(" — ")[0]
        assert not context_part.rstrip("…").endswith(" ")

    def test_fallback_skips_blockquotes(self):
        md = "---\ntitle: t\n---\n\n> This is a blockquote\n\nActual content here.\n"
        result = extract_excerpt(md)
        assert "Actual content here." in result
        assert "blockquote" not in result

    def test_fallback_skips_headings(self):
        md = "---\ntitle: t\n---\n\n# Big heading\n\nReal content.\n"
        result = extract_excerpt(md)
        assert "Real content." in result
        assert "Big heading" not in result

    def test_context_only_when_no_decision_section(self):
        md = "---\ntitle: t\n---\n## Context\nOnly context here.\n"
        result = extract_excerpt(md)
        assert "Only context here." in result
        assert " — " not in result  # no decision separator


# ---------------------------------------------------------------------------
# index command — content_hash logic
# ---------------------------------------------------------------------------

class TestIndexCommand:
    def _make_knowledge_file(self, tmp_path: Path, name: str, content: str) -> Path:
        d = tmp_path / "knowledge" / "decisions"
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_text(content)
        return f

    def _index_path(self, tmp_path: Path) -> Path:
        return tmp_path / ".memex" / "index.json"

    def _run_index(self, tmp_path, monkeypatch, mock_embed=None):
        if mock_embed is None:
            mock_embed = MagicMock(return_value=[[0.1] * 384])
        monkeypatch.chdir(tmp_path)
        with patch("memex.cli.embed", mock_embed):
            runner = CliRunner()
            result = runner.invoke(cli, ["index"])
        return result, mock_embed

    def test_new_file_gets_content_hash(self, tmp_path, monkeypatch):
        self._make_knowledge_file(tmp_path, "record.md", FULL_MD)
        self._run_index(tmp_path, monkeypatch)
        index = json.loads(self._index_path(tmp_path).read_text())
        entry = list(index.values())[0]
        assert "content_hash" in entry
        assert len(entry["content_hash"]) == 64  # SHA256 hex

    def test_unchanged_file_not_reembedded(self, tmp_path, monkeypatch):
        self._make_knowledge_file(tmp_path, "record.md", FULL_MD)
        _, mock_embed = self._run_index(tmp_path, monkeypatch)
        assert mock_embed.call_count == 1
        # Second run — should skip
        _, mock_embed2 = self._run_index(tmp_path, monkeypatch)
        assert mock_embed2.call_count == 0

    def test_changed_file_gets_reembedded(self, tmp_path, monkeypatch):
        f = self._make_knowledge_file(tmp_path, "record.md", FULL_MD)
        self._run_index(tmp_path, monkeypatch)
        # Mutate the file
        f.write_text(FULL_MD.replace("PostgreSQL was being hit", "MySQL was being hit"))
        _, mock_embed2 = self._run_index(tmp_path, monkeypatch)
        assert mock_embed2.call_count == 1

    def test_legacy_entry_without_hash_gets_reembedded(self, tmp_path, monkeypatch):
        f = self._make_knowledge_file(tmp_path, "record.md", FULL_MD)
        # Pre-populate index without content_hash (legacy format)
        index_path = self._index_path(tmp_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps({
            str(f): {
                "embedding": [0.1] * 384,
                "title": "Use Redis for caching",
                "excerpt": "old excerpt",
                "confidence": 0.85,
                "path": str(f),
                # no content_hash
            }
        }))
        monkeypatch.chdir(tmp_path)
        mock_embed = MagicMock(return_value=[[0.2] * 384])
        with patch("memex.cli.embed", mock_embed):
            CliRunner().invoke(cli, ["index"])
        assert mock_embed.call_count == 1

    def test_deleted_record_removed_from_index(self, tmp_path, monkeypatch):
        f1 = self._make_knowledge_file(tmp_path, "record1.md", FULL_MD)
        f2 = self._make_knowledge_file(tmp_path, "record2.md", LOW_CONF_MD)
        mock_embed = MagicMock(side_effect=lambda texts: [[0.1] * 384] * len(texts))
        self._run_index(tmp_path, monkeypatch, mock_embed)
        # Delete one file
        f2.unlink()
        self._run_index(tmp_path, monkeypatch)
        index = json.loads(self._index_path(tmp_path).read_text())
        # Index stores paths relative to cwd (tmp_path)
        rel_f1 = str(f1.relative_to(tmp_path))
        rel_f2 = str(f2.relative_to(tmp_path))
        assert rel_f2 not in index
        assert rel_f1 in index

    def test_embed_receives_clean_text_not_yaml(self, tmp_path, monkeypatch):
        self._make_knowledge_file(tmp_path, "record.md", FULL_MD)
        captured = []

        def mock_embed(texts):
            captured.extend(texts)
            return [[0.1] * 384] * len(texts)

        monkeypatch.chdir(tmp_path)
        with patch("memex.cli.embed", mock_embed):
            CliRunner().invoke(cli, ["index"])

        assert captured, "embed was not called"
        embedded_text = captured[0]
        assert "confidence:" not in embedded_text
        assert "tags:" not in embedded_text
        assert "⚠️" not in embedded_text


# ---------------------------------------------------------------------------
# query command — --min-score
# ---------------------------------------------------------------------------

def _make_index_entry(title: str, score_hint: float, path: str = "knowledge/decisions/test.md"):
    """Make a fake index entry with a fixed embedding (we'll mock cosine_similarity)."""
    return {
        "embedding": [score_hint],  # mock will use actual cosine_similarity override
        "title": title,
        "excerpt": f"Excerpt for {title}",
        "confidence": 0.85,
        "path": path,
    }


class TestQueryMinScore:
    def _run_query(self, tmp_path, monkeypatch, index_data: dict, args: list[str]):
        index_path = tmp_path / ".memex" / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index_data))
        monkeypatch.chdir(tmp_path)

        # Mock embed to return a fixed vector, mock cosine_similarity to return
        # the embedding value directly as the score
        def mock_embed(texts):
            return [[0.5] * 1] * len(texts)

        def mock_cosine(a, b):
            return b[0]  # score encoded in the entry's embedding

        with patch("memex.cli.embed", mock_embed), \
             patch("memex.cli.cosine_similarity", mock_cosine):
            runner = CliRunner()
            result = runner.invoke(cli, ["query"] + args)
        return result

    def test_filters_result_below_min_score(self, tmp_path, monkeypatch):
        index_data = {
            "k/a.md": {**_make_index_entry("Irrelevant result", 0.0), "embedding": [0.60]},
        }
        result = self._run_query(tmp_path, monkeypatch, index_data,
                                 ["some", "query", "--min-score", "0.70"])
        assert "No relevant results found" in result.output

    def test_shows_result_above_min_score(self, tmp_path, monkeypatch):
        index_data = {
            "k/a.md": {**_make_index_entry("Good result", 0.0), "embedding": [0.80]},
        }
        result = self._run_query(tmp_path, monkeypatch, index_data,
                                 ["some", "query", "--min-score", "0.70"])
        assert "Good result" in result.output

    def test_no_results_message_contains_threshold(self, tmp_path, monkeypatch):
        index_data = {
            "k/a.md": {**_make_index_entry("Low match", 0.0), "embedding": [0.50]},
        }
        result = self._run_query(tmp_path, monkeypatch, index_data,
                                 ["test", "--min-score", "0.80"])
        assert "0.80" in result.output

    def test_no_results_suggests_lower_score(self, tmp_path, monkeypatch):
        index_data = {
            "k/a.md": {**_make_index_entry("Low match", 0.0), "embedding": [0.50]},
        }
        result = self._run_query(tmp_path, monkeypatch, index_data,
                                 ["test", "--min-score", "0.80"])
        assert "--min-score 0.6" in result.output

    def test_top_option_respected_after_filter(self, tmp_path, monkeypatch):
        index_data = {f"k/{i}.md": {**_make_index_entry(f"Result {i}", 0.0), "embedding": [0.90]}
                      for i in range(5)}
        result = self._run_query(tmp_path, monkeypatch, index_data,
                                 ["test", "--min-score", "0.0", "--top", "2"])
        # Only 2 results should be shown
        assert result.output.count("#1") == 1
        assert result.output.count("#2") == 1
        assert "#3" not in result.output

    def test_default_min_score_is_070(self, tmp_path, monkeypatch):
        # Result at 0.69 should be hidden by default
        index_data = {
            "k/a.md": {**_make_index_entry("Borderline", 0.0), "embedding": [0.69]},
        }
        result = self._run_query(tmp_path, monkeypatch, index_data, ["test"])
        assert "No relevant results found" in result.output


# ---------------------------------------------------------------------------
# query command — --expand
# ---------------------------------------------------------------------------

class TestQueryExpand:
    def _run_query_with_expand(self, tmp_path, monkeypatch, expanded_text: str, args: list[str]):
        index_path = tmp_path / ".memex" / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_data = {
            "k/a.md": {**_make_index_entry("Some result", 0.0), "embedding": [0.80]},
        }
        index_path.write_text(json.dumps(index_data))
        monkeypatch.chdir(tmp_path)

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=expanded_text)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        captured_embed_args = []

        def mock_embed(texts):
            captured_embed_args.extend(texts)
            return [[0.5]] * len(texts)

        def mock_cosine(a, b):
            return b[0]

        with patch("memex.cli.embed", mock_embed), \
             patch("memex.cli.cosine_similarity", mock_cosine), \
             patch("memex.cli._anthropic_client", return_value=mock_client):
            runner = CliRunner()
            result = runner.invoke(cli, ["query"] + args)

        return result, mock_client, captured_embed_args

    def test_expand_calls_haiku(self, tmp_path, monkeypatch):
        _, mock_client, _ = self._run_query_with_expand(
            tmp_path, monkeypatch, "expanded terms", ["test query", "--expand"]
        )
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"

    def test_expand_passes_expanded_text_to_embed(self, tmp_path, monkeypatch):
        _, _, captured = self._run_query_with_expand(
            tmp_path, monkeypatch, "rich expanded search terms", ["original query", "--expand"]
        )
        assert captured[0] == "rich expanded search terms"

    def test_expand_fallback_on_empty_response(self, tmp_path, monkeypatch):
        _, _, captured = self._run_query_with_expand(
            tmp_path, monkeypatch, "", ["original query", "--expand"]
        )
        assert captured[0] == "original query"

    def test_no_expand_skips_anthropic_client(self, tmp_path, monkeypatch):
        index_path = tmp_path / ".memex" / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_data = {
            "k/a.md": {**_make_index_entry("Result", 0.0), "embedding": [0.80]},
        }
        index_path.write_text(json.dumps(index_data))
        monkeypatch.chdir(tmp_path)

        with patch("memex.cli.embed", return_value=[[0.5]]), \
             patch("memex.cli.cosine_similarity", lambda a, b: b[0]), \
             patch("memex.cli._anthropic_client") as mock_factory:
            CliRunner().invoke(cli, ["query", "test"])

        mock_factory.assert_not_called()
