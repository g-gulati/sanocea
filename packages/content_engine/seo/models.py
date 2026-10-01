"""Models for the SEO brief/draft workflow. Every brief field carries its basis, so "why does this exist?" is answerable
from stored data alone."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from packages.content_engine.models import QAResult

# OBSERVED: read from a source. CALCULATED: derived from observed values by a stated rule. INFERRED: a lexical cue, stated.
# GENERATED_RECOMMENDATION: SANOCEA's own suggestion, not evidence. REQUIRES_VERIFICATION: must be confirmed by a human/source.
# EDITORIAL: supplied by the tenant. NOT_AVAILABLE: no source exists; nothing is invented.
Basis = Literal["OBSERVED", "CALCULATED", "INFERRED", "GENERATED_RECOMMENDATION", "REQUIRES_VERIFICATION", "EDITORIAL", "NOT_AVAILABLE"]


class Sourced(BaseModel):
    value: Any = None
    basis: Basis
    evidence_refs: List[str] = Field(default_factory=list)  # e.g. ["evidence.query", "decision.rationale"]
    note: Optional[str] = None


class TenantProfile(BaseModel):
    tenant_id: str
    brand: str
    domain: str
    audience: Optional[str] = None  # editorial: who the content is for. Absent => the audience QA check fails.


class OpportunityRef(BaseModel):
    """Snapshot of the opportunity exactly as the worker reported it when the brief was made."""
    opportunity_id: str
    type: str
    target: str
    status: str
    detected_at: str
    source: str
    recommended_action: str
    reason: str
    evidence: Dict[str, Any]
    decision: Dict[str, Any]
    approval: Dict[str, str]  # {"by": "human:...", "at": iso}


class InternalLink(BaseModel):
    url: str
    justification: str
    direction: Literal["to_new_page", "from_new_page", "both"] = "both"


class SeoBrief(BaseModel):
    brief_id: str
    tenant_id: str
    created_at: str
    status: Literal["BRIEF_READY"] = "BRIEF_READY"
    lineage: OpportunityRef
    content_type: Sourced
    target: Sourced
    intent: Sourced
    audience: Sourced
    existing_page_assessment: Sourced
    overlap: Sourced
    proposed_title: Sourced
    proposed_meta_description: Sourced
    primary_questions: Sourced
    supporting_questions: Sourced
    entities: Sourced
    internal_links: List[InternalLink] = Field(default_factory=list)
    internal_links_basis: Basis = "CALCULATED"
    research_requirements: Sourced
    schema_opportunity: Sourced
    canonical: Sourced
    factual_constraints: List[str] = Field(default_factory=list)
    claims_requiring_verification: List[str] = Field(default_factory=list)
    not_available: List[str] = Field(default_factory=list)


class ApprovedFact(BaseModel):
    id: str
    text: str
    source: str  # where the fact comes from (document, page, owner)


class DraftParagraph(BaseModel):
    text: str
    fact_ids: List[str] = Field(default_factory=list)


class DraftSection(BaseModel):
    level: int  # 1 = h1, 2 = h2, 3 = h3
    heading: str
    paragraphs: List[DraftParagraph] = Field(default_factory=list)


class SeoDraft(BaseModel):
    draft_id: str
    brief_id: str
    tenant_id: str
    created_at: str
    status: Literal["DRAFT_READY", "NEEDS_REVISION", "GENERATION_FAILED"]
    writer: str
    title: str = ""
    meta_description: str = ""
    sections: List[DraftSection] = Field(default_factory=list)
    internal_links_used: List[str] = Field(default_factory=list)
    fact_ids_used: List[str] = Field(default_factory=list)
    qa: Optional[QAResult] = None
    error: Optional[str] = None
    lineage: Dict[str, Any] = Field(default_factory=dict)  # {"brief_id", "opportunity_id", "approved_by"}
