---
title: "Expose memex as both a CLI tool and a GitHub Actions module"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.60
tags: ["init"]
---

# Expose memex as both a CLI tool and a GitHub Actions module

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The tool needs to be usable in automated CI pipelines (for the self-running bot) but also by developers who want to run extraction locally or initialise a new repository.

## Decision

Memex ships a `memex` CLI entry point (via `click`) for interactive/local use, and a separate `memex.action` module invoked directly by `python -m memex.action` in CI.

## Alternatives considered

_None recorded_

## Constraints

- CLI and action entrypoints must share core extraction logic to avoid duplication

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
