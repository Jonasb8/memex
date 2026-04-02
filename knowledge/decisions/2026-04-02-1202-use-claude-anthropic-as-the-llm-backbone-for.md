---
title: "Use Claude (Anthropic) as the LLM backbone for knowledge extraction"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.65
tags: ["init"]
---

# Use Claude (Anthropic) as the LLM backbone for knowledge extraction

## Context

The system needs to extract structured architectural decisions from pull request text and repository snapshots. An LLM is required to interpret free-form engineering prose and produce structured output.

## Decision

Anthropic's Claude API is used as the sole LLM provider for knowledge extraction, via the `anthropic>=0.34.0` dependency.

## Alternatives considered

_None recorded_

## Constraints

- Requires an ANTHROPIC_API_KEY secret to be configured in the GitHub repository
- Ties the tool to a commercial, closed-source API

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
