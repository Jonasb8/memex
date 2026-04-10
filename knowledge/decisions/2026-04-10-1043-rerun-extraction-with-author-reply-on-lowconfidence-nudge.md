---
title: "Re-run extraction with author reply on low-confidence nudge comments"
date: 2026-04-10
author: "bennisjonas@gmail.com"
source: "https://github.com/Jonasb8/memex/commit/cd30d56bbfda29c9f4157d686627d439dc04c870"
repo: "Jonasb8/memex"
confidence: 0.60
tags: []
---

# Re-run extraction with author reply on low-confidence nudge comments

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

When Memex detects a PR that looks like it contains a decision but lacks sufficient rationale, it posts a comment asking the author for one sentence of context. Previously, that reply was not acted upon — extraction was only triggered on merged PRs.

## Decision

Extend the GitHub Actions workflow to also trigger on `issue_comment` events, passing the comment body and author as environment variables so that when the PR author replies to a low-confidence nudge, Memex re-runs extraction with the reply and writes the knowledge record.

## Alternatives considered

_None recorded_

## Constraints

- The workflow must support two distinct trigger paths (merged PR and issue comment) using the same extraction job
- PR number must be resolved from either the pull_request or issue event context depending on trigger type
- The git branch checkout step must handle the case where the branch already exists (from the initial low-confidence pass)

## Revisit signals

_None_

---

_Extracted by Memex from [commit cd30d56b](https://github.com/Jonasb8/memex/commit/cd30d56bbfda29c9f4157d686627d439dc04c870) · 2026-04-10_
