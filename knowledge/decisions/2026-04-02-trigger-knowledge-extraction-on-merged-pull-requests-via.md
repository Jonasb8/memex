---
title: "Trigger knowledge extraction on merged pull requests via GitHub Actions"
date: 2026-04-02
author: "memex-init"
source: "pyproject.toml"
repo: "memex"
confidence: 0.68
tags: ["init"]
---

# Trigger knowledge extraction on merged pull requests via GitHub Actions

## Context

Architectural knowledge needs to be captured continuously as the team ships code. A decision had to be made about when and how to trigger the extraction pipeline without requiring manual intervention.

## Decision

A GitHub Actions workflow is triggered exclusively on `pull_request` `closed` events where `merged == true`, making merged PRs the atomic unit of knowledge capture.

## Alternatives considered

- Scheduled batch scans of the repository
- Commit-level hooks
- Manual CLI invocation only

## Constraints

- Requires GitHub as the VCS host
- Requires `ACCESS_TOKEN_GITHUB` secret with contents write permission

## Revisit signals

_None_

---

_Extracted by Memex from repo scan of `memex` · 2026-04-02_
