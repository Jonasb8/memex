---
title: "Use Anthropic Claude as the LLM backend for knowledge extraction"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.65
tags: ["init"]
---

# Use Anthropic Claude as the LLM backend for knowledge extraction

## Context

Memex needs an LLM to extract and structure institutional knowledge from pull requests. A specific LLM provider must be chosen, which implies a trade-off between capability, cost, API design, and vendor lock-in.

## Decision

Anthropic's Claude API (via the `anthropic` SDK) was chosen as the sole LLM backend for knowledge extraction.

## Alternatives considered

_None recorded_

## Constraints

- ANTHROPIC_API_KEY must be provided as a GitHub Actions secret
- No multi-provider abstraction layer present

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
