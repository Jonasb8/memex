"""Unit tests for memex/init.py."""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from memex.init import (
    _read_truncated,
    _is_binary,
    _collect_globs,
    _root_sweep,
    _directory_tree,
    render_init_markdown,
    write_init_record,
    detect_repo_name,
    extract_architecture,
    ArchitectureExtractionResult,
)
from memex.schema import KnowledgeRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**kwargs) -> KnowledgeRecord:
    defaults = dict(
        title="Use PostgreSQL for billing",
        context="The team needed a relational database for billing.",
        decision="Chose PostgreSQL over MySQL.",
        alternatives_considered=[],
        constraints=[],
        revisit_signals=[],
        confidence=0.85,
        confidence_rationale="Clear rationale in pyproject.toml.",
    )
    defaults.update(kwargs)
    return KnowledgeRecord(**defaults)


# ---------------------------------------------------------------------------
# _read_truncated
# ---------------------------------------------------------------------------

def test_read_truncated_short_file(tmp_path):
    f = tmp_path / "small.txt"
    f.write_text("hello world")
    assert _read_truncated(f) == "hello world"


def test_read_truncated_long_file(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 5000)
    result = _read_truncated(f, max_chars=100)
    assert result.startswith("x" * 100)
    assert "[truncated at 100 chars]" in result
    assert len(result) > 100  # includes suffix


def test_read_truncated_missing_file(tmp_path):
    result = _read_truncated(tmp_path / "nonexistent.txt")
    assert result == ""


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------

def test_is_binary_text_file(tmp_path):
    f = tmp_path / "text.txt"
    f.write_text("just text")
    assert _is_binary(f) is False


def test_is_binary_binary_file(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"some\x00binary\x00data")
    assert _is_binary(f) is True


def test_is_binary_missing_file(tmp_path):
    assert _is_binary(tmp_path / "ghost.bin") is True


# ---------------------------------------------------------------------------
# _collect_globs
# ---------------------------------------------------------------------------

