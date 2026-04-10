#!/usr/bin/env python3
"""
check_docs.py — validates CLAUDE.md stays in sync with the actual codebase.

Checks:
  1. Every memex/*.py module (except __init__.py) is listed in CLAUDE.md
  2. Every @cli.command() in cli.py appears in the CLI behaviour section
  3. Model strings in extractor.py and init.py match the tech stack table
  4. Required env vars (os.environ["VAR"]) in action.py have rows in the env vars table

Exit 0 = clean. Exit 1 = drift detected (printed to stdout so Claude Code surfaces it).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"
MEMEX_DIR = ROOT / "memex"

errors = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


claude = CLAUDE_MD.read_text()

# ── 1. Module files ────────────────────────────────────────────────────────────
py_files = sorted(f.name for f in MEMEX_DIR.glob("*.py") if f.name != "__init__.py")
for fname in py_files:
    check(fname in claude, f"file structure: memex/{fname} not listed in CLAUDE.md")

# ── 2. CLI commands ────────────────────────────────────────────────────────────
cli_src = (MEMEX_DIR / "cli.py").read_text()
# Commands may have @click.option decorators between @cli.command() and def,
# so scan line-by-line: find @cli.command, then look forward for the def name.
lines = cli_src.splitlines()
command_names = []
for i, line in enumerate(lines):
    m = re.match(r'\s*@cli\.command\((?:"(\w+)")?\)', line)
    if m:
        explicit_name = m.group(1)
        for j in range(i + 1, min(i + 15, len(lines))):
            def_match = re.match(r'\s*def (\w+)', lines[j])
            if def_match:
                command_names.append(explicit_name or def_match.group(1))
                break

cli_section_match = re.search(
    r"## CLI behaviour(.*?)^##", claude, re.DOTALL | re.MULTILINE
)
cli_text = cli_section_match.group(1) if cli_section_match else ""

for cmd in command_names:
    check(
        f"memex {cmd}" in cli_text,
        f"CLI behaviour section: 'memex {cmd}' not documented in CLAUDE.md",
    )

# ── 3. Model strings ───────────────────────────────────────────────────────────
for fname in ["extractor.py", "init.py"]:
    src = (MEMEX_DIR / fname).read_text()
    models = re.findall(r'model=["\']([^"\']+)["\']', src)
    for model in set(models):
        check(
            model in claude,
            f"tech stack: model '{model}' used in memex/{fname} but not in CLAUDE.md",
        )

# ── 4. Required env vars ───────────────────────────────────────────────────────
action_src = (MEMEX_DIR / "action.py").read_text()
# Only required vars (os.environ["VAR"], not os.environ.get)
required_vars = re.findall(r'os\.environ\["(\w+)"\]', action_src)
# Exclude internal GitHub meta-vars that don't need user documentation
skip_vars = {"GITHUB_EVENT_NAME"}
required_vars = sorted(set(v for v in required_vars if v not in skip_vars))

env_section_match = re.search(
    r"## Environment variables.*?\n(.*?)^##", claude, re.DOTALL | re.MULTILINE
)
env_text = env_section_match.group(1) if env_section_match else ""

for var in required_vars:
    check(
        f"`{var}`" in env_text,
        f"env vars table: '{var}' used in action.py but not documented in CLAUDE.md",
    )

# ── Report ─────────────────────────────────────────────────────────────────────
if errors:
    print("CLAUDE.md drift detected:\n")
    for e in errors:
        print(f"  ✗ {e}")
    print(
        f"\n{len(errors)} issue(s) — update CLAUDE.md to match the code, "
        "or run 'python scripts/check_docs.py' to recheck."
    )
    sys.exit(1)
else:
    print(
        f"CLAUDE.md is in sync "
        f"({len(py_files)} modules, {len(command_names)} CLI commands, "
        f"{len(required_vars)} env vars checked)"
    )
    sys.exit(0)
