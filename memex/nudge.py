"""
Low-confidence nudge comment logic.

Posts a single GitHub PR comment asking for rationale when extraction confidence
is borderline. Handles detection of existing nudge comments to avoid duplicates,
and bot-author filtering to prevent infinite loops.
"""
import json
import subprocess

from .extractor import DISCARD_THRESHOLD

NUDGE_THRESHOLD = 0.80
NUDGE_MARKER = "<!-- memex-nudge -->"
NUDGE_COMMENT_BODY = (
    "Memex detected an architectural decision in this PR but couldn't capture "
    "the rationale fully. One sentence: what was the main reason for this approach?\n\n"
    + NUDGE_MARKER
)


def should_nudge(confidence: float) -> bool:
    """Return True if confidence is in the nudge range: [DISCARD_THRESHOLD, NUDGE_THRESHOLD)."""
    return DISCARD_THRESHOLD <= confidence < NUDGE_THRESHOLD


def get_pr_comments(pr_number: str, repo: str) -> list[dict]:
    """Fetch all comments on a PR via gh CLI. Returns [] on any failure."""
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", pr_number,
                "--repo", repo,
                "--json", "comments",
                "--jq", "[.comments[] | {body: .body, author: .author.login}]",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "[]")
    except Exception:
        pass
    return []


def has_nudge_comment(pr_number: str, repo: str) -> bool:
    """Return True if a Memex nudge comment already exists on this PR."""
    comments = get_pr_comments(pr_number, repo)
    return any(NUDGE_MARKER in c.get("body", "") for c in comments)


def post_nudge_comment(pr_number: str, repo: str) -> None:
    """Post the nudge comment on the PR. Caller must check has_nudge_comment first."""
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--repo", repo, "--body", NUDGE_COMMENT_BODY],
        check=True, capture_output=True, timeout=15,
    )


def is_bot_comment(author_login: str) -> bool:
    """Return True if the author looks like a bot (to prevent infinite loops)."""
    return author_login == "memex-bot" or author_login.endswith("[bot]")
