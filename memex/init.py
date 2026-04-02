"""
memex init — bootstraps the knowledge graph from a repo's current state.

Scans package manifests, infrastructure files, and directory structure, then
asks Claude to identify the architectural decisions embedded in that snapshot.
Produces KnowledgeRecord files tagged ["init"] in knowledge/decisions/.
"""

from __future__ import annotations

import subprocess
from datetime import date, datetime
from pathlib import Path

import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field

from .config import load_api_key
from .schema import KnowledgeRecord, ConfidenceLevel
from .extractor import confidence_level

# ---------------------------------------------------------------------------
# Structured output model
# ---------------------------------------------------------------------------

class ArchitectureExtractionResult(BaseModel):
    """What the LLM returns for a full-repo scan."""

    records: list[KnowledgeRecord] = Field(
        description=(
            "One KnowledgeRecord per distinct architectural decision visible in "
            "the repo snapshot. Aim for 3–10 records. Do not manufacture decisions "
            "— only extract choices where there is at least implicit rationale "
            "(e.g. a dependency that implies a deliberate trade-off, a directory "
            "layout that implies an architecture style)."
        )
    )


# ---------------------------------------------------------------------------
# Repo scanning
# ---------------------------------------------------------------------------

# Glob patterns — each may match multiple files.
# Ordered from highest to lowest signal value.
_MANIFEST_GLOBS = [
    # Python
    "pyproject.toml",
    "*requirements*.txt",
    "*requirements*/*.txt",
    "setup.cfg",
    "setup.py",
    "Pipfile",
    # JavaScript / Node
    "package.json",
    "pnpm-workspace.yaml",
    "turbo.json",
    "bun.lockb",
    "deno.json",
    "deno.jsonc",
    # Rust
    "Cargo.toml",
    # Go
    "go.mod",
    # JVM
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    # Ruby
    "Gemfile",
    # PHP
    "composer.json",
    # .NET
    "*.csproj",
    "*.fsproj",
    "*.sln",
    # Nix
    "flake.nix",
    "default.nix",
    # Elixir
    "mix.exs",
    # Swift / Xcode
    "Package.swift",
]

_INFRA_GLOBS = [
    # Docker — name variations and multi-stage setups
    "Dockerfile*",
    "*.dockerfile",
    "**/Dockerfile*",                # one level deep (e.g. services/api/Dockerfile)
    # Compose — Docker renamed compose.yaml as the canonical name
    "*compose*.y*ml",
    # Task runners
    "Makefile",
    "justfile",
    "Taskfile.yml",
    "Taskfile.yaml",
    # Env templates
    ".env.example",
    ".env.sample",
    ".env.template",
]

_CI_GLOBS = [
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".circleci/config.yml",
    ".circleci/config.yaml",
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
    "Jenkinsfile",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    ".travis.yml",
    "bitbucket-pipelines.yml",
    ".buildkite/pipeline.yml",
    ".buildkite/pipeline.yaml",
    "cloudbuild.yaml",          # Google Cloud Build
    ".woodpecker.yml",
]

_DOC_GLOBS = [
    "README*",
    "ARCHITECTURE*",
    "CONTRIBUTING*",
    "docs/architecture*",
    "docs/ARCHITECTURE*",
    "docs/adr/*.md",
    "docs/decisions/*.md",
    "decisions/*.md",
    "adr/*.md",
]

# Known infra directories — we list their contents + sample a few files
_INFRA_DIRS = [
    "terraform", "tf",
    "k8s", "kubernetes",
    "helm", "charts",
    "infra", "infrastructure",
    "deploy", "deployment", "deployments",
    "ansible",
    "pulumi",
    "cdk",
    "serverless",
    "config", "configs", "configuration",
]

# Extensions that are interesting to sweep at root level
_ROOT_SWEEP_EXTENSIONS = {
    ".toml", ".json", ".yaml", ".yml",
    ".mod",   # go.mod
    ".tf",    # Terraform
    ".nix",   # Nix
    ".gradle",
}

# Files / directories that are never worth reading
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    "target", ".next", ".nuxt", "coverage", ".turbo", ".cache",
}

_SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "Gemfile.lock", "composer.lock",
    "go.sum",  # checksums, not decisions
    ".DS_Store",
}


