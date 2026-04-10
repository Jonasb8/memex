"""MCP server for Memex — exposes institutional knowledge to AI coding agents.

Three tools:
  memex_query        — semantic search over indexed decisions
  memex_get_decision — fetch a specific record by path/slug
  memex_list_recent  — browse recent decisions, optionally filtered by domain

Start with: memex serve
Configure in .mcp.json / claude_desktop_config.json:
  {"mcpServers": {"memex": {"command": "memex", "args": ["serve"], "cwd": "/your/repo"}}}
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .cli import (
    KNOWLEDGE_DIR,
    cosine_similarity,
    embed,
    extract_confidence,
    load_index,
)

mcp = FastMCP("memex")

_NO_INDEX = (
    "No index found. Run `memex index` first to embed your knowledge records."
)


@mcp.tool()
def memex_query(question: str, top: int = 3, min_score: float = 0.5) -> str:
    """Semantic search over indexed architectural decisions.

    Returns the most relevant decisions matching the question.
    Low-confidence records are included with their confidence score surfaced
    so you can hedge your answer. Default min_score is 0.5 (lower than the CLI
    default of 0.7 — agents benefit from seeing borderline matches).
    Run `memex index` first if the index is empty.
    """
    index = load_index()
    if not index:
        return _NO_INDEX

    [query_embedding] = embed([question])

    scored = [
        (cosine_similarity(query_embedding, entry["embedding"]), entry)
        for entry in index.values()
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [(s, e) for s, e in scored if s >= min_score][:top]

    if not results:
        return (
            f"No results above similarity threshold {min_score:.2f}. "
            "Try a lower threshold or rephrase your question."
        )

    lines = [f"Results for: {question}\n"]
    for i, (score, entry) in enumerate(results, 1):
        confidence = entry.get("confidence", 1.0)
        if confidence < 0.65:
            conf_note = " ⚠️ limited rationale"
        elif confidence < 0.80:
            conf_note = " 💡 partial rationale"
        else:
            conf_note = ""

        lines.append(f"{i}. {entry['title']}  [score {score:.2f}{conf_note}]")
        if entry.get("excerpt"):
            lines.append(f"   {entry['excerpt'][:300]}")
        lines.append(f"   {entry['path']}\n")

    return "\n".join(lines)


@mcp.tool()
def memex_get_decision(id: str) -> str:
    """Fetch the full text of a specific decision record by path or title slug.

    `id` can be an exact file path
    (e.g. 'knowledge/decisions/2024-11-14-migrate-billing.md'),
    a filename fragment (e.g. 'migrate-billing'), or any partial path suffix.
    Returns the raw markdown including frontmatter.
    """
    # Exact path first
    exact = Path(id)
    if exact.exists():
        return exact.read_text()

    # Match against indexed paths
    index = load_index()
    for path_str in index:
        if id in path_str:
            p = Path(path_str)
            if p.exists():
                return p.read_text()

    # Fallback: glob knowledge dir directly (works even without an index)
    matches = list(KNOWLEDGE_DIR.rglob(f"*{id}*.md"))
    if matches:
        return matches[0].read_text()

    return (
        f"No record found matching '{id}'. "
        "Use memex_query to search by topic, then pass the returned path here."
    )


@mcp.tool()
def memex_list_recent(domain: str = "", limit: int = 10) -> str:
    """List recent architectural decisions, optionally filtered by domain keyword.

    `domain` is matched case-insensitively against each record's title and excerpt
    (e.g. 'auth', 'database', 'api', 'infra'). Returns up to `limit` records
    sorted most-recent first (by filename date).
    """
    index = load_index()
    if not index:
        return _NO_INDEX

    entries = list(index.values())

    if domain:
        kw = domain.lower()
        entries = [
            e for e in entries
            if kw in e.get("title", "").lower() or kw in e.get("excerpt", "").lower()
        ]
        if not entries:
            return f"No decisions found matching domain '{domain}'."

    def _date_key(entry: dict) -> str:
        stem = Path(entry["path"]).stem
        return stem[:10] if len(stem) >= 10 else "0000-00-00"

    entries.sort(key=_date_key, reverse=True)
    entries = entries[:limit]

    header = "Recent decisions"
    if domain:
        header += f" in '{domain}'"
    header += f" ({len(entries)} shown):\n"

    lines = [header]
    for entry in entries:
        confidence = entry.get("confidence", 1.0)
        conf_note = " ⚠️" if confidence < 0.65 else ""
        date_str = _date_key(entry)
        lines.append(f"  {date_str}  {entry['title']}{conf_note}")
        lines.append(f"             {entry['path']}\n")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
