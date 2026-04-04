# Memex — Claude Code context

This file gives Claude Code everything it needs to work autonomously on this codebase.
Read it fully before making any changes.

---

## What this project is

Memex is an open-source framework that extracts, structures, and makes queryable the
institutional knowledge of engineering teams. It hooks into GitHub pull requests,
incident post-mortems, and ADRs — artifacts that already exist — and captures decision
context automatically, without requiring any behavior change from engineers.

The core insight: knowledge lives in PRs, review threads, and post-mortems. It just
isn't structured or queryable. Memex makes it both.

**This is not a documentation tool.** Engineers do not write anything new. Extraction
is fully automatic and passive.

---

## Current phase: MVP (Phase 1)

We are building only the following four things. Do not add anything else without
explicit instruction.

1. **GitHub Action** — triggers on PR merge, extracts decision context, commits a `.md` file
2. **CLI** — `memex index` and `memex query` for local semantic search over knowledge files
3. **ADR parser** — scans repo on install for existing ADR files and indexes them
4. **Low-confidence nudge** — posts a single GitHub PR comment asking for rationale when confidence is borderline

Everything else (web UI, cross-repo search, Slack integration, cloud backend, enterprise
features) is Phase 2 or later. Do not build it, stub it, or reference it in code.

---

## File structure

```
memex/
├── .github/
│   └── workflows/
│       └── memex.yml          # GitHub Action definition
├── memex/
│   ├── __init__.py
│   ├── schema.py              # Pydantic models — KnowledgeRecord, ExtractionResult
│   ├── extractor.py           # LLM extraction pipeline (LiteLLM + Instructor)
│   ├── writer.py              # Renders KnowledgeRecord to .md and commits it
│   ├── action.py              # GitHub Action entry point — reads env vars, orchestrates
│   ├── adr.py                 # ADR parser — find_adr_files, parse_adr, index_adrs
│   ├── cli.py                 # Click CLI — `memex index` and `memex query`
│   ├── init.py                # `memex init` — bootstrap from repo scan
│   └── update.py              # `memex update` — incremental extraction from git history
├── tests/
│   └── ...
├── pyproject.toml
└── README.md
```

Knowledge records are written to:
```
knowledge/
└── decisions/
    └── 2024-11-14-migrate-billing-store-to-postgresql.md
```

The index cache lives at:
```
.memex/
└── index.json                 # embedding vectors + metadata, git-ignored
```

---

## Tech stack — do not deviate from this

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.12+ | Best LLM ecosystem |
| LLM — extraction | `claude-sonnet-4-6` via `anthropic` SDK | Best structured output quality |
| LLM — embeddings | `voyage-3-lite` via `anthropic` SDK | Same SDK, same API key, no OpenAI account |
| Structured output | `instructor` + `pydantic` | Guaranteed schema compliance, auto-retry |
| Vector search | `numpy` cosine similarity over `index.json` | No database needed at MVP scale (<5k records) |
| CLI | `click` | Standard, simple |
| GitHub API | `gh` CLI in Actions, `PyGithub` if needed in Python | Already available in Actions runner |

**There is no database.** Knowledge records are markdown files in the repo.
The index is a JSON file. Do not introduce SQLite, PostgreSQL, Redis, or any other
persistence layer in Phase 1.

**There is no server.** The Action runs in GitHub's infrastructure. The CLI runs
locally. Do not introduce FastAPI, Flask, or any web framework in Phase 1.

**One API key.** Everything goes through `ANTHROPIC_API_KEY`. Do not introduce
OpenAI, Cohere, or any other LLM provider dependency.

---

## Core data model

```python
class KnowledgeRecord(BaseModel):
    title: str                          # "Migrate billing store to PostgreSQL"
    context: str                        # 2-3 sentences: what prompted this decision
    decision: str                       # one sentence: what was decided
    alternatives_considered: list[str]  # options explicitly discussed or ruled out
    constraints: list[str]              # technical/org/time constraints that shaped it
    revisit_signals: list[str]          # "temporary until X", "revisit when Y"
    confidence: float                   # 0.0–1.0: how much rationale is actually present
    confidence_rationale: str           # one sentence explaining the score

class ExtractionResult(BaseModel):
    contains_decision: bool             # is there a real decision here?
    record: Optional[KnowledgeRecord]   # null if contains_decision is False
```

**Confidence thresholds:**
- `>= 0.80` (`high`) — publish record normally
- `0.65–0.80` (`medium`) — publish record with `⚠️ Low confidence` flag in markdown
- `< 0.65` (`low`) — publish record with `⚠️ Low confidence` flag in markdown

---

## Extraction pipeline — exact sequence

When a PR merges, `action.py` runs this sequence:

1. Read `PR_TITLE`, `PR_BODY`, `PR_URL`, `PR_NUMBER`, `PR_AUTHOR`, `REPO` from env
2. Fetch review comments via `gh pr view {number} --json reviews`
3. Fetch changed files via `gh pr view {number} --json files`
4. **ADR files in this PR** — for each changed `.md` in `docs/adr/`, `docs/decisions/`,
   `decisions/`, or `adr/`: call `parse_adr(path)` and write with `tags: ["adr"]`
