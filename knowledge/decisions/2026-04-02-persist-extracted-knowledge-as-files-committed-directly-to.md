---
title: "Persist extracted knowledge as files committed directly to the repository"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.68
tags: ["init"]
---

# Persist extracted knowledge as files committed directly to the repository

## Context

Extracted knowledge records need to be stored somewhere durable and accessible to the team. Options include external databases, wikis, or keeping records inside the repository itself.

## Decision

Knowledge records are written to a `knowledge/` directory inside the repository and committed by a bot user (`memex-bot`) as part of the CI workflow.

## Alternatives considered

- External database or vector store
- GitHub Wiki
- Dedicated knowledge-base SaaS

## Constraints

- Requires `contents: write` permission in the workflow
- Knowledge history is tied to Git history of the repo

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
