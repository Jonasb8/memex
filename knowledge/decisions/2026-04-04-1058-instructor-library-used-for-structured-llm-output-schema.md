---
title: "instructor library used for structured LLM output (schema enforcement)"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.55
tags: ["init"]
---

# instructor library used for structured LLM output (schema enforcement)

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Raw LLM responses are free-form text, but Memex needs consistently structured records (title, context, decision, confidence, etc.) that match a defined schema. A mechanism to enforce output structure is required.

## Decision

Use the `instructor` library on top of the Anthropic client to enforce Pydantic-validated structured outputs from Claude, rather than parsing free-form JSON manually.

## Alternatives considered

_None recorded_

## Constraints

- Ties output validation to the instructor + Pydantic ecosystem

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
