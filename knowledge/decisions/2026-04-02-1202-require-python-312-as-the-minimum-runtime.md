---
title: "Require Python 3.12 as the minimum runtime"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.55
tags: ["init"]
---

# Require Python 3.12 as the minimum runtime

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The project must choose a minimum Python version that balances modern language features with broad compatibility for users and CI environments.

## Decision

Python 3.12 is set as the minimum required version (`requires-python = '>=3.12'`) and is the pinned version in the CI workflow.

## Alternatives considered

_None recorded_

## Constraints

- Excludes users on Python 3.10 or 3.11 without an upgrade

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
