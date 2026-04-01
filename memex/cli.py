import json
import click
import numpy as np
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()
KNOWLEDGE_DIR = Path("knowledge")
INDEX_FILE = Path(".memex/index.json")


def embed(texts: list[str]) -> list[list[float]]:
    """Get embeddings from Anthropic — no extra dependency needed."""
    # Voyager is Anthropic's embedding model, available via the same SDK
    response = client.embeddings.create(
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
