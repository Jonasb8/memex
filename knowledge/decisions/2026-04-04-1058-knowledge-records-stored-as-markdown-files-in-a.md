---
title: "Knowledge records stored as Markdown files in a versioned knowledge/ directory"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.68
tags: ["init"]
---

# Knowledge records stored as Markdown files in a versioned knowledge/ directory

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Extracted knowledge records need to be persisted, versioned, and human-readable. The team needed a storage format that integrates naturally with existing Git workflows and doesn't require a separate database.

## Decision

Store all knowledge records as structured Markdown files under knowledge/decisions/, committed to the repository itself, rather than using an external database or a SaaS knowledge store.

## Alternatives considered

_None recorded_

## Constraints

- Knowledge records live in the same repo as the code, coupling them tightly to a single repository

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
