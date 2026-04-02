"""
memex configuration — API key resolution and storage.

Resolution order (first match wins):
  1. ANTHROPIC_API_KEY environment variable
  2. ~/.config/memex/config.toml  [api_key]
  3. Raise MissingApiKeyError with instructions
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "memex"
CONFIG_FILE = CONFIG_DIR / "config.toml"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MissingApiKeyError(Exception):
    """Raised when no Anthropic API key can be found anywhere in the resolution chain."""

    def __str__(self) -> str:
        return (
            "No Anthropic API key found.\n\n"
            "Run  memex configure  to save your key, or set the environment variable:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _read_config_file() -> dict[str, str]:
    """Parse ~/.config/memex/config.toml without adding a toml dependency."""
    if not CONFIG_FILE.exists():
        return {}
    result: dict[str, str] = {}
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def load_api_key() -> str:
    """
    Return the Anthropic API key, checking env var then config file.
    Raises MissingApiKeyError if neither is set.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key

    key = _read_config_file().get("api_key", "").strip()
    if key:
        return key

    raise MissingApiKeyError()


def save_api_key(api_key: str) -> None:
    """Write the Anthropic API key to ~/.config/memex/config.toml (chmod 600)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing = _read_config_file()
    existing["api_key"] = api_key

    lines = ["# Memex configuration\n"]
    for k, v in existing.items():
        lines.append(f'{k} = "{v}"\n')

    CONFIG_FILE.write_text("".join(lines), encoding="utf-8")
    CONFIG_FILE.chmod(0o600)  # owner-read/write only — this is a secret


def key_source() -> str:
    """Human-readable description of where the active Anthropic key comes from."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "environment variable ANTHROPIC_API_KEY"
    if CONFIG_FILE.exists() and _read_config_file().get("api_key"):
        return str(CONFIG_FILE)
    return "not set"
