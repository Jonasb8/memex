---
title: "Package and distribute memex via PyPI (`memex-oss`)"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.62
tags: ["init"]
---

# Package and distribute memex via PyPI (`memex-oss`)

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The GitHub Actions workflow needs to install memex in a clean CI runner environment. A distribution strategy must be chosen that is portable and requires no local repository checkout of memex itself.

## Decision

Memex is packaged as `memex-oss` on PyPI using Hatchling as the build backend, allowing the workflow to install it with a simple `pip install memex-oss`.

## Alternatives considered

- Installing from the Git repo directly
- Bundling the action code inside the workflow

## Constraints

- Version must be bumped and published to PyPI for CI consumers to pick up changes

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
