"""
Entry point for the GitHub Action.
Reads PR context from environment variables, runs extraction,
writes the record, and optionally posts a nudge comment.
"""
import os
import json
import subprocess
from pathlib import Path
from .extractor import extract, confidence_level
from .writer import write_record
from .schema import ConfidenceLevel

NUDGE_THRESHOLD_LOW = 0.30   # below this: don't bother asking
NUDGE_THRESHOLD_HIGH = 0.40  # above this: high enough, no nudge needed


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


def post_nudge_comment(pr_number: str, repo: str) -> None:
    """Post a single low-confidence nudge comment to the PR."""
    body = (
        "**Memex** detected what looks like an architectural decision here, "
        "but couldn't find enough rationale to capture it confidently.\n\n"
        "One sentence would help: **what was the main reason for this approach?** "
        "Reply here and Memex will incorporate it.\n\n"
        "<sub>To suppress this message on a PR, add the label `memex:skip`.</sub>"
    )
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--repo", repo, "--body", body],
        timeout=15,
    )


def main() -> None:
    pr_title = os.environ["PR_TITLE"]
    pr_body = os.environ.get("PR_BODY", "")
    pr_url = os.environ["PR_URL"]
    pr_number = os.environ["PR_NUMBER"]
    pr_author = os.environ["PR_AUTHOR"]
    repo = os.environ["REPO"]

    # Fetch review comments from GitHub API
    review_comments = get_review_comments(pr_number, repo)

    # Run extraction
    result = extract(pr_title, pr_body, review_comments)

    if result is None:
        print("Low-signal PR — skipped.")
        return

    if not result.contains_decision or result.record is None:
        score = result.record.confidence if result.record else 0.0
        # Post nudge only in the borderline zone
        if NUDGE_THRESHOLD_LOW <= score < NUDGE_THRESHOLD_HIGH:
            post_nudge_comment(pr_number, repo)
            print(f"No clear decision found (confidence {score:.2f}) — nudge comment posted.")
        else:
            print(f"No decision found (confidence {score:.2f}) — discarded silently.")
        return

    # Write the knowledge record
    path = write_record(
        record=result.record,
        source_url=pr_url,
        author=pr_author,
        pr_number=int(pr_number),
        repo=repo,
    )

    level = confidence_level(result.record.confidence)
    print(f"Knowledge record written: {path} (confidence {result.record.confidence:.2f} — {level.value})")


if __name__ == "__main__":
    main()
