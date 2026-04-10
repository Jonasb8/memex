"""Unit tests for memex/action.py nudge integration and issue_comment handling."""
import json
import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from memex.schema import KnowledgeRecord, ExtractionResult


def _make_record(confidence: float) -> KnowledgeRecord:
    return KnowledgeRecord(
        title="Switch event queue to Redis",
        context="SQS message size limit was being hit consistently.",
        decision="Switched event queue from SQS to Redis Streams.",
        confidence=confidence,
        confidence_rationale="Author explained the SQS size limitation clearly.",
    )


def _make_result(confidence: float) -> ExtractionResult:
    return ExtractionResult(
        contains_decision=True,
        record=_make_record(confidence),
    )


BASE_ENV = {
    "PR_TITLE": "Switch event queue to Redis",
    "PR_BODY": "We hit SQS limits.",
    "PR_URL": "https://github.com/acme/repo/pull/42",
    "PR_NUMBER": "42",
    "PR_AUTHOR": "srajan",
    "REPO": "acme/repo",
    "GH_TOKEN": "token",
    "ANTHROPIC_API_KEY": "key",
}


# --- get_review_comments ---

def _mock_run(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


def _is_reviews_call(cmd):
    return "--json" in cmd and "reviews" in cmd

def _is_inline_comments_call(cmd):
    return any("pulls" in arg for arg in cmd)

def _is_general_comments_call(cmd):
    return any("issues" in arg for arg in cmd)


class TestGetReviewComments:
    def test_combines_review_bodies_inline_and_general_comments(self):
        from memex.action import get_review_comments

        def fake_run(cmd, **kwargs):
            if _is_reviews_call(cmd):
                return _mock_run(json.dumps(["Top-level review body"]))
            if _is_inline_comments_call(cmd):
                return _mock_run(json.dumps(["Inline line comment"]))
            if _is_general_comments_call(cmd):
                return _mock_run(json.dumps(["General PR comment"]))
            return _mock_run("[]")

        with patch("memex.action.subprocess.run", side_effect=fake_run):
            result = get_review_comments("42", "acme/repo")

        assert result == ["Top-level review body", "Inline line comment", "General PR comment"]

    def test_filters_empty_strings(self):
        from memex.action import get_review_comments

        def fake_run(cmd, **kwargs):
            if _is_reviews_call(cmd):
                return _mock_run(json.dumps([""]))        # empty review body
            if _is_inline_comments_call(cmd):
                return _mock_run(json.dumps(["Inline comment"]))
            if _is_general_comments_call(cmd):
                return _mock_run(json.dumps([""]))        # empty general comment
            return _mock_run("[]")

        with patch("memex.action.subprocess.run", side_effect=fake_run):
            result = get_review_comments("42", "acme/repo")

        assert result == ["Inline comment"]

    def test_returns_empty_list_when_all_calls_fail(self):
        from memex.action import get_review_comments

        failing = _mock_run("", returncode=1)
        with patch("memex.action.subprocess.run", return_value=failing):
            result = get_review_comments("42", "acme/repo")

        assert result == []

    def test_partial_failure_returns_successful_sources(self):
        from memex.action import get_review_comments

        def fake_run(cmd, **kwargs):
            if _is_reviews_call(cmd):
                return _mock_run("", returncode=1)        # reviews call fails
            if _is_inline_comments_call(cmd):
                return _mock_run(json.dumps(["Inline comment"]))
            if _is_general_comments_call(cmd):
                return _mock_run(json.dumps(["General comment"]))
            return _mock_run("[]")

        with patch("memex.action.subprocess.run", side_effect=fake_run):
            result = get_review_comments("42", "acme/repo")

        assert result == ["Inline comment", "General comment"]


# --- handle_pr_merge: nudge logic ---

class TestHandlePrMergeNudge:
    def test_posts_nudge_on_medium_confidence(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=[]), \
             patch("memex.action.extract", return_value=_make_result(0.55)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")), \
             patch("memex.action.has_nudge_comment", return_value=False) as mock_has, \
             patch("memex.action.post_nudge_comment") as mock_post:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_post.assert_called_once_with("42", "acme/repo")

    def test_no_nudge_on_high_confidence(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=[]), \
             patch("memex.action.extract", return_value=_make_result(0.85)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")), \
             patch("memex.action.post_nudge_comment") as mock_post:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_post.assert_not_called()

    def test_no_nudge_if_already_posted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=[]), \
             patch("memex.action.extract", return_value=_make_result(0.55)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")), \
             patch("memex.action.has_nudge_comment", return_value=True), \
             patch("memex.action.post_nudge_comment") as mock_post:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_post.assert_not_called()

    def test_no_nudge_when_no_decision(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        no_decision = ExtractionResult(contains_decision=False, record=None)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=[]), \
             patch("memex.action.extract", return_value=no_decision), \
             patch("memex.action.post_nudge_comment") as mock_post:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_post.assert_not_called()

    def test_no_nudge_on_low_signal_pr(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=[]), \
             patch("memex.action.extract", return_value=None), \
             patch("memex.action.post_nudge_comment") as mock_post:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_post.assert_not_called()


# --- handle_issue_comment ---

COMMENT_ENV = {
    "PR_NUMBER": "42",
    "REPO": "acme/repo",
    "GH_TOKEN": "token",
    "ANTHROPIC_API_KEY": "key",
    "COMMENT_BODY": "We needed Redis consumer groups — SQS doesn't support exactly-once per tenant.",
    "COMMENT_AUTHOR": "srajan",
    "GITHUB_EVENT_NAME": "issue_comment",
}

PR_DATA = {
    "title": "Switch event queue to Redis",
    "body": "We hit SQS limits.",
    "url": "https://github.com/acme/repo/pull/42",
    "author": "srajan",
    "review_comments": [],
}


class TestHandleIssueComment:
    def test_skips_bot_author(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {**COMMENT_ENV, "COMMENT_AUTHOR": "memex-bot"}
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.extract") as mock_extract:
            from memex.action import handle_issue_comment
            handle_issue_comment()

        mock_extract.assert_not_called()

    def test_skips_without_prior_nudge_comment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in COMMENT_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.has_nudge_comment", return_value=False), \
             patch("memex.action.extract") as mock_extract:

            from memex.action import handle_issue_comment
            handle_issue_comment()

        mock_extract.assert_not_called()

    def test_re_extracts_with_reply_appended(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in COMMENT_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.has_nudge_comment", return_value=True), \
             patch("memex.action._fetch_pr_data", return_value=PR_DATA), \
             patch("memex.action.extract", return_value=_make_result(0.83)) as mock_extract, \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")):

            from memex.action import handle_issue_comment
            handle_issue_comment()

        mock_extract.assert_called_once()
        _, call_kwargs = mock_extract.call_args
        # extract is called positionally: extract(title, body, reviews)
        call_args = mock_extract.call_args[0]
        augmented_body = call_args[1]
        assert "## Author reply" in augmented_body
        assert COMMENT_ENV["COMMENT_BODY"] in augmented_body

    def test_re_extraction_writes_record(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in COMMENT_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.has_nudge_comment", return_value=True), \
             patch("memex.action._fetch_pr_data", return_value=PR_DATA), \
             patch("memex.action.extract", return_value=_make_result(0.83)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")) as mock_write:

            from memex.action import handle_issue_comment
            handle_issue_comment()

        mock_write.assert_called_once()
        _, kwargs = mock_write.call_args
        assert kwargs["pr_number"] == 42
        assert kwargs["repo"] == "acme/repo"

    def test_re_extraction_no_decision_skips_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for k, v in COMMENT_ENV.items():
            monkeypatch.setenv(k, v)

        no_decision = ExtractionResult(contains_decision=False, record=None)

        with patch("memex.action.has_nudge_comment", return_value=True), \
             patch("memex.action._fetch_pr_data", return_value=PR_DATA), \
             patch("memex.action.extract", return_value=no_decision), \
             patch("memex.action.write_record") as mock_write:

            from memex.action import handle_issue_comment
            handle_issue_comment()

        mock_write.assert_not_called()


# --- main dispatch ---

class TestMainDispatch:
    def test_dispatches_to_pr_merge(self, monkeypatch):
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        with patch("memex.action.handle_pr_merge") as mock_merge, \
             patch("memex.action.handle_issue_comment") as mock_comment:
            from memex.action import main
            main()
        mock_merge.assert_called_once()
        mock_comment.assert_not_called()

    def test_dispatches_to_issue_comment(self, monkeypatch):
        monkeypatch.setenv("GITHUB_EVENT_NAME", "issue_comment")
        with patch("memex.action.handle_pr_merge") as mock_merge, \
             patch("memex.action.handle_issue_comment") as mock_comment:
            from memex.action import main
            main()
        mock_comment.assert_called_once()
        mock_merge.assert_not_called()

    def test_defaults_to_pr_merge(self, monkeypatch):
        monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
        with patch("memex.action.handle_pr_merge") as mock_merge, \
             patch("memex.action.handle_issue_comment"):
            from memex.action import main
            main()
        mock_merge.assert_called_once()


# --- changed_files wiring ---

class TestChangedFilesWiring:
    def test_changed_files_passed_to_extract(self, tmp_path, monkeypatch):
        """changed_files from get_changed_files() should be forwarded to extract()."""
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        structural_files = ["migrations/001_add_sessions.py"]

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=structural_files), \
             patch("memex.action.extract", return_value=_make_result(0.85)) as mock_extract, \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")):

            from memex.action import handle_pr_merge
            handle_pr_merge()

        mock_extract.assert_called_once()
        assert mock_extract.call_args.kwargs.get("changed_files") == structural_files

    def test_structural_tags_written_for_migration_pr(self, tmp_path, monkeypatch):
        """Structural tags derived from changed_files should reach write_record."""
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=["migrations/001_add_sessions.py"]), \
             patch("memex.action.extract", return_value=_make_result(0.85)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")) as mock_write:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        _, kwargs = mock_write.call_args
        assert "migration" in (kwargs.get("tags") or [])

    def test_no_structural_tags_for_plain_pr(self, tmp_path, monkeypatch):
        """Non-structural files should produce no structural tags."""
        monkeypatch.chdir(tmp_path)
        for k, v in BASE_ENV.items():
            monkeypatch.setenv(k, v)

        with patch("memex.action.get_review_comments", return_value=[]), \
             patch("memex.action.get_changed_files", return_value=["src/auth.py", "tests/test_auth.py"]), \
             patch("memex.action.extract", return_value=_make_result(0.85)), \
             patch("memex.action.write_record", return_value=Path("knowledge/decisions/foo.md")) as mock_write:

            from memex.action import handle_pr_merge
            handle_pr_merge()

        _, kwargs = mock_write.call_args
        assert kwargs.get("tags") is None
