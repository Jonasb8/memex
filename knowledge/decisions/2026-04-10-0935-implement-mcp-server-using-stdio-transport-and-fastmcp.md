---
title: "Implement MCP server using stdio transport and FastMCP SDK for AI agent integration"
date: 2026-04-10
author: "Jonasb8"
source: "https://github.com/Jonasb8/memex/pull/14"
pr: 14
repo: "Jonasb8/memex"
confidence: 0.88
tags: []
---

# Implement MCP server using stdio transport and FastMCP SDK for AI agent integration

## Context

The memex CLI already provides semantic search over a local knowledge index for human users, but AI coding agents (Claude Code, Cursor, Copilot, Windsurf) need a different integration path — some cannot run arbitrary bash commands, and all benefit from auto-discoverable tools rather than prompt-based invocation. An MCP (Model Context Protocol) server would expose the knowledge index natively to these agents.

## Decision

Implement a stdio-transport MCP server using the official `mcp` SDK's `FastMCP` class, exposing three tools (`memex_query`, `memex_get_decision`, `memex_list_recent`) that reuse existing CLI functions with no duplication, launchable via `memex serve` or `python -m memex.mcp_server`.

## Alternatives considered

- Network/HTTP transport (rejected in favour of stdio — no port, no persistent process, launched as subprocess by editor)
- Third-party MCP dependencies (rejected — official `mcp` SDK used instead)
- Higher default min_score for memex_query (CLI uses 0.7; agents get 0.5 so borderline matches are surfaced with confidence score)

## Constraints

- Must support agents that cannot run arbitrary bash (Cursor, Copilot)
- No network port or persistent process — must be launchable as a subprocess by the editor
- Must reuse existing functions from cli.py with zero duplication
- Early listing in MCP registries is prioritised over completeness
- Must use official mcp SDK (mcp>=1.0.0), no third-party alternatives

## Revisit signals

- Being listed in MCP registries early matters more than being listed complete — implies feature set may expand later

---

_Extracted by Memex from [PR #14](https://github.com/Jonasb8/memex/pull/14) · 2026-04-10_
