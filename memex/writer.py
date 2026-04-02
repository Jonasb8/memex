from datetime import date, datetime
from pathlib import Path
from typing import Optional
from .schema import KnowledgeRecord, ConfidenceLevel
from .extractor import confidence_level


def render_markdown(
    record: KnowledgeRecord,
    source_url: str,
    author: str,
    repo: str,
    pr_number: Optional[int] = None,
) -> str:
    """Render a KnowledgeRecord to the canonical Memex markdown format."""
    level = confidence_level(record.confidence)
    confidence_flag = (
        "\n> ⚠️ **Low confidence** — limited rationale present in source. "
        "Verify before relying on this record.\n"
        if level == ConfidenceLevel.medium
        else ""
    )

    alternatives_md = (
        "\n".join(f"- {a}" for a in record.alternatives_considered)
        if record.alternatives_considered
        else "_None recorded_"
    )
    constraints_md = (
        "\n".join(f"- {c}" for c in record.constraints)
        if record.constraints
        else "_None recorded_"
    )
    revisit_md = (
        "\n".join(f"- {r}" for r in record.revisit_signals)
        if record.revisit_signals
        else "_None_"
    )

    # pr: field only present for PR-sourced records
    pr_line = f"pr: {pr_number}\n" if pr_number else ""

    # Footer label adapts to source type
    if pr_number:
        footer = f"_Extracted by Memex from [PR #{pr_number}]({source_url}) · {date.today().isoformat()}_"
    else:
        short_sha = source_url.split("/")[-1][:8] if "/commit/" in source_url else source_url
        footer = f"_Extracted by Memex from [commit {short_sha}]({source_url}) · {date.today().isoformat()}_"

    return f"""---
title: "{record.title}"
date: {date.today().isoformat()}
author: "{author}"
source: "{source_url}"
{pr_line}repo: "{repo}"
confidence: {record.confidence:.2f}
tags: []
---

# {record.title}
{confidence_flag}
## Context

{record.context}

## Decision

{record.decision}

## Alternatives considered

{alternatives_md}

## Constraints

{constraints_md}

## Revisit signals

{revisit_md}

---

{footer}
"""


def write_record(
    record: KnowledgeRecord,
    source_url: str,
    author: str,
    repo: str,
    pr_number: Optional[int] = None,
    output_dir: Path = Path("knowledge/decisions"),
) -> Path:
    """Write a rendered knowledge record to disk. Returns the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = record.title.lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:8])
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    filename = f"{timestamp}-{slug}.md"

    path = output_dir / filename
    path.write_text(render_markdown(record, source_url, author, repo, pr_number))
    return path
