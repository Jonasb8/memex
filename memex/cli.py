import json
import click
import numpy as np
from pathlib import Path
from anthropic import Anthropic

from .config import load_api_key, save_api_key, key_source, MissingApiKeyError, CONFIG_FILE

KNOWLEDGE_DIR = Path("knowledge")
INDEX_FILE = Path(".memex/index.json")


def _anthropic_client() -> Anthropic:
    """Return an Anthropic client, with a clean error if the key is missing."""
    try:
        return Anthropic(api_key=load_api_key())
    except MissingApiKeyError as e:
        raise click.ClickException(str(e)) from e


_embedder = None

def _get_embedder():
    """Return a cached fastembed TextEmbedding model (downloads once, ~130 MB)."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts locally using fastembed — no API key required."""
    return [emb.tolist() for emb in _get_embedder().embed(texts)]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {}


def save_index(index: dict) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def extract_title(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("title:"):
            return line.replace("title:", "").strip().strip('"')
    return "Unknown"


def extract_confidence(content: str) -> float:
    for line in content.splitlines():
        if line.startswith("confidence:"):
            try:
                return float(line.replace("confidence:", "").strip())
            except ValueError:
                pass
    return 1.0


def _extract_md_section(content: str, header: str) -> str:
    """Extract the body of a named ## section from markdown content."""
    import re
    pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\n---|\Z)"
    m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def build_embed_text(content: str) -> str:
    """Build a clean semantic string for embedding — strips YAML, warnings, and markdown noise."""
    import re

    def _bullets(text: str) -> list[str]:
        items = []
        for line in text.splitlines():
            m = re.match(r"^\s*[-*]\s+(.+)", line)
            if m:
                item = m.group(1).strip()
                if not item.startswith("_"):  # skip "_None recorded_" placeholders
                    items.append(item)
        return items

    title = extract_title(content)
    context = _extract_md_section(content, "Context")
    decision = _extract_md_section(content, "Decision")
    alts = _bullets(_extract_md_section(content, "Alternatives considered"))
    constraints = _bullets(_extract_md_section(content, "Constraints"))

    parts = [p for p in [title, context, decision] if p]
    if alts:
        parts.append("Alternatives: " + "; ".join(alts))
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints))

    return "\n".join(parts) if parts else content


def extract_excerpt(content: str) -> str:
    """Pull a human-readable preview from the Context and Decision sections."""
    context = _extract_md_section(content, "Context")
    decision = _extract_md_section(content, "Decision")

    if context or decision:
        if context:
            # Truncate at a word boundary so we don't cut mid-word
            if len(context) > 300:
                context = context[:300].rsplit(None, 1)[0] + "…"
        excerpt = context
        if decision:
            separator = " — " if excerpt else ""
            excerpt += separator + decision  # decisions are one sentence — show in full
        return excerpt

    # Fallback: first non-blank, non-heading, non-blockquote line after frontmatter
    in_frontmatter = False
    fm_count = 0
    for line in content.splitlines():
        if line.strip() == "---":
            fm_count += 1
            in_frontmatter = fm_count < 2
            continue
        if in_frontmatter:
            continue
        if line.strip() and not line.startswith("#") and not line.startswith(">"):
            return line[:400]
    return ""


def _strip_markdown(text: str) -> str:
    """Remove common markdown syntax for clean terminal display."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # italic
    text = re.sub(r"`(.+?)`", r"\1", text)           # inline code
    text = re.sub(r"^>\s*", "", text)                # blockquote
    return text.strip()


def _wrap(text: str, width: int, indent: str) -> str:
    """Wrap text to width, prefixing every line with indent."""
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


@click.group()
def cli():
    """Memex — query your team's institutional knowledge."""
    pass