def _read_truncated(path: Path, max_chars: int = 3000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... [truncated at {max_chars} chars]"
        return text
    except OSError:
        return ""


def _is_binary(path: Path) -> bool:
    """Quick check — read first 512 bytes and look for null bytes."""
    try:
        return b"\x00" in path.read_bytes()[:512]
    except OSError:
        return True


def _directory_tree(root: Path, max_depth: int = 2) -> str:
    """Return a compact tree of the repo, skipping noise directories."""
    lines: list[str] = []

    def _recurse(path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        visible = [
            c for c in children
            if not c.name.startswith(".") and c.name not in _SKIP_DIRS
        ]
        for i, child in enumerate(visible[:30]):
            connector = "└── " if i == len(visible) - 1 else "├── "
            lines.append(f"{prefix}{connector}{child.name}{'/' if child.is_dir() else ''}")
            if child.is_dir():
                extension = "    " if i == len(visible) - 1 else "│   "
                _recurse(child, depth + 1, prefix + extension)

    lines.append(f"{root.name}/")
    _recurse(root, 1, "")
    return "\n".join(lines)


def _collect_globs(
    root: Path,
    patterns: list[str],
    seen: set[Path],
    max_chars: int = 3000,
    per_pattern_cap: int = 5,
) -> dict[str, str]:
    """Expand glob patterns, read matching files, skip already-seen paths."""
    results: dict[str, str] = {}
    for pattern in patterns:
        matches = sorted(root.glob(pattern))[:per_pattern_cap]
        for path in matches:
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if path.name in _SKIP_FILES:
                continue
            if _is_binary(path):
                continue
            content = _read_truncated(path, max_chars)
            if content:
                label = str(path.relative_to(root))
                results[label] = content
                seen.add(resolved)
    return results


def _root_sweep(root: Path, seen: set[Path]) -> dict[str, str]:
    """
    Pick up any config/manifest at the repo root that the globs didn't catch.
    Only looks one level deep, only interesting extensions, skips lockfiles.
    """
    results: dict[str, str] = {}
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except PermissionError:
        return results

    for path in entries:
        if not path.is_file():
            continue
        if path.name.startswith(".") and path.name not in {".env.example", ".env.sample"}:
            continue
        if path.name in _SKIP_FILES:
            continue
        if path.suffix not in _ROOT_SWEEP_EXTENSIONS:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        if _is_binary(path):
            continue
        content = _read_truncated(path)
        if content:
            label = str(path.relative_to(root))
            results[label] = content
            seen.add(resolved)
    return results


def _infra_dir_scan(root: Path, seen: set[Path]) -> dict[str, str]:
    """
    For known infra directories, include a sample of files so the LLM
    understands the infrastructure choices even if filenames are non-standard.
    """
    results: dict[str, str] = {}
    for dirname in _INFRA_DIRS:
        d = root / dirname
        if not d.is_dir():
            continue
        # List the directory tree as context
        tree_lines = [f"{dirname}/"]
        try:
            for p in sorted(d.rglob("*"))[:50]:
                if p.is_file() and p.name not in _SKIP_FILES:
                    tree_lines.append(f"  {p.relative_to(d)}")
        except PermissionError:
            pass
        results[f"__{dirname}_tree__"] = "\n".join(tree_lines)

        # Sample up to 3 substantive files (prefer .tf, .yml, .yaml, .json, .toml)
        candidates = sorted(
            (p for p in d.rglob("*") if p.is_file() and p.name not in _SKIP_FILES),
            key=lambda p: (p.suffix not in {".tf", ".yml", ".yaml", ".json", ".toml"}, p.name),
        )
        for path in candidates[:3]:
            resolved = path.resolve()
            if resolved in seen or _is_binary(path):
                continue
            content = _read_truncated(path, max_chars=2000)
            if content:
                label = str(path.relative_to(root))
                results[label] = content
                seen.add(resolved)
    return results


def scan_repo(root: Path) -> dict[str, str]:
    """
    Collect every signal that reveals architectural decisions.

    Three-pass strategy so non-standard naming conventions are never missed:

    Pass 1 — Glob patterns: expand well-known patterns across all common
              naming conventions (e.g. Dockerfile*, *compose*.y*ml).

    Pass 2 — Root sweep: any config-like file at the repo root that the
              globs didn't match yet (catches bespoke/new tooling).

    Pass 3 — Infra dir scan: for directories like terraform/, k8s/, helm/
              include a file listing + sample files regardless of names.

    Returns a dict mapping a human-readable label → file contents.
    The special key "__directory_structure__" always holds the repo tree.
    """
    seen: set[Path] = set()
    signals: dict[str, str] = {}

    # Pass 1a — manifests
    signals.update(_collect_globs(root, _MANIFEST_GLOBS, seen))

    # Pass 1b — infra files (Dockerfiles, compose, task runners, env templates)
    signals.update(_collect_globs(root, _INFRA_GLOBS, seen, max_chars=2000))

    # Pass 1c — CI/CD (cap each pattern at 3 so 10-workflow repos don't drown signal)
    signals.update(_collect_globs(root, _CI_GLOBS, seen, max_chars=2000, per_pattern_cap=3))

    # Pass 1d — documentation
    signals.update(_collect_globs(root, _DOC_GLOBS, seen, max_chars=4000))

    # Pass 2 — root-level sweep for anything the globs missed
    signals.update(_root_sweep(root, seen))

    # Pass 3 — infra directories (terraform/, k8s/, etc.)
    signals.update(_infra_dir_scan(root, seen))

    # Always last — directory tree gives the LLM structural context
    signals["__directory_structure__"] = _directory_tree(root)

    return signals


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def _build_init_prompt(signals: dict[str, str], repo_name: str) -> str:
    sections = []
    for label, content in signals.items():
        if label == "__directory_structure__":
            sections.append(f"## Directory structure\n\n```\n{content}\n```")
        else:
            ext = label.rsplit(".", 1)[-1] if "." in label else ""
            fence = ext if ext in {"toml", "json", "yaml", "yml", "txt", "md"} else ""
            sections.append(f"## {label}\n\n```{fence}\n{content}\n```")

    joined = "\n\n".join(sections)

    return f"""You are analysing a software repository called "{repo_name}" to extract \
the architectural decisions embedded in its current state.

You will receive a snapshot of the repo: package manifests, infrastructure files, \
CI configuration, documentation, and directory structure. From this, identify the \
genuine architectural decisions the team has already made.

## Rules

- Extract only REAL decisions — non-obvious technology choices, structural trade-offs, \
or patterns that imply deliberate reasoning.
- Do NOT extract every library or tool — focus on choices that carry meaningful trade-offs \
(e.g. "chose Postgres over Mongo", "chose a monorepo layout", "chose serverless deployment").
- Confidence should be moderate (0.45–0.70). We are inferring from current state, not \
reading the original decision discussion. Never assign > 0.75 for init records.
- alternatives_considered may be empty if none are evident — do NOT invent them.
- revisit_signals may be empty — do NOT invent them.
- Aim for 3–10 records. A sparse, accurate graph beats a noisy one.
- Each record's `confidence_rationale` must explain what in the repo snapshot \
justified this confidence score.

## Repo snapshot

{joined}

Now extract the architectural decisions as a list of KnowledgeRecord objects."""


def extract_architecture(
    signals: dict[str, str],
    repo_name: str,
) -> list[KnowledgeRecord]:
    """Call Claude to extract architectural decisions from the repo snapshot."""
    client = instructor.from_anthropic(Anthropic(api_key=load_api_key()))

    result: ArchitectureExtractionResult = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": _build_init_prompt(signals, repo_name),
            }
        ],
        response_model=ArchitectureExtractionResult,
    )

    # Filter out anything below discard threshold (shouldn't happen given the
    # prompt, but be defensive)
    return [r for r in result.records if r.confidence >= 0.40]


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_init_markdown(
    record: KnowledgeRecord,
    source_file: str,
    repo_name: str,
) -> str:
    """Render an init KnowledgeRecord to Memex markdown format."""
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

    today = date.today().isoformat()

    return f"""---
title: "{record.title}"
date: {today}
author: "memex-init"
source: "{source_file}"
repo: "{repo_name}"
confidence: {record.confidence:.2f}
tags: ["init"]
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

_Extracted by Memex from repo scan of `{repo_name}` · {today}_
"""


def write_init_record(
    record: KnowledgeRecord,
    source_file: str,
    repo_name: str,
    output_dir: Path = Path("knowledge/decisions"),
) -> Path:
    """Write a rendered init record to disk. Returns the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = record.title.lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:8])
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    filename = f"{timestamp}-{slug}.md"

    path = output_dir / filename
    path.write_text(render_init_markdown(record, source_file, repo_name))
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_repo_name(root: Path) -> str:
    """Best-effort: git remote → directory name."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        # https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
        name = url.rstrip("/").rstrip(".git").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        if name:
            return name
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return root.resolve().name
