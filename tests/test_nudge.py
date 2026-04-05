"""Unit tests for memex/nudge.py."""
import json
import pytest
from unittest.mock import patch, MagicMock

from memex.nudge import (
    NUDGE_MARKER,
    NUDGE_COMMENT_BODY,
    NUDGE_THRESHOLD,
    should_nudge,
    get_pr_comments,
    has_nudge_comment,
    post_nudge_comment,
    is_bot_comment,
)
from memex.extractor import DISCARD_THRESHOLD


# --- should_nudge ---

def test_should_nudge_below_discard_threshold():
    assert should_nudge(DISCARD_THRESHOLD - 0.01) is False

def test_should_nudge_at_discard_threshold():
    assert should_nudge(DISCARD_THRESHOLD) is True

def test_should_nudge_in_range():
    assert should_nudge(0.55) is True

def test_should_nudge_at_medium_boundary():
    assert should_nudge(0.65) is True

def test_should_nudge_just_below_threshold():
    assert should_nudge(NUDGE_THRESHOLD - 0.01) is True

def test_should_nudge_at_nudge_threshold():
    assert should_nudge(NUDGE_THRESHOLD) is False

def test_should_nudge_high_confidence():
    assert should_nudge(0.92) is False


# --- get_pr_comments ---

def _make_subprocess_result(stdout: str, returncode: int = 0):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


def test_get_pr_comments_success():
    payload = json.dumps([{"body": "hello", "author": "user1"}])
    with patch("subprocess.run", return_value=_make_subprocess_result(payload)):
        comments = get_pr_comments("42", "acme/repo")
    assert comments == [{"body": "hello", "author": "user1"}]


def test_get_pr_comments_gh_failure():
    with patch("subprocess.run", return_value=_make_subprocess_result("", returncode=1)):
        comments = get_pr_comments("42", "acme/repo")
    assert comments == []


def test_get_pr_comments_exception():
    with patch("subprocess.run", side_effect=Exception("timeout")):
        comments = get_pr_comments("42", "acme/repo")
    assert comments == []


def test_get_pr_comments_empty_stdout():
    with patch("subprocess.run", return_value=_make_subprocess_result("")):
        comments = get_pr_comments("42", "acme/repo")
    assert comments == []


# --- has_nudge_comment ---

def test_has_nudge_comment_present():
    comments = [{"body": f"some text {NUDGE_MARKER}", "author": "memex-bot"}]
    with patch("memex.nudge.get_pr_comments", return_value=comments):
        assert has_nudge_comment("42", "acme/repo") is True


def test_has_nudge_comment_absent():
    comments = [{"body": "just a normal comment", "author": "user1"}]
    with patch("memex.nudge.get_pr_comments", return_value=comments):
        assert has_nudge_comment("42", "acme/repo") is False


def test_has_nudge_comment_no_comments():
    with patch("memex.nudge.get_pr_comments", return_value=[]):
        assert has_nudge_comment("42", "acme/repo") is False


def test_has_nudge_comment_gh_failure():
    with patch("memex.nudge.get_pr_comments", return_value=[]):
        assert has_nudge_comment("42", "acme/repo") is False


# --- post_nudge_comment ---

def test_post_nudge_comment_calls_gh():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        post_nudge_comment("42", "acme/repo")

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "gh" in call_args
    assert "pr" in call_args
    assert "comment" in call_args
    assert "42" in call_args
    assert "--repo" in call_args
    assert "acme/repo" in call_args
    assert "--body" in call_args
    body_idx = call_args.index("--body")
    assert NUDGE_MARKER in call_args[body_idx + 1]


# --- is_bot_comment ---

def test_is_bot_comment_memex_bot():
    assert is_bot_comment("memex-bot") is True

def test_is_bot_comment_github_actions():
    assert is_bot_comment("github-actions[bot]") is True

def test_is_bot_comment_dependabot():
    assert is_bot_comment("dependabot[bot]") is True

def test_is_bot_comment_human():
    assert is_bot_comment("srajan") is False

def test_is_bot_comment_empty():
    assert is_bot_comment("") is False
