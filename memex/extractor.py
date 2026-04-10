import os
import re
from anthropic import Anthropic
import instructor
from .config import load_api_key
from .schema import ExtractionResult, ConfidenceLevel
from .structural import categorize_file, is_structural_change, build_changed_files_section


def _client():
    """Lazily build the instructor-patched client so the key is resolved at call time."""
    return instructor.from_anthropic(Anthropic(api_key=load_api_key()))

DISCARD_THRESHOLD = 0.40

# Always skip — body content never rescues these (dep bumps, lockfile noise)
_ALWAYS_LOW_SIGNAL = [
    r"bump .+ from .+ to .+",
    r"update (dependencies|deps|packages|lockfile)",
]

# Skip only when body is absent or trivial — a substantive body may contain a real decision
_TITLE_LOW_SIGNAL = [
    r"^(chore|fix|style|docs|test|ci|build)(\(.+\))?: .{1,40}$",
    r"^(wip|WIP)[\s:]",
]

_BODY_TRIVIAL_THRESHOLD = 80  # chars — below this, treat body as absent


def is_low_signal(title: str, body: str, changed_files: list[str] | None = None) -> bool:
    """Quick heuristic check before spending an LLM call."""
    text = f"{title}\n{body}"
    # Always-low patterns win regardless of structural files (dep bumps are always noise)
    if any(re.search(p, text, re.IGNORECASE) for p in _ALWAYS_LOW_SIGNAL):
        return True
    # Structural files override the title-based heuristics
    if changed_files and is_structural_change(changed_files):
        return False
    body_is_trivial = len((body or "").strip()) < _BODY_TRIVIAL_THRESHOLD
    if body_is_trivial:
        if any(re.search(p, title, re.IGNORECASE) for p in _TITLE_LOW_SIGNAL):
            return True
    return False


def build_prompt(
    pr_title: str,
    pr_body: str,
    review_comments: list[str],
    changed_files: list[str] | None = None,
) -> str:
    reviews_text = "\n---\n".join(review_comments) if review_comments else "No review comments."
    changed_files_section = build_changed_files_section(changed_files)
    return f"""You are extracting institutional knowledge from a GitHub pull request.

Your task: determine whether this PR contains a genuine architectural, technical, or
product decision — and if so, extract the decision context.

A genuine decision involves a non-obvious choice between alternatives, a trade-off,
or a constraint that shaped how something was built. Routine changes (dependency
updates, typo fixes, style cleanup, test additions) do NOT qualify.

Be strict. It is better to return contains_decision=false than to manufacture
rationale that isn't actually present in the text.

## PR Title
{pr_title}

## PR Description
{pr_body or "No description provided."}

## Review Comments
{reviews_text}

## Changed Files
{changed_files_section}

If changed files include migrations, infrastructure-as-code, or schema definitions, \
these represent architectural decisions worth capturing even when the PR description is thin. \
Extract the decision (what changed and why it matters structurally), but set confidence \
based on how much explicit rationale is actually present in the text — do not infer \
motivation that is not stated.

Extract the decision context now. Set confidence based on how much explicit rationale
is actually present in the text above — do not infer or assume."""


def extract(
    pr_title: str,
    pr_body: str,
    review_comments: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> ExtractionResult | None:
    """
    Run the extraction pipeline on a single PR.
    Returns None if the PR is low-signal (skipped before LLM call).
    Returns ExtractionResult with contains_decision=False if LLM finds no decision.
    Returns ExtractionResult with record populated if a decision is found.
    """
    review_comments = review_comments or []

    # Gate 1: cheap heuristic filter (changed_files enables structural override)
    if is_low_signal(pr_title, pr_body or "", changed_files):
        return None

    # Gate 2: LLM extraction with structured output
    result: ExtractionResult = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": build_prompt(pr_title, pr_body, review_comments, changed_files),
            }
        ],
        response_model=ExtractionResult,
    )

    # Gate 3: confidence threshold
    if result.contains_decision and result.record:
        if result.record.confidence < DISCARD_THRESHOLD:
            result.contains_decision = False
            result.record = None

    return result


def confidence_level(score: float) -> ConfidenceLevel:
    if score >= 0.80:
        return ConfidenceLevel.high
    if score >= 0.65:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low
