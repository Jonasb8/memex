"""Unit tests for memex/mcp_server.py — three MCP tools."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RECORD_A = {
    "embedding": [1.0, 0.0, 0.0],
    "title": "Migrate billing store to PostgreSQL",
    "excerpt": "Unbounded schema flexibility was causing silent data corruption.",
    "confidence": 0.92,
    "path": "knowledge/decisions/2024-11-14-migrate-billing.md",
    "content_hash": "abc123",
}

RECORD_B = {
    "embedding": [0.0, 1.0, 0.0],
    "title": "Switch event queue from SQS to Redis Streams",
    "excerpt": "SQS 256KB limit was consistently hit as event payloads grew.",
    "confidence": 0.45,  # low confidence
    "path": "knowledge/decisions/2024-09-01-switch-event-queue.md",
    "content_hash": "def456",
}

FIXTURE_INDEX = {
    RECORD_A["path"]: RECORD_A,
    RECORD_B["path"]: RECORD_B,
}

FULL_MARKDOWN = """\
---
title: "Migrate billing store to PostgreSQL"
date: 2024-11-14
author: "srajan"
source: "https://github.com/acme/api-core/pull/2847"
confidence: 0.92
tags: []
---

# Migrate billing store to PostgreSQL

## Context

The billing team hit repeated data integrity issues with MongoDB.

## Decision

Migrate the billing store to PostgreSQL.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_tools():
    """Import the three tool functions from mcp_server."""
    from memex.mcp_server import memex_query, memex_get_decision, memex_list_recent
    return memex_query, memex_get_decision, memex_list_recent


# ---------------------------------------------------------------------------
# memex_query
# ---------------------------------------------------------------------------

class TestMemexQuery:
    def test_returns_results_above_threshold(self):
        # query vector [1,0,0] is identical to RECORD_A — score should be 1.0
        memex_query, _, _ = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX), \
             patch("memex.mcp_server.embed", return_value=[[1.0, 0.0, 0.0]]):
            result = memex_query("why did we move off MongoDB")

        assert "Migrate billing store to PostgreSQL" in result
        assert "score 1.00" in result
        assert "knowledge/decisions/2024-11-14-migrate-billing.md" in result

    def test_low_confidence_surfaced(self):
        # query vector [0,1,0] matches RECORD_B (low confidence)
        memex_query, _, _ = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX), \
             patch("memex.mcp_server.embed", return_value=[[0.0, 1.0, 0.0]]):
            result = memex_query("event queue choice")

        assert "Switch event queue from SQS to Redis Streams" in result
        assert "limited rationale" in result  # confidence < 0.65 annotated

    def test_no_results_below_threshold(self):
        memex_query, _, _ = _import_tools()
        # query vector [0,0,1] has zero similarity to both records
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX), \
             patch("memex.mcp_server.embed", return_value=[[0.0, 0.0, 1.0]]):
            result = memex_query("unrelated question", min_score=0.5)

        assert "No results" in result

    def test_empty_index_returns_guidance(self):
        memex_query, _, _ = _import_tools()
        with patch("memex.mcp_server.load_index", return_value={}):
            result = memex_query("anything")

        assert "memex index" in result

    def test_top_n_limits_results(self):
        memex_query, _, _ = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX), \
             patch("memex.mcp_server.embed", return_value=[[1.0, 1.0, 0.0]]):
            result = memex_query("question", top=1, min_score=0.0)

        # Only one result should appear (the higher-scored one)
        assert result.count("\n   knowledge/") == 1


# ---------------------------------------------------------------------------
# memex_get_decision
# ---------------------------------------------------------------------------

class TestMemexGetDecision:
    def test_exact_path_match(self, tmp_path):
        md_file = tmp_path / "decision.md"
        md_file.write_text(FULL_MARKDOWN)
        memex_query, memex_get_decision, _ = _import_tools()

        with patch("memex.mcp_server.load_index", return_value={}):
            result = memex_get_decision(str(md_file))

        assert "Migrate billing store to PostgreSQL" in result

    def test_partial_path_match_from_index(self, tmp_path):
        md_file = tmp_path / "2024-11-14-migrate-billing.md"
        md_file.write_text(FULL_MARKDOWN)
        index = {str(md_file): {**RECORD_A, "path": str(md_file)}}
        _, memex_get_decision, _ = _import_tools()

        with patch("memex.mcp_server.load_index", return_value=index):
            result = memex_get_decision("migrate-billing")

        assert "Migrate billing store to PostgreSQL" in result

    def test_not_found_returns_guidance(self):
        _, memex_get_decision, _ = _import_tools()
        with patch("memex.mcp_server.load_index", return_value={}), \
             patch("memex.mcp_server.KNOWLEDGE_DIR", Path("/nonexistent")):
            result = memex_get_decision("nonexistent-slug-xyz")

        assert "No record found" in result
        assert "memex_query" in result


# ---------------------------------------------------------------------------
# memex_list_recent
# ---------------------------------------------------------------------------

class TestMemexListRecent:
    def test_lists_all_records_sorted_by_date(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent()

        # RECORD_A (2024-11-14) should appear before RECORD_B (2024-09-01)
        pos_a = result.index("Migrate billing")
        pos_b = result.index("Switch event queue")
        assert pos_a < pos_b

    def test_domain_filter_matches_title(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent(domain="billing")

        assert "Migrate billing store to PostgreSQL" in result
        assert "Switch event queue" not in result

    def test_domain_filter_matches_excerpt(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent(domain="SQS")

        assert "Switch event queue from SQS to Redis Streams" in result
        assert "Migrate billing" not in result

    def test_domain_no_match_returns_message(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent(domain="kubernetes")

        assert "No decisions found" in result

    def test_low_confidence_flagged(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent()

        # RECORD_B has confidence 0.45 — should show warning flag
        assert "⚠️" in result

    def test_limit_respected(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value=FIXTURE_INDEX):
            result = memex_list_recent(limit=1)

        # Only the most recent record should appear
        assert "Migrate billing store to PostgreSQL" in result
        assert "Switch event queue" not in result

    def test_empty_index_returns_guidance(self):
        _, _, memex_list_recent = _import_tools()
        with patch("memex.mcp_server.load_index", return_value={}):
            result = memex_list_recent()

        assert "memex index" in result
