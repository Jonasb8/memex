---
title: "Python-only implementation distributed as a pip-installable package"
date: 2026-04-04
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.60
tags: ["init"]
---

# Python-only implementation distributed as a pip-installable package

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

Memex needs to be easy to adopt in any GitHub repository without requiring Docker, a compiled binary, or a bespoke GitHub Action container. The target audience is engineering teams already using Python tooling.

## Decision

Implement the entire tool in Python 3.12 and distribute it as a standard PyPI package (memex-oss), installed with a single `pip install` in both the CLI and CI contexts.

## Alternatives considered

_None recorded_

## Constraints

- Python 3.12+ is required, which may block teams on older runtimes
- CI jobs must include a Python setup step

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-04_