@cli.command()
def configure():
    """Save your Anthropic API key for all memex commands.

    The key is written to ~/.config/memex/config.toml (chmod 600).
    The environment variable ANTHROPIC_API_KEY takes precedence if set.

    Semantic search (memex index / memex query) runs locally via fastembed
    — no second API key needed.
    """
    current = key_source()
    if current != "not set":
        click.echo(f"Current key source: {current}")

    anthropic_key = click.prompt(
        "Anthropic API key",
        hide_input=True,
        prompt_suffix=" (sk-ant-...): ",
    ).strip()

    if not anthropic_key.startswith("sk-"):
        raise click.ClickException(
            "That doesn't look like a valid Anthropic API key (should start with 'sk-')."
        )

    click.echo("Validating key...", nl=False)
    try:
        _client = Anthropic(api_key=anthropic_key)
        _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        click.echo(" ✓")
    except Exception as exc:
        raise click.ClickException(f"Key rejected: {exc}") from exc

    save_api_key(anthropic_key)
    click.echo(f"\nKey saved to {CONFIG_FILE}")
    click.echo("You're all set. Try: memex init")


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--dry-run", is_flag=True, help="Print what would be written without writing.")
def init(path, dry_run):
    """Bootstrap the knowledge graph from this repo's current state.

    Scans package manifests, infrastructure files, and directory structure,
    then asks Memex to identify architectural decisions already embedded
    in the codebase. Records are written to knowledge/decisions/ and tagged [init].

    Example: memex init
             memex init /path/to/other-repo
    """
    from .init import scan_repo, extract_architecture, write_init_record, detect_repo_name

    root = Path(path).resolve()
    repo_name = detect_repo_name(root)

    click.echo(f"Scanning {root} ({repo_name})...")
    signals = scan_repo(root)

    file_list = [k for k in signals if k != "__directory_structure__"]
    click.echo(f"Found {len(file_list)} signal file(s): {', '.join(file_list)}")
    click.echo("Asking Memex to extract architectural decisions...")

    records = extract_architecture(signals, repo_name)

    if not records:
        click.echo("No architectural decisions extracted. Try a repo with richer manifests.")
        return

    click.echo(f"\nExtracted {len(records)} decision(s):\n")
    output_dir = root / "knowledge" / "decisions"

    for i, record in enumerate(records, 1):
        # Source: whichever signal file is most relevant — use first manifest or README
        source_file = file_list[0] if file_list else "repo-scan"
        click.echo(f"  {i}. {record.title}  (confidence {record.confidence:.2f})")

        if not dry_run:
            written = write_init_record(record, source_file, repo_name, output_dir)
            click.echo(f"     → {written.relative_to(root)}")

    if dry_run:
        click.echo("\n[dry-run] No files written.")
    else:
        from .adr import index_adrs
        adr_paths = index_adrs(root, output_dir=root / "knowledge" / "decisions", repo=repo_name)
        if adr_paths:
            click.echo(f"\nIndexed {len(adr_paths)} ADR(s):")
            for p in adr_paths:
                try:
                    click.echo(f"  → {Path(p).resolve().relative_to(root.resolve())}")
                except ValueError:
                    click.echo(f"  → {p}")
        click.echo(f"\nDone. Run `memex index` to embed and make them queryable.")


@cli.command()
@click.option("--limit", default=20, show_default=True,
              help="Max commits to scan on first run (no prior state).")
@click.option("--since", default=None, metavar="DATE",
              help="Scan commits since this date, e.g. 2024-01-01. Overrides --limit.")
@click.option("--repo", default=None, metavar="OWNER/REPO",
              help="Override auto-detected GitHub repo.")
def update(limit, since, repo):
    """Pull new decisions from git history since last run.

    Two commit tracks are processed automatically:

    \b
      PR merges:       message contains #N → fetches full PR context via gh
      Direct commits:  no PR → stat-filtered (>10 files = skip) → diff extraction

    State is stored in .memex/state.json — only new commits are ever processed.
    Run `memex index` afterwards to embed the new records.

    \b
    Examples:
      memex update                      # commits since last run
      memex update --since 2024-01-01   # backfill from a date
      memex update --limit 50           # bootstrap: scan last 50 commits
    """
    from .update import run_update

    click.echo("Scanning git history for new decisions...\n")

    result = run_update(
        limit=limit,
        since=since,
        repo=repo,
        progress_cb=click.echo,
    )

    if result.errors:
        click.echo("")
        for err in result.errors:
            click.echo(f"  ⚠  {err}", err=True)

    click.echo(
        f"\n{result.processed} commits scanned — "
        f"{result.written} written, "
        f"{result.skipped_already_indexed} already indexed, "
        f"{result.skipped_low_signal} low signal, "
        f"{result.skipped_stat_filter} stat-filtered, "
        f"{result.skipped_no_decision} no decision found."
    )

    if result.written > 0:
        click.echo("Run `memex index` to embed and make the new records queryable.")


