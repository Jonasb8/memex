---
title: "Change GitHub Action to create PRs instead of direct commits for knowledge records"
date: 2026-04-03
author: "bennisjonas@gmail.com"
source: "https://github.com/Jonasb8/memex/commit/8fdbac445cdd693c185811d0e2377aef72f11831"
repo: "Jonasb8/memex"
confidence: 0.75
tags: []
---

# Change GitHub Action to create PRs instead of direct commits for knowledge records

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The existing memex GitHub Action was directly committing and pushing knowledge records to the repository whenever a PR was merged. This workflow needed to accommodate review and visibility of extracted knowledge before it lands in the main branch.

## Decision

Modified the GitHub Action workflow to create a branch (memex/pr-{N}) and open a pull request for each knowledge record extraction, instead of directly committing to the base branch.

## Alternatives considered

- Direct commit and push to the base branch (previous implementation)

## Constraints

_None recorded_

## Revisit signals

_None_

---

_Extracted by Memex from [commit 8fdbac44](https://github.com/Jonasb8/memex/commit/8fdbac445cdd693c185811d0e2377aef72f11831) · 2026-04-03_
