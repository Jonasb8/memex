---
title: "Use structured embed text (title + context + decision + alternatives + constraints) instead of raw markdown for semantic search"
date: 2026-04-10
author: "Jonasb8"
source: "https://github.com/Jonasb8/memex/pull/11"
pr: 11
repo: "Jonasb8/memex"
confidence: 0.55
tags: []
---

# Use structured embed text (title + context + decision + alternatives + constraints) instead of raw markdown for semantic search

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The memex system was previously embedding raw markdown content for knowledge records, which reduced semantic search quality. The PR introduces a cleaned, structured representation for embedding to improve retrieval relevance.

## Decision

Embedding now uses a structured representation composed of title, context, decision, alternatives, and constraints fields rather than raw markdown, and query excerpts are drawn from structured sections (## Context and ## Decision) rather than the first raw paragraph.

## Alternatives considered

_None recorded_

## Constraints

_None recorded_

## Revisit signals

_None_

---

_Extracted by Memex from [PR #11](https://github.com/Jonasb8/memex/pull/11) · 2026-04-10_