@cli.command()
@click.option("--force", is_flag=True, help="Re-index all records, ignoring existing cache.")
@click.option("--include-adrs", is_flag=True, help="Parse ADR files before embedding.")
def index(force, include_adrs):
    """Make knowledge queryable."""
    if include_adrs:
        from .adr import index_adrs
        adr_paths = index_adrs(Path("."), KNOWLEDGE_DIR / "decisions", repo="local")
        if adr_paths:
            click.echo(f"Parsed {len(adr_paths)} new ADR(s).")

    records = list(KNOWLEDGE_DIR.rglob("*.md"))
    if not records:
        click.echo("No knowledge records found. Is the GitHub Action installed?")
        return

    import hashlib

    existing = load_index() if not force else {}

    disk_paths = {str(r) for r in records}
    stale = [k for k in existing if k not in disk_paths]
    for k in stale:
        del existing[k]
    if stale:
        click.echo(f"Removed {len(stale)} deleted record(s) from index.")

    to_index = []
    for r in records:
        content = r.read_text()
        embed_text = build_embed_text(content)
        h = hashlib.sha256(embed_text.encode()).hexdigest()
        entry = existing.get(str(r))
        if entry is None or entry.get("content_hash") != h:
            to_index.append((r, content, embed_text, h))

    if not to_index:
        if stale:
            save_index(existing)
        click.echo(f"Index up to date — {len(existing)} records indexed.")
        return

    click.echo(f"Indexing {len(to_index)} record(s)...")
    embeddings = embed([embed_text for _, _, embed_text, _ in to_index])

    for (path, content, embed_text, h), embedding in zip(to_index, embeddings):
        existing[str(path)] = {
            "embedding": embedding,
            "title": extract_title(content),
            "excerpt": extract_excerpt(content),
            "confidence": extract_confidence(content),
            "path": str(path),
            "content_hash": h,
        }

    save_index(existing)
    click.echo(f"Done. {len(existing)} records total.")


@cli.command()
@click.argument("query", nargs=-1)
@click.option("--top", default=3, help="Number of results")
@click.option(
    "--min-score",
    default=0.70,
    show_default=True,
    help="Minimum similarity score (0–1). Results below this are hidden.",
)
@click.option(
    "--expand",
    is_flag=True,
    default=False,
    help="Use Claude Haiku to rewrite query into richer search terms (adds ~1s latency).",
)
def query(query, top, min_score, expand):
    """Query your institutional knowledge.

    Example: memex query why did we move off MongoDB
    """
    query_text = " ".join(query)
    if not query_text:
        click.echo("Usage: memex query <your question>")
        return

    index = load_index()
    if not index:
        click.echo("Nothing indexed yet. Run `memex index` first.")
        return

    if expand:
        client = _anthropic_client()
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"Rewrite this search query as 4-6 rich technical search phrases, "
                    f"comma-separated, no explanation:\n\n{query_text}"
                ),
            }],
        )
        expanded = resp.content[0].text.strip()
        query_text = expanded if expanded else query_text
        click.echo(f"  Expanded: {query_text}", err=True)

    # Embed the query
    [query_embedding] = embed([query_text])

    # Score every record — brute force, totally fine at this scale
    scored = [
        (cosine_similarity(query_embedding, entry["embedding"]), entry)
        for entry in index.values()
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    passing = [(s, e) for s, e in scored if s >= min_score]
    to_display = passing[:top]

    import shutil
    term_width = min(shutil.get_terminal_size((80, 24)).columns, 100)
    divider = "─" * term_width

    click.echo(f"\nResults for: {query_text}")
    click.echo(divider)

    if not to_display:
        lower = round(max(0.0, min_score - 0.2), 1)
        click.echo(
            f"\n  No relevant results found (threshold: {min_score:.2f}).\n"
            f'  Try `memex query --min-score {lower} "..."` to broaden the search.'
        )
        click.echo("")
        return

    for i, (score, entry) in enumerate(to_display, 1):
        title = entry["title"]
        excerpt = _strip_markdown(entry["excerpt"])
        path = entry["path"]

        # Confidence from index (or read from file if legacy entry lacks it)
        if "confidence" in entry:
            confidence = entry["confidence"]
        else:
            try:
                confidence = extract_confidence(Path(path).read_text())
            except OSError:
                confidence = 1.0

        # Score badge: colour green above 0.8, yellow above 0.6, default below
        score_str = f"{score:.2f}"
        if score >= 0.8:
            score_label = click.style(f"[{score_str}]", fg="green", bold=True)
        elif score >= 0.6:
            score_label = click.style(f"[{score_str}]", fg="yellow", bold=True)
        else:
            score_label = click.style(f"[{score_str}]", fg="white")

        rank = click.style(f"#{i}", bold=True)
        click.echo(f"\n  {rank}  {title}  {score_label}")

        # Confidence label — reflects quality of rationale in the source record,
        # independent of the similarity score above.
        if confidence >= 0.80:
            conf_line = click.style("✅ Rationale: well-documented", fg="green")
            click.echo(f"      {conf_line}")
        elif confidence >= 0.65:
            conf_line = click.style("💡 Rationale: partial — verify if critical", fg="yellow")
            click.echo(f"      {conf_line}")
        else:
            conf_line = click.style(
                "⚠️  Rationale: limited — limited reasoning in source, verify before relying on this record.",
                fg="yellow",
            )
            click.echo(f"      {conf_line}")

        # Excerpt
        if excerpt:
            click.echo(_wrap(excerpt, term_width - 6, "      "))

        click.echo(f"      {click.style(path, dim=True)}")

    click.echo("")
