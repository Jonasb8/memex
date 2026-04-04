"""
ADR parser — scans for Nygard-format ADR files and converts them to KnowledgeRecords.

Supported locations: docs/adr/, docs/decisions/, decisions/, adr/
Supported naming: NNNN-*.md or any .md containing ## Status and ## Decision headers.
"""
import re
from pathlib import Path
from typing import Optional

from .schema import KnowledgeRecord

ADR_DIRS = ["docs/adr", "docs/decisions", "decisions", "adr"]

_STATUS_CONFIDENCE = {
    "accepted": 0.85,
    "proposed": 0.70,
    "deprecated": 0.60,
    "superseded": 0.60,
}


def find_adr_files(root: Path) -> list[Path]:
    """Return all ADR markdown files under known ADR directories."""
    found = []
    for dirname in ADR_DIRS:
        d = root / dirname
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            content = path.read_text(errors="replace")
            # Accept NNNN-*.md naming OR files with both ## Status and ## Decision
            is_numbered = bool(re.match(r"\d{2,}", path.stem))
            has_markers = "## Status" in content and "## Decision" in content
            if is_numbered or has_markers:
                found.append(path)
    return found


def _extract_section(content: str, header: str) -> str:
    """Return the text of the named ## section, stripped."""
    pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _first_sentences(text: str, n: int = 3) -> str:
    """Return up to n sentences from text."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:n]).strip()


def _first_sentence(text: str) -> str:
    return _first_sentences(text, 1)


def _bullet_lines(text: str) -> list[str]:
    """Extract lines starting with - or * as a list of strings."""
    lines = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)", line)
        if m:
            lines.append(m.group(1).strip())
    return lines


def parse_adr(path: Path) -> Optional[KnowledgeRecord]:
    """Parse a single Nygard-format ADR file into a KnowledgeRecord. Returns None if unusable."""
    content = path.read_text(errors="replace")

    # Title: first H1 line, else filename stem
    title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()

    # Status → confidence
    status_text = _extract_section(content, "Status").lower().split()[0] if _extract_section(content, "Status") else ""
    confidence = _STATUS_CONFIDENCE.get(status_text, 0.70)
    confidence_rationale = f"ADR with {status_text or 'unknown'} status"

    # Context
    context_raw = _extract_section(content, "Context")
    if not context_raw:
        context_raw = _extract_section(content, "Problem Statement")
    context = _first_sentences(context_raw, 3) or "No context recorded."

    # Decision
    decision_raw = _extract_section(content, "Decision")
    if not decision_raw:
        return None  # nothing actionable
    decision = _first_sentence(decision_raw) or decision_raw[:200]

    # Alternatives
    alternatives: list[str] = []
    for header in ("Options Considered", "Alternatives Considered", "Alternatives", "Options"):
        alt_raw = _extract_section(content, header)
        if alt_raw:
            alternatives = _bullet_lines(alt_raw)
            break

    # Constraints / consequences
    consequences_raw = _extract_section(content, "Consequences")
    constraints = _bullet_lines(consequences_raw)
    if not constraints and consequences_raw:
        constraints = [_first_sentence(consequences_raw)]

    # Revisit signals: look for "until", "when", "revisit" in consequences
    revisit_signals = [
        c for c in constraints
        if any(kw in c.lower() for kw in ("until", "revisit", "when ", "temporary"))
    ]
    constraints = [c for c in constraints if c not in revisit_signals]

    return KnowledgeRecord(
        title=title,
        context=context,
        decision=decision,
        alternatives_considered=alternatives,
        constraints=constraints,
        revisit_signals=revisit_signals,
        confidence=confidence,
        confidence_rationale=confidence_rationale,
    )


def already_indexed(adr_path: Path, output_dir: Path) -> bool:
    """Return True if a knowledge record with this ADR as source already exists."""
    if not output_dir.is_dir():
        return False
    needle = str(adr_path)
    for md in output_dir.glob("*.md"):
        for line in md.read_text(errors="replace").splitlines():
            if line.startswith("source:") and needle in line:
                return True
    return False


def index_adrs(root: Path, output_dir: Path, repo: str) -> list[Path]:
    """Find, parse, and write all un-indexed ADR files. Returns paths of written records."""
    from .writer import write_record

    written = []
    for adr_path in find_adr_files(root):
        if already_indexed(adr_path, output_dir):
            continue
        record = parse_adr(adr_path)
        if record is None:
            continue
        source = str(adr_path.relative_to(root))
        path = write_record(
            record=record,
            source_url=source,
            author="adr",
            repo=repo,
            tags=["adr"],
        )
        written.append(path)
    return written
