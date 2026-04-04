# Memex

Memex extracts and indexes the institutional knowledge buried in your GitHub pull requests, review threads, and ADRs — automatically, without changing how your team works.

Engineers don't write anything new. Memex hooks into the artifacts that already exist and makes them searchable.

```bash
$ memex query "why did we move off MongoDB"

Results for: why did we move off MongoDB
──────────────────────────────────────────────────────────────────────

  1. Migrate billing store to PostgreSQL                     [0.91] ●
     Unbounded schema flexibility was causing silent data corruption
     in the billing pipeline. MongoDB's lack of enforced schema...
     knowledge/decisions/2024-11-14-migrate-billing-store-to-postgresql.md

  2. ...
```

---

## How it works

1. **GitHub Action** — triggers on every merged PR, calls Claude to extract decision context, opens a `memex/pr-{N}` branch with the structured `.md` file, and creates a PR for review
2. **Local CLI** — `memex index` embeds your knowledge files locally; `memex query` runs semantic search over them
3. **ADR parser** — on first run, scans your repo for existing ADR files and indexes them automatically
4. **Low-confidence nudge** — when a PR looks like it contains a decision but lacks rationale, Memex posts a single comment asking for one sentence of context

---

## Installation

```bash
pip install memex-oss
```

Requires Python 3.12+.

---

## Quickstart

### 1. Add your API key

```bash
memex configure
```