5. Run `is_low_signal(title, body)` — regex check for dependency bumps, style fixes, etc.
   If true → exit 0, log "low-signal PR skipped"
6. Call `extract(title, body, review_comments)` — Instructor + Claude Sonnet
7. If `contains_decision` is False → exit 0 silently
7b. If `contains_decision` is True but `confidence < 0.65` → discard silently
8. If `contains_decision` is True:
   - Scan PR body + review comments for `ADR-NNN` patterns; glob matching knowledge records
     into a `related` list
   - Call `write_record(...)` with `related=related` → renders markdown, writes to `knowledge/decisions/`
   - Git commit and push the new file

**The nudge comment is posted at most once per PR. Never post it twice.**

---

## Markdown output format

Every knowledge record must follow this exact format:

```markdown
---
title: "Migrate billing store to PostgreSQL"
date: 2024-11-14
author: "srajan"
source: "https://github.com/acme/api-core/pull/2847"
pr: 2847
repo: "acme/api-core"
confidence: 0.87
tags: []
related: ["knowledge/decisions/2024-01-10-adr-041-use-postgresql.md"]
---

# Migrate billing store to PostgreSQL

## Context

...2–3 sentences...

## Decision

...one sentence...

## Alternatives considered

- CockroachDB — ruled out due to zero ops experience on the team
- Keeping MongoDB — rejected after the billing incident

## Constraints

- Team has no CockroachDB experience
- Migration must complete before Q4 billing cycle

## Revisit signals

- None

---

_Extracted by Memex from [PR #2847](https://github.com/acme/api-core/pull/2847) · 2024-11-14_
```

The frontmatter fields are the machine-readable contract. Do not add or remove fields
without updating the indexer and CLI accordingly.

- `tags` — always present, defaults to `[]`. ADR-sourced records carry `["adr"]`; init records carry `["init"]`.
- `related` — optional. Only written when non-empty. Contains paths to related knowledge records (e.g. when a PR cites an ADR number).

---

## CLI behaviour

```bash
memex index      # embed all .md files in knowledge/, write to .memex/index.json
memex query "why did we move off MongoDB"   # cosine similarity search, top 3 results
```

`memex index` should be incremental — only embed files not already in `index.json`.
Do not re-embed records that haven't changed.

`memex query` output format:
```
Results for: why did we move off MongoDB
──────────────────────────────────────────────────────

  1. Migrate billing store to PostgreSQL
     Unbounded schema flexibility was causing silent data corruption in the billing...
     knowledge/decisions/2024-11-14-migrate-billing-store-to-postgresql.md  (score 0.91)

  2. ...
```

---

## ADR parser

Implemented in `memex/adr.py`. Three entry points — all use the same shared logic:

| Entry point | When it runs |
|---|---|
| `memex init` | Always — ADRs are part of the bootstrap scan |
| `memex index --include-adrs` | On demand, safe to run repeatedly (deduped by `source:` field) |
| GitHub Action | Automatically when a merged PR adds/modifies a file in an ADR directory |

**Scanning:** `find_adr_files(root)` globs `docs/adr/`, `docs/decisions/`, `decisions/`, `adr/`.
Accepts `.md` files matching `NNNN-*.md` OR containing both `## Status` and `## Decision` headers.

**Parsing:** `parse_adr(path)` maps Nygard sections to `KnowledgeRecord`:

| ADR section | Field |
|---|---|
| H1 title | `title` |
| `## Context` | `context` (first 3 sentences) |
| `## Decision` | `decision` (first sentence) |
| `## Consequences` | `constraints` (bullet lines); lines with "revisit/until/when/temporary" → `revisit_signals` |
| `## Status` | `confidence`: Accepted→0.85, Proposed→0.70, Deprecated/Superseded→0.60 |

Returns `None` if `## Decision` is empty — never writes an empty record.

**Deduplication:** `already_indexed(adr_path, output_dir)` checks if any existing record has a
`source:` frontmatter value matching the ADR path. Re-running `index_adrs` is always safe.

**Cross-referencing:** When a PR body or review comment contains `ADR-NNN`, `action.py` globs
`knowledge/decisions/` for matching records and writes them to the `related:` frontmatter field
of the PR's knowledge record.

---

## Agent rules — cross-cutting concerns

Before implementing any feature that touches knowledge record creation, extraction logic,
frontmatter fields, or file I/O, **pause and check whether the change also affects these
three existing entry points**:

| Entry point | File | Triggers |
|---|---|---|
| `memex init` | `memex/init.py` + `cli.py` | Manual bootstrap from repo scan |
| `memex update` | `memex/update.py` + `cli.py` | Incremental git history extraction |
| GitHub Action | `memex/action.py` | Every merged PR |

If the change is relevant to one or more of these and the spec doesn't explicitly say to
update them, **ask for clarification before proceeding**. Examples that require a check:

- Adding a new frontmatter field → does the indexer need updating? Does `already_indexed` need updating?
- Changing `write_record` signature → are all three entry points passing the right args?
- Changing confidence thresholds or discard logic → should the same logic apply in `update.py`?
- Adding a new source type (e.g. incident reports) → should it be wired into `init`, `update`, and the Action?

Do not silently skip one entry point to keep the diff small. Inconsistency across entry points
is harder to debug than a slightly larger PR.

---

## Quality rules — enforce these strictly

- **Null extraction is correct behaviour.** Most PRs should produce nothing.
  The discard rate should be 70–80%. A sparse graph beats a noisy one.
- **Never invent rationale.** If the PR description says nothing about why,
  `confidence` should be low and `contains_decision` may be False. Do not
  fill in plausible-sounding alternatives that aren't in the source text.
- **Every record must have a source URL.** No orphaned records without a
  traceable link back to the original PR or ADR.
- **One nudge comment per PR maximum.** Check for an existing Memex comment
  before posting. The comment must include the suppression instruction.
- **Do not commit to main directly in tests.** The writer and action tests
  should use a temp directory, never the actual repo.

---

## Environment variables (GitHub Action)

| Variable | Source | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | GitHub Secret | Required. Anthropic API key for Claude + Voyage |
| `PR_TITLE` | `github.event.pull_request.title` | PR title |
| `PR_BODY` | `github.event.pull_request.body` | PR description |
| `PR_URL` | `github.event.pull_request.html_url` | Full URL to PR |
| `PR_NUMBER` | `github.event.pull_request.number` | PR number |
| `PR_AUTHOR` | `github.event.pull_request.user.login` | GitHub username |
| `REPO` | `github.repository` | `owner/repo` format |
| `GH_TOKEN` | `secrets.GITHUB_TOKEN` | For posting comments and committing |

---

## Testing approach

- Unit test `extractor.py` with fixture PR texts — known high-signal PRs should
  return `contains_decision=True`, dependency bumps should return `None`
- Unit test `writer.py` with a mock `KnowledgeRecord` — assert frontmatter is valid,
  assert file is written to the correct path
- Unit test `cli.py` index/query cycle with a small fixture knowledge directory
- Do not make real LLM calls in tests — mock the `instructor` client
- Use `pytest` and `pytest-mock`

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## What good looks like — example high-signal PR

```
Title: Switch event queue from SQS to Redis Streams

Body:
We've been hitting SQS's 256KB message size limit consistently as event payloads
grew. We considered SNS fanout but the filtering model doesn't give us what we need
for per-tenant routing. Redis Streams gives us larger payloads, consumer groups for
exactly-once processing, and we already run Redis for caching so ops overhead is
minimal. The main risk is that Redis becomes a SPOF for both caching and eventing —
we're accepting that for now and will revisit when we move to a multi-region setup.
```

This should produce confidence ~0.85 and capture:
- `decision`: switched event queue from SQS to Redis Streams
- `alternatives_considered`: SNS fanout
- `constraints`: SQS 256KB limit, existing Redis dependency, per-tenant routing requirement
- `revisit_signals`: revisit when moving to multi-region

---

## What bad looks like — example low-signal PR

```
Title: bump axios from 1.6.0 to 1.7.2
Body: Bumps axios from 1.6.0 to 1.7.2
```

This should be caught by `is_low_signal()` before any LLM call is made.
Confidence 0.0, no record written, no comment posted.

---

## Decisions already made — do not relitigate

These were explicitly chosen and the reasoning is documented above:

- Python over TypeScript — LLM ecosystem advantage
- `fastembed` (`BAAI/bge-small-en-v1.5`) for local embeddings — no API key required, no data leaves the machine during queries
- `numpy` over ChromaDB — no database needed at this scale
- `instructor` over raw JSON parsing — reliability, not convenience
- Markdown files over SQLite — git-native, diffable, user-owned
- `claude-sonnet-4-6` for extraction — best structured output quality
- Opt-out extraction (with `memex:skip` label) over opt-in — coverage beats precision

If you believe one of these decisions should be revisited, say so explicitly and
explain why. Do not silently make a different choice.

---

## What to build next (in order)

If you are picking up this project fresh, work in this sequence:

1. `memex/schema.py` — define `KnowledgeRecord` and `ExtractionResult`
2. `memex/extractor.py` — `is_low_signal()` + `extract()` with Instructor
3. `memex/writer.py` — `render_markdown()` + `write_record()`
4. `memex/action.py` — wire everything together, handle env vars and nudge comment
5. `.github/workflows/memex.yml` — the Action definition
6. `memex/cli.py` — `memex index` and `memex query`
7. `tests/` — unit tests for each module with mocked LLM calls
8. `memex/adr.py` — ADR parser; wire into `init`, `index --include-adrs`, and `action.py` ✅
9. `README.md` — installation instructions, one-minute quickstart

Do not start step N+1 until step N has tests passing.