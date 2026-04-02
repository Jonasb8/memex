import json
import click
import numpy as np
from pathlib import Path
from anthropic import Anthropic

from .config import load_api_key, save_api_key, key_source, MissingApiKeyError, CONFIG_FILE

KNOWLEDGE_DIR = Path("knowledge")
INDEX_FILE = Path(".memex/index.json")


def _client() -> Anthropic:
    """Return an Anthropic client, with a clean error if the key is missing."""
    try:
        return Anthropic(api_key=load_api_key())
    except MissingApiKeyError as e:
        raise click.ClickException(str(e)) from e


def embed(texts: list[str]) -> list[list[float]]:
    """Get embeddings from Anthropic — no extra dependency needed."""
    response = _client().embeddings.create(
        model="voyage-3-lite",
        input=texts,
    )
    return [r.embedding for r in response.data]


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


def extract_excerpt(content: str) -> str:
    """Pull first substantive paragraph after the frontmatter."""
    in_frontmatter = False
    for line in content.splitlines():
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter and line.strip() and not line.startswith("#"):
            return line[:140]
    return ""


@click.group()
def cli():
    """Memex — query your team's institutional knowledge."""
    pass


@cli.command()
def configure():
    """Save your Anthropic API key for all memex commands.

    The key is written to ~/.config/memex/config.toml (chmod 600).
    Setting the ANTHROPIC_API_KEY environment variable takes precedence
    over the config file if both are present.
    """
    current_source = key_source()
    if current_source != "not set":
        click.echo(f"Current key source: {current_source}")

    api_key = click.prompt(
        "Anthropic API key",
        hide_input=True,
        prompt_suffix=" (sk-ant-...): ",
    ).strip()

    if not api_key.startswith("sk-"):
        raise click.ClickException(
            "That doesn't look like a valid Anthropic API key (should start with 'sk-')."
        )

    click.echo("Validating key...", nl=False)
    try:
        client = Anthropic(api_key=api_key)
        # Cheapest possible call — one token, just to confirm the key is accepted
        client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        click.echo(" ✓")
    except Exception as exc:
        raise click.ClickException(f"Key rejected by Anthropic API: {exc}") from exc

    save_api_key(api_key)
    click.echo(f"Key saved to {CONFIG_FILE}")
    click.echo("\nYou're all set. Try: memex init")


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
        click.echo(f"\nDone. Run `memex index` to embed and make them queryable.")


@cli.command()
def index():
    """Embed and index all knowledge records in this repo."""
    records = list(KNOWLEDGE_DIR.rglob("*.md"))
    if not records:
        click.echo("No knowledge records found. Is the GitHub Action installed?")
        return

    existing = load_index()
    new_records = [r for r in records if str(r) not in existing]

    if not new_records:
        click.echo(f"Index up to date — {len(existing)} records indexed.")
        return

    click.echo(f"Indexing {len(new_records)} new records...")
    contents = [r.read_text() for r in new_records]
    embeddings = embed(contents)

    for path, content, embedding in zip(new_records, contents, embeddings):
        existing[str(path)] = {
            "embedding": embedding,
            "title": extract_title(content),
            "excerpt": extract_excerpt(content),
            "path": str(path),
        }

    save_index(existing)
    click.echo(f"Done. {len(existing)} records total.")


@cli.command()
@click.argument("query", nargs=-1)
@click.option("--top", default=3, help="Number of results")
def query(query, top):
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

    # Embed the query
    [query_embedding] = embed([query_text])

    # Score every record — brute force, totally fine at this scale
    scored = [
        (cosine_similarity(query_embedding, entry["embedding"]), entry)
        for entry in index.values()
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    click.echo(f"\nResults for: {query_text}\n" + "─" * 50)
    for score, entry in scored[:top]:
        click.echo(f"\n  {entry['title']}")
        click.echo(f"  {entry['excerpt']}...")
        click.echo(f"  {entry['path']}  (score {score:.2f})")
