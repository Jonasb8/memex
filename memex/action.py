"""
Entry point for the GitHub Action.
Reads PR context from environment variables, runs extraction, and writes the record.
"""
import os
import re
import json
import subprocess
from pathlib import Path
from .extractor import extract, confidence_level
from .writer import write_record
from .schema import ConfidenceLevel


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


def main() -> None:
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
    result = extract(pr_title, pr_body, review_comments)

    if result is None:
        print("Low-signal PR — skipped.")
        return

    if not result.contains_decision or result.record is None:
        print("No decision found — discarded silently.")
        return

    level = confidence_level(result.record.confidence)

    # Cross-reference any ADR-NNN mentions in the PR body / comments
    all_text = pr_body + " " + " ".join(review_comments)
    related = find_related_adrs(all_text) or None

    # Write the knowledge record
    path = write_record(
        record=result.record,
        source_url=pr_url,
        author=pr_author,
        pr_number=int(pr_number),
        repo=repo,
        related=related,
    )

    print(f"Knowledge record written: {path} (confidence {result.record.confidence:.2f} — {level.value})")


if __name__ == "__main__":
    main()
