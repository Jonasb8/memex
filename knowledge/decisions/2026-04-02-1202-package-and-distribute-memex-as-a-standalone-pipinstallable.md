---
title: "Package and distribute memex as a standalone pip-installable tool"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.65
tags: ["init"]
---

# Package and distribute memex as a standalone pip-installable tool

## Context

The tool needs to be usable both as a CLI for local/manual use and as a step inside GitHub Actions CI pipelines without requiring a complex environment setup.

## Decision

The project is packaged as `memex-oss` on PyPI using `hatchling`, exposing a `memex` CLI entry-point and installed with a simple `pip install memex-oss` in CI.

## Alternatives considered

- Docker-based distribution
- GitHub Action published to the Actions Marketplace

## Constraints

- Requires publishing a release to PyPI to update the version used in CI

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
