---
title: "Switch embed text from raw markdown to structured cleaned representation"
date: 2026-04-10
author: "Jonasb8"
source: "https://github.com/Jonasb8/memex/pull/11"
pr: 11
repo: "Jonasb8/memex"
confidence: 0.55
tags: []
---

# Switch embed text from raw markdown to structured cleaned representation

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The memex system was using raw markdown content for generating embeddings when indexing knowledge records. This meant that semantic search quality was affected by markdown formatting noise and inconsistent structure across records.

## Decision

Embedding now uses a cleaned, structured representation composed of title + context + decision + alternatives + constraints rather than raw markdown, to improve semantic search quality.

## Alternatives considered

- Raw markdown as embed text (previous approach)

## Constraints

- Embed text must be deterministic enough to support incremental indexing via SHA-256 hash comparison

## Revisit signals

_None_

---

_Extracted by Memex from [PR #11](https://github.com/Jonasb8/memex/pull/11) · 2026-04-10_
