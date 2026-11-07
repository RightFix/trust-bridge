"""Pydantic schemas — request bodies and the structured spec/report shapes
that the LLM must produce (validated, retried once on invalid output)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CheckType = Literal["word_count", "file_type", "keywords", "sections", "code_tests"]


class Check(BaseModel):
    """Deterministic check attached to an OBJECTIVE checklist item."""
    type: CheckType
    min: Optional[int] = Field(None, description="Minimum word count")
    max: Optional[int] = Field(None, description="Maximum word count")
    extensions: Optional[list[str]] = Field(None, description="Allowed file extensions")
    mode: Optional[Literal["all", "any"]] = Field(
        None, description="keywords: require all values or any value")
    values: Optional[list[str]] = Field(None, description="Keywords / sections required")
    test_code: Optional[str] = Field(
        None, description="Standalone Python test script for a code deliverable")

    @field_validator("extensions", "values", mode="after")
    @classmethod
    def _strip(cls, v):
        if v is None:
            return v
        return [x.strip() for x in v if x and x.strip()]


class ChecklistItem(BaseModel):
    id: str
    text: str
    kind: Literal["OBJECTIVE", "SUBJECTIVE"]
    check: Optional[Check] = None

    @field_validator("text", mode="after")
    @classmethod
    def _text(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("checklist item text cannot be empty")
        return v


class Spec(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    deliverables: list[str] = Field(min_length=1)
    checklist: list[ChecklistItem] = Field(min_length=1)
    deadline: str = Field(min_length=3)
    revision_limit: int = Field(ge=0, le=20)
    out_of_scope: list[str] = Field(default_factory=list)

    @field_validator("title", mode="after")
    @classmethod
    def _title(cls, v):
        return v.strip()


class Question(BaseModel):
    id: str
    text: str


class QuestionsResponse(BaseModel):
    questions: list[Question] = Field(min_length=3, max_length=5)

    @field_validator("questions", mode="after")
    @classmethod
    def _unique_ids(cls, v):
        ids = [q.id for q in v]
        if len(set(ids)) != len(ids):
            raise ValueError("question ids must be unique")
        return v


# --- request bodies ---------------------------------------------------------
class CreateJobRequest(BaseModel):
    brief: str = Field(min_length=10, max_length=8000)
    title: Optional[str] = None


class ClarifyRequest(BaseModel):
    answers: dict[str, str] = Field(min_length=1)


class RoleRequest(BaseModel):
    role: Literal["client", "freelancer", "reviewer"]


class FundRequest(BaseModel):
    role: Literal["client"] = "client"
    amount_usdt: Optional[float] = Field(None, gt=0, le=1_000_000)


class SubmitRequest(BaseModel):
    role: Literal["freelancer"] = "freelancer"
    kind: Literal["text", "file", "code"] = "text"
    content: str = Field(min_length=1, max_length=500_000)
    filename: Optional[str] = Field(None, max_length=255)


class FlagRequest(BaseModel):
    role: Literal["freelancer"] = "freelancer"
    item_id: str
    note: str = Field(default="", max_length=2000)


class SpecUpdateRequest(BaseModel):
    role: Literal["client"] = "client"
    spec: Spec


class ReviewRequest(BaseModel):
    role: Literal["reviewer"] = "reviewer"
    decision: Literal["release", "request_changes", "refund"]
    note: str = Field(default="", max_length=2000)


# --- report -----------------------------------------------------------------
class ItemResult(BaseModel):
    id: str
    text: str
    kind: Literal["OBJECTIVE", "SUBJECTIVE"]
    source: Literal["deterministic", "ai"]
    verdict: Literal["pass", "fail", "needs_human_review"]
    reason: str


class VerificationReport(BaseModel):
    job_id: str
    overall: Literal["pass", "fail", "needs_human_review"]
    auto_release: bool
    recommendation: str
    items: list[ItemResult]
    checked_by_ai: int
    checked_deterministically: int
    created_at: str
