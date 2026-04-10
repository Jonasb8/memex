"""
Structural file detection — pure classification, no LLM dependency.

Identifies high-value file patterns (migrations, IaC, schema, deployment)
that indicate architectural decisions worth extracting even when PR descriptions
are thin. Shared by extractor.py and update.py.
"""
from __future__ import annotations

import re
from collections import defaultdict

# File patterns that indicate high-value structural changes.
# Deliberately conservative — no raw .yaml/.yml (too broad for most projects).
_STRUCTURAL_PATTERNS: dict[str, list[str]] = {
    "migration": [
        r"migrations?/",
        r"alembic/versions/",
        r"db/migrate/",
        r"\d{14}_\w+\.rb$",   # Rails migration naming convention
    ],
    "infra": [
        r"\.tf$",
        r"terraform/",
        r"k8s/",
        r"kubernetes/",
        r"helm/",
        r"charts/",
        r"manifests/",
    ],
    "schema": [
        r"openapi\.ya?ml$",
        r"openapi\.json$",
        r"swagger\.ya?ml$",
        r"schema\.json$",
        r"schema\.graphql$",
        r"\.graphql$",
        r"\.proto$",
    ],
    "deployment": [
        r"docker-compose.*\.ya?ml$",
        r"Dockerfile(\.\w+)?$",
    ],
}

STRUCTURAL_LABEL: dict[str, str] = {
    "migration": "Database migrations",
    "infra": "Infrastructure / IaC",
    "schema": "API / Schema definitions",
    "deployment": "Deployment configuration",
}


def categorize_file(path: str) -> str | None:
    """Return the structural category for a file path, or None if not structural."""
    p = path.replace("\\", "/")
    for category, patterns in _STRUCTURAL_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, p, re.IGNORECASE):
                return category
    return None


def is_structural_change(changed_files: list[str]) -> bool:
    """True if any changed file matches a high-value structural pattern."""
    return any(categorize_file(p) is not None for p in changed_files)


def build_changed_files_section(changed_files: list[str] | None) -> str:
    """Build the Changed Files section for the LLM prompt."""
    if not changed_files:
        return "No file list available."
    buckets: dict[str, list[str]] = defaultdict(list)
    for path in changed_files:
        cat = categorize_file(path) or "other"
        buckets[cat].append(path)
    lines = []
    for cat in ["migration", "infra", "schema", "deployment"]:
        if cat not in buckets:
            continue
        lines.append(f"**{STRUCTURAL_LABEL[cat]}** ({len(buckets[cat])} files):")
        for f in buckets[cat]:
            lines.append(f"  - {f}")
    other_count = len(buckets.get("other", []))
    if other_count:
        lines.append(f"Other changed files: {other_count}")
    if not lines:
        return f"{len(changed_files)} files changed (none match structural patterns)."
    return "\n".join(lines)
