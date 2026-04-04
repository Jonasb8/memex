---
title: "Bot-opened PR for human review of each extracted knowledge record"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.67
tags: ["init"]
---

# Bot-opened PR for human review of each extracted knowledge record

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Automated LLM extraction can produce incorrect or low-quality records. The team needed a mechanism to let engineers validate or reject extracted decisions before they are merged into the main knowledge base.

## Decision

Have memex-bot push each extracted record to a dedicated branch (memex/pr-{N}) and open a pull request for human review, rather than committing directly to the default branch.

## Alternatives considered

_None recorded_

## Constraints

- Adds latency and PR noise to repositories with high merge rates

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
