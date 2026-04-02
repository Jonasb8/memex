---
title: "Store knowledge records as files committed directly into the repository"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.72
tags: ["init"]
---

# Store knowledge records as files committed directly into the repository

## Context

Extracted architectural decisions need to be persisted and made accessible to the team. The system must decide between an external store (database, SaaS) and an in-repo approach.

## Decision

Knowledge records are written as files under `knowledge/decisions/` and committed to the repository by a bot user (`memex-bot`) via the CI workflow.

## Alternatives considered

- External database or vector store
- GitHub Issues or wiki pages

## Constraints

- Requires `contents: write` GitHub Actions permission
- Requires a personal access token (ACCESS_TOKEN_GITHUB) to push from CI

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