This prompts for your [Anthropic API key](https://console.anthropic.com/), validates it, and saves it to `~/.config/memex/config.toml`.

### 2. Bootstrap from your existing codebase

```bash
memex init
```

Scans your repo for architectural decisions already embedded in config files, package manifests, and infrastructure code. Writes initial knowledge records to `knowledge/decisions/`.

Use `--dry-run` to preview what would be extracted without writing any files.

### 3. Pull in decisions from your git history

```bash
memex update
```

Walks your git history and processes merged PRs it hasn't seen yet. Use `--since 2024-01-01` to scope the scan, or `--limit 50` to process the most recent N PRs.

### 4. Commit and push your knowledge records

> **Recommended for existing projects:** before setting up the GitHub Action, commit and push everything `memex init` and `memex update` wrote to `knowledge/decisions/`. This gives the Action a populated baseline and avoids re-extracting decisions that are already indexed.

```bash
git add knowledge/
git commit -m "memex: bootstrap knowledge records from existing codebase"
git push
```

### 5. Index and query

```bash
memex index          # embed all knowledge files (incremental — skips unchanged files)
memex query "why did we switch from SQS to Redis"
```

---

## GitHub Action setup

Add this to `.github/workflows/memex.yml` in any repo you want to capture:

```yaml
name: Memex knowledge extraction

on:
  pull_request:
    types: [closed]

permissions:
  contents: write
  pull-requests: write

jobs:
  extract:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install memex-oss

      - name: Extract knowledge
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_URL: ${{ github.event.pull_request.html_url }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          PR_AUTHOR: ${{ github.event.pull_request.user.login }}
          REPO: ${{ github.repository }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python -m memex.action

      - name: Commit knowledge record and open PR
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          git config user.name "memex-bot"
          git config user.email "memex-bot@users.noreply.github.com"
          git add knowledge/ 2>/dev/null || true
          git diff --cached --quiet && exit 0
          BRANCH="memex/pr-${{ github.event.pull_request.number }}"
          git checkout -b "$BRANCH"
          git commit -m "memex: capture decision from PR #${{ github.event.pull_request.number }}"
          git push origin "$BRANCH"
          gh pr create \
            --title "memex: capture decision from PR #${{ github.event.pull_request.number }}" \
            --body "Knowledge record extracted from [PR #${{ github.event.pull_request.number }}](${{ github.event.pull_request.html_url }}) by memex-bot." \
            --base "${{ github.event.pull_request.base.ref }}" \
            --head "$BRANCH"
```

Add `ANTHROPIC_API_KEY` as a repository secret. That's the only secret required.

> **Required repo setting:** GitHub Actions cannot create pull requests by default. Go to your repo's **Settings → Actions → General → Workflow permissions** and enable **"Allow GitHub Actions to create and approve pull requests"**, then save. Without this, the Action will push the branch but fail to open the PR.

When a decision is found, Memex opens a `memex/pr-{N}` branch and creates a PR targeting your base branch. No knowledge record lands on `main` without a review.

---

## Knowledge record format

Every extracted decision is a plain markdown file committed to `knowledge/decisions/`:

```markdown
---
title: "Switch event queue from SQS to Redis Streams"
date: 2024-11-14
author: "srajan"
source: "https://github.com/acme/api-core/pull/2847"
pr: 2847
repo: "acme/api-core"
confidence: 0.87
tags: []
---

# Switch event queue from SQS to Redis Streams

## Context

We've been hitting SQS's 256KB message size limit consistently as event
payloads grew with per-tenant metadata.

## Decision

Switched event queue from SQS to Redis Streams.

## Alternatives considered

- SNS fanout — filtering model doesn't support per-tenant routing

## Constraints

- SQS 256KB message size limit
- Redis already running for caching (ops overhead minimal)

## Revisit signals

- Revisit when moving to multi-region setup (Redis becomes SPOF)

---

_Extracted by Memex from [PR #2847](https://github.com/acme/api-core/pull/2847) · 2024-11-14_
```

Files are human-readable, git-diffable, and owned by your repo. There is no external database.

---

## What gets extracted (and what doesn't)

Memex is deliberately conservative. The expected discard rate is **70–80% of PRs**.

**Extracted** — PRs with real decision rationale:
- Architecture changes with alternatives discussed
- Technology migrations with reasoning
- Approach choices under constraints

**Skipped silently** — low-signal PRs caught by heuristics before any LLM call:
- Dependency bumps (`bump axios from 1.6.0 to 1.7.2`)
- Style/lint fixes, formatting changes
- WIP/draft PRs, reverts, conventional `chore:` commits

**Nudge comment** — borderline PRs (confidence 0.30–0.40): Memex posts a single comment asking for one sentence of rationale. Posted at most once per PR.

To skip a specific PR from extraction, add the `memex:skip` label before merging.

---

## CLI reference

```
memex configure            Prompt for API key and save to ~/.config/memex/config.toml
memex init [PATH]          Bootstrap knowledge from existing codebase (--dry-run to preview)
memex update               Process merged PRs from git history not yet indexed
  --limit N                Process at most N recent PRs
  --since DATE             Only process PRs merged after DATE (YYYY-MM-DD)
  --repo OWNER/REPO        Target a specific repo (default: current repo)
memex index                Embed knowledge files and write vectors to .memex/index.json
  --force                  Re-embed all files, ignoring the incremental cache
memex query QUESTION       Semantic search over indexed knowledge
  --top N                  Return top N results (default: 3)
```

---

## How extraction works

Memex uses [Claude](https://www.anthropic.com/claude) (`claude-sonnet-4-6`) with [Instructor](https://github.com/jxnl/instructor) for structured extraction, guaranteeing schema compliance with automatic retries.

Each extracted record includes a `confidence` score (0.0–1.0) reflecting how much rationale is actually present in the source PR — not a hallucinated guess. Memex never invents alternatives or constraints that aren't in the text.

Local semantic search uses [fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`) — no second API key, no external service, no data leaves your machine during queries.

---

## Confidence scores

The `confidence` field measures **how much decision rationale is present in the PR or the commits** — not whether the extraction is accurate. A low score means the PR described *what* changed but not *why*.

| Score | Meaning | Action |
|---|---|---|
| `< 0.30` | Barely any rationale | Discarded silently |
| `0.30–0.40` | Decision detected but reasoning thin | Record discarded, nudge comment posted |
| `0.40–0.65` | Some rationale present | Record written with `⚠️ Low confidence` flag |
| `> 0.65` | Clear reasoning captured | Record written normally |

### What drives a low score

- **No alternatives mentioned** — the PR doesn't say what else was considered or ruled out
- **No constraints stated** — no mention of what shaped the decision (deadlines, existing infra, team skills)
- **Vague context** — "we needed a better solution" without explaining what was wrong with the current one
- **Decision-only descriptions** — the PR says what was done but not why

### How to get higher confidence

You don't need to write an essay. One or two sentences covering these points is enough:

**State the reason for the change:**
> "We were hitting SQS's 256KB message size limit as payloads grew."

**Name what you considered and why you didn't choose it:**
> "We looked at SNS fanout but its filtering model doesn't support per-tenant routing."

**Note the key constraints:**
> "Redis was already running for caching, so ops overhead was minimal."

**Flag anything temporary:**
> "Redis becomes a SPOF for both caching and eventing — we'll revisit this when we move to multi-region."

A PR description with these four elements will consistently score above 0.75. A PR that only says "migrate X to Y" will score around 0.40.

---

## Requirements

- Python 3.12+
- `ANTHROPIC_API_KEY` — for extraction (GitHub Action) and `memex init` / `memex update`
- `gh` CLI — installed automatically in GitHub Actions runners; needed locally for `memex update`
- Git — for committing knowledge records from the Action

---

## License

MIT
