---
title: "ADR-0001: Use of fastembed with BAAI/bge-small-en-v1.5 for local embeddings"
date: 2026-04-04
author: "adr"
source: "docs/adr/0001-use-fastembed.md"
repo: "memex"
confidence: 0.85
tags: ["adr"]
---

# ADR-0001: Use of fastembed with BAAI/bge-small-en-v1.5 for local embeddings

## Context

Memex needs to embed knowledge records so users can run semantic search (`memex query`)
locally. The embedding solution must not require a second API key, must not send document
content to an external service, and must work in a CLI context where startup time and
install size matter. Knowledge records contain potentially sensitive internal engineering
decisions, so data privacy is a hard constraint.

## Decision

Use fastembed with the `BAAI/bge-small-en-v1.5` model for all embedding operations.
fastembed runs the model locally in ONNX format (CPU only, no GPU required), downloads
the model once (~130 MB), and returns 384-dimensional vectors. No data leaves the machine
during indexing or querying.

## Alternatives considered

- **VoyageAI** (`voyage-3` and similar) — ruled out because embeddings are computed on
  VoyageAI's servers, meaning every `memex index` and `memex query` call sends document
  content to an external API. This is a privacy concern for internal engineering knowledge.
  Also charges per token. Quality is generally higher (larger dimensional space, better
  benchmarks) but the trade-off was not acceptable given the privacy and cost constraints.
- **sentence-transformers** — runs locally but requires PyTorch as a dependency, which
  significantly increases install size and startup time. fastembed uses ONNX format instead,
  which is faster on CPU and has minimal dependencies.
- **ChromaDB / hosted vector databases** — introduce an external persistence layer and
  server dependency, contradicting the local-first, no-database design principle.

## Constraints

- No API key should be required for semantic search — only extraction (Claude) needs one
- Internal engineering decisions must never be sent to external services during querying
- Must work on CPU without GPU
- Install footprint should stay small for CLI use

## Revisit signals

- If result quality becomes a bottleneck at scale, VoyageAI or a larger BGE variant
  (e.g. `BAAI/bge-large-en-v1.5`, 1024 dimensions) could be evaluated
- If the corpus grows beyond ~5k records, brute-force cosine similarity may need replacing
  with an approximate nearest-neighbour index (e.g. FAISS)

---

_Extracted by Memex from [docs/adr/0001-use-fastembed.md](docs/adr/0001-use-fastembed.md) · 2026-04-04_
