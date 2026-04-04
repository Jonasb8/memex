"""
Entry point for the GitHub Action.
Reads PR context from environment variables, runs extraction, and writes the record.
"""
import os
import json
import subprocess
from pathlib import Path
from .extractor import extract, confidence_level
from .writer import write_record
from .schema import ConfidenceLevel


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
        print("No decision found — discarded silently.")
        return

    level = confidence_level(result.record.confidence)

    # Write the knowledge record
    path = write_record(
        record=result.record,
        source_url=pr_url,
        author=pr_author,
        pr_number=int(pr_number),
        repo=repo,
    )

    print(f"Knowledge record written: {path} (confidence {result.record.confidence:.2f} — {level.value})")


if __name__ == "__main__":
    main()
