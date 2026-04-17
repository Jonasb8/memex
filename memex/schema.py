from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ConfidenceLevel(str, Enum):
    high = "high"       # >= 0.80 — publish
    medium = "medium"   # 0.65–0.80 — publish with flag
    low = "low"         # < 0.65 — publish with ⚠️ flag


class KnowledgeRecord(BaseModel):
    """A single extracted decision record."""

    title: str = Field(
        description="Short title summarising the decision, e.g. 'Migrate billing store to PostgreSQL'"
    )
    context: str = Field(
        description="2-3 sentences: what situation or problem prompted this decision?"
    )
    decision: str = Field(
        description="What was decided? One clear sentence."
    )
    alternatives_considered: list[str] = Field(
        default_factory=list,
        description="Other options that were explicitly discussed or ruled out"
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Technical, organisational, or time constraints that shaped the decision"
    )
    revisit_signals: list[str] = Field(
        default_factory=list,
        description="Any 'revisit when X' or 'temporary until Y' signals present in the text"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How much genuine rationale is present? 0 = no rationale, 1 = detailed explicit reasoning"
    )
    confidence_rationale: str = Field(
        description="One sentence: why did you assign this confidence score?"
    )


class ExtractionResult(BaseModel):
    """Wrapper returned by the LLM — may be null if no decision present."""

    contains_decision: bool = Field(
        description="Is there a genuine architectural or product decision in this PR? "
                    "Dependency bumps, typo fixes, and style changes are NOT decisions."
    )
    record: Optional[KnowledgeRecord] = Field(
        default=None,
        description="The extracted record. Null if contains_decision is false."
    )
