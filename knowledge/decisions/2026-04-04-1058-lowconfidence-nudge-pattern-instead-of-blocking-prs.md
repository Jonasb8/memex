---
title: "Low-confidence nudge pattern instead of blocking PRs"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.50
tags: ["init"]
---

# Low-confidence nudge pattern instead of blocking PRs

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Some PRs contain decisions but lack enough rationale for Memex to extract useful context. The team had to choose between blocking the merge, silently skipping the PR, or prompting the author for more context.

## Decision

When a PR appears to contain a decision but lacks sufficient rationale, post a single PR comment asking the author for one sentence of context, rather than blocking the merge or silently discarding the record.

## Alternatives considered

- Silently skipping low-rationale PRs
- Blocking merge until rationale is provided

## Constraints

- Requires PR comment write permissions
- Depends on the author choosing to respond

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
