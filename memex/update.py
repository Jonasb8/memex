"""
memex update — pull new decisions from git history since last run.

Two tracks run for each commit since last_sha:
  Track 1 (PR commits):    message contains #N → fetch full PR via gh, extract
  Track 2 (direct commits): no PR number → stat-first filter → diff extraction

State is persisted in .memex/state.json so only new commits are ever processed.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

STATE_FILE = Path(".memex/state.json")
KNOWLEDGE_DIR = Path("knowledge/decisions")

MAX_DIFF_CHARS = 6000   # truncation limit for diff-based extraction
MAX_FILES_CHANGED = 10  # stat-first filter: skip commits touching more than this


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CommitInfo:
    sha: str
    subject: str
    author: str
    pr_number: Optional[int] = None


@dataclass
class UpdateResult:
    processed: int = 0
    written: int = 0
    skipped_low_signal: int = 0
    skipped_already_indexed: int = 0
    skipped_stat_filter: int = 0
    skipped_no_decision: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(last_sha: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = load_state()
    state["last_sha"] = last_sha
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_head_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def git_log_since(
    last_sha: Optional[str],
    limit: int,
    since: Optional[str] = None,
) -> list[CommitInfo]:
    """Return commits since last_sha (or --since date, or most recent --limit N)."""
    # Unit-separator (\x1f) avoids collisions with commit message content
    fmt = "%H\x1f%s\x1f%ae"

    if since:
        cmd = ["git", "log", f"--since={since}", f"--format={fmt}"]
    elif last_sha:
        cmd = ["git", "log", f"{last_sha}..HEAD", f"--format={fmt}"]
    else:
        cmd = ["git", "log", f"-{limit}", f"--format={fmt}"]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return []

    commits = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, author = parts
        commits.append(CommitInfo(
            sha=sha,
            subject=subject,
            author=author,
            pr_number=_extract_pr_number(subject),
        ))
    return commits


def _extract_pr_number(message: str) -> Optional[int]:
    """Extract PR number from common GitHub commit message patterns.

    Handles:
      "Merge pull request #123 from branch"
      "Feature: do something (#123)"
      "fix: whatever (#123)"
    """
    m = re.search(r"#(\d+)", message)
    return int(m.group(1)) if m else None


def git_files_changed(sha: str) -> int:
    """Return number of files changed in a commit — used by the stat-first filter."""
    r = subprocess.run(
        ["git", "show", "--stat", "--format=", sha],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return 0
    # Summary line: "5 files changed, 123 insertions(+), 45 deletions(-)"
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    if not lines:
        return 0
    m = re.search(r"(\d+) files? changed", lines[-1])
    return int(m.group(1)) if m else 0


def git_diff(sha: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    """Return truncated unified diff for a single commit."""
    r = subprocess.run(
        ["git", "show", "--format=", sha],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    diff = r.stdout.strip()
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n... [diff truncated]"
    return diff


# ---------------------------------------------------------------------------
# Repo / PR helpers
# ---------------------------------------------------------------------------

def detect_repo() -> Optional[str]:
    """Detect owner/repo from git remote origin URL."""
    r = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    # Handles both https://github.com/owner/repo.git and git@github.com:owner/repo.git
    m = re.search(r"github\.com[:/](.+/.+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def fetch_pr_data(pr_number: int, repo: str) -> Optional[dict]:
    """Fetch PR title, body, author, url, and reviews via gh CLI."""
    r = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo,
         "--json", "title,body,author,url,reviews"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def commit_url(sha: str, repo: str) -> str:
    return f"https://github.com/{repo}/commit/{sha}"


# ---------------------------------------------------------------------------
# Deduplication — scan existing records once, build skip-sets
# ---------------------------------------------------------------------------

def build_skip_sets() -> tuple[set[int], set[str]]:
    """Scan knowledge/decisions/ once and return (pr_numbers, source_urls)."""
    pr_numbers: set[int] = set()
    source_urls: set[str] = set()

    if not KNOWLEDGE_DIR.exists():
        return pr_numbers, source_urls

    for f in KNOWLEDGE_DIR.glob("*.md"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("pr:"):
                try:
                    n = int(line.split(":", 1)[1].strip())
                    if n > 0:
                        pr_numbers.add(n)
                except (ValueError, IndexError):
                    pass
            elif line.startswith("source:"):
                url = line.split(":", 1)[1].strip().strip('"').strip("'")
                if url:
                    source_urls.add(url)

    return pr_numbers, source_urls


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def run_update(
    limit: int = 20,
    since: Optional[str] = None,
    repo: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> UpdateResult:
    """
    Process all new commits since the last recorded SHA.

    Args:
        limit:       Max commits to scan when no prior state exists (bootstrap).
        since:       ISO date string — alternative bootstrap anchor.
        repo:        Override auto-detected owner/repo.
        progress_cb: Called with a human-readable status line per commit.
    """
    from .extractor import extract, is_low_signal
    from .writer import write_record

    result = UpdateResult()

    repo = repo or detect_repo()
    if not repo:
        result.errors.append(
            "Could not detect repo from git remote. "
            "Run from a git repo with a GitHub remote, or pass --repo owner/repo."
        )
        return result

    state = load_state()
    last_sha = state.get("last_sha")

    try:
        head_sha = git_head_sha()
    except subprocess.CalledProcessError:
        result.errors.append("Not inside a git repository.")
        return result

    if head_sha == last_sha:
        if progress_cb:
            progress_cb("Already up to date.")
        return result

    commits = git_log_since(last_sha, limit=limit, since=since)
    if not commits:
        if progress_cb:
            progress_cb("No new commits found.")
        save_state(head_sha)
        return result

    # Build skip-sets once upfront — O(knowledge_files) not O(commits × knowledge_files)
    indexed_prs, indexed_sources = build_skip_sets()

    for commit in commits:
        result.processed += 1
        _process_commit(
            commit=commit,
            repo=repo,
            result=result,
            indexed_prs=indexed_prs,
            indexed_sources=indexed_sources,
            extract=extract,
            is_low_signal=is_low_signal,
            write_record=write_record,
            progress_cb=progress_cb,
        )

    save_state(head_sha)
    return result


def _process_commit(
    commit: CommitInfo,
    repo: str,
    result: UpdateResult,
    indexed_prs: set[int],
    indexed_sources: set[str],
    extract,
    is_low_signal,
    write_record,
    progress_cb: Optional[Callable],
) -> None:
    sha_short = commit.sha[:8]

    if commit.pr_number:
        _process_pr_commit(
            commit=commit,
            repo=repo,
            result=result,
            indexed_prs=indexed_prs,
            indexed_sources=indexed_sources,
            extract=extract,
            is_low_signal=is_low_signal,
            write_record=write_record,
            progress_cb=progress_cb,
        )
    else:
        _process_direct_commit(
            commit=commit,
            sha_short=sha_short,
            repo=repo,
            result=result,
            indexed_sources=indexed_sources,
            extract=extract,
            is_low_signal=is_low_signal,
            write_record=write_record,
            progress_cb=progress_cb,
        )


def _process_pr_commit(
    commit: CommitInfo,
    repo: str,
    result: UpdateResult,
    indexed_prs: set[int],
    indexed_sources: set[str],
    extract,
    is_low_signal,
    write_record,
    progress_cb: Optional[Callable],
) -> None:
    pr_num = commit.pr_number

    if pr_num in indexed_prs:
        result.skipped_already_indexed += 1
        if progress_cb:
            progress_cb(f"  ~ #{pr_num} already indexed — skip")
        return

    pr = fetch_pr_data(pr_num, repo)
    if not pr:
        result.errors.append(
            f"Could not fetch PR #{pr_num} — is gh installed and authenticated? "
            f"(run: gh auth login)"
        )
        return

    title = pr.get("title", commit.subject)
    body = pr.get("body") or ""
    author = (pr.get("author") or {}).get("login", commit.author)
    pr_url = pr.get("url", f"https://github.com/{repo}/pull/{pr_num}")
    reviews = [r.get("body", "") for r in pr.get("reviews", []) if r.get("body")]

    if is_low_signal(title, body):
        result.skipped_low_signal += 1
        if progress_cb:
            progress_cb(f"  ✗ #{pr_num} low signal — skip")
        return

    extraction = extract(title, body, reviews)
    if extraction is None or not extraction.contains_decision or extraction.record is None:
        result.skipped_no_decision += 1
        if progress_cb:
            progress_cb(f"  ✗ #{pr_num} no decision found — skip")
        return

    path = write_record(
        record=extraction.record,
        source_url=pr_url,
        author=author,
        pr_number=pr_num,
        repo=repo,
    )
    indexed_prs.add(pr_num)
    result.written += 1
    if progress_cb:
        progress_cb(f"  ✓ #{pr_num} {extraction.record.title[:60]} → {path}")


def _process_direct_commit(
    commit: CommitInfo,
    sha_short: str,
    repo: str,
    result: UpdateResult,
    indexed_sources: set[str],
    extract,
    is_low_signal,
    write_record,
    progress_cb: Optional[Callable],
) -> None:
    c_url = commit_url(commit.sha, repo)

    if c_url in indexed_sources:
        result.skipped_already_indexed += 1
        if progress_cb:
            progress_cb(f"  ~ {sha_short} already indexed — skip")
        return

    # Stat-first filter — skip large commits before any LLM call
    n_files = git_files_changed(commit.sha)
    if n_files > MAX_FILES_CHANGED:
        result.skipped_stat_filter += 1
        if progress_cb:
            progress_cb(f"  ✗ {sha_short} {n_files} files changed — stat filter")
        return

    diff = git_diff(commit.sha)
    if not diff:
        result.skipped_low_signal += 1
        if progress_cb:
            progress_cb(f"  ✗ {sha_short} empty diff — skip")
        return

    if is_low_signal(commit.subject, diff):
        result.skipped_low_signal += 1
        if progress_cb:
            progress_cb(f"  ✗ {sha_short} low signal — skip")
        return

    extraction = extract(commit.subject, diff, [])
    if extraction is None or not extraction.contains_decision or extraction.record is None:
        result.skipped_no_decision += 1
        if progress_cb:
            progress_cb(f"  ✗ {sha_short} no decision found — skip")
        return

    path = write_record(
        record=extraction.record,
        source_url=c_url,
        author=commit.author,
        pr_number=None,  # direct commit — no PR number
        repo=repo,
    )
    indexed_sources.add(c_url)
    result.written += 1
    if progress_cb:
        progress_cb(f"  ✓ {sha_short} {extraction.record.title[:60]} → {path}")
