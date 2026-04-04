---
title: "Claude (Anthropic) as the LLM for knowledge extraction"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.65
tags: ["init"]
---

# Claude (Anthropic) as the LLM for knowledge extraction

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Memex needs to extract structured decision context from unstructured PR titles, bodies, and review threads. A language model is required to interpret and summarize this natural language content into structured knowledge records.

## Decision

Use Anthropic's Claude API (via the `anthropic` and `instructor` libraries) as the sole LLM backend for extraction, rather than OpenAI or a local model.

## Alternatives considered

_None recorded_

## Constraints

- Requires an Anthropic API key to be provisioned as a GitHub Actions secret
- Teams without an Anthropic account cannot use the tool out of the box

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
