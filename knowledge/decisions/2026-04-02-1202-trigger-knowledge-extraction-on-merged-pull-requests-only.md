---
title: "Trigger knowledge extraction on merged pull requests only"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.70
tags: ["init"]
---

# Trigger knowledge extraction on merged pull requests only

## Context

The system needs a trigger point for when to extract and persist an architectural decision. Running on every push or on open PRs would produce noise; only merged PRs represent accepted, stable decisions.

## Decision

The GitHub Actions workflow is triggered exclusively on `pull_request` events of type `closed` with an additional `if: github.event.pull_request.merged == true` gate.

## Alternatives considered

- Trigger on every push to main
- Trigger on PR open/update for draft capture

## Constraints

- Decisions made outside of PRs (e.g. direct commits) are not captured

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
