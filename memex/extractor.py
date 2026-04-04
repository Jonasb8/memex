import os
import re
from anthropic import Anthropic
import instructor
from .config import load_api_key
from .schema import ExtractionResult, ConfidenceLevel


def _client():
    """Lazily build the instructor-patched client so the key is resolved at call time."""
    return instructor.from_anthropic(Anthropic(api_key=load_api_key()))

DISCARD_THRESHOLD = 0.40

# Patterns that indicate a low-signal PR — skip LLM call entirely
LOW_SIGNAL_PATTERNS = [
    r"^(chore|fix|style|docs|test|ci|build)(\(.+\))?: .{1,40}$",
    r"bump .+ from .+ to .+",
    r"update (dependencies|deps|packages|lockfile)",
    r"^(wip|WIP)[\s:]",
]


def is_low_signal(title: str, body: str) -> bool:
    """Quick heuristic check before spending an LLM call."""
    text = f"{title}\n{body}"
    return any(re.search(p, text, re.IGNORECASE) for p in LOW_SIGNAL_PATTERNS)


def build_prompt(pr_title: str, pr_body: str, review_comments: list[str]) -> str:
    reviews_text = "\n---\n".join(review_comments) if review_comments else "No review comments."
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

Extract the decision context now. Set confidence based on how much explicit rationale 
is actually present in the text above — do not infer or assume."""


def extract(
    pr_title: str,
    pr_body: str,
    review_comments: list[str] | None = None,
) -> ExtractionResult | None:
    """
    Run the extraction pipeline on a single PR.
    Returns None if the PR is low-signal (skipped before LLM call).
    Returns ExtractionResult with contains_decision=False if LLM finds no decision.
    Returns ExtractionResult with record populated if a decision is found.
    """
    review_comments = review_comments or []

    # Gate 1: cheap heuristic filter
    if is_low_signal(pr_title, pr_body or ""):
        return None

    # Gate 2: LLM extraction with structured output
    result: ExtractionResult = _client().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": build_prompt(pr_title, pr_body, review_comments),
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
