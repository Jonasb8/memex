"""
Entry point for the GitHub Action.
Reads PR context from environment variables, runs extraction, and writes the record.
Handles two event types: pull_request (merge) and issue_comment (nudge reply).
"""
import os
import re
import json
import subprocess
from pathlib import Path
from .extractor import extract, confidence_level
from .structural import categorize_file
from .writer import write_record
from .schema import ConfidenceLevel
from .nudge import should_nudge, has_nudge_comment, post_nudge_comment, is_bot_comment


_ADR_DIRS = {"docs/adr", "docs/decisions", "decisions", "adr"}


def get_review_comments(pr_number: str, repo: str) -> list[str]:
    """Fetch review comments via GitHub CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--repo", repo,
             "--json", "reviews", "--jq", "[.reviews[].body]"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "[]")
    except Exception:
        pass
    return []


def get_changed_files(pr_number: str, repo: str) -> list[str]:
    """Return list of file paths changed in this PR."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--repo", repo,
             "--json", "files", "--jq", "[.files[].path]"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "[]")
    except Exception:
        pass
    return []


def find_related_adrs(text: str) -> list[str]:
    """Return paths of knowledge records matching ADR-NNN references found in text."""
    nums = re.findall(r"ADR[-](\d+)", text, re.IGNORECASE)
    related = []
    base = Path("knowledge/decisions")
    for n in set(nums):
        padded = f"{int(n):03d}"
        for pattern in (f"*adr*{padded}*.md", f"*adr*{n}*.md"):
            related += [str(p) for p in base.glob(pattern)]
    return list(dict.fromkeys(related))  # deduplicate, preserve order


def _fetch_pr_data(pr_number: str, repo: str) -> dict:
    """
    Fetch PR title, body, url, author, and review comments via gh CLI.
    Returns dict with keys: title, body, url, author, review_comments.
    Falls back to empty strings/lists on failure.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--repo", repo,
             "--json", "title,body,url,author,reviews"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "title": data.get("title", ""),
                "body": data.get("body", "") or "",
                "url": data.get("url", ""),
                "author": (data.get("author") or {}).get("login", ""),
                "review_comments": [r.get("body", "") for r in data.get("reviews", [])],
            }
    except Exception:
        pass
    return {"title": "", "body": "", "url": "", "author": "", "review_comments": []}


def handle_pr_merge() -> None:
    """Handle a merged PR event: extract decision, write record, post nudge if needed."""
    pr_title = os.environ["PR_TITLE"]
    pr_body = os.environ.get("PR_BODY", "")
    pr_url = os.environ["PR_URL"]
    pr_number = os.environ["PR_NUMBER"]
    pr_author = os.environ["PR_AUTHOR"]
    repo = os.environ["REPO"]

    # Fetch review comments and changed files from GitHub API
    review_comments = get_review_comments(pr_number, repo)
    changed_files = get_changed_files(pr_number, repo)

    # Parse any ADR files added/modified in this PR
    from .adr import parse_adr
    for filepath in changed_files:
        p = Path(filepath)
        if p.suffix == ".md" and str(p.parent) in _ADR_DIRS and p.exists():
            record = parse_adr(p)
            if record:
                adr_path = write_record(
                    record=record,
                    source_url=filepath,
                    author=pr_author,
                    repo=repo,
                    tags=["adr"],
                )
                print(f"ADR record written: {adr_path}")

    # Run extraction on the PR itself
    result = extract(pr_title, pr_body, review_comments, changed_files=changed_files)

    if result is None:
        print("Low-signal PR — skipped.")
        return

    if not result.contains_decision or result.record is None:
        print("No decision found — discarded silently.")
        return

    level = confidence_level(result.record.confidence)

    # Post nudge comment if confidence is borderline and not already posted
    if should_nudge(result.record.confidence):
        if not has_nudge_comment(pr_number, repo):
            try:
                post_nudge_comment(pr_number, repo)
                print(f"Nudge comment posted on {repo}#{pr_number}.")
            except Exception as e:
                print(f"Warning: could not post nudge comment: {e}")

    # Cross-reference any ADR-NNN mentions in the PR body / comments
    all_text = pr_body + " " + " ".join(review_comments)
    related = find_related_adrs(all_text) or None

    # Derive structural tags from changed files (e.g. ["migration", "schema"])
    structural_tags = sorted({categorize_file(f) for f in changed_files if categorize_file(f)}) or None

    # Write the knowledge record
    path = write_record(
        record=result.record,
        source_url=pr_url,
        author=pr_author,
        pr_number=int(pr_number),
        repo=repo,
        related=related,
        tags=structural_tags,
    )

    print(f"Knowledge record written: {path} (confidence {result.record.confidence:.2f} — {level.value})")


def handle_issue_comment() -> None:
    """Handle an issue_comment event: re-extract using the reply as additional context."""
    comment_body = os.environ.get("COMMENT_BODY", "")
    comment_author = os.environ.get("COMMENT_AUTHOR", "")
    pr_number = os.environ["PR_NUMBER"]
    repo = os.environ["REPO"]

    if is_bot_comment(comment_author):
        print("Bot comment — skipped.")
        return

    if not has_nudge_comment(pr_number, repo):
        print("No nudge comment on this PR — skipped.")
        return

    # Fetch full PR context (not available in env for issue_comment events)
    pr_data = _fetch_pr_data(pr_number, repo)
    augmented_body = pr_data["body"] + "\n\n## Author reply\n" + comment_body

    result = extract(pr_data["title"], augmented_body, pr_data["review_comments"])

    if result is None or not result.contains_decision or result.record is None:
        print("Re-extraction produced no decision — skipped.")
        return

    all_text = augmented_body + " " + " ".join(pr_data["review_comments"])
    related = find_related_adrs(all_text) or None

    path = write_record(
        record=result.record,
        source_url=pr_data["url"],
        author=pr_data["author"],
        pr_number=int(pr_number),
        repo=repo,
        related=related,
    )

    level = confidence_level(result.record.confidence)
    print(f"Re-extracted record written: {path} (confidence {result.record.confidence:.2f} — {level.value})")


def main() -> None:
    event = os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    if event == "issue_comment":
        handle_issue_comment()
    else:
        handle_pr_merge()


if __name__ == "__main__":
    main()
