---
title: "Use `instructor` + Pydantic for structured LLM output parsing"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.68
tags: ["init"]
---

# Use `instructor` + Pydantic for structured LLM output parsing

## Context

Raw LLM responses are unstructured text. The system needs to reliably extract typed, validated knowledge records from model output to write them to files.

## Decision

The `instructor>=1.4.0` library is used alongside `pydantic>=2.8.0` to enforce structured, schema-validated output from Claude responses.

## Alternatives considered

- Manual JSON parsing of LLM responses
- LangChain output parsers

## Constraints

- Requires Pydantic v2 (>=2.8.0), a breaking-change boundary from v1

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
