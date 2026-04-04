---
title: "Use fastembed for local semantic embeddings"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.60
tags: ["init"]
---

# Use fastembed for local semantic embeddings

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Memex needs to embed knowledge records locally so users can run semantic search (memex query) without sending document content to an external API. A lightweight, dependency-friendly embedding library was needed.

## Decision

Use fastembed for generating embeddings locally, as documented in ADR-0001.

## Alternatives considered

_None recorded_

## Constraints

- Local execution requirement means embeddings run on the developer's machine, not a hosted service

## Revisit signals

- ADR-0001 notes 'I must learn more about embeddings', suggesting the author was still evaluating the domain

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
