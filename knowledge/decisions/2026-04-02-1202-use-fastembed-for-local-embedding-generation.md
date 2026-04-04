---
title: "Use `fastembed` for local embedding generation"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.50
tags: ["init"]
---

# Use `fastembed` for local embedding generation

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The system likely needs to compute vector embeddings for knowledge records to support similarity search or deduplication without relying on an external embedding API.

## Decision

The `fastembed>=0.3.0` library is used for embedding generation, running models locally rather than calling a remote embedding endpoint.

## Alternatives considered

- OpenAI Embeddings API
- Anthropic embeddings (not offered)

## Constraints

- Requires downloading model weights at runtime or install time
- Adds a non-trivial dependency footprint (numpy is a co-dependency)

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
