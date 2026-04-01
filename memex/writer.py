from datetime import date
from pathlib import Path
from .schema import KnowledgeRecord, ConfidenceLevel
from .extractor import confidence_level


def render_markdown(
    record: KnowledgeRecord,
    pr_url: str,
    pr_author: str,
    pr_number: int,
    repo: str,
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

    return f"""---
title: "{record.title}"
date: {date.today().isoformat()}
author: "{pr_author}"
source: "{pr_url}"
pr: {pr_number}
repo: "{repo}"
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

_Extracted by Memex from [PR #{pr_number}]({pr_url}) · {date.today().isoformat()}_
"""


def write_record(
    record: KnowledgeRecord,
    pr_url: str,
    pr_author: str,
    pr_number: int,
    repo: str,
    output_dir: Path = Path("knowledge/decisions"),
) -> Path:
    """Write a rendered knowledge record to disk. Returns the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Slug: date + sanitised title
    slug = record.title.lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:8])
    filename = f"{date.today().isoformat()}-{slug}.md"

    path = output_dir / filename
    path.write_text(render_markdown(record, pr_url, pr_author, pr_number, repo))
    return path
