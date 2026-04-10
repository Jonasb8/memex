---
title: "Expand get_review_comments to fetch all three GitHub PR comment types"
date: 2026-04-10
author: "bennisjonas@gmail.com"
source: "https://github.com/Jonasb8/memex/commit/cb591c4516921463b79e30f770b26cf27340515d"
repo: "Jonasb8/memex"
confidence: 0.55
tags: []
---

# Expand get_review_comments to fetch all three GitHub PR comment types

> ⚠️ **Low confidence** — limited rationale present in source. Verify before relying on this record.

## Context

The existing `get_review_comments` function only retrieved top-level review bodies submitted via GitHub's 'Review changes' flow. This meant inline line-level code comments and general PR thread (issue-level) comments were silently ignored, leaving potentially significant reviewer feedback uncaptured.

## Decision

Refactor `get_review_comments` to make three separate GitHub API calls — one for top-level review bodies (`gh pr view --json reviews`), one for inline review comments (`repos/{repo}/pulls/{pr_number}/comments`), and one for general PR thread comments (`repos/{repo}/issues/{pr_number}/comments`) — aggregating all results into a single deduplicated list.

## Alternatives considered

_None recorded_

## Constraints

- GitHub exposes PR comments across three distinct API endpoints with no single endpoint returning all comment types
- Must use GitHub CLI (`gh`) subprocess calls rather than a direct API client

## Revisit signals

_None_

---

_Extracted by Memex from [commit cb591c45](https://github.com/Jonasb8/memex/commit/cb591c4516921463b79e30f770b26cf27340515d) · 2026-04-10_
