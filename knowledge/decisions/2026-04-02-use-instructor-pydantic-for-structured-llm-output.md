---
title: "Use `instructor` + Pydantic for structured LLM output"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.70
tags: ["init"]
---

# Use `instructor` + Pydantic for structured LLM output

## Context

Raw LLM responses are free-form text. To reliably extract structured knowledge records, the output must be coerced into a defined schema. The team needed a way to enforce typed, validated output from the Claude API.

## Decision

The `instructor` library (built on Pydantic) is used to enforce structured, validated output from the LLM, with schemas defined via Pydantic v2 models in `schema.py`.

## Alternatives considered

- Ad-hoc JSON parsing of LLM responses
- LangChain output parsers

## Constraints

- Requires Pydantic v2 (>=2.8.0)
- Tied to instructor's compatibility with the Anthropic SDK

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
