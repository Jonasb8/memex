"""Unit tests for memex/update.py."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import memex.update as upd
from memex.update import (
    CommitInfo,
    UpdateResult,
    _extract_pr_number,
    build_skip_sets,
    commit_url,
    detect_repo,
    git_diff,
    git_files_changed,
    git_log_since,
    load_state,
    save_state,
    _process_pr_commit,
    _process_direct_commit,
    run_update,
    MAX_FILES_CHANGED,
)
from memex.schema import KnowledgeRecord, ExtractionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(confidence: float = 0.85) -> KnowledgeRecord:
    return KnowledgeRecord(
        title="Switch queue to Redis",
        context="SQS limits were hit.",
        decision="Switched to Redis Streams.",
        confidence=confidence,
        confidence_rationale="Clear rationale.",
    )


def _make_extraction(confidence: float = 0.85) -> ExtractionResult:
    return ExtractionResult(contains_decision=True, record=_make_record(confidence))


def _no_decision() -> ExtractionResult:
    return ExtractionResult(contains_decision=False, record=None)


def _subprocess_result(stdout: str = "", returncode: int = 0):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    return r


# ---------------------------------------------------------------------------
# _extract_pr_number
# ---------------------------------------------------------------------------

def test_extract_pr_number_merge_message():
    assert _extract_pr_number("Merge pull request #123 from branch") == 123


def test_extract_pr_number_squash_message():
    assert _extract_pr_number("Feature: do something (#456)") == 456


def test_extract_pr_number_fix_message():
    assert _extract_pr_number("fix: whatever (#789)") == 789


def test_extract_pr_number_no_pr():
    assert _extract_pr_number("add readme") is None


def test_extract_pr_number_empty():
    assert _extract_pr_number("") is None


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

def test_load_state_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(upd, "STATE_FILE", tmp_path / ".memex" / "state.json")
    assert load_state() == {}


def test_save_then_load_state(tmp_path, monkeypatch):
    monkeypatch.setattr(upd, "STATE_FILE", tmp_path / ".memex" / "state.json")
    save_state("abc123")
    assert load_state() == {"last_sha": "abc123"}


def test_save_state_preserves_existing_keys(tmp_path, monkeypatch):
    state_file = tmp_path / ".memex" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"other_key": "value"}))
    monkeypatch.setattr(upd, "STATE_FILE", state_file)
    save_state("def456")
    state = load_state()
    assert state["last_sha"] == "def456"
    assert state["other_key"] == "value"


# ---------------------------------------------------------------------------
# git_log_since
# ---------------------------------------------------------------------------

def _log_line(sha, subject, author):
    return f"{sha}\x1f{subject}\x1f{author}"


def test_git_log_since_returns_commit_list():
    line = _log_line("abc123def456", "Merge pull request #42 from feat", "alice@x.com")
    with patch("subprocess.run", return_value=_subprocess_result(line)):
        commits = git_log_since(None, limit=10)
    assert len(commits) == 1
    c = commits[0]
    assert c.sha == "abc123def456"
    assert c.pr_number == 42
    assert c.author == "alice@x.com"


def test_git_log_since_nonzero_returncode():
    with patch("subprocess.run", return_value=_subprocess_result("", returncode=1)):
        assert git_log_since(None, limit=10) == []


def test_git_log_since_empty_stdout():
    with patch("subprocess.run", return_value=_subprocess_result("")):
        assert git_log_since(None, limit=10) == []


def test_git_log_since_uses_range_with_last_sha():
    with patch("subprocess.run", return_value=_subprocess_result("")) as mock_run:
        git_log_since("deadbeef", limit=10)
    cmd = mock_run.call_args[0][0]
    assert "deadbeef..HEAD" in cmd


def test_git_log_since_uses_since_flag():
    with patch("subprocess.run", return_value=_subprocess_result("")) as mock_run:
        git_log_since(None, limit=10, since="2024-01-01")
    cmd = mock_run.call_args[0][0]
    assert any("--since=2024-01-01" in part for part in cmd)


def test_git_log_since_uses_limit_without_state():
    with patch("subprocess.run", return_value=_subprocess_result("")) as mock_run:
        git_log_since(None, limit=15)
    cmd = mock_run.call_args[0][0]
    assert "-15" in cmd


# ---------------------------------------------------------------------------
# git_files_changed
# ---------------------------------------------------------------------------

def test_git_files_changed_multiple():
    output = "diff --git a/f1 b/f1\n5 files changed, 123 insertions(+), 10 deletions(-)"
    with patch("subprocess.run", return_value=_subprocess_result(output)):
        assert git_files_changed("abc") == 5


def test_git_files_changed_single():
    output = "diff\n1 file changed, 2 insertions(+)"
    with patch("subprocess.run", return_value=_subprocess_result(output)):
        assert git_files_changed("abc") == 1


def test_git_files_changed_nonzero_returncode():
    with patch("subprocess.run", return_value=_subprocess_result("", returncode=1)):
        assert git_files_changed("abc") == 0


def test_git_files_changed_empty_output():
    with patch("subprocess.run", return_value=_subprocess_result("")):
        assert git_files_changed("abc") == 0


# ---------------------------------------------------------------------------
# git_diff
# ---------------------------------------------------------------------------

def test_git_diff_returns_content():
    diff = "diff --git a/foo.py b/foo.py\n+new line"
    with patch("subprocess.run", return_value=_subprocess_result(diff)):
        assert git_diff("abc") == diff


def test_git_diff_truncates_long_output():
    long_diff = "x" * 10000
    with patch("subprocess.run", return_value=_subprocess_result(long_diff)):
        result = git_diff("abc", max_chars=100)
    assert len(result) > 100  # includes suffix
    assert "[diff truncated]" in result
    assert result.startswith("x" * 100)


def test_git_diff_nonzero_returncode():
    with patch("subprocess.run", return_value=_subprocess_result("", returncode=1)):
        assert git_diff("abc") == ""


# ---------------------------------------------------------------------------
# detect_repo
# ---------------------------------------------------------------------------

def test_detect_repo_https_url():
    with patch("subprocess.run", return_value=_subprocess_result("https://github.com/owner/myrepo.git\n")):
        assert detect_repo() == "owner/myrepo"


def test_detect_repo_ssh_url():
    with patch("subprocess.run", return_value=_subprocess_result("git@github.com:owner/myrepo.git\n")):
        assert detect_repo() == "owner/myrepo"


def test_detect_repo_nonzero_returncode():
    with patch("subprocess.run", return_value=_subprocess_result("", returncode=1)):
        assert detect_repo() is None


# ---------------------------------------------------------------------------
# commit_url
# ---------------------------------------------------------------------------

def test_commit_url():
    assert commit_url("abc123", "acme/api") == "https://github.com/acme/api/commit/abc123"


# ---------------------------------------------------------------------------
# build_skip_sets
# ---------------------------------------------------------------------------

def test_build_skip_sets_no_knowledge_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", tmp_path / "knowledge" / "decisions")
    prs, sources = build_skip_sets()
    assert prs == set()
    assert sources == set()


def test_build_skip_sets_reads_pr_number(tmp_path, monkeypatch):
    kd = tmp_path / "knowledge" / "decisions"
    kd.mkdir(parents=True)
    (kd / "record.md").write_text(
        '---\ntitle: "foo"\npr: 42\nsource: "https://example.com/pr/42"\n---\n'
    )
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", kd)
    prs, sources = build_skip_sets()
    assert 42 in prs


def test_build_skip_sets_reads_source_url(tmp_path, monkeypatch):
    kd = tmp_path / "knowledge" / "decisions"
    kd.mkdir(parents=True)
    (kd / "record.md").write_text(
        '---\ntitle: "foo"\nsource: "https://github.com/a/b/commit/abc"\n---\n'
    )
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", kd)
    _, sources = build_skip_sets()
    assert "https://github.com/a/b/commit/abc" in sources


def test_build_skip_sets_ignores_malformed_pr_line(tmp_path, monkeypatch):
    kd = tmp_path / "knowledge" / "decisions"
    kd.mkdir(parents=True)
    (kd / "record.md").write_text("pr: notanumber\n")
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", kd)
    prs, _ = build_skip_sets()  # should not raise
    assert prs == set()


def test_build_skip_sets_pr_zero_not_added(tmp_path, monkeypatch):
    kd = tmp_path / "knowledge" / "decisions"
    kd.mkdir(parents=True)
    (kd / "record.md").write_text("pr: 0\n")
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", kd)
    prs, _ = build_skip_sets()
    assert 0 not in prs


# ---------------------------------------------------------------------------
# _process_pr_commit
# ---------------------------------------------------------------------------

def _make_pr_commit(pr_number=42):
    return CommitInfo(
        sha="abc123def456",
        subject=f"Merge pull request #{pr_number} from feat",
        author="alice@x.com",
        pr_number=pr_number,
    )


_SENTINEL = object()

_DEFAULT_PR_DATA = {
    "title": "Switch queue to Redis",
    "body": "We hit SQS limits.",
    "author": {"login": "alice"},
    "url": "https://github.com/acme/repo/pull/42",
    "reviews": [],
}


def _call_process_pr(commit, indexed_prs=None, indexed_sources=None,
                     fetch_return=_SENTINEL, is_low=False, extraction=None, write_return=None):
    result = UpdateResult()
    if indexed_prs is None:
        indexed_prs = set()
    if indexed_sources is None:
        indexed_sources = set()
    if fetch_return is _SENTINEL:
        fetch_return = _DEFAULT_PR_DATA

    mock_extract = MagicMock(return_value=extraction or _make_extraction())
    mock_is_low = MagicMock(return_value=is_low)
    mock_write = MagicMock(return_value=Path("knowledge/decisions/foo.md"))
    if write_return is not None:
        mock_write.return_value = write_return

    with patch("memex.update.fetch_pr_data", return_value=fetch_return):
        _process_pr_commit(
            commit=commit,
            repo="acme/repo",
            result=result,
            indexed_prs=indexed_prs,
            indexed_sources=indexed_sources,
            extract=mock_extract,
            is_low_signal=mock_is_low,
            write_record=mock_write,
            progress_cb=None,
        )

    return result, mock_extract, mock_write


def test_process_pr_commit_already_indexed():
    commit = _make_pr_commit(42)
    result, mock_extract, _ = _call_process_pr(commit, indexed_prs={42})
    assert result.skipped_already_indexed == 1
    mock_extract.assert_not_called()


def test_process_pr_commit_fetch_failure():
    commit = _make_pr_commit(42)
    # Pass explicit None (not the sentinel) to simulate gh CLI failure
    result, _, _ = _call_process_pr(commit, fetch_return=None)
    assert len(result.errors) == 1
    assert "42" in result.errors[0]


def test_process_pr_commit_low_signal():
    commit = _make_pr_commit(42)
    result, mock_extract, mock_write = _call_process_pr(commit, is_low=True)
    assert result.skipped_low_signal == 1
    mock_extract.assert_not_called()
    mock_write.assert_not_called()


def test_process_pr_commit_no_decision():
    commit = _make_pr_commit(42)
    result, _, mock_write = _call_process_pr(commit, extraction=_no_decision())
    assert result.skipped_no_decision == 1
    mock_write.assert_not_called()


def test_process_pr_commit_happy_path():
    commit = _make_pr_commit(42)
    indexed_prs: set[int] = set()
    result, _, mock_write = _call_process_pr(commit, indexed_prs=indexed_prs)
    assert result.written == 1
    mock_write.assert_called_once()
    assert 42 in indexed_prs


# ---------------------------------------------------------------------------
# _process_direct_commit
# ---------------------------------------------------------------------------

def _make_direct_commit():
    return CommitInfo(
        sha="deadbeef12345678",
        subject="refactor: extract service layer",
        author="bob@x.com",
        pr_number=None,
    )


def _call_process_direct(commit, indexed_sources=None, n_files=1,
                          diff="some diff", is_low=False, extraction=None):
    result = UpdateResult()
    if indexed_sources is None:
        indexed_sources = set()

    mock_extract = MagicMock(return_value=extraction or _make_extraction())
    mock_is_low = MagicMock(return_value=is_low)
    mock_write = MagicMock(return_value=Path("knowledge/decisions/foo.md"))

    with patch("memex.update.git_files_changed", return_value=n_files), \
         patch("memex.update.git_diff", return_value=diff):
        _process_direct_commit(
            commit=commit,
            sha_short=commit.sha[:8],
            repo="acme/repo",
            result=result,
            indexed_sources=indexed_sources,
            extract=mock_extract,
            is_low_signal=mock_is_low,
            write_record=mock_write,
            progress_cb=None,
        )

    return result, mock_extract, mock_write


def test_process_direct_commit_already_indexed():
    commit = _make_direct_commit()
    url = commit_url(commit.sha, "acme/repo")
    result, mock_extract, _ = _call_process_direct(commit, indexed_sources={url})
    assert result.skipped_already_indexed == 1
    mock_extract.assert_not_called()


def test_process_direct_commit_stat_filter():
    commit = _make_direct_commit()
    result, mock_extract, mock_write = _call_process_direct(
        commit, n_files=MAX_FILES_CHANGED + 1
    )
    assert result.skipped_stat_filter == 1
    mock_extract.assert_not_called()
    mock_write.assert_not_called()


def test_process_direct_commit_empty_diff():
    commit = _make_direct_commit()
    result, mock_extract, mock_write = _call_process_direct(commit, diff="")
    assert result.skipped_low_signal == 1
    mock_extract.assert_not_called()


def test_process_direct_commit_low_signal():
    commit = _make_direct_commit()
    result, mock_extract, mock_write = _call_process_direct(
        commit, diff="bump version", is_low=True
    )
    assert result.skipped_low_signal == 1
    mock_write.assert_not_called()


def test_process_direct_commit_no_decision():
    commit = _make_direct_commit()
    result, _, mock_write = _call_process_direct(commit, extraction=_no_decision())
    assert result.skipped_no_decision == 1
    mock_write.assert_not_called()


def test_process_direct_commit_happy_path():
    commit = _make_direct_commit()
    indexed_sources: set[str] = set()
    result, _, mock_write = _call_process_direct(commit, indexed_sources=indexed_sources)
    assert result.written == 1
    mock_write.assert_called_once()
    assert commit_url(commit.sha, "acme/repo") in indexed_sources


# ---------------------------------------------------------------------------
# run_update
# ---------------------------------------------------------------------------

def test_run_update_no_repo_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upd, "STATE_FILE", tmp_path / ".memex" / "state.json")
    with patch("memex.update.detect_repo", return_value=None):
        result = run_update()
    assert len(result.errors) == 1
    assert "remote" in result.errors[0].lower() or "repo" in result.errors[0].lower()


def test_run_update_already_up_to_date(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_file = tmp_path / ".memex" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"last_sha": "abc123"}))
    monkeypatch.setattr(upd, "STATE_FILE", state_file)

    with patch("memex.update.detect_repo", return_value="acme/repo"), \
         patch("memex.update.git_head_sha", return_value="abc123"):
        result = run_update()

    assert result.processed == 0
    assert result.written == 0


def test_run_update_no_new_commits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upd, "STATE_FILE", tmp_path / ".memex" / "state.json")
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", tmp_path / "knowledge" / "decisions")

    with patch("memex.update.detect_repo", return_value="acme/repo"), \
         patch("memex.update.git_head_sha", return_value="newsha"), \
         patch("memex.update.git_log_since", return_value=[]), \
         patch("memex.update.save_state") as mock_save:
        result = run_update()

    assert result.processed == 0
    mock_save.assert_called_once_with("newsha")


def test_run_update_processes_one_pr_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upd, "STATE_FILE", tmp_path / ".memex" / "state.json")
    monkeypatch.setattr(upd, "KNOWLEDGE_DIR", tmp_path / "knowledge" / "decisions")

    commit = CommitInfo(sha="abc123", subject="feat (#7)", author="alice@x.com", pr_number=7)

    pr_data = {
        "title": "Switch queue",
        "body": "We hit limits.",
        "author": {"login": "alice"},
        "url": "https://github.com/acme/repo/pull/7",
        "reviews": [],
    }

    with patch("memex.update.detect_repo", return_value="acme/repo"), \
         patch("memex.update.git_head_sha", return_value="abc123"), \
         patch("memex.update.git_log_since", return_value=[commit]), \
         patch("memex.update.fetch_pr_data", return_value=pr_data), \
         patch("memex.update.save_state"), \
         patch("memex.extractor.extract", return_value=_make_extraction()), \
         patch("memex.extractor.is_low_signal", return_value=False), \
         patch("memex.writer.write_record", return_value=Path("knowledge/decisions/foo.md")):
        result = run_update()

    assert result.processed == 1