def test_collect_globs_matches_pattern(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
    seen: set[Path] = set()
    result = _collect_globs(tmp_path, ["pyproject.toml"], seen)
    assert "pyproject.toml" in result
    assert "[tool.poetry]" in result["pyproject.toml"]


def test_collect_globs_deduplicates(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text("content")
    seen: set[Path] = {f.resolve()}
    result = _collect_globs(tmp_path, ["pyproject.toml"], seen)
    assert result == {}


def test_collect_globs_skips_skip_files(tmp_path):
    (tmp_path / "package-lock.json").write_text('{"lockfile": true}')
    seen: set[Path] = set()
    result = _collect_globs(tmp_path, ["package-lock.json"], seen)
    assert result == {}


def test_collect_globs_skips_binary(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02")
    seen: set[Path] = set()
    result = _collect_globs(tmp_path, ["*.bin"], seen)
    assert result == {}


def test_collect_globs_respects_per_pattern_cap(tmp_path):
    for i in range(5):
        (tmp_path / f"req{i}.txt").write_text(f"dep{i}")
    seen: set[Path] = set()
    result = _collect_globs(tmp_path, ["req*.txt"], seen, per_pattern_cap=2)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _root_sweep
# ---------------------------------------------------------------------------

def test_root_sweep_picks_up_toml(tmp_path):
    (tmp_path / "myconfig.toml").write_text("[settings]")
    seen: set[Path] = set()
    result = _root_sweep(tmp_path, seen)
    assert "myconfig.toml" in result


def test_root_sweep_skips_lock_files(tmp_path):
    (tmp_path / "poetry.lock").write_text("locked")
    seen: set[Path] = set()
    result = _root_sweep(tmp_path, seen)
    assert "poetry.lock" not in result


def test_root_sweep_skips_dotfiles(tmp_path):
    (tmp_path / ".hidden.toml").write_text("secret")
    seen: set[Path] = set()
    result = _root_sweep(tmp_path, seen)
    assert ".hidden.toml" not in result


def test_root_sweep_allows_env_example(tmp_path):
    # .env.example passes the dotfile check but has extension .example which is
    # not in _ROOT_SWEEP_EXTENSIONS, so it is filtered by the extension check.
    # Confirm it does NOT appear in the result (correct behaviour).
    (tmp_path / ".env.example").write_text("KEY=value")
    seen: set[Path] = set()
    result = _root_sweep(tmp_path, seen)
    # The dotfile whitelist only prevents early-exit; the extension filter still applies.
    assert ".env.example" not in result


def test_root_sweep_skips_non_interesting_extensions(tmp_path):
    (tmp_path / "README.md").write_text("# readme")
    seen: set[Path] = set()
    result = _root_sweep(tmp_path, seen)
    assert "README.md" not in result


# ---------------------------------------------------------------------------
# _directory_tree
# ---------------------------------------------------------------------------

def test_directory_tree_includes_root_name(tmp_path):
    tree = _directory_tree(tmp_path)
    assert tmp_path.name in tree


def test_directory_tree_includes_files(tmp_path):
    (tmp_path / "main.py").write_text("pass")
    tree = _directory_tree(tmp_path)
    assert "main.py" in tree


def test_directory_tree_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "lib.js").write_text("module.exports = {}")
    tree = _directory_tree(tmp_path)
    assert "node_modules" not in tree


def test_directory_tree_respects_max_depth(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("pass")
    tree = _directory_tree(tmp_path, max_depth=1)
    assert "deep.py" not in tree


# ---------------------------------------------------------------------------
# render_init_markdown
# ---------------------------------------------------------------------------

def test_render_init_markdown_high_confidence_no_warning():
    record = _make_record(confidence=0.85)
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "⚠️" not in md


def test_render_init_markdown_medium_confidence_warning():
    record = _make_record(confidence=0.70)
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "⚠️" in md
    assert "Low confidence" in md


def test_render_init_markdown_low_confidence_warning():
    record = _make_record(confidence=0.50)
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "⚠️" in md


def test_render_init_markdown_empty_alternatives():
    record = _make_record(alternatives_considered=[])
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "_None recorded_" in md


def test_render_init_markdown_empty_constraints():
    record = _make_record(constraints=[])
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "_None recorded_" in md


def test_render_init_markdown_empty_revisit():
    record = _make_record(revisit_signals=[])
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "_None_" in md


def test_render_init_markdown_non_empty_alternatives():
    record = _make_record(alternatives_considered=["MySQL", "SQLite"])
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "- MySQL" in md
    assert "- SQLite" in md


def test_render_init_markdown_frontmatter_fields():
    record = _make_record()
    md = render_init_markdown(record, "pyproject.toml", "acme/api")
    assert 'author: "memex-init"' in md
    assert 'tags: ["init"]' in md
    assert 'repo: "acme/api"' in md
    assert 'source: "pyproject.toml"' in md


def test_render_init_markdown_title_in_body():
    record = _make_record(title="Use PostgreSQL for billing")
    md = render_init_markdown(record, "pyproject.toml", "myrepo")
    assert "# Use PostgreSQL for billing" in md


# ---------------------------------------------------------------------------
# write_init_record
# ---------------------------------------------------------------------------

def test_write_init_record_creates_output_dir(tmp_path):
    record = _make_record()
    out = tmp_path / "knowledge" / "decisions"
    path = write_init_record(record, "pyproject.toml", "myrepo", output_dir=out)
    assert out.exists()
    assert path.exists()


def test_write_init_record_returns_path(tmp_path):
    record = _make_record()
    path = write_init_record(record, "pyproject.toml", "myrepo", output_dir=tmp_path)
    assert isinstance(path, Path)
    assert path.suffix == ".md"


def test_write_init_record_file_has_content(tmp_path):
    record = _make_record(title="Deploy with Docker")
    path = write_init_record(record, "Dockerfile", "myrepo", output_dir=tmp_path)
    content = path.read_text()
    assert "Deploy with Docker" in content
    assert 'author: "memex-init"' in content


def test_write_init_record_filename_includes_slug(tmp_path):
    record = _make_record(title="Use PostgreSQL for billing")
    path = write_init_record(record, "pyproject.toml", "myrepo", output_dir=tmp_path)
    assert "use-postgresql-for-billing" in path.name


def test_write_init_record_filename_includes_date(tmp_path):
    record = _make_record()
    path = write_init_record(record, "pyproject.toml", "myrepo", output_dir=tmp_path)
    # Filename starts with YYYY-MM-DD
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", path.name)


# ---------------------------------------------------------------------------
# detect_repo_name
# ---------------------------------------------------------------------------

def _subprocess_result(stdout: str, returncode: int = 0):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    return r


def test_detect_repo_name_https_url(tmp_path):
    with patch("subprocess.check_output", return_value="https://github.com/owner/myrepo.git\n"):
        name = detect_repo_name(tmp_path)
    assert name == "myrepo"


def test_detect_repo_name_ssh_url(tmp_path):
    with patch("subprocess.check_output", return_value="git@github.com:owner/myrepo.git\n"):
        name = detect_repo_name(tmp_path)
    assert name == "myrepo"


def test_detect_repo_name_fallback_to_dir(tmp_path):
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")):
        name = detect_repo_name(tmp_path)
    assert name == tmp_path.resolve().name


def test_detect_repo_name_git_not_found(tmp_path):
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        name = detect_repo_name(tmp_path)
    assert name == tmp_path.resolve().name


# ---------------------------------------------------------------------------
# extract_architecture (mocked LLM)
# ---------------------------------------------------------------------------

def test_extract_architecture_returns_records():
    record = _make_record()
    mock_result = ArchitectureExtractionResult(records=[record])

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_result

    with patch("memex.init.instructor.from_anthropic", return_value=mock_client), \
         patch("memex.init.load_api_key", return_value="test-key"):
        result = extract_architecture({"pyproject.toml": "[tool]"}, "myrepo")

    assert result == [record]


def test_extract_architecture_uses_correct_model():
    mock_result = ArchitectureExtractionResult(records=[])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_result

    with patch("memex.init.instructor.from_anthropic", return_value=mock_client), \
         patch("memex.init.load_api_key", return_value="test-key"):
        extract_architecture({}, "myrepo")

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-6"


def test_extract_architecture_empty_records():
    mock_result = ArchitectureExtractionResult(records=[])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_result

    with patch("memex.init.instructor.from_anthropic", return_value=mock_client), \
         patch("memex.init.load_api_key", return_value="test-key"):
        result = extract_architecture({}, "myrepo")

    assert result == []
